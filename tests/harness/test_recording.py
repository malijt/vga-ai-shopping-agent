"""11.1.3: record a live run at the contract boundary, replay it offline.

A "live" run here uses the shared fakes for the three boundaries, plus a fake network
(``StoreHttpFixtures``) that the searcher really talks to, so the tests can prove a replay touches
neither the network nor the model.
"""

import asyncio
import base64
import json
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from eval.harness.errors import RecordingError, RecordingMismatchError
from eval.harness.queries import AcceptanceQuery
from eval.harness.recording import (
    MANIFEST_FILE,
    RECORDING_FORMAT,
    RecordingSession,
    ReplaySession,
    _refuse_image_data,
)
from eval.harness.runner import QueryRun, run_queries
from eval.harness.wiring import Boundaries

from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_settings,
    make_store_config,
    make_store_result,
    make_understand_result,
)
from tests.fakes import (
    FakeClock,
    FakeImageRanker,
    FakeStoreSearcher,
    FakeUnderstander,
    RecordedResponse,
    StoreHttpFixtures,
)
from tests.harness.helpers import ToyPipeline, make_query
from vga.errors import CallBudgetExceededError, LlmError
from vga.models import (
    Category,
    InputType,
    ItemIntent,
    Product,
    QueryImage,
    SearchRequest,
    StoreConfig,
    StoreResult,
    StoreStatus,
    UnderstandResult,
)

PHOTO = make_image_bytes("JPEG", (64, 64), (10, 120, 200))
OUTFIT_TEXT = "an outfit: top and shoes"


def stores() -> list[StoreConfig]:
    return [
        make_store_config(
            id=name,
            name=name.title(),
            search_url_template=f"https://www.{name}.example/search?q={{query}}",
            allowed_hosts=[f"www.{name}.example", f"cdn.{name}.example"],
        )
        for name in ("alpha", "beta")
    ]


def understand_for(req: SearchRequest) -> UnderstandResult:
    """Two garments for the outfit query, one item otherwise."""
    if req.text == OUTFIT_TEXT:
        items = [
            make_item_intent(category=Category.TOPS, search_keywords=["white shirt"]),
            make_item_intent(category=Category.SHOES, search_keywords=["white sneakers"]),
        ]
        return make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items)
    kind = InputType.PRODUCT_PHOTO if req.text is None else InputType.TEXT
    return make_understand_result(input_type=kind)


class NetworkedSearcher:
    """Like the real fetch engine: it really issues a request per store, through a fake network."""

    def __init__(self, fixtures: StoreHttpFixtures, inner: FakeStoreSearcher) -> None:
        self._fixtures = fixtures
        self.inner = inner

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        async with httpx.AsyncClient(transport=self._fixtures.transport()) as client:
            for store in stores:
                await client.get(f"https://www.{store.id}.example/search?q=x")
        return await self.inner.search(item, stores)


class LiveParts:
    """The fake 'live' boundaries and everything that proves what they were asked."""

    def __init__(self) -> None:
        self.fixtures = StoreHttpFixtures()
        for store in stores():
            host = f"www.{store.id}.example"
            self.fixtures.add(
                f"https://{host}/", RecordedResponse(f"https://{host}/", 200, {}, b"{}")
            )
        self.understander = FakeUnderstander(understand_for)
        self.searcher = NetworkedSearcher(self.fixtures, FakeStoreSearcher(product_count=4))
        self.ranker = FakeImageRanker({}, default=0.8)

    def boundaries(self) -> Boundaries:
        return Boundaries(self.understander, self.searcher, self.ranker)

    def calls(self) -> tuple[int, int, int, int]:
        return (
            self.fixtures.request_count(),
            len(self.understander.calls),
            len(self.searcher.inner.calls),
            len(self.ranker.calls),
        )


def acceptance_queries() -> list[AcceptanceQuery]:
    return [
        make_query("q01_photo", "product_photo"),
        make_query("q04_outfit", "text", text=OUTFIT_TEXT),
        make_query("q06_text", "text"),
    ]


def photo_loader(query: AcceptanceQuery) -> bytes | None:
    return PHOTO if query.image else None


async def run_with(
    boundaries: Boundaries, scope: RecordingSession | ReplaySession
) -> list[QueryRun]:
    pipeline = ToyPipeline(
        boundaries.understander, boundaries.searcher, boundaries.image_ranker, stores()
    )
    return await run_queries(
        acceptance_queries(),
        pipeline,
        make_settings(),
        clock=FakeClock(),
        load_image=photo_loader,
        scope=scope,
    )


async def record(directory: Path, live: LiveParts) -> list[QueryRun]:
    session = RecordingSession(directory)
    return await run_with(session.wrap(live.boundaries()), session)


