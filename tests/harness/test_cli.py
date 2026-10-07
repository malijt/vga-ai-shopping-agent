"""The command line, end to end with the fakes: mock, record, replay, rescore and labelling.

Nothing here touches the network or OpenAI, and nothing waits on real time. The repository root
is a temporary folder, so no test writes into ``eval/results/`` of the real checkout.
"""

import asyncio
import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest

from eval.harness.cli import _next_run_number, main
from eval.harness.errors import WiringError
from eval.harness.links import LinkResult
from eval.harness.queries import QUERIES_PATH, load_queries
from eval.harness.runstore import LABELS_FILE, REPORT_FILE, RUN_FILE, load_run
from eval.harness.wiring import Wiring, WiringFactory, load_wiring_factory
from tests.factories import make_settings
from tests.fakes import FakeClock, FakeUnderstander
from tests.harness.helpers import ToyPipeline
from tests.harness.live_parts import LiveParts, make_stores, ok_link_fetch, understand_for
from vga.models import SearchRequest, UnderstandResult
from vga.settings import Settings

TODAY = date(2026, 10, 7)


class Cli:
    """Runs ``main`` against a temporary repository root and keeps what it printed."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run(self, *argv: str, wiring: WiringFactory | None = None) -> int:
        return main(
            list(argv),
            wiring_factory=wiring,
            settings=make_settings(),
            clock=FakeClock(),
            today=lambda: TODAY,
            root=self.root,
            stdout=self.out,
            stderr=self.err,
        )

    @property
    def printed(self) -> str:
        return self.out.getvalue()

    @property
    def errors(self) -> str:
        return self.err.getvalue()


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(tmp_path)


def put_photos(root: Path) -> None:
    """The five private photos, as 1-byte stand-ins (the fake pipeline ignores their content)."""
    for query in load_queries(QUERIES_PATH, require_images=False):
        if query.image:
            target = root / query.image
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"photo")


def wiring_over(live: LiveParts, fetch: object = ok_link_fetch) -> WiringFactory:
    stores = make_stores()

    def factory(settings: Settings) -> Wiring:
        return Wiring(
            pipeline_factory=lambda u, s, r: ToyPipeline(u, s, r, stores),
            stores=stores,
            link_fetch=fetch,  # type: ignore[arg-type]
            build_boundaries=live.boundaries,
        )

    return factory


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fill_sheet(path: Path, good_queries: int) -> None:
    """Label every result of the first ``good_queries`` queries good and the rest not good."""
    ids = [query.id for query in load_queries(QUERIES_PATH, require_images=False)]
    rows = read_rows(path)
    for row in rows:
        row["label"] = "1" if ids.index(row["query_id"]) < good_queries else "0"
    write_rows(path, rows)


class TestMock:
    def test_a_mock_run_saves_ten_responses_a_report_and_a_blank_labelling_sheet(
        self, cli: Cli
    ) -> None:
        assert cli.run("--mock") == 0

        out = cli.root / "eval" / "results" / "mock"
        assert len(list((out / "responses").glob("*.json"))) == 10
        assert (out / REPORT_FILE).is_file()
        assert (out / RUN_FILE).is_file()
        sheet = read_rows(out / LABELS_FILE)
        assert len(sheet) == 190  # the sample has two garments: 10 + 9 rows for each of 10 queries
        assert {row["label"] for row in sheet} == {""}

    def test_it_runs_without_the_private_photos(self, cli: Cli) -> None:
        assert not (cli.root / "eval" / "data").exists()

        assert cli.run("--mock") == 0

    def test_it_says_what_it_did_and_that_nothing_is_decided_yet(self, cli: Cli) -> None:
        cli.run("--mock")

        assert "q01_product_gown: 21 results in 5.5 s" in cli.printed
        assert "10 of 10 queries answered" in cli.printed
        assert "Labelling sheet:" in cli.printed
        assert "Verdict: PENDING" in cli.printed

    def test_the_report_is_a_mock_report_for_all_ten_queries(self, cli: Cli) -> None:
        cli.run("--mock")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert text.startswith("# Acceptance results: run mock")
        assert "2026-10-07" in text
        for query in load_queries(QUERIES_PATH, require_images=False):
            assert f"| {query.id} |" in text

    def test_running_mock_again_replaces_the_mock_folder_without_complaint(self, cli: Cli) -> None:
        assert cli.run("--mock") == 0
        assert cli.run("--mock") == 0

    def test_links_none_leaves_the_links_column_undecided(self, cli: Cli) -> None:
        cli.run("--mock", "--links", "none")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert "| not checked |" in text
        assert "Links were not checked in this run" in text

    def test_links_top10_checks_the_top_ten_of_each_garment_group_only(self, cli: Cli) -> None:
        cli.run("--mock", "--links", "top10")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert "19/19 (top 10 only; 21 results)" in text

    def test_a_run_number_can_be_given(self, cli: Cli) -> None:
        cli.run("--mock", "--run", "7")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert text.startswith("# Acceptance results: run 7")

    def test_an_explicit_output_folder_is_used(self, cli: Cli, tmp_path: Path) -> None:
        cli.run("--mock", "--out", str(tmp_path / "somewhere"))

        assert (tmp_path / "somewhere" / REPORT_FILE).is_file()


class TestLabellingThroughTheCommandLine:
    def labelled(self, cli: Cli, good_queries: int) -> Path:
        cli.run("--mock")
        run_dir = cli.root / "eval" / "results" / "mock"
        sheet = run_dir / LABELS_FILE
        fill_sheet(sheet, good_queries)
        return run_dir

    def verdict_line(self, run_dir: Path) -> str:
        text = (run_dir / REPORT_FILE).read_text(encoding="utf-8")
        return next(line for line in text.splitlines() if line.startswith("Verdict:"))

    def test_seven_queries_with_good_labels_pass_the_demo(self, cli: Cli) -> None:
        run_dir = self.labelled(cli, good_queries=7)

        assert cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE)) == 0

        assert self.verdict_line(run_dir) == "Verdict: PASS"
        assert "7 of 10 queries pass" in cli.printed

    def test_six_queries_with_good_labels_fail_it(self, cli: Cli) -> None:
        run_dir = self.labelled(cli, good_queries=6)

        cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE))

        assert self.verdict_line(run_dir) == "Verdict: FAIL"

    def test_the_report_then_shows_good_at_10_per_garment(self, cli: Cli) -> None:
        run_dir = self.labelled(cli, good_queries=10)

        cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE))

        text = (run_dir / REPORT_FILE).read_text(encoding="utf-8")
        assert "| q01_product_gown | 12 / 9 | 4 | 5.5 | 21/21 | 10 / 9 | yes |" in text

    def test_rescoring_changes_only_the_report_never_the_run_or_the_sheet(self, cli: Cli) -> None:
        run_dir = self.labelled(cli, good_queries=7)
        before = {name: (run_dir / name).read_bytes() for name in (RUN_FILE, LABELS_FILE)}

        cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE))

        assert {name: (run_dir / name).read_bytes() for name in before} == before

    def test_rescoring_without_labels_keeps_the_verdict_pending(self, cli: Cli) -> None:
        cli.run("--mock")

        cli.run("--rescore", str(cli.root / "eval" / "results" / "mock"))

        assert "Verdict: PENDING" in cli.printed

    def test_a_bad_label_stops_with_the_row_named_and_leaves_the_run_intact(self, cli: Cli) -> None:
        cli.run("--mock")
        run_dir = cli.root / "eval" / "results" / "mock"
        rows = read_rows(run_dir / LABELS_FILE)
        for row in rows:
            row["label"] = "1"
        rows[4]["label"] = "yes"
        write_rows(run_dir / LABELS_FILE, rows)

        code = cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE))

        assert code == 2
        assert "row 6" in cli.errors
        assert "label must be 1 or 0, got 'yes'" in cli.errors
        assert load_run(run_dir).runs  # the saved run is untouched

    def test_labels_given_with_a_fresh_run_are_scored_and_no_blank_sheet_is_written(
        self, cli: Cli, tmp_path: Path
    ) -> None:
        cli.run("--mock", "--out", str(tmp_path / "first"))
        filled = tmp_path / "filled.csv"
        filled.write_bytes((tmp_path / "first" / LABELS_FILE).read_bytes())
        fill_sheet(filled, good_queries=10)

        code = cli.run("--mock", "--out", str(tmp_path / "second"), "--labels", str(filled))

        assert code == 0
        assert not (tmp_path / "second" / LABELS_FILE).exists()
        assert "Verdict: PASS" in cli.printed

    def test_rescoring_a_folder_that_is_not_a_run_says_so(self, cli: Cli, tmp_path: Path) -> None:
        assert cli.run("--rescore", str(tmp_path / "nothing")) == 2
        assert "No saved run" in cli.errors


class TestWorkIsNotLost:
    """The expensive part of a run, and a person's labels and notes, survive mistakes."""

    def test_an_interrupt_during_the_link_phase_leaves_the_finished_run_on_disk(
        self, cli: Cli
    ) -> None:
        calls = 0

        async def fetch(url: str) -> LinkResult:
            nonlocal calls
            calls += 1
            if calls == 4:
                raise KeyboardInterrupt
            return await ok_link_fetch(url)

        put_photos(cli.root)
        run_dir = cli.root / "eval" / "results" / "run-1"

        with pytest.raises(KeyboardInterrupt):
            cli.run("--record", str(run_dir / "recording"), wiring=wiring_over(LiveParts(), fetch))

        assert len(list((run_dir / "responses").glob("*.json"))) == 10
        assert (run_dir / LABELS_FILE).is_file()
        text = (run_dir / REPORT_FILE).read_text(encoding="utf-8")
        assert "| not checked |" in text  # links had not run yet; the report says so
        assert len(load_run(run_dir).runs) == 10

    def test_rerunning_mock_never_replaces_a_labelling_sheet_that_has_labels(
        self, cli: Cli
    ) -> None:
        cli.run("--mock")
        run_dir = cli.root / "eval" / "results" / "mock"
        fill_sheet(run_dir / LABELS_FILE, good_queries=10)
        filled = (run_dir / LABELS_FILE).read_bytes()

        assert cli.run("--mock") == 0

        assert (run_dir / LABELS_FILE).read_bytes() == filled
        assert (run_dir / "labels.new.csv").is_file()
        assert "labels.new.csv" in cli.printed

    def test_rescoring_keeps_a_report_a_person_has_added_notes_to(self, cli: Cli) -> None:
        cli.run("--mock")
        run_dir = cli.root / "eval" / "results" / "mock"
        report = run_dir / REPORT_FILE
        report.write_text(
            report.read_text(encoding="utf-8") + "\nMy own note: the rubric changed.\n",
            encoding="utf-8",
        )
        fill_sheet(run_dir / LABELS_FILE, good_queries=10)

        cli.run("--rescore", str(run_dir), "--labels", str(run_dir / LABELS_FILE))

        backup = run_dir / "results.bak-1.md"
        assert "My own note: the rubric changed." in backup.read_text(encoding="utf-8")
        assert "My own note" not in report.read_text(encoding="utf-8")
        assert "results.bak-1.md" in cli.printed

    def test_rescoring_an_unchanged_report_makes_no_backup(self, cli: Cli) -> None:
        cli.run("--mock")
        run_dir = cli.root / "eval" / "results" / "mock"

        cli.run("--rescore", str(run_dir))

        assert not list(run_dir.glob("results.bak-*.md"))


