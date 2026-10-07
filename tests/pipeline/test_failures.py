"""Plan 13.2.1: one test per row of the PRD "If something fails" table, plus the other ways a
request can go wrong. Each asserts what the shopper is told (``warnings`` and the store reasons) AND
the log line: a warning with the request id, so the failure can be found afterwards.
"""

import logging
from collections.abc import Sequence

import pytest

from tests.factories import (
    make_item_intent,
    make_search_request,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.test_outfit import OUTFIT, outfit_understander
from tests.pipeline.world import DEFAULT_PRICES, StoreWorld, generated_body, store_for
from tests.understand.fake_openai import FakeOpenAI, http_error
from vga.errors import CallBudgetExceededError, InvalidInputError, LlmError
from vga.models import (
    Category,
    InputType,
    ItemIntent,
    SearchResponse,
    StoreConfig,
    StoreResult,
    StoreStatus,
    Tier,
)
from vga.pipeline import messages
from vga.settings import Settings
from vga.understand import FALLBACK_MARKER, FALLBACK_WARNING, OpenAIUnderstander
from vga.understand.budget import CallBudget


@pytest.fixture(autouse=True)
def _log_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="vga")


def warnings_logged(caplog: pytest.LogCaptureFixture, request_id: str) -> list[str]:
    """Messages of the pipeline's own warning lines that carry this request id."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.name.startswith("vga.pipeline")
        and getattr(record, "request_id", None) == request_id
    ]


def assert_empty(response: SearchResponse) -> None:
    assert response.result_count == 0
    assert response.groups, "an empty search still has its groups, so the page can explain"
    for group in response.groups:
        assert [tier.name for tier in group.tiers] == list(Tier)
        assert all(tier.count == 0 for tier in group.tiers)


# --------------------------------------------------------------------------------------------
# Row 1: the language model fails -> the shopper's own words are searched
# --------------------------------------------------------------------------------------------


async def test_when_the_model_fails_the_shoppers_own_words_are_searched_and_the_response_says_so(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list[StoreConfig],
    settings: Settings,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The real understander against an OpenAI that only answers with server errors.
    fake = FakeOpenAI(default=http_error(500))
    understander = OpenAIUnderstander(
        make_settings(openai_model="gpt-5-mini-2025-08-07"),
        fake.client(),
        clock=clock,
        budget=CallBudget(),
        jitter=lambda: 0.5,
    )
    pipeline = make_pipeline(understander=understander)
    request = make_search_request(text="black oversized blazer for men under 400 AED")

    response = await pipeline.run(request, settings)
    await fake.aclose()

    assert response.understood.model == FALLBACK_MARKER
    assert response.understood.prompt_version == FALLBACK_MARKER
    assert FALLBACK_WARNING in response.warnings
    assert response.result_count > 0  # the search went on with the words as typed
    sent = [query.lower() for query in world.queries("alpha")]
    assert sent
    assert all("400" not in q and "aed" not in q and "under" not in q for q in sent)  # Rule 7
    logged = warnings_logged(caplog, request.request_id)
    assert any("the model path failed" in message for message in logged)


async def test_a_fallback_result_with_no_note_of_its_own_still_tells_the_shopper(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fallback = make_understand_result(
        model=FALLBACK_MARKER,
        prompt_version=FALLBACK_MARKER,
        items=[make_item_intent(search_keywords=["black blazer"])],
    )
    pipeline = make_pipeline(understander=FakeUnderstander(fallback))
    request = make_search_request(text="black blazer")

    response = await pipeline.run(request, settings)

    assert FALLBACK_WARNING in response.warnings
    assert warnings_logged(caplog, request.request_id)


@pytest.mark.parametrize("error_type", [LlmError, CallBudgetExceededError, InvalidInputError])
async def test_when_there_is_no_fallback_the_understanders_plain_error_reaches_the_caller(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list[StoreConfig],
    settings: Settings,
    error_type: type[Exception],
) -> None:
    pipeline = make_pipeline(understander=FakeUnderstander(error=error_type()))

    with pytest.raises(error_type):
        await pipeline.run(make_search_request(text="black blazer"), settings)

    assert world.all_requests() == 0  # no store was bothered


async def test_an_unexpected_crash_in_the_understander_becomes_a_plain_llm_error(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipeline = make_pipeline(understander=FakeUnderstander(error=KeyError("secret internals")))

    with pytest.raises(LlmError) as caught:
        await pipeline.run(make_search_request(text="black blazer"), settings)

    assert "secret internals" not in caught.value.user_message
    assert "secret internals" not in str(caught.value)
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


# --------------------------------------------------------------------------------------------
# Row 2: one store fails -> skipped, listed with its reason, the others carry on
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "store_status", "phrase"),
    [
        (403, StoreStatus.BLOCKED, "did not allow the search"),
        (500, StoreStatus.ERROR, "could not be read"),
    ],
)
async def test_one_failing_store_is_skipped_and_the_others_still_answer(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
    status: int,
    store_status: StoreStatus,
    phrase: str,
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"), status=status)
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)

    assert response.result_count > 0
    assert {s.product.store for s in response.products} == {"Alpha"}
    assert [r.store_id for r in response.stores_used] == ["alpha"]
    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("beta", store_status)
    assert skipped.reason == messages.store_reason(store_status)
    assert any(phrase in warning and "Beta" in warning for warning in response.warnings)
    assert any(
        "store skipped" in message for message in warnings_logged(caplog, request.request_id)
    )
    store_lines = [
        record
        for record in caplog.records
        if record.getMessage() == "store skipped" and getattr(record, "store", None) == "beta"
    ]
    assert store_lines
    assert getattr(store_lines[0], "request_id", None) == request.request_id


async def test_a_slow_store_is_skipped_when_it_does_not_answer_in_time(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"), delay=100.0)
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)

    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("beta", StoreStatus.TIMEOUT)
    assert "did not answer in time" in " ".join(response.warnings)
    assert response.result_count > 0
    # the engine gives up on its own (6 s per request) long before the 30 s request deadline
    assert not any("longer than" in warning for warning in response.warnings)
    assert warnings_logged(caplog, request.request_id)


async def test_a_store_that_found_nothing_is_listed_without_a_failure_warning(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"), bodies={})  # answers, but has nothing
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    [skipped] = response.stores_skipped
    assert (skipped.store_id, skipped.status) == ("beta", StoreStatus.EMPTY)
    assert skipped.reason == messages.store_reason(StoreStatus.EMPTY)
    assert not any("Beta" in warning for warning in response.warnings)


# --------------------------------------------------------------------------------------------
# Row 3: every store fails or finds nothing -> an empty response with the reason, not an exception
# --------------------------------------------------------------------------------------------


async def test_when_every_store_fails_the_response_is_empty_and_gives_the_reasons(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world.add(store_for("alpha"), status=403)
    world.add(store_for("beta"), status=500)
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)  # no exception

    assert_empty(response)
    assert response.stores_used == []
    assert {r.store_id: r.status for r in response.stores_skipped} == {
        "alpha": StoreStatus.BLOCKED,
        "beta": StoreStatus.ERROR,
    }
    assert all(r.reason for r in response.stores_skipped)
    assert messages.NO_RESULTS_ANYWHERE in response.warnings
    assert any("Alpha" in w for w in response.warnings)
    assert any("Beta" in w for w in response.warnings)
    logged = warnings_logged(caplog, request.request_id)
    assert any("no store returned products" in message for message in logged)


async def test_when_every_store_finds_nothing_the_response_is_empty_and_says_so(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world.add(store_for("alpha"), bodies={})
    world.add(store_for("beta"), bodies={})
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)

    assert_empty(response)
    assert [r.status for r in response.stores_skipped] == [StoreStatus.EMPTY] * 2
    assert messages.NO_RESULTS_ANYWHERE in response.warnings
    assert warnings_logged(caplog, request.request_id)


async def test_products_that_do_not_match_the_request_count_as_nothing_found(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))  # sells blazers, shoes, shirts and jeans
    pipeline = make_pipeline(
        understander=FakeUnderstander(
            make_understand_result(
                items=[make_item_intent(category=Category.TOPS, search_keywords=["blazer"])]
            )
        )
    )

    # The store's search pads results with blazers, but the request is for a top: all dropped.
    response = await pipeline.run(make_search_request(text="a blazer"), settings)

    assert_empty(response)
    assert messages.NO_RESULTS_ANYWHERE in response.warnings


async def test_no_enabled_store_gives_an_empty_response_and_a_warning(
    make_pipeline: PipelineMaker, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    pipeline = make_pipeline(stores=[])
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, settings)

    assert_empty(response)
    assert messages.NO_STORES_CONFIGURED in response.warnings
    assert warnings_logged(caplog, request.request_id)


async def test_a_disabled_store_is_never_searched(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta", enabled=False))
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.queries("beta") == []
    assert [r.store_id for r in response.stores_used] == ["alpha"]


# --------------------------------------------------------------------------------------------
# Row 4: image similarity fails -> ranked by text and price, and it says so
# --------------------------------------------------------------------------------------------


async def test_when_the_image_ranker_returns_no_scores_the_results_are_ranked_without_them(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    photo: bytes,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = make_settings(image_ranker="siglip", log_dir=str(tmp_path / "logs"))
    ranker = FakeImageRanker(default=None)
    pipeline = make_pipeline(image_ranker=ranker)
    request = make_search_request(image=photo, text="black oversized blazer")

    response = await pipeline.run(request, configured)

    assert len(ranker.calls) == 1  # it was asked
    assert any("image similarity was not available" in w for w in response.warnings)
    assert response.result_count > 0
    assert all(scored.scores.image is None for scored in response.products)
    assert all(scored.scores.total > 0 for scored in response.products)
    logged = warnings_logged(caplog, request.request_id)
    assert any("image similarity unavailable" in message for message in logged)


async def test_a_ranker_that_raises_costs_the_request_nothing_but_the_image_scores(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    photo: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipeline = make_pipeline(image_ranker=FakeImageRanker(error=RuntimeError("model crashed")))
    request = make_search_request(image=photo, text="black oversized blazer")

    response = await pipeline.run(request, settings)

    assert response.result_count > 0
    assert any("image similarity was not available" in w for w in response.warnings)
    assert all(scored.scores.image is None for scored in response.products)
    assert warnings_logged(caplog, request.request_id)


async def test_no_image_warning_when_the_ranker_is_switched_off_in_the_settings(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    photo: bytes,
) -> None:
    assert settings.image_ranker == "off"
    pipeline = make_pipeline(image_ranker=FakeImageRanker(default=None))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    assert not any("image similarity" in w for w in response.warnings)


async def test_no_image_warning_when_the_scores_arrive(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    tmp_path,
    photo: bytes,
) -> None:
    configured = make_settings(image_ranker="siglip", log_dir=str(tmp_path / "logs"))
    pipeline = make_pipeline(image_ranker=FakeImageRanker(default=0.7))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), configured)

    assert not any("image similarity" in w for w in response.warnings)
    assert all(scored.scores.image == 0.7 for scored in response.products)


# --------------------------------------------------------------------------------------------
# Other ways a request goes wrong
# --------------------------------------------------------------------------------------------


class CrashingSearcher:
    """A searcher whose search for one category blows up (a bug), delegating the rest."""

    def __init__(self, inner, crash_on: Category) -> None:
        self._inner = inner
        self._crash_on = crash_on

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        if item.category is self._crash_on:
            raise RuntimeError("searcher bug")
        return await self._inner.search(item, stores)  # type: ignore[no-any-return]


async def test_a_crash_while_searching_one_garment_loses_only_that_garment(
    make_pipeline: PipelineMaker,
    two_stores: list[StoreConfig],
    settings: Settings,
    photo: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipeline = make_pipeline(
        understander=outfit_understander(OUTFIT[:2]),
        wrap_searcher=lambda inner: CrashingSearcher(inner, Category.TOPS),
    )
    request = make_search_request(image=photo, text=None)

    response = await pipeline.run(request, settings)

    blazers, tops = response.groups
    assert blazers.result_count > 0
    assert tops.result_count == 0
    assert messages.SEARCH_CRASHED in response.warnings
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "searcher bug" not in " ".join(response.warnings)


async def test_one_empty_garment_of_an_outfit_gets_its_own_note(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    only_blazers = generated_body("blazer", "alpha", DEFAULT_PRICES["blazer"])
    world.add(store_for("alpha"), bodies={"blazer": only_blazers})  # no shirts at all
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]))

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    blazers, tops = response.groups
    assert blazers.result_count > 0
    assert tops.result_count == 0
    assert messages.nothing_found_for(Category.TOPS) in response.warnings
    assert messages.NO_RESULTS_ANYWHERE not in response.warnings


async def test_the_input_type_does_not_matter_to_the_failure_paths(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    world.add(store_for("alpha"), status=403)
    understander = FakeUnderstander(make_understand_result(input_type=InputType.PRODUCT_PHOTO))
    pipeline = make_pipeline(understander=understander)

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert_empty(response)
    assert [r.status for r in response.stores_skipped] == [StoreStatus.BLOCKED]