async def replay(directory: Path) -> list[QueryRun]:
    session = ReplaySession(directory)
    return await run_with(session.boundaries(), session)


def same_apart_from_request_id(first: QueryRun, second: QueryRun) -> bool:
    assert first.response is not None
    assert second.response is not None
    return first.response.model_dump(exclude={"request_id"}) == second.response.model_dump(
        exclude={"request_id"}
    )


class TestRecordThenReplay:
    async def test_a_replayed_run_reproduces_the_recorded_responses(self, tmp_path: Path) -> None:
        recorded = await record(tmp_path / "rec", LiveParts())

        replayed = await replay(tmp_path / "rec")

        assert [r.query.id for r in replayed] == [r.query.id for r in recorded]
        assert all(
            same_apart_from_request_id(a, b) for a, b in zip(recorded, replayed, strict=True)
        )
        counts = [run.response.result_count for run in replayed if run.response]
        assert counts == [run.response.result_count for run in recorded if run.response]
        assert all(count > 0 for count in counts)

    async def test_a_replay_makes_no_network_call_and_no_model_call(self, tmp_path: Path) -> None:
        live = LiveParts()
        await record(tmp_path / "rec", live)
        before = live.calls()
        assert before[0] > 0  # the recording run did use the fake network
        assert all(count > 0 for count in before)

        await replay(tmp_path / "rec")

        assert live.calls() == before
        live.fixtures.assert_no_unexpected_requests()

    async def test_the_pipeline_recomputes_its_ranking_from_the_replayed_values(
        self, tmp_path: Path
    ) -> None:
        await record(tmp_path / "rec", LiveParts())

        replayed = await replay(tmp_path / "rec")

        # The toy pipeline scores 0.5 + 0.4 x image score. The replayed ranker returned the
        # recorded 0.8, so the pipeline's own arithmetic ran again on it.
        top = replayed[0].response.groups[0].tiers[0].results[0]  # type: ignore[union-attr]
        assert top.scores.image == pytest.approx(0.8)
        assert top.scores.total == pytest.approx(0.82)

    async def test_the_recorded_live_duration_is_kept_for_each_query(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())

        session = ReplaySession(tmp_path / "rec")

        assert session.live_duration_ms("q01_photo") == 1234.0
        assert session.live_duration_ms("not-recorded") is None


class TestEachBoundaryReturnsExactlyWhatWasSaved:
    async def test_every_value_comes_back_identical(self, tmp_path: Path) -> None:
        live = LiveParts()
        request = SearchRequest(text="black blazer")
        item = make_item_intent(search_keywords=["black blazer"])
        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(live.boundaries())

        session.begin_query("q06_text")
        understood = await wrapped.understander.understand(request)
        found = await wrapped.searcher.search(item, stores())
        flat: list[Product] = [p for result in found for p in result.products]
        scores = await wrapped.image_ranker.score(QueryImage(image=PHOTO), flat)
        session.end_query("q06_text", duration_ms=10.0)

        replayed = ReplaySession(tmp_path / "rec")
        replayed.begin_query("q06_text")
        boundaries = replayed.boundaries()
        assert await boundaries.understander.understand(request) == understood
        assert await boundaries.searcher.search(item, stores()) == found
        assert await boundaries.image_ranker.score(QueryImage(image=PHOTO), flat) == scores

    async def test_an_understander_error_is_replayed_as_the_same_kind_of_error(
        self, tmp_path: Path
    ) -> None:
        failing = FakeUnderstander(error=LlmError("The model did not answer.", detail="hidden"))
        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(Boundaries(failing, FakeStoreSearcher(), FakeImageRanker()))
        session.begin_query("q06_text")
        with pytest.raises(LlmError):
            await wrapped.understander.understand(SearchRequest(text="x"))
        session.end_query("q06_text", duration_ms=1.0)

        replayed = ReplaySession(tmp_path / "rec")
        replayed.begin_query("q06_text")
        with pytest.raises(LlmError, match="did not answer") as caught:
            await replayed.understander.understand(SearchRequest(text="x"))

        assert caught.value.code == "llm_failure"
        assert caught.value.detail is None

    async def test_a_budget_error_keeps_its_own_type(self, tmp_path: Path) -> None:
        failing = FakeUnderstander(error=CallBudgetExceededError())
        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(Boundaries(failing, FakeStoreSearcher(), FakeImageRanker()))
        session.begin_query("q06_text")
        with pytest.raises(CallBudgetExceededError):
            await wrapped.understander.understand(SearchRequest(text="x"))
        session.end_query("q06_text", duration_ms=1.0)

        replayed = ReplaySession(tmp_path / "rec")
        replayed.begin_query("q06_text")

        with pytest.raises(CallBudgetExceededError):
            await replayed.understander.understand(SearchRequest(text="x"))

    async def test_a_store_that_failed_is_replayed_with_its_status(self, tmp_path: Path) -> None:
        blocked = make_store_result(StoreStatus.BLOCKED, store_id="alpha", detail="HTTP 403")
        searcher = FakeStoreSearcher(results={"alpha": blocked})
        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(Boundaries(FakeUnderstander(), searcher, FakeImageRanker()))
        session.begin_query("q06_text")
        await wrapped.searcher.search(make_item_intent(), stores())
        session.end_query("q06_text", duration_ms=1.0)

        replayed = ReplaySession(tmp_path / "rec")
        replayed.begin_query("q06_text")
        results = await replayed.searcher.search(make_item_intent(), stores())

        assert results[0].status is StoreStatus.BLOCKED
        assert results[0].detail == "HTTP 403"
        assert results[1].status is StoreStatus.OK