class TestAMockOrReplayRunSaysSo:
    def test_the_printed_verdict_of_a_mock_run_carries_a_warning(self, cli: Cli) -> None:
        cli.run("--mock")

        assert "Mock run: the verdict below says nothing about the real app." in cli.printed

    def test_the_report_opens_with_a_banner(self, cli: Cli) -> None:
        cli.run("--mock")

        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert "\n> Mock run: a canned response, not a real result.\n" in text


class TestSafety:
    def test_a_folder_that_already_has_files_is_not_overwritten(
        self, cli: Cli, tmp_path: Path
    ) -> None:
        target = tmp_path / "keep"
        target.mkdir()
        (target / "precious.txt").write_text("a live run", encoding="utf-8")

        assert cli.run("--mock", "--out", str(target)) == 2

        assert "already holds files" in cli.errors
        assert [p.name for p in target.iterdir()] == ["precious.txt"]

    def test_overwrite_allows_it(self, cli: Cli, tmp_path: Path) -> None:
        target = tmp_path / "again"
        target.mkdir()
        (target / "old.txt").write_text("old", encoding="utf-8")

        assert cli.run("--mock", "--out", str(target), "--overwrite") == 0

    def test_one_mode_is_required(self, cli: Cli) -> None:
        with pytest.raises(SystemExit) as caught:
            cli.run()

        assert caught.value.code == 2

    def test_two_modes_at_once_are_refused(self, cli: Cli) -> None:
        with pytest.raises(SystemExit) as caught:
            cli.run("--mock", "--replay", "somewhere")

        assert caught.value.code == 2

    def test_a_bad_links_value_is_refused(self, cli: Cli) -> None:
        with pytest.raises(SystemExit):
            cli.run("--mock", "--links", "some")

    def test_record_without_the_real_application_explains_what_is_missing(self, cli: Cli) -> None:
        put_photos(cli.root)

        code = cli.run("--record", str(cli.root / "rec"))

        assert code == 2
        assert "--wiring" in cli.errors
        assert "--mock" in cli.errors
        assert not (cli.root / "rec").exists()

    def test_record_without_the_photos_names_them_before_spending_anything(self, cli: Cli) -> None:
        live = LiveParts()

        code = cli.run("--record", str(cli.root / "rec"), wiring=wiring_over(live))

        assert code == 2
        assert "eval/data/assets/private/dress_burgundy_gown.png" in cli.errors
        assert "eval/data/ASSETS.md" in cli.errors
        assert live.calls() == (0, 0, 0, 0)
        assert not (cli.root / "rec").exists()

    def test_a_replay_cannot_check_links(self, cli: Cli) -> None:
        assert cli.run("--replay", "rec", "--links", "all") == 2
        assert "no network call" in cli.errors

    def test_a_bad_wiring_name_is_a_plain_error(self, cli: Cli) -> None:
        put_photos(cli.root)

        assert cli.run("--record", str(cli.root / "rec"), "--wiring", "nonsense") == 2
        assert "package.module:function" in cli.errors


