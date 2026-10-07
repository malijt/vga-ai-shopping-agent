"""Plan 13.2.2: a request has one deadline (30 s). At the deadline the pipeline stops waiting for
whatever is still running and returns what has been ranked so far, with a warning.

Time here is the ``FakeClock``: a store that takes 100 s costs the test no real time at all.
"""

import asyncio
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
from tests.pipeline.builders import OUTFIT, outfit_understander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.errors import VgaError
from vga.models import Product, QueryImage, StoreStatus, UnderstandResult
from vga.pipeline import RequestTimeoutError, messages
from vga.settings import Settings

DEADLINE_S = 30.0
MARGIN_S = 1.0
"""How far past the deadline a response may be: only the time to assemble it."""


@pytest.fixture(autouse=True)
def _log_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="vga")


def slow_store(key: str):
    """A store whose requests may take up to 30 s each, so only the request deadline stops it."""
    return store_for(key, timeout_s=30, max_variants=1)


def leftover_tasks() -> list[asyncio.Task]:
    current = asyncio.current_task()
    return [t for t in asyncio.all_tasks() if t is not current and not t.done()]


async def test_a_slow_store_cannot_keep_the_response_past_the_deadline(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world.add(store_for("alpha"))
    world.add(slow_store("beta"), delay=100.0)
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")
    started = clock.monotonic()

    response = await pipeline.run(request, settings)

    elapsed = clock.monotonic() - started
    assert DEADLINE_S <= elapsed <= DEADLINE_S + MARGIN_S
    assert response.duration_ms <= (DEADLINE_S + MARGIN_S) * 1000
    assert messages.deadline_warning(DEADLINE_S) in response.warnings
    assert "longer than 30 seconds" in " ".join(response.warnings)
    assert any(
        record.levelno == logging.WARNING
        and "deadline reached" in record.getMessage()
        and getattr(record, "request_id", None) == request.request_id
        for record in caplog.records
    )


async def test_what_the_other_stores_found_before_the_deadline_is_still_ranked_and_shown(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(slow_store("beta"), delay=100.0)
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert response.result_count > 0
    assert {scored.product.store for scored in response.products} == {"Alpha"}
    assert [report.store_id for report in response.stores_used] == ["alpha"]
    [slow] = response.stores_skipped
    assert (slow.store_id, slow.status) == ("beta", StoreStatus.TIMEOUT)
    assert slow.reason == messages.STORE_NOT_FINISHED
    # the search stage is timed as cut short; the stages after it still ran on what was found
    search = next(t for t in response.timings if t.step == "search")
    assert (search.status, search.duration_ms) == ("timeout", DEADLINE_S * 1000)
    assert {"assemble"} <= {t.step for t in response.timings}


async def test_nothing_is_left_running_after_the_deadline(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(slow_store("beta"), delay=100.0)
    pipeline = make_pipeline()

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert leftover_tasks() == []


async def test_a_shorter_deadline_in_the_settings_is_honoured(
    make_pipeline: PipelineMaker, world: StoreWorld, tmp_path, clock: FakeClock
) -> None:
    short = make_settings(request_deadline_s=5, log_dir=str(tmp_path / "logs"))
    world.add(store_for("alpha"))
    world.add(store_for("beta"), delay=10.0)  # the engine would wait 12 s for it
    pipeline = make_pipeline(engine_settings=short)
    started = clock.monotonic()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), short)

    assert 5.0 <= clock.monotonic() - started <= 5.0 + MARGIN_S
    assert messages.deadline_warning(5) in response.warnings
    assert response.result_count > 0


async def test_a_run_that_finishes_in_time_carries_no_deadline_warning(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert not any("longer than" in warning for warning in response.warnings)
    assert not any(t.status == "timeout" for t in response.timings)


async def test_in_an_outfit_the_garments_ranked_before_the_deadline_are_kept(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, photo: bytes
) -> None:
    # The shirt searches never answer in time; the blazer searches are quick.
    def slow_for_shirts(query: str) -> float:
        return 100.0 if "shirt" in query else 0.0

    world.add(slow_store("alpha"), delay=slow_for_shirts)
    world.add(slow_store("beta"), delay=slow_for_shirts)
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]))

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    blazers, tops = response.groups
    assert blazers.result_count > 0
    assert tops.result_count == 0
    assert messages.deadline_warning(DEADLINE_S) in response.warnings
    # the empty garment is explained by the deadline, not by "no store had anything"
    assert messages.NO_RESULTS_ANYWHERE not in response.warnings
    assert messages.nothing_found_for(tops.category) not in response.warnings


