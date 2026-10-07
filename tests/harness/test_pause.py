"""A live run rests between queries (``--pause``), so ten searches are not sent back to back.

The first recorded run sent its ten queries in under a minute and the platform turned every store
away. A shopper never searches that fast. The wait sits between one query's end (its links
included) and the next query's start, so it is never inside a query's time. A mock or replay run
touches no store and never waits. Nothing here really waits: time is a fake clock.
"""

import pytest

from eval.harness.links import LinkResult
from eval.harness.runstore import REPORT_FILE, load_run
from tests.fakes import FakeClock, FakeUnderstander
from tests.harness.cli_support import Cli, put_photos, wiring_over
from tests.harness.live_parts import LiveParts, ok_link_fetch, understand_for
from tests.harness.live_run_support import WatchingClock, stepped_wiring
from vga.models import SearchRequest, UnderstandResult

RUN = "eval/results/run-1"


def record(cli: Cli, clock: FakeClock, *extra: str, links: str = "none") -> int:
    put_photos(cli.root)
    return cli.run(
        "--record",
        str(cli.root / "eval" / "results" / "run-1" / "recording"),
        "--links",
        links,
        *extra,
        wiring=wiring_over(LiveParts()),
        clock=clock,
    )


class TestThePause:
    def test_a_live_run_rests_30_seconds_between_queries_by_default(self, cli: Cli) -> None:
        clock = FakeClock()

        assert record(cli, clock) == 0, cli.errors

        assert clock.sleeps == [30.0] * 9  # ten queries have nine gaps, and none after the last

    def test_the_pause_can_be_chosen(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, clock, "--pause", "7.5")

        assert clock.sleeps == [7.5] * 9

    def test_a_pause_of_zero_means_no_waiting(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, clock, "--pause", "0")

        assert clock.sleeps == []
        assert "Pausing" not in cli.printed

    def test_a_negative_pause_is_refused(self, cli: Cli) -> None:
        with pytest.raises(SystemExit) as caught:
            cli.run("--mock", "--pause", "-1")

        assert caught.value.code == 2

    def test_a_pause_that_is_not_a_number_is_refused(self, cli: Cli) -> None:
        with pytest.raises(SystemExit) as caught:
            cli.run("--mock", "--pause", "soon")

        assert caught.value.code == 2

    def test_a_mock_run_never_pauses(self, cli: Cli) -> None:
        clock = FakeClock()

        cli.run("--mock", "--pause", "30", clock=clock)

        assert clock.sleeps == []
        assert "Pausing" not in cli.printed

    def test_a_replay_never_pauses(self, cli: Cli) -> None:
        record(cli, FakeClock(), "--pause", "0")
        clock = FakeClock()

        cli.run(
            "--replay",
            str(cli.root / "eval" / "results" / "run-1" / "recording"),
            "--pause",
            "30",
            wiring=wiring_over(LiveParts()),
            clock=clock,
        )

        assert clock.sleeps == []
        assert "Pausing" not in cli.printed


class TestThePauseIsSaidAsItHappens:
    def test_each_pause_is_printed_before_the_wait_starts(self, cli: Cli) -> None:
        printed_when_waiting_started: list[str] = []
        clock = WatchingClock(lambda seconds: printed_when_waiting_started.append(cli.printed))

        record(cli, clock)

        assert len(printed_when_waiting_started) == 9
        first = printed_when_waiting_started[0]
        assert first.rstrip().splitlines()[-1] == (
            "Pausing 30 s before q02_product_abaya to give the stores a rest."
        )
        assert cli.printed.count("Pausing 30 s before") == 9

    def test_the_report_says_what_the_pause_was(self, cli: Cli) -> None:
        record(cli, FakeClock(), "--pause", "12")

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert "paused 12 s between queries" in text
        assert "outside every query's seconds" in text

    def test_a_run_with_no_pause_says_so(self, cli: Cli) -> None:
        record(cli, FakeClock(), "--pause", "0")

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert "no pause between queries" in text

    def test_a_mock_report_says_nothing_about_a_pause(self, cli: Cli) -> None:
        cli.run("--mock")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert "paused" not in text
        assert "no pause" not in text


class TestThePauseIsOutsideEveryQuery:
    def test_a_querys_seconds_do_not_include_the_wait(self, cli: Cli) -> None:
        clock = FakeClock()
        put_photos(cli.root)

        cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            "--links",
            "none",
            wiring=stepped_wiring(LiveParts(), clock=clock, seconds=7.0),
            clock=clock,
        )

        saved = load_run(cli.root / RUN)
        assert [run.duration_ms for run in saved.runs] == [7000.0] * 10
        assert [run.wall_ms for run in saved.runs] == [7000.0] * 10
        # The clock did move: ten queries of 7 s (plus 3 searches after an answer) and 9 pauses.
        searches = 10 + sum(1 for run in saved.runs if run.gender and run.gender.asked)
        assert clock.monotonic() - 1000.0 == pytest.approx(7.0 * searches + 30.0 * 9)

    def test_the_wait_comes_after_the_links_of_the_query_before(self, cli: Cli) -> None:
        events: list[str] = []
        live = LiveParts()

        def understand(req: SearchRequest) -> UnderstandResult:
            events.append("search")
            return understand_for(req)

        async def fetch(url: str) -> LinkResult:
            events.append("link")
            return await ok_link_fetch(url)

        live.understander = FakeUnderstander(understand)
        clock = WatchingClock(lambda seconds: events.append("pause"))
        put_photos(cli.root)

        cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            wiring=wiring_over(live, fetch),
            clock=clock,
        )

        first_pause = events.index("pause")
        before = events[:first_pause]
        # The first query's search, its re-search after the answer and its eight links come
        # before the first pause; the next query's search comes only after it.
        assert before.count("search") == 2
        assert before.count("link") == 8
        assert events[first_pause + 1] == "search"
