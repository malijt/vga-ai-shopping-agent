"""Plan 16.1.1: the image model is loaded once, before the first timed query, and that time is
reported on its own.

The 30 s limit is about a search on an app that is already running. Loading the image model takes
about 10 s cold, so a harness that let the first photo query load it would fail that query for a
reason that is not the app's search. These tests use a fake ranker that charges 10 virtual seconds
the first time it is used, to show where the harness puts that time.
"""

import json
from pathlib import Path

from eval.harness.recording import RecordingSession
from eval.harness.runstore import REPORT_FILE, RUN_FILE, load_run
from eval.harness.wiring import Boundaries, Wiring, WiringFactory
from tests.fakes import FakeClock, FakeImageRanker, FakeStoreSearcher, FakeUnderstander
from tests.harness.cli_support import LOAD_SECONDS, Cli, SlowToLoadRanker, put_photos
from tests.harness.helpers import ToyPipeline
from tests.harness.live_parts import LiveParts, make_stores
from vga.pipeline import SearchPipeline, pipeline_factory
from vga.settings import Settings


class WarmableToyPipeline(ToyPipeline):
    """The toy pipeline plus the real pipeline's ``warm_up``: it asks the ranker it was given."""

    async def warm_up(self) -> bool:
        warm = getattr(self._image_ranker, "warm_up", None)
        return True if warm is None else bool(await warm())


def warm_wiring(live: LiveParts) -> WiringFactory:
    stores = make_stores()

    def factory(settings: Settings) -> Wiring:
        return Wiring(
            pipeline_factory=lambda u, s, r: WarmableToyPipeline(u, s, r, stores),
            stores=stores,
            link_fetch=None,
            build_boundaries=live.boundaries,
        )

    return factory


def live_with(ranker: SlowToLoadRanker) -> LiveParts:
    live = LiveParts()
    live.ranker = ranker
    return live


def record(cli: Cli, live: LiveParts, clock: FakeClock, *extra: str) -> int:
    put_photos(cli.root)
    return cli.run(
        "--record",
        str(cli.root / "rec"),
        "--links",
        "none",
        *extra,
        wiring=warm_wiring(live),
        clock=clock,
    )