class TestWhatIsSaved:
    async def test_the_layout_is_a_manifest_and_one_file_per_query(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())

        files = sorted(p.name for p in (tmp_path / "rec").iterdir())
        manifest = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text(encoding="utf-8"))

        assert files == ["manifest.json", "q01_photo.json", "q04_outfit.json", "q06_text.json"]
        assert manifest["format"] == RECORDING_FORMAT
        assert list(manifest["queries"]) == ["q01_photo", "q04_outfit", "q06_text"]
        assert manifest["models"] == ["test-model-2026-01-01"]
        assert manifest["prompt_versions"] == ["test-1"]

    async def test_calls_are_saved_in_call_order_with_the_item_and_store_ids(
        self, tmp_path: Path
    ) -> None:
        await record(tmp_path / "rec", LiveParts())

        outfit = json.loads((tmp_path / "rec" / "q04_outfit.json").read_text(encoding="utf-8"))

        assert len(outfit["understand"]) == 1
        assert [call["item"]["category"] for call in outfit["search"]] == ["tops", "shoes"]
        assert outfit["search"][0]["stores"] == ["alpha", "beta"]
        assert len(outfit["image_scores"]) == 2

    async def test_no_photo_no_image_bytes_and_no_embedding_is_ever_written(
        self, tmp_path: Path
    ) -> None:
        live = LiveParts()
        await record(tmp_path / "rec", live)
        assert live.ranker.calls  # the ranker really ran, and sets an embedding on photo queries

        for file in (tmp_path / "rec").iterdir():
            raw = file.read_bytes()
            text = raw.decode("utf-8")
            assert PHOTO not in raw
            assert base64.b64encode(PHOTO).decode() not in text
            assert "embedding" not in text
            assert '"image"' not in text
            assert "0.1, 0.2" not in text

    async def test_a_directory_that_already_holds_a_recording_is_refused(
        self, tmp_path: Path
    ) -> None:
        await record(tmp_path / "rec", LiveParts())

        with pytest.raises(RecordingError, match="never overwritten"):
            RecordingSession(tmp_path / "rec")

    async def test_a_boundary_that_failed_mid_call_marks_the_recording_incomplete(
        self, tmp_path: Path
    ) -> None:
        class Exploding:
            async def search(
                self, item: ItemIntent, stores: Sequence[StoreConfig]
            ) -> list[StoreResult]:
                raise RuntimeError("network down")

        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(Boundaries(FakeUnderstander(), Exploding(), FakeImageRanker()))
        session.begin_query("q06_text")
        with pytest.raises(RuntimeError, match="network down"):
            await wrapped.searcher.search(make_item_intent(), stores())
        session.end_query("q06_text", duration_ms=1.0)

        assert session.incomplete == ["q06_text"]
        replayed = ReplaySession(tmp_path / "rec")
        with pytest.raises(RecordingError, match="incomplete"):
            replayed.begin_query("q06_text")

    def test_the_guard_refuses_bytes_and_photo_shaped_fields(self) -> None:
        with pytest.raises(RecordingError, match="binary"):
            _refuse_image_data({"scores": {"a": b"\x89PNG"}})
        with pytest.raises(RecordingError, match="'embedding'"):
            _refuse_image_data({"call": [{"embedding": [0.1]}]})
        with pytest.raises(RecordingError, match="'query_embedding'"):
            _refuse_image_data({"query_embedding": [0.1]})
        _refuse_image_data({"image_url": "https://cdn.example/a.jpg", "scores": {"u": 0.5}})

    async def test_calls_are_numbered_when_they_start_not_when_they_finish(
        self, tmp_path: Path
    ) -> None:
        class SlowThenFast:
            def __init__(self) -> None:
                self.inner = FakeStoreSearcher()

            async def search(
                self, item: ItemIntent, stores: Sequence[StoreConfig]
            ) -> list[StoreResult]:
                if item.category is Category.TOPS:
                    for _ in range(5):
                        await asyncio.sleep(0)
                return await self.inner.search(item, stores)

        session = RecordingSession(tmp_path / "rec")
        wrapped = session.wrap(Boundaries(FakeUnderstander(), SlowThenFast(), FakeImageRanker()))
        tops = make_item_intent(category=Category.TOPS, search_keywords=["shirt"])
        shoes = make_item_intent(category=Category.SHOES, search_keywords=["sneakers"])
        session.begin_query("q04_outfit")

        await asyncio.gather(
            wrapped.searcher.search(tops, stores()), wrapped.searcher.search(shoes, stores())
        )
        session.end_query("q04_outfit", duration_ms=1.0)

        saved = json.loads((tmp_path / "rec" / "q04_outfit.json").read_text(encoding="utf-8"))
        assert [call["item"]["category"] for call in saved["search"]] == ["tops", "shoes"]


