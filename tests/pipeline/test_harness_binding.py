"""The acceptance harness builds the pipeline from the three boundaries
(``Wiring.pipeline_factory``) and records or replays a run at those boundaries. This proves the
real pipeline fits that:

- it is built by ``pipeline_factory(stores)`` from recorders around the real store engine,
- a replay of the recording runs the same pipeline with no network call and no model call,
- the replay gives the same answer, the calls were made in a deterministic order (an outfit's
  garments are searched side by side), and the replay finds nothing to complain about.
"""

import json
from pathlib import Path

from eval.harness.queries import AcceptanceQuery
from eval.harness.recording import RecordingSession, ReplaySession
from eval.harness.runner import QueryRun, run_queries
from eval.harness.wiring import Boundaries
from tests.factories import make_item_intent, make_settings, make_understand_result
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.harness.helpers import make_query
from tests.pipeline.builders import OUTFIT
from tests.pipeline.world import StoreWorld, store_for
from vga.models import InputType, SearchRequest, SearchResponse, UnderstandResult
from vga.pipeline import pipeline_factory
from vga.stores import StoreRegistry, StoreSearchEngine

OUTFIT_TEXT = "an outfit: blazer and shirt"


def understand_for(req: SearchRequest) -> UnderstandResult:
    if req.text == OUTFIT_TEXT:
        return make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=OUTFIT[:2])
    item = make_item_intent(search_keywords=["black oversized blazer", "oversized blazer"])
    kind = InputType.TEXT if req.image is None else InputType.PHOTO_TEXT
    return make_understand_result(input_type=kind, items=[item])


def queries() -> list[AcceptanceQuery]:
    return [
        make_query("q01_text", "text", text="black oversized blazer"),
        make_query("q02_outfit", "text", text=OUTFIT_TEXT),
    ]


def comparable(response: SearchResponse | None) -> dict:
    """The answer, without what differs between two runs: the id and the clock."""
    assert response is not None
    return response.model_dump(exclude={"request_id", "timings", "duration_ms"})


async def run_through(
    boundaries: Boundaries, scope: RecordingSession | ReplaySession, stores: list
) -> list[QueryRun]:
    pipeline = pipeline_factory(stores)(
        boundaries.understander, boundaries.searcher, boundaries.image_ranker
    )
    return await run_queries(
        queries(),
        pipeline,
        make_settings(),
        clock=FakeClock(),
        load_image=lambda query: None,
        scope=scope,
    )


async def test_a_recorded_run_of_the_real_pipeline_replays_with_no_network_and_no_model_call(
    world: StoreWorld, tmp_path: Path, clock: FakeClock
) -> None:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    settings = make_settings()
    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    understander = FakeUnderstander(understand_for)
    ranker = FakeImageRanker()

    session = RecordingSession(tmp_path / "recording")
    live = Boundaries(understander, engine, ranker)
    recorded = await run_through(session.wrap(live), session, stores)
    await engine.aclose()
    requests_after_recording = world.all_requests()

    replaying = ReplaySession(tmp_path / "recording")
    replayed = await run_through(replaying.boundaries(), replaying, stores)

    assert [run.failure for run in recorded] == [None, None]
    assert [run.failure for run in replayed] == [None, None]
    assert requests_after_recording > 0  # the recording really used the fake network
    assert world.all_requests() == requests_after_recording  # the replay used none
    assert len(understander.calls) == 2  # ... and no model call
    assert [comparable(a.response) for a in recorded] == [comparable(b.response) for b in replayed]
    assert all(run.response and run.response.result_count > 0 for run in replayed)
    assert replaying.mismatches == []
    assert replaying.final_notes() == []  # every recorded call was used, none was missing


async def test_the_calls_of_an_outfit_are_recorded_in_item_order_then_store_order(
    world: StoreWorld, tmp_path: Path, clock: FakeClock
) -> None:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    settings = make_settings()
    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    session = RecordingSession(tmp_path / "recording")
    live = Boundaries(FakeUnderstander(understand_for), engine, FakeImageRanker())

    await run_through(session.wrap(live), session, stores)
    await engine.aclose()

    outfit = json.loads((tmp_path / "recording" / "q02_outfit.json").read_text(encoding="utf-8"))
    searched = [(call["item"]["category"], call["stores"]) for call in outfit["search"]]
    assert searched == [
        ("outerwear", ["alpha"]),
        ("outerwear", ["beta"]),
        ("tops", ["alpha"]),
        ("tops", ["beta"]),
    ]
