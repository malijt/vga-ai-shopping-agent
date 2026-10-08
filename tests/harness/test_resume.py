"""``--only`` finishes a live run that was stopped or interrupted, without sending the finished
queries again.

The first session here is a run stopped at its fourth query (every store blocked): three queries
finished, the fourth was turned away and the other six were never sent. The second session runs the
rest into the same folder and the same recording. Everything is the command line over the toy
pipeline and fakes: no network, no OpenAI, no real waiting.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from eval.harness.errors import RecordingError
from eval.harness.links import LinkResult
from eval.harness.recording import MANIFEST_FILE, RecordingSession, ReplaySession
from eval.harness.report import escape
from eval.harness.runstore import LABELS_FILE, REPORT_FILE, load_run
from tests.fakes import FakeClock
from tests.harness.cli_support import Cli, fill_sheet, put_photos, read_rows
from tests.harness.live_parts import LiveParts, ok_link_fetch
from tests.harness.live_run_support import SteppedPipeline, stepped_wiring
from tests.harness.test_not_run import blocked, with_stores
from tests.harness.test_report import table_after
from vga.models import SearchResponse

RUN = "eval/results/run-1"
FIRST_DAY = date(2026, 10, 8)
LATER_DAY = date(2026, 10, 9)
ALL = [
    "q01_product_gown",
    "q02_product_abaya",
    "q03_product_skinny_jeans",
    "q04_outfit_palazzo_top",
    "q05_outfit_dress_heels",
    "q06_text_blazer_budget",
    "q07_text_arabic_shirt",
    "q08_text_wide_leg_jeans",
    "q09_photo_text_gown_green",
    "q10_photo_text_jeans_black",
]
DONE = ALL[:3]
REST = ALL[3:]


def turned_away_at(position: int) -> Callable[[int], SearchResponse | None]:
    def answer(at: int) -> SearchResponse | None:
        return with_stores(blocked("alpha"), blocked("beta")) if at == position else None

    return answer


def recording(cli: Cli) -> Path:
    return cli.root / RUN / "recording"


def first_session(cli: Cli, *extra: str, links: str = "none", **wiring: object) -> int:
    """A run stopped at its fourth query: three finished, one turned away, six never sent."""
    put_photos(cli.root)
    return cli.run(
        "--record",
        str(recording(cli)),
        "--pause",
        "0",
        "--links",
        links,
        *extra,
        wiring=stepped_wiring(LiveParts(), answer=turned_away_at(3), **wiring),  # type: ignore[arg-type]
        today=FIRST_DAY,
    )


def second_session(
    root: Path,
    only: str,
    *extra: str,
    answer: object = None,
    pipelines: list[SteppedPipeline] | None = None,
    clock: FakeClock | None = None,
    **wiring: object,
) -> Cli:
    """Finish the run: a new command in the same repository."""
    cli = Cli(root)
    cli.run(
        "--record",
        str(root / RUN / "recording"),
        "--only",
        only,
        "--pause",
        "0",
        *extra,
        wiring=stepped_wiring(LiveParts(), answer=answer, pipelines=pipelines, **wiring),  # type: ignore[arg-type]
        clock=clock,
        today=LATER_DAY,
    )
    return cli


def rest() -> str:
    return ",".join(REST)


class TestFinishingAStoppedRun:
    def test_only_the_named_queries_are_sent(self, cli: Cli) -> None:
        first_session(cli)
        pipelines: list[SteppedPipeline] = []

        second = second_session(cli.root, rest(), "--links", "none", pipelines=pipelines)

        assert second.errors == ""
        assert pipelines[0].queries_started == 7  # q04 to q10; q01 to q03 are not sent again

    def test_it_says_what_it_is_doing(self, cli: Cli) -> None:
        first_session(cli)

        second = second_session(cli.root, rest(), "--links", "none")

        assert (
            f"Continuing run-1: this session runs {', '.join(REST)}; the other 3 queries are "
            "left as they are and not sent again."
        ) in second.printed

    def test_the_finished_queries_are_left_exactly_as_they_were(self, cli: Cli) -> None:
        first_session(cli)
        responses = cli.root / RUN / "responses"
        before = {name: (responses / f"{name}.json").read_bytes() for name in DONE}
        recorded = {name: (recording(cli) / f"{name}.json").read_bytes() for name in DONE}

        second_session(cli.root, rest(), "--links", "none")

        assert {name: (responses / f"{name}.json").read_bytes() for name in DONE} == before
        assert {name: (recording(cli) / f"{name}.json").read_bytes() for name in DONE} == recorded

    def test_the_folder_then_holds_all_ten_queries_each_with_a_result(self, cli: Cli) -> None:
        first_session(cli)

        second_session(cli.root, rest(), "--links", "none")

        saved = load_run(cli.root / RUN)
        assert [run.query.id for run in saved.runs] == ALL
        assert all(run.not_run is None and run.response is not None for run in saved.runs)
        assert len(list((cli.root / RUN / "responses").glob("*.json"))) == 10

    def test_the_report_is_rebuilt_over_all_ten_and_is_no_longer_incomplete(self, cli: Cli) -> None:
        first_session(cli)

        second = second_session(cli.root, rest(), "--links", "none")

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert [row[0] for row in table_after(text, "## Results")[1:]] == ALL
        assert "not run" not in text
        assert "Queries not run" not in text
        assert "INCOMPLETE" not in text
        assert "Verdict: INCOMPLETE" not in second.printed
        assert "10 of 10 queries answered" in second.printed

    def test_the_labelling_sheet_then_has_rows_for_all_ten(self, cli: Cli) -> None:
        first_session(cli)

        second_session(cli.root, rest(), "--links", "none")

        assert {row["query_id"] for row in read_rows(cli.root / RUN / LABELS_FILE)} == set(ALL)

    def test_the_run_keeps_the_date_it_was_started_on(self, cli: Cli) -> None:
        first_session(cli)

        second_session(cli.root, rest(), "--links", "none")

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert "| Date | 2026-10-08 |" in text
        assert load_run(cli.root / RUN).meta.date == FIRST_DAY

    def test_the_report_says_how_each_session_was_made(self, cli: Cli) -> None:
        first_session(cli, "--pause", "12")  # the helper's own --pause 0 comes first; this wins
        cli_2 = Cli(cli.root)
        cli_2.run(
            "--record",
            str(recording(cli)),
            "--only",
            rest(),
            "--links",
            "none",
            "--pause",
            "5",
            wiring=stepped_wiring(LiveParts()),
            today=LATER_DAY,
        )

        notes = load_run(cli.root / RUN).meta.session_notes

        assert len(notes) == 2
        assert notes[0].startswith("Session 1 (2026-10-08): paused 12 s between queries")
        assert notes[1].startswith(f"Session 2 (2026-10-09, ran {', '.join(REST)}): paused 5 s")
        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert escape(notes[0]) in text
        assert escape(notes[1]) in text

    def test_the_second_session_pauses_between_its_own_queries_only(self, cli: Cli) -> None:
        first_session(cli)
        clock = FakeClock()

        cli_2 = Cli(cli.root)
        cli_2.run(
            "--record",
            str(recording(cli)),
            "--only",
            rest(),
            "--links",
            "none",
            "--pause",
            "20",
            wiring=stepped_wiring(LiveParts()),
            clock=clock,
        )

        assert clock.sleeps == [20.0] * 6  # seven queries, six gaps; none for the finished three

    def test_the_recording_replays_as_one_run(self, cli: Cli) -> None:
        first_session(cli)
        second_session(cli.root, rest(), "--links", "none")
        replay = Cli(cli.root)

        code = replay.run(
            "--replay", str(recording(cli)), wiring=stepped_wiring(LiveParts()), today=LATER_DAY
        )

        assert code == 0, replay.errors
        assert "NOT RUN" not in replay.printed
        assert "FAILED" not in replay.printed
        assert "10 of 10 queries answered" in replay.printed
        saved = load_run(cli.root / "eval" / "results" / "replay")
        assert [run.query.id for run in saved.runs] == ALL
        assert all(run.not_run is None for run in saved.runs)

    def test_the_query_that_was_turned_away_has_its_new_recording(self, cli: Cli) -> None:
        first_session(cli)
        stopped = json.loads(
            (recording(cli) / "q04_outfit_palazzo_top.json").read_text(encoding="utf-8")
        )
        assert stopped["search"] == []  # the stores were turned away before any call was recorded

        second_session(cli.root, rest(), "--links", "none")

        fresh = json.loads(
            (recording(cli) / "q04_outfit_palazzo_top.json").read_text(encoding="utf-8")
        )
        assert fresh["search"]  # the recording of the query that finally ran

    def test_the_manifest_keeps_the_plan_and_gains_the_queries(self, cli: Cli) -> None:
        first_session(cli)
        before = json.loads((recording(cli) / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert list(before["queries"]) == ALL[:4]

        second_session(cli.root, rest(), "--links", "none")

        after = json.loads((recording(cli) / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert list(after["queries"]) == [*ALL[:3], *REST]
        assert after["planned"] == ALL

    def test_a_part_of_the_rest_leaves_the_report_incomplete_for_what_is_still_missing(
        self, cli: Cli
    ) -> None:
        first_session(cli)

        second = second_session(
            cli.root, "q04_outfit_palazzo_top,q05_outfit_dress_heels", "--links", "none"
        )

        assert "Ran (5):" in second.printed
        assert "Verdict: INCOMPLETE. 5 of 10 queries ran and 5 did not" in second.printed
        assert f"--only {','.join(ALL[5:])}" in second.printed
        assert "Stopped after" not in second.printed  # nothing was turned away this time


class TestFinishingAnInterruptedRun:
    def test_what_was_saved_is_enough_to_finish_it(self, cli: Cli) -> None:
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
                str(recording(cli)),
                "--pause",
                "0",
                wiring=stepped_wiring(LiveParts(), fetch=fetch),
                today=FIRST_DAY,
            )
        saved = load_run(cli.root / RUN)
        unreached = [run.query.id for run in saved.runs if run.not_run is not None]
        assert unreached == ALL[1:]

        second = second_session(cli.root, ",".join(unreached), "--links", "all")

        assert second.errors == ""
        assert all(run.not_run is None for run in load_run(cli.root / RUN).runs)


class TestTheLinksOfTheEarlierSession:
    def test_they_are_kept_and_their_urls_are_not_asked_again(self, cli: Cli) -> None:
        asked: list[str] = []

        async def fetch(url: str) -> LinkResult:
            asked.append(url)
            return await ok_link_fetch(url)

        first_session(cli, links="all", fetch=fetch)
        asked_in_the_first = len(asked)
        assert asked_in_the_first == 8

        second_session(cli.root, rest(), fetch=fetch)

        assert len(asked) == asked_in_the_first  # the toy products repeat; none is asked again
        saved = load_run(cli.root / RUN)
        assert set(saved.links) == set(ALL) - {"q04_outfit_palazzo_top"} | {
            "q04_outfit_palazzo_top"
        }
        assert saved.meta.links.value == "all"

    def test_a_link_a_store_turned_away_is_asked_again(self, cli: Cli) -> None:
        asked: list[str] = []
        first_time = True

        async def fetch(url: str) -> LinkResult:
            asked.append(url)
            if first_time:
                return LinkResult(url=url, error="store_blocked (HTTP 429)", throttled=True)
            return await ok_link_fetch(url)

        first_session(cli, links="all", fetch=fetch)
        first_time = False
        count = len(asked)

        second_session(cli.root, rest(), fetch=fetch)

        assert len(asked) > count  # nothing had been looked at, so the second session looks


class TestWhatItRefuses:
    def test_a_query_that_already_has_a_result_is_not_sent_again(self, cli: Cli) -> None:
        first_session(cli)
        pipelines: list[SteppedPipeline] = []

        second = second_session(
            cli.root, "q02_product_abaya", "--links", "none", pipelines=pipelines
        )

        assert "q02_product_abaya" in second.errors
        assert "already have a result" in second.errors
        assert "--overwrite" in second.errors
        assert pipelines == []  # nothing was built, nothing was sent

    def test_overwrite_runs_it_again_and_replaces_its_result_and_recording(self, cli: Cli) -> None:
        first_session(cli)
        before = (cli.root / RUN / "responses" / "q02_product_abaya.json").read_bytes()
        pipelines: list[SteppedPipeline] = []

        second = second_session(
            cli.root,
            "q02_product_abaya",
            "--links",
            "none",
            "--overwrite",
            pipelines=pipelines,
        )

        assert second.errors == ""
        assert pipelines[0].queries_started == 1
        after = (cli.root / RUN / "responses" / "q02_product_abaya.json").read_bytes()
        assert load_run(cli.root / RUN).runs[1].query.id == "q02_product_abaya"
        assert after != before  # a new request id, a new answer

    def test_an_unknown_query_is_named_with_the_ones_that_exist(self, cli: Cli) -> None:
        first_session(cli)

        second = second_session(cli.root, "q99_nothing", "--links", "none")

        assert "q99_nothing" in second.errors
        assert "q01_product_gown" in second.errors

    def test_an_empty_entry_is_refused(self, cli: Cli) -> None:
        first_session(cli)

        second = second_session(cli.root, "q05_outfit_dress_heels,", "--links", "none")

        assert "separated by commas" in second.errors

    def test_it_needs_a_live_run(self, cli: Cli) -> None:
        mock = cli.run("--mock", "--only", "q01_product_gown")

        assert mock == 2
        assert "--record" in cli.errors

    def test_it_needs_a_folder_that_holds_a_run(self, cli: Cli) -> None:
        put_photos(cli.root)

        second = Cli(cli.root)
        code = second.run(
            "--record",
            str(cli.root / "elsewhere" / "recording"),
            "--only",
            "q01_product_gown",
            wiring=stepped_wiring(LiveParts()),
        )

        assert code == 2
        assert "nothing to continue" in second.errors

    def test_a_mock_result_cannot_be_finished(self, cli: Cli) -> None:
        cli.run("--mock")
        put_photos(cli.root)

        second = Cli(cli.root)
        code = second.run(
            "--record",
            str(cli.root / "rec"),
            "--out",
            str(cli.root / "eval" / "results" / "mock"),
            "--only",
            "q01_product_gown",
            wiring=stepped_wiring(LiveParts()),
        )

        assert code == 2
        assert "is a mock result" in second.errors

    def test_a_run_is_finished_the_way_it_was_started_as_to_links(self, cli: Cli) -> None:
        first_session(cli, links="none")

        second = second_session(cli.root, rest(), "--links", "all")

        assert "--links none" in second.errors

    def test_a_run_is_finished_with_the_same_queries_file(self, cli: Cli, tmp_path: Path) -> None:
        first_session(cli)
        other = tmp_path / "other_queries.yaml"
        other.write_text(
            "queries:\n  - id: x01_text\n    type: text\n    text: black blazer\n"
            "    image: null\n    notes: another set\n",
            encoding="utf-8",
        )

        second = second_session(cli.root, "x01_text", "--queries", str(other))

        assert "acceptance queries, not the extra set" in second.errors


class TestALabelledSheetIsNeverReplaced:
    def test_the_new_sheet_goes_beside_it(self, cli: Cli) -> None:
        first_session(cli)
        sheet = cli.root / RUN / LABELS_FILE
        fill_sheet(sheet, good_queries=3)
        labelled = sheet.read_bytes()

        second = second_session(cli.root, rest(), "--links", "none")

        assert sheet.read_bytes() == labelled
        assert (cli.root / RUN / "labels.new.csv").is_file()
        assert "labels.new.csv" in second.printed
        assert {row["query_id"] for row in read_rows(cli.root / RUN / "labels.new.csv")} == set(ALL)


class TestStoppedAgain:
    def test_a_second_session_that_is_turned_away_stops_and_says_what_is_still_missing(
        self, cli: Cli
    ) -> None:
        first_session(cli)
        pipelines: list[SteppedPipeline] = []

        second = second_session(
            cli.root,
            rest(),
            "--links",
            "none",
            answer=turned_away_at(0),
            pipelines=pipelines,
        )

        assert pipelines[0].queries_started == 1
        assert "Stopped after q04_outfit_palazzo_top" in second.printed
        assert f"Ran (3): {', '.join(DONE)}." in second.printed
        assert f"--only {rest()}" in second.printed
        saved = load_run(cli.root / RUN)
        assert [run.not_run.kind if run.not_run else None for run in saved.runs] == [
            None,
            None,
            None,
            "stores_unavailable",
            *["not_sent"] * 6,
        ]
        assert "stopped after q04_outfit_palazzo_top" in (
            saved.runs[4].not_run.reason if saved.runs[4].not_run else ""
        )


class TestTheRecordingSession:
    def test_it_keeps_the_earlier_queries_and_adds_the_new_ones(self, tmp_path: Path) -> None:
        first = RecordingSession(tmp_path / "rec", planned=["q01", "q02", "q03"])
        for query_id in ("q01", "q02"):
            first.begin_query(query_id)
            first.end_query(query_id, duration_ms=1000.0)

        more = RecordingSession(tmp_path / "rec", planned=["q01", "q02", "q03", "q04"], resume=True)
        more.begin_query("q03")
        more.end_query("q03", duration_ms=2000.0)

        manifest = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert list(manifest["queries"]) == ["q01", "q02", "q03"]
        assert manifest["queries"]["q01"]["live_duration_ms"] == 1000.0
        assert manifest["planned"] == ["q01", "q02", "q03", "q04"]
        replay = ReplaySession(tmp_path / "rec")
        replay.begin_query("q03")

    def test_a_query_recorded_again_replaces_its_earlier_recording(self, tmp_path: Path) -> None:
        first = RecordingSession(tmp_path / "rec")
        first.begin_query("q01")
        first.end_query("q01", duration_ms=1000.0)

        again = RecordingSession(tmp_path / "rec", resume=True)
        again.begin_query("q01")
        again.end_query("q01", duration_ms=5000.0)

        manifest = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert manifest["queries"]["q01"]["live_duration_ms"] == 5000.0

    def test_without_a_recording_there_is_nothing_to_continue(self, tmp_path: Path) -> None:
        with pytest.raises(RecordingError, match="manifest"):
            RecordingSession(tmp_path / "rec", resume=True)

    def test_a_fresh_session_still_refuses_a_folder_that_holds_a_recording(
        self, tmp_path: Path
    ) -> None:
        first = RecordingSession(tmp_path / "rec")
        first.begin_query("q01")
        first.end_query("q01", duration_ms=1000.0)

        with pytest.raises(RecordingError, match="already holds a recording"):
            RecordingSession(tmp_path / "rec")
