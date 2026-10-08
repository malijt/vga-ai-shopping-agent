"""A live run stops at the first query whose stores were all turned away, instead of grinding on.

Sending the other queries to stores that have just said "too many requests" only asks them again
and gets the same answer. The run stops, says which queries ran and which did not, how long to
wait, and that it must be repeated later. ``--keep-going`` overrides that. A mock or replay run
never stops: it contacts no store.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from eval.harness.errors import QueryNotReachedError, RecordingError
from eval.harness.links import LinkResult
from eval.harness.recording import MANIFEST_FILE, RecordingSession, ReplaySession
from eval.harness.runner import Pacing, QueryRun, run_queries
from eval.harness.runstore import LABELS_FILE, REPORT_FILE, load_run
from tests.factories import make_settings, make_store_report
from tests.fakes import FakeClock
from tests.harness.cli_support import Cli, put_photos, read_rows
from tests.harness.helpers import make_query, make_response
from tests.harness.live_parts import LiveParts, ok_link_fetch
from tests.harness.live_run_support import SteppedPipeline, stepped_wiring
from tests.harness.test_not_run import blocked, with_stores
from tests.harness.test_report import table_after
from vga.models import RunOverrides, SearchRequest, SearchResponse, StoreReport, StoreStatus
from vga.settings import Settings

RUN = "eval/results/run-1"
THIRD = "q04_outfit_palazzo_top"
RAN = ["q01_product_gown", "q02_product_abaya", "q03_product_skinny_jeans"]
NOT_SENT = [
    "q05_outfit_dress_heels",
    "q06_text_blazer_budget",
    "q07_text_arabic_shirt",
    "q08_text_wide_leg_jeans",
    "q09_photo_text_gown_green",
    "q10_photo_text_jeans_black",
]


def turned_away(position: int) -> SearchResponse | None:
    """The answer for the query at ``position`` (0 is the first): every store blocked."""
    return with_stores(blocked("alpha"), blocked("beta")) if position == 3 else None


def record(
    cli: Cli,
    *extra: str,
    clock: FakeClock | None = None,
    pipelines: list[SteppedPipeline] | None = None,
    command: str = "--record",
) -> int:
    put_photos(cli.root)
    return cli.run(
        command,
        str(cli.root / RUN / "recording"),
        "--pause",
        "0",
        "--links",
        "none",
        *extra,
        wiring=stepped_wiring(
            LiveParts(),
            answer=turned_away,
            pipelines=pipelines,
        ),
        clock=clock,
    )


class TestTheRunStops:
    def test_the_queries_after_the_throttled_one_are_not_sent(self, cli: Cli) -> None:
        pipelines: list[SteppedPipeline] = []

        assert record(cli, pipelines=pipelines) == 0, cli.errors

        assert pipelines[0].queries_started == 4  # q01 to q03, and the one that was turned away

    def test_it_says_where_it_stopped_and_why(self, cli: Cli) -> None:
        record(cli)

        assert (
            f"Stopped after {THIRD}: every store that could be asked was blocked or in cooldown, "
            "so the other 6 queries were not sent (--keep-going sends them anyway)."
        ) in cli.printed

    def test_it_lists_what_ran_and_what_did_not(self, cli: Cli) -> None:
        record(cli)

        assert f"Ran (3): {', '.join(RAN)}." in cli.printed
        assert (
            f"Did not run (7): {THIRD} (the stores were blocked or in cooldown), "
            f"{', '.join(NOT_SENT)} (not sent)."
        ) in cli.printed

    def test_it_says_how_long_to_wait_and_that_the_run_must_be_repeated(self, cli: Cli) -> None:
        record(cli)

        assert (
            "A store that turns a search away is left alone for 15 minutes (the store_cooldown_s "
            "setting). The responses do not say how much of that is left, and a new run does not "
            "remember it, so wait at least that long."
        ) in cli.printed
        assert (
            "This run is incomplete and must be repeated later for the queries that did not run:"
            in (cli.printed)
        )

    def test_it_prints_the_command_to_finish_the_run(self, cli: Cli) -> None:
        record(cli, "--wiring", "tests.harness.live_parts:fake_wiring")

        recording = cli.root / RUN / "recording"
        only = ",".join([THIRD, *NOT_SENT])
        assert (
            f"  uv run --group ml python -m eval.harness --record {recording} --only {only} "
            "--wiring tests.harness.live_parts:fake_wiring"
        ) in cli.printed

    def test_the_verdict_is_incomplete_and_says_how_many_ran(self, cli: Cli) -> None:
        record(cli)

        assert (
            "Verdict: INCOMPLETE. 3 of 10 queries ran and 7 did not (1 because the stores were "
            "blocked or in cooldown, 6 because the run stopped before sending them)."
        ) in cli.printed
        assert "3 of 10 queries answered (7 not run)" in cli.printed

    def test_it_does_not_wait_after_the_query_that_stopped_it(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, "--pause", "30", clock=clock)

        assert clock.sleeps == [30.0] * 3  # before q02, q03 and q04; nothing after q04

    def test_the_report_lists_the_queries_and_what_to_do(self, cli: Cli) -> None:
        record(cli)

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert (
            f"Ran (3): {', '.join(RAN)}. Did not run (7): {THIRD}, {', '.join(NOT_SENT)}." in text
        )
        assert "left alone for 15 minutes" in text
        assert "must be repeated later" in text
        assert f"`--only {THIRD},{','.join(NOT_SENT)}`" in text
        rows = {row[0]: row for row in table_after(text, "## Queries not run")[1:]}
        assert "Not sent: the run stopped after" in rows[NOT_SENT[0]][1]
        assert THIRD in rows[NOT_SENT[0]][1]

    def test_the_run_folder_holds_all_ten_queries_the_unsent_ones_marked(self, cli: Cli) -> None:
        record(cli)

        saved = load_run(cli.root / RUN)
        assert [run.query.id for run in saved.runs] == [*RAN, THIRD, *NOT_SENT]
        kinds = {run.query.id: run.not_run.kind if run.not_run else None for run in saved.runs}
        assert kinds[RAN[0]] is None
        assert kinds[THIRD] == "stores_unavailable"
        assert {kinds[query_id] for query_id in NOT_SENT} == {"not_sent"}
        assert saved.runs[-1].response is None
        assert saved.runs[-1].failure is None

    def test_the_labelling_sheet_has_rows_for_the_queries_that_ran_only(self, cli: Cli) -> None:
        record(cli)

        queries = {row["query_id"] for row in read_rows(cli.root / RUN / LABELS_FILE)}
        assert queries == set(RAN)

    def test_the_queries_that_ran_have_their_links_checked(self, cli: Cli) -> None:
        asked: list[str] = []

        async def fetch(url: str) -> LinkResult:
            asked.append(url)
            return await ok_link_fetch(url)

        put_photos(cli.root)
        cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            "--pause",
            "0",
            wiring=stepped_wiring(LiveParts(), answer=turned_away, fetch=fetch),
        )

        assert len(asked) == 8
        # Every query that ran has its checks (the toy products repeat, so only q01 fetched them).
        assert set(load_run(cli.root / RUN).links) == set(RAN)


class TestKeepGoing:
    def test_it_sends_every_query_anyway(self, cli: Cli) -> None:
        pipelines: list[SteppedPipeline] = []

        record(cli, "--keep-going", pipelines=pipelines)

        assert pipelines[0].queries_started == 10

    def test_it_does_not_say_it_stopped_but_still_says_what_did_not_run(self, cli: Cli) -> None:
        record(cli, "--keep-going")

        assert "Stopped after" not in cli.printed
        assert f"Did not run (1): {THIRD} (the stores were blocked or in cooldown)." in cli.printed
        assert "must be repeated later" in cli.printed
        assert "Verdict: INCOMPLETE. 9 of 10 queries ran and 1 did not" in cli.printed

    def test_it_keeps_the_pause_between_all_the_queries(self, cli: Cli) -> None:
        clock = FakeClock()

        record(cli, "--keep-going", "--pause", "30", clock=clock)

        assert clock.sleeps == [30.0] * 9


class TestOnlyTheRightThingsStopTheRun:
    def test_a_query_that_got_results_from_some_stores_does_not_stop_it(self, cli: Cli) -> None:
        pipelines: list[SteppedPipeline] = []
        put_photos(cli.root)

        cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            "--pause",
            "0",
            "--links",
            "none",
            wiring=stepped_wiring(
                LiveParts(),
                answer=lambda position: (
                    make_response(skipped=["x", "y"]) if position == 3 else None
                ),
                pipelines=pipelines,
            ),
        )

        assert pipelines[0].queries_started == 10
        assert "Stopped after" not in cli.printed

    def test_a_query_that_failed_for_another_reason_does_not_stop_it(self, cli: Cli) -> None:
        pipelines: list[SteppedPipeline] = []
        put_photos(cli.root)

        cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            "--pause",
            "0",
            "--links",
            "none",
            wiring=stepped_wiring(
                LiveParts(),
                answer=lambda position: (
                    with_stores(blocked("a"), _timeout("b")) if position == 3 else None
                ),
                pipelines=pipelines,
            ),
        )

        assert pipelines[0].queries_started == 10
        assert "Stopped after" not in cli.printed

    def test_a_mock_run_never_stops_and_never_mentions_it(self, cli: Cli) -> None:
        cli.run("--mock")

        assert "Stopped after" not in cli.printed
        assert "must be repeated later" not in cli.printed


def _timeout(store_id: str) -> StoreReport:
    return make_store_report(StoreStatus.TIMEOUT, store_id=store_id)


class TestTheRunnerAlone:
    async def test_it_stops_after_the_throttled_query_and_returns_one_run_for_every_query(
        self,
    ) -> None:
        said: list[str] = []
        queries = [make_query(f"q0{n}_text") for n in range(1, 6)]
        pipeline = SteppedPipelineAnswers(
            [make_response(), with_stores(blocked("a")), make_response()]
        )

        runs = await run_queries(
            queries,
            pipeline,
            make_settings(),
            clock=FakeClock(),
            load_image=lambda query: None,
            pacing=Pacing(pause_s=0.0, say=said.append, stop_when_throttled=True),
        )

        assert [run.query.id for run in runs] == [query.id for query in queries]
        assert [run.not_run.kind if run.not_run else None for run in runs] == [
            None,
            "stores_unavailable",
            "not_sent",
            "not_sent",
            "not_sent",
        ]
        assert pipeline.calls == 2
        assert "q02_text" in (runs[2].not_run.reason if runs[2].not_run else "")

    async def test_the_after_query_hook_sees_the_query_that_stopped_it(self) -> None:
        seen: list[list[str]] = []

        async def after(runs: Sequence[QueryRun]) -> None:
            seen.append([run.query.id for run in runs])

        await run_queries(
            [make_query("q01_a"), make_query("q02_b"), make_query("q03_c")],
            SteppedPipelineAnswers([with_stores(blocked("a"))]),
            make_settings(),
            clock=FakeClock(),
            load_image=lambda query: None,
            pacing=Pacing(stop_when_throttled=True),
            after_query=after,
        )

        assert seen == [["q01_a"]]

    async def test_without_the_stop_every_query_is_sent(self) -> None:
        pipeline = SteppedPipelineAnswers([with_stores(blocked("a"))] * 3)

        runs = await run_queries(
            [make_query("q01_a"), make_query("q02_b"), make_query("q03_c")],
            pipeline,
            make_settings(),
            clock=FakeClock(),
            load_image=lambda query: None,
            pacing=Pacing(stop_when_throttled=False),
        )

        assert pipeline.calls == 3
        assert all(run.not_run is not None for run in runs)


class SteppedPipelineAnswers:
    """A pipeline that gives the answers it was given, one per call."""

    def __init__(self, answers: list[SearchResponse]) -> None:
        self._answers = iter(answers)
        self.calls = 0

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: object = None,
    ) -> SearchResponse:
        self.calls += 1
        return next(self._answers)


class TestTheRecordingKnowsWhatWasPlanned:
    def test_the_manifest_lists_the_queries_the_run_set_out_to_send(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec", planned=["q01", "q02", "q03"])
        session.begin_query("q01")
        session.end_query("q01", duration_ms=1000.0)

        manifest = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text(encoding="utf-8"))

        assert manifest["planned"] == ["q01", "q02", "q03"]
        assert list(manifest["queries"]) == ["q01"]

    def test_a_query_the_run_never_reached_is_not_reached_not_missing(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec", planned=["q01", "q02"])
        session.begin_query("q01")
        session.end_query("q01", duration_ms=1000.0)
        replay = ReplaySession(tmp_path / "rec")

        with pytest.raises(QueryNotReachedError, match="stopped before this query"):
            replay.begin_query("q02")

    def test_a_query_nobody_planned_is_still_an_error_of_the_recording(
        self, tmp_path: Path
    ) -> None:
        session = RecordingSession(tmp_path / "rec", planned=["q01"])
        session.begin_query("q01")
        session.end_query("q01", duration_ms=1000.0)
        replay = ReplaySession(tmp_path / "rec")

        with pytest.raises(RecordingError) as caught:
            replay.begin_query("q99")

        assert not isinstance(caught.value, QueryNotReachedError)

    def test_a_recording_made_before_this_change_still_replays(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec")
        session.begin_query("q01")
        session.end_query("q01", duration_ms=1000.0)

        manifest = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text(encoding="utf-8"))

        assert "planned" not in manifest
        ReplaySession(tmp_path / "rec").begin_query("q01")


class TestReplayOfAStoppedRun:
    def test_the_queries_the_live_run_never_sent_are_not_run_not_failed(self, cli: Cli) -> None:
        record(cli)

        code = cli.run(
            "--replay",
            str(cli.root / RUN / "recording"),
            wiring=stepped_wiring(LiveParts(), answer=turned_away),
        )

        assert code == 0, cli.errors
        replay_output = cli.printed.split("Rescored")[0].rsplit("Stores in this run", 1)[-1]
        assert "FAILED" not in replay_output
        saved = load_run(cli.root / "eval" / "results" / "replay")
        kinds = {run.query.id: run.not_run.kind if run.not_run else None for run in saved.runs}
        assert [kinds[query_id] for query_id in NOT_SENT] == ["not_sent"] * 6
        assert kinds[THIRD] == "stores_unavailable"
        assert "Verdict: INCOMPLETE. 3 of 10 queries ran and 7 did not" in cli.printed

    def test_a_replay_does_not_stop_either(self, cli: Cli) -> None:
        record(cli, "--keep-going")

        cli.run(
            "--replay",
            str(cli.root / RUN / "recording"),
            wiring=stepped_wiring(LiveParts(), answer=turned_away),
        )

        assert "Stopped after" not in cli.printed.rsplit("Replay", 1)[-1]
        saved = load_run(cli.root / "eval" / "results" / "replay")
        assert sum(1 for run in saved.runs if run.not_run) == 1


class TestAnInterruptedRunCanBeFinishedToo:
    def test_the_queries_not_reached_are_saved_as_not_sent_yet(self, cli: Cli) -> None:
        calls = 0

        async def fetch(url: str) -> LinkResult:
            nonlocal calls
            calls += 1
            if calls == 4:
                raise KeyboardInterrupt
            return await ok_link_fetch(url)

        put_photos(cli.root)

        with pytest.raises(KeyboardInterrupt):
            cli.run(
                "--record",
                str(cli.root / RUN / "recording"),
                "--pause",
                "0",
                wiring=stepped_wiring(LiveParts(), fetch=fetch),
            )

        saved = load_run(cli.root / RUN)
        assert len(saved.runs) == 10
        assert saved.runs[0].response is not None
        later = list(saved.runs[1:])
        assert all(run.not_run is not None and run.not_run.kind == "not_sent" for run in later)
        assert "had not reached this query" in (later[0].not_run.reason if later[0].not_run else "")
        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert "Verdict: INCOMPLETE" in text