class TestReplayRefusesWhatWasNotRecorded:
    async def test_a_third_search_when_two_were_recorded_is_a_mismatch(
        self, tmp_path: Path
    ) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")
        session.begin_query("q04_outfit")
        boundaries = session.boundaries()
        tops = make_item_intent(category=Category.TOPS, search_keywords=["white shirt"])
        shoes = make_item_intent(category=Category.SHOES, search_keywords=["white sneakers"])
        await boundaries.searcher.search(tops, stores())
        await boundaries.searcher.search(shoes, stores())

        with pytest.raises(RecordingMismatchError, match="search call number 3"):
            await boundaries.searcher.search(shoes, stores())

    async def test_a_search_for_other_stores_is_a_mismatch(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")
        session.begin_query("q06_text")

        with pytest.raises(RecordingMismatchError, match="stores"):
            await session.searcher.search(make_item_intent(), stores()[:1])

    async def test_a_search_for_a_different_item_is_a_mismatch(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")
        session.begin_query("q06_text")
        other = make_item_intent(search_keywords=["red coat"])

        with pytest.raises(RecordingMismatchError, match="different item"):
            await session.searcher.search(other, stores())

    async def test_a_product_without_a_recorded_image_score_gets_none_and_a_note(
        self, tmp_path: Path
    ) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")
        session.begin_query("q01_photo")
        found = await session.searcher.search(make_item_intent(), stores())
        known = found[0].products[0]
        stranger = Product.model_validate(
            {**known.model_dump(), "product_url": "https://www.alpha.example/p/never-recorded"}
        )

        scores = await session.image_ranker.score(QueryImage(image=PHOTO), [known, stranger])

        assert scores[known.key] == pytest.approx(0.8)
        assert scores[stranger.key] is None
        assert any("1 product" in note for note in session.final_notes())

    async def test_unused_recorded_calls_are_noted_not_hidden(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")
        session.begin_query("q06_text")

        session.end_query("q06_text", duration_ms=0.0)

        assert any("q06_text" in note and "search" in note for note in session.notes)

    def test_a_query_that_was_not_recorded_is_named(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec")
        session.begin_query("q01_photo")
        session.end_query("q01_photo", duration_ms=1.0)
        replayed = ReplaySession(tmp_path / "rec")

        with pytest.raises(RecordingError, match="q05_layered"):
            replayed.begin_query("q05_layered")

    async def test_a_boundary_called_outside_a_query_is_an_error(self, tmp_path: Path) -> None:
        await record(tmp_path / "rec", LiveParts())
        session = ReplaySession(tmp_path / "rec")

        with pytest.raises(RecordingError, match="outside a query"):
            await session.understander.understand(SearchRequest(text="x"))


class TestAnUnusableRecording:
    def test_a_missing_recording_says_to_record_first(self, tmp_path: Path) -> None:
        with pytest.raises(RecordingError, match="--record"):
            ReplaySession(tmp_path / "nothing")

    def test_a_recording_of_another_format_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / MANIFEST_FILE).write_text(
            json.dumps({"format": 99, "queries": {}}), encoding="utf-8"
        )

        with pytest.raises(RecordingError, match="format"):
            ReplaySession(tmp_path)

    def test_a_broken_manifest_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / MANIFEST_FILE).write_text("{oops", encoding="utf-8")

        with pytest.raises(RecordingError, match="not valid JSON"):
            ReplaySession(tmp_path)