class TestWiringLookup:
    def test_a_module_and_function_name_resolve(self) -> None:
        factory = load_wiring_factory("tests.harness.live_parts:fake_wiring")

        assert isinstance(factory(make_settings()), Wiring)

    @pytest.mark.parametrize("spec", ["", "nocolon", ":function", "module:"])
    def test_a_malformed_name_is_refused(self, spec: str) -> None:
        with pytest.raises(WiringError, match=r"package\.module:function"):
            load_wiring_factory(spec)

    def test_a_module_that_does_not_exist_is_named(self) -> None:
        with pytest.raises(WiringError, match="not_a_module_at_all"):
            load_wiring_factory("not_a_module_at_all:build")

    def test_a_function_that_does_not_exist_is_named(self) -> None:
        with pytest.raises(WiringError, match="no_such_function"):
            load_wiring_factory("tests.harness.live_parts:no_such_function")

    def test_a_wiring_function_that_returns_the_wrong_thing_is_refused(self, cli: Cli) -> None:
        put_photos(cli.root)

        code = cli.run(
            "--record",
            str(cli.root / "rec"),
            wiring=lambda settings: "not a wiring",  # type: ignore[arg-type,return-value]
        )

        assert code == 2
        assert "must return a Wiring" in cli.errors

    def test_the_wiring_option_runs_a_recording_end_to_end(self, cli: Cli) -> None:
        put_photos(cli.root)

        code = cli.run(
            "--record",
            str(cli.root / "rec"),
            "--wiring",
            "tests.harness.live_parts:fake_wiring",
        )

        assert code == 0
        assert (cli.root / "rec" / "manifest.json").is_file()


