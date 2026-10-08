"""The harness reads what the REAL pipeline says when the platform turns every store away.

``test_not_run.py`` builds responses by hand. This file asks the real pipeline and the real store
engine (over a fake network that answers 429), so the reading of ``stores_skipped`` is checked
against what the app really writes there: a blocked store, a store left in cooldown, and a store
left out because it does not sell for the garment's gender.
"""

from collections.abc import Iterator

import pytest
import respx

from eval.harness.notrun import THROTTLED
from eval.harness.runner import Pacing, QueryRun, run_queries
from tests.factories import make_item_intent, make_settings, make_understand_result
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.harness.helpers import make_query
from tests.pipeline.world import StoreWorld, store_for
from vga.models import Gender, GenderSource, StoreStatus
from vga.pipeline import pipeline_factory
from vga.stores import StoreRegistry, StoreSearchEngine

WOMENS_BLAZER = make_item_intent(
    gender=Gender.WOMEN,
    gender_source=GenderSource.EXPLICIT,
    search_keywords=["black oversized blazer", "oversized blazer"],
)


@pytest.fixture
def clock() -> FakeClock:
    fake = FakeClock()
    fake.SETTLE_HOPS = 500  # a whole pipeline run has long stretches of zero-time work
    return fake


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


@pytest.fixture
def world(router: respx.MockRouter, clock: FakeClock) -> StoreWorld:
    return StoreWorld(router, clock)


async def run_three_queries(
    world: StoreWorld, clock: FakeClock, *, stop: bool
) -> tuple[list[QueryRun], StoreSearchEngine]:
    """Three queries against two stores that answer 429 and a men-only store."""
    stores = [
        store_for("alpha"),
        store_for("beta"),
        store_for("mens", genders=[Gender.MEN]),
    ]
    for store in stores[:2]:
        world.add(store, status=429)
    world.add(stores[2])
    settings = make_settings()
    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    understander = FakeUnderstander(make_understand_result(items=[WOMENS_BLAZER]))
    pipeline = pipeline_factory(stores)(understander, engine, FakeImageRanker())
    runs = await run_queries(
        [make_query(f"q0{n}_text", text=f"black oversized blazer {n}") for n in (1, 2, 3)],
        pipeline,
        settings,
        clock=clock,
        load_image=lambda query: None,
        pacing=Pacing(stop_when_throttled=stop),
    )
    await engine.aclose()
    return runs, engine


def asked_in_total(world: StoreWorld) -> int:
    return sum(len(world.queries(store_id)) for store_id in ("alpha", "beta", "mens"))


class TestWhatTheRealPipelineSaysWhenEveryStoreIsTurnedAway:
    async def test_the_first_query_is_not_run_and_names_the_stores_that_were_turned_away(
        self, world: StoreWorld, clock: FakeClock
    ) -> None:
        runs, _engine = await run_three_queries(world, clock, stop=False)

        first = runs[0]
        assert first.failure is None
        assert first.not_run is not None
        assert first.not_run.kind == "stores_unavailable"
        # The men-only store was left out for the garment and is not named; the other two are.
        assert {s.store_id for s in first.not_run.stores} == {"alpha", "beta"}
        assert {s.status for s in first.not_run.stores} <= THROTTLED
        assert StoreStatus.BLOCKED in {s.status for s in first.not_run.stores}
        assert all(s.reason for s in first.not_run.stores)

    async def test_the_next_query_finds_the_stores_in_cooldown_and_is_not_run_either(
        self, world: StoreWorld, clock: FakeClock
    ) -> None:
        runs, _engine = await run_three_queries(world, clock, stop=False)

        second = runs[1]
        assert second.not_run is not None
        assert {s.status for s in second.not_run.stores} == {StoreStatus.COOLDOWN}

    async def test_with_the_stop_the_other_queries_are_not_sent(
        self, world: StoreWorld, clock: FakeClock
    ) -> None:
        runs, _engine = await run_three_queries(world, clock, stop=True)

        assert [run.not_run.kind if run.not_run else None for run in runs] == [
            "stores_unavailable",
            "not_sent",
            "not_sent",
        ]
        assert asked_in_total(world) <= 2  # at most one search request to each blocked store
        assert world.queries("mens") == []

    async def test_the_apps_own_cooldown_holds_even_when_the_harness_keeps_going(
        self, world: StoreWorld, clock: FakeClock
    ) -> None:
        await run_three_queries(world, clock, stop=False)

        assert asked_in_total(world) <= 2  # three queries, and each store was asked at most once