class TestTheRecorderPassesTheWarmUpOn:
    """The real pipeline looks for ``warm_up`` on the ranker it was given. In a live run that is
    the recorder, so the recorder has to hand the call on or the model would load in query 1."""

    async def test_the_real_pipeline_warms_the_real_ranker_through_the_recorder(
        self, tmp_path: Path
    ) -> None:
        ranker = SlowToLoadRanker(FakeClock())
        session = RecordingSession(tmp_path / "rec")
        live = session.wrap(Boundaries(FakeUnderstander(), FakeStoreSearcher(), ranker))
        pipeline = pipeline_factory(make_stores())(
            live.understander, live.searcher, live.image_ranker
        )

        assert isinstance(pipeline, SearchPipeline)
        assert await pipeline.warm_up() is True

        assert ranker.warm_ups == 1
        assert ranker.loaded

    async def test_an_unavailable_model_is_reported_as_not_ready(self, tmp_path: Path) -> None:
        ranker = SlowToLoadRanker(FakeClock(), ready=False)
        session = RecordingSession(tmp_path / "rec")
        live = session.wrap(Boundaries(FakeUnderstander(), FakeStoreSearcher(), ranker))
        pipeline = pipeline_factory(make_stores())(
            live.understander, live.searcher, live.image_ranker
        )

        assert await pipeline.warm_up() is False

    async def test_a_ranker_with_nothing_to_load_is_ready(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec")
        live = session.wrap(Boundaries(FakeUnderstander(), FakeStoreSearcher(), FakeImageRanker()))
        pipeline = pipeline_factory(make_stores())(
            live.understander, live.searcher, live.image_ranker
        )

        assert await pipeline.warm_up() is True


class TestTheCommandLineWarmsUpBeforeTheFirstQuery:
    def test_the_model_is_loaded_once_before_any_query_and_outside_every_query_time(
        self, cli: Cli
    ) -> None:
        clock = FakeClock()
        ranker = SlowToLoadRanker(clock)

        assert record(cli, live_with(ranker), clock) == 0

        assert (ranker.warm_ups, ranker.loads) == (1, 1)
        run = load_run(cli.root / "eval" / "results" / "run-1")
        assert run.meta.warm_up is not None
        assert run.meta.warm_up.duration_ms == LOAD_SECONDS * 1000
        assert run.meta.warm_up.ready is True
        assert all(query.wall_ms < LOAD_SECONDS * 1000 for query in run.runs)

    def test_without_the_warm_up_the_first_photo_query_would_carry_the_load(self, cli: Cli) -> None:
        # The control: a pipeline that has no warm_up leaves the load to the first photo query.
        clock = FakeClock()
        ranker = SlowToLoadRanker(clock)
        live = live_with(ranker)
        stores = make_stores()

        def factory(settings: Settings) -> Wiring:
            return Wiring(
                pipeline_factory=lambda u, s, r: ToyPipeline(u, s, r, stores),
                stores=stores,
                build_boundaries=live.boundaries,
            )

        put_photos(cli.root)
        cli.run("--record", str(cli.root / "rec"), "--links", "none", wiring=factory, clock=clock)

        run = load_run(cli.root / "eval" / "results" / "run-1")
        assert run.meta.warm_up is None
        assert run.runs[0].wall_ms >= LOAD_SECONDS * 1000  # q01 is a photo query

    def test_it_says_how_long_the_warm_up_took_and_that_it_is_not_in_a_query(
        self, cli: Cli
    ) -> None:
        clock = FakeClock()

        record(cli, live_with(SlowToLoadRanker(clock)), clock)

        lines = cli.printed.splitlines()
        warm = next(line for line in lines if line.startswith("Warm-up:"))
        assert "done in 10.0 s" in warm
        assert "outside every query's time" in warm
        assert lines.index(warm) < lines.index(next(x for x in lines if x.startswith("q01_")))

    def test_the_report_shows_the_warm_up_apart_from_the_query_seconds(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, live_with(SlowToLoadRanker(clock)), clock)

        text = (cli.root / "eval" / "results" / "run-1" / REPORT_FILE).read_text(encoding="utf-8")
        assert "Warm-up before the first query: 10.0 s; image scoring ready." in text
        assert "not inside any query's seconds" in text

    def test_the_warm_up_is_saved_with_the_run(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, live_with(SlowToLoadRanker(clock)), clock)

        saved = json.loads(
            (cli.root / "eval" / "results" / "run-1" / RUN_FILE).read_text(encoding="utf-8")
        )
        assert saved["meta"]["warm_up"] == {"duration_ms": 10000.0, "ready": True, "detail": None}

    def test_an_unavailable_model_is_said_loudly_and_the_run_carries_on(self, cli: Cli) -> None:
        clock = FakeClock()

        code = record(cli, live_with(SlowToLoadRanker(clock, ready=False)), clock)

        assert code == 0
        assert "image scoring is NOT available" in cli.printed
        assert "uv sync --group ml" in cli.printed
        assert "10 of 10 queries answered" in cli.printed
        text = (cli.root / "eval" / "results" / "run-1" / REPORT_FILE).read_text(encoding="utf-8")
        assert "NOT available (photo queries ranked on text and price)" in text
        assert "does not show what the finished app does with a photo" in text

    def test_a_warm_up_that_raises_is_reported_and_does_not_stop_the_run(self, cli: Cli) -> None:
        clock = FakeClock()

        code = record(cli, live_with(SlowToLoadRanker(clock, fails=True)), clock)

        assert code == 0
        run = load_run(cli.root / "eval" / "results" / "run-1")
        assert run.meta.warm_up is not None
        assert run.meta.warm_up.ready is False
        assert run.meta.warm_up.detail == "RuntimeError: the weights are corrupt"
        assert "10 of 10 queries answered" in cli.printed

    def test_a_replay_loads_nothing_and_does_not_warm_up(self, cli: Cli) -> None:
        clock = FakeClock()
        record(cli, live_with(SlowToLoadRanker(clock)), clock)
        replay_ranker = SlowToLoadRanker(clock)

        code = cli.run(
            "--replay",
            str(cli.root / "rec"),
            wiring=warm_wiring(live_with(replay_ranker)),
            clock=clock,
        )

        assert code == 0
        assert replay_ranker.warm_ups == 0
        assert load_run(cli.root / "eval" / "results" / "replay").meta.warm_up is None
        assert "Warm-up" not in cli.printed.split("10 of 10 queries answered")[-1]

    def test_a_mock_run_has_no_warm_up(self, cli: Cli) -> None:
        cli.run("--mock")

        assert load_run(cli.root / "eval" / "results" / "mock").meta.warm_up is None
        assert "Warm-up" not in cli.printed