class TestRecordThenReplayThroughTheCommandLine:
    def record(self, cli: Cli, live: LiveParts, *extra: str) -> int:
        put_photos(cli.root)
        return cli.run("--record", str(cli.root / "rec"), *extra, wiring=wiring_over(live))

    def test_a_recorded_run_lands_in_the_next_numbered_folder(self, cli: Cli) -> None:
        live = LiveParts()

        assert self.record(cli, live) == 0

        run_dir = cli.root / "eval" / "results" / "run-1"
        assert len(list((run_dir / "responses").glob("*.json"))) == 10
        assert (run_dir / LABELS_FILE).is_file()
        text = (run_dir / REPORT_FILE).read_text(encoding="utf-8")
        assert text.startswith("# Acceptance results: run 1")
        assert "| Run | 1 (live, recorded) |" in text

    def test_the_recording_holds_a_file_per_query_and_a_manifest(self, cli: Cli) -> None:
        self.record(cli, LiveParts())

        names = sorted(path.name for path in (cli.root / "rec").iterdir())
        assert names[0] == "manifest.json"
        assert len(names) == 11
        manifest = json.loads((cli.root / "rec" / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["queries"]) == 10

    def test_the_recording_may_live_inside_the_runs_own_folder(self, cli: Cli) -> None:
        # Plan 16.1.1: "eval/results/run-1/ has JSON, report, labelling CSV and the recording".
        put_photos(cli.root)
        recording = cli.root / "eval" / "results" / "run-1" / "recording"

        code = cli.run("--record", str(recording), wiring=wiring_over(LiveParts()))

        assert code == 0, cli.errors
        run_dir = recording.parent
        assert (recording / "manifest.json").is_file()
        assert (run_dir / REPORT_FILE).is_file()
        assert (run_dir / LABELS_FILE).is_file()
        assert len(list((run_dir / "responses").glob("*.json"))) == 10
        assert (
            (run_dir / REPORT_FILE)
            .read_text(encoding="utf-8")
            .startswith("# Acceptance results: run 1")
        )

    def test_the_pipeline_and_the_link_checks_share_one_event_loop(self, cli: Cli) -> None:
        # A real HTTP client belongs to the loop it first ran in; two loops would break it.
        loops: list[object] = []
        live = LiveParts()

        def understand_on_a_loop(req: SearchRequest) -> UnderstandResult:
            loops.append(asyncio.get_running_loop())
            return understand_for(req)

        live.understander = FakeUnderstander(understand_on_a_loop)

        async def fetch(url: str) -> LinkResult:
            loops.append(asyncio.get_running_loop())
            return await ok_link_fetch(url)

        put_photos(cli.root)
        cli.run("--record", str(cli.root / "rec"), wiring=wiring_over(live, fetch))

        assert len(loops) > 10
        assert len({id(loop) for loop in loops}) == 1

    def test_the_next_free_run_number_is_used(self, cli: Cli) -> None:
        results = cli.root / "eval" / "results"
        (results / "run-1").mkdir(parents=True)
        (results / "run-2").mkdir()
        (results / "mock").mkdir()

        assert _next_run_number(results) == 3

    def test_every_link_is_checked_once_and_in_the_report(self, cli: Cli) -> None:
        asked: list[str] = []

        async def fetch(url: str) -> LinkResult:
            asked.append(url)
            return await ok_link_fetch(url)

        put_photos(cli.root)
        cli.run("--record", str(cli.root / "rec"), wiring=wiring_over(LiveParts(), fetch))

        text = (cli.root / "eval" / "results" / "run-1" / REPORT_FILE).read_text(encoding="utf-8")
        assert len(asked) == len(set(asked)) == 8  # 8 distinct products, asked once each
        assert "| 8/8 |" in text

    def test_a_failing_link_is_a_row_in_the_failures_table(self, cli: Cli) -> None:
        async def fetch(url: str) -> LinkResult:
            if url.endswith("alpha-2"):
                return LinkResult(url=url, status=404, title="Not Found")
            return await ok_link_fetch(url)

        put_photos(cli.root)
        cli.run("--record", str(cli.root / "rec"), wiring=wiring_over(LiveParts(), fetch))

        text = (cli.root / "eval" / "results" / "run-1" / REPORT_FILE).read_text(encoding="utf-8")
        assert "| q01_product_gown | Links ok | store |" in text
        assert "HTTP 404, not 200" in text

    def test_a_live_runs_folder_is_never_overwritten(self, cli: Cli) -> None:
        put_photos(cli.root)
        out = cli.root / "eval" / "results" / "run-1"
        out.mkdir(parents=True)
        (out / "run.json").write_text("{}", encoding="utf-8")
        live = LiveParts()

        code = cli.run(
            "--record", str(cli.root / "rec"), "--out", str(out), wiring=wiring_over(live)
        )

        assert code == 2
        assert "already holds files" in cli.errors
        assert live.calls() == (0, 0, 0, 0)  # refused before any live call

    def test_a_replay_makes_no_call_and_reproduces_the_recorded_results(self, cli: Cli) -> None:
        live = LiveParts()
        self.record(cli, live)
        before = live.calls()
        assert before[0] > 0
        for photo in (cli.root / "eval" / "data").rglob("*.jpg"):
            photo.unlink()  # a replay needs no private photos

        code = cli.run("--replay", str(cli.root / "rec"), wiring=wiring_over(live))

        assert code == 0
        assert live.calls() == before
        recorded = load_run(cli.root / "eval" / "results" / "run-1")
        replayed = load_run(cli.root / "eval" / "results" / "replay")
        assert [r.response.result_count for r in replayed.runs if r.response] == [
            r.response.result_count for r in recorded.runs if r.response
        ]

    def test_a_replay_report_says_so_and_uses_the_recorded_seconds(self, cli: Cli) -> None:
        self.record(cli, LiveParts())

        cli.run("--replay", str(cli.root / "rec"), wiring=wiring_over(LiveParts()))

        text = (cli.root / "eval" / "results" / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert f"replay of {cli.root / 'rec'}" in text
        assert "1.2 (recorded)" in text
        assert "Replay: the real pipeline ran again on a recording" in text
        assert "| Links ok |" in text
        assert "| not checked |" in text

    def test_a_replay_with_one_unrecorded_query_still_runs_the_others(self, cli: Cli) -> None:
        self.record(cli, LiveParts())
        manifest = cli.root / "rec" / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        del data["queries"]["q03_product_skinny_jeans"]
        manifest.write_text(json.dumps(data), encoding="utf-8")

        code = cli.run("--replay", str(cli.root / "rec"), wiring=wiring_over(LiveParts()))

        assert code == 0
        assert "q03_product_skinny_jeans: FAILED" in cli.printed
        assert "9 of 10 queries answered" in cli.printed
        text = (cli.root / "eval" / "results" / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert "could not serve q03_product_skinny_jeans from the recording" in text
        assert "| q03_product_skinny_jeans | Results | store |" in text

    def test_a_replay_without_a_recorded_duration_cannot_pass_the_time_rule(self, cli: Cli) -> None:
        self.record(cli, LiveParts())
        manifest = cli.root / "rec" / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        del data["queries"]["q01_product_gown"]["live_duration_ms"]
        manifest.write_text(json.dumps(data), encoding="utf-8")

        cli.run("--replay", str(cli.root / "rec"), wiring=wiring_over(LiveParts()))

        text = (cli.root / "eval" / "results" / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert "| q01_product_gown | 8 | 2 | not recorded |" in text

    def test_a_replay_report_opens_with_a_banner(self, cli: Cli) -> None:
        self.record(cli, LiveParts())

        cli.run("--replay", str(cli.root / "rec"), wiring=wiring_over(LiveParts()))

        text = (cli.root / "eval" / "results" / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert "\n> Replay of a recording: no live data was fetched in this run.\n" in text

    def test_replaying_a_recording_that_does_not_exist_says_to_record_first(self, cli: Cli) -> None:
        code = cli.run("--replay", str(cli.root / "nothing"), wiring=wiring_over(LiveParts()))

        assert code == 2
        assert "--record" in cli.errors

    def test_replay_without_the_real_application_explains_what_is_missing(self, cli: Cli) -> None:
        self.record(cli, LiveParts())

        assert cli.run("--replay", str(cli.root / "rec")) == 2
        assert "--wiring" in cli.errors