async def test_a_slow_image_ranker_still_gives_a_text_and_price_ranking_by_the_deadline(
    make_pipeline: PipelineMaker,
    two_stores: list,
    settings: Settings,
    clock: FakeClock,
    photo: bytes,
) -> None:
    class NeverFinishes:
        def __init__(self) -> None:
            self.queries: list[QueryImage] = []

        async def score(
            self, query: QueryImage | None, products: Sequence[Product]
        ) -> dict[str, float | None]:
            assert query is not None
            self.queries.append(query)
            await clock.sleep(1000)
            return dict.fromkeys(p.key for p in products)

    ranker = NeverFinishes()
    pipeline = make_pipeline(image_ranker=ranker)
    started = clock.monotonic()

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    assert DEADLINE_S <= clock.monotonic() - started <= DEADLINE_S + MARGIN_S
    assert response.result_count > 0  # ranked on text and price
    assert all(scored.scores.image is None for scored in response.products)
    assert messages.deadline_warning(DEADLINE_S) in response.warnings
    image_step = next(t for t in response.timings if t.step == "image_rank")
    assert image_step.status == "timeout"
    assert [query.image for query in ranker.queries] == [None]  # the photo was dropped anyway


class SlowUnderstander:
    """Stands in for an OpenAI call that does not come back in time."""

    def __init__(self, clock: FakeClock, result: UnderstandResult) -> None:
        self._clock = clock
        self._result = result

    async def understand(self, req) -> UnderstandResult:
        await self._clock.sleep(1000)
        return self._result


async def test_a_request_that_is_not_understood_by_the_deadline_is_a_plain_error(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipeline = make_pipeline(
        understander=SlowUnderstander(clock, make_understand_result()),  # type: ignore[arg-type]
    )
    request = make_search_request(text="black blazer")
    started = clock.monotonic()

    with pytest.raises(RequestTimeoutError) as caught:
        await pipeline.run(request, settings)

    assert isinstance(caught.value, VgaError)
    assert caught.value.code == "request_timeout"
    assert "try again" in caught.value.user_message
    assert DEADLINE_S <= clock.monotonic() - started <= DEADLINE_S + MARGIN_S
    assert world.all_requests() == 0
    assert any(
        record.levelno == logging.WARNING
        and getattr(record, "request_id", None) == request.request_id
        for record in caplog.records
    )
    assert leftover_tasks() == []


async def test_the_deadline_counts_from_the_start_of_the_run_not_from_each_step(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings, clock: FakeClock
) -> None:
    class TwentyFiveSeconds(FakeUnderstander):
        async def understand(self, req):  # type: ignore[no-untyped-def]
            await clock.sleep(25)
            return await super().understand(req)

    world.add(store_for("alpha"), delay=10.0)  # 25 s + 10 s = 35 s, over the deadline
    understander = TwentyFiveSeconds(
        make_understand_result(items=[make_item_intent(search_keywords=["black oversized blazer"])])
    )
    pipeline = make_pipeline(understander=understander)

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert messages.deadline_warning(DEADLINE_S) in response.warnings
    assert response.duration_ms <= (DEADLINE_S + MARGIN_S) * 1000


async def test_an_image_ranker_that_is_quick_is_not_cut_off(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(image_ranker=FakeImageRanker(default=0.9))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    assert not any("longer than" in warning for warning in response.warnings)
    assert all(scored.scores.image == 0.9 for scored in response.products)
