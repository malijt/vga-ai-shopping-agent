"""The 11 extra photos (``extra_queries.yaml``) run through the same harness, but they are not the
acceptance result.

The acceptance file keeps its strict checks (the PRD mix of 10). Any other queries file is an
extra set: no mix to check, the verdict counts "k of N", the report says plainly that it is not the
acceptance result, and it never lands in the folder of an acceptance run.
"""

import json
from pathlib import Path

import pytest

from eval.harness import queries as queries_module
from eval.harness.cli import _next_run_number
from eval.harness.criteria import Criterion, CriterionResult, QueryEvaluation, Status
from eval.harness.errors import QueryFileError
from eval.harness.queries import (
    EXTRA_QUERIES_PATH,
    QUERIES_PATH,
    load_queries,
    query_set_of,
)
from eval.harness.runner import QueryRun
from eval.harness.runstore import REPORT_FILE, RUN_FILE, load_run
from eval.harness.verdict import overall_verdict
from tests.harness.cli_support import Cli, read_rows, wiring_over, write_rows
from tests.harness.helpers import make_query, make_response
from tests.harness.live_parts import LiveParts

EXTRA = str(EXTRA_QUERIES_PATH)


def put_extra_photos(root: Path) -> None:
    """The 11 extra photos, as 1-byte stand-ins (the fake pipeline ignores their content)."""
    for query in load_queries(EXTRA_QUERIES_PATH, require_images=False, check_mix=False):
        if query.image:
            target = root / query.image
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"photo")


def results_text(cli: Cli, folder: str) -> str:
    return (cli.root / "eval" / "results" / folder / REPORT_FILE).read_text(encoding="utf-8")


class TestWhichFileIsTheAcceptanceSet:
    def test_the_frozen_queries_file_is_the_acceptance_set(self) -> None:
        assert query_set_of(QUERIES_PATH) == "acceptance"
        assert query_set_of(str(QUERIES_PATH)) == "acceptance"

    def test_the_same_file_by_a_relative_path_is_still_the_acceptance_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(QUERIES_PATH.parent.parent.parent)

        assert query_set_of("eval/data/queries.yaml") == "acceptance"
        assert query_set_of("eval/data/../data/queries.yaml") == "acceptance"

    def test_any_other_file_is_an_extra_set(self, tmp_path: Path) -> None:
        copy = tmp_path / "queries.yaml"
        copy.write_text(QUERIES_PATH.read_text(encoding="utf-8"), encoding="utf-8")

        assert query_set_of(EXTRA_QUERIES_PATH) == "extra"
        assert query_set_of(copy) == "extra"  # a copy of the acceptance file is not the file

    def test_the_extra_file_has_no_prd_mix_and_the_strict_loader_still_refuses_it(self) -> None:
        with pytest.raises(QueryFileError, match="the mix must be"):
            load_queries(EXTRA_QUERIES_PATH, require_images=False)

        extras = load_queries(EXTRA_QUERIES_PATH, require_images=False, check_mix=False)
        assert [query.id[:1] for query in extras] == ["x"] * 11


class TestTheAcceptanceRunKeepsItsStrictChecks:
    def test_a_wrong_mix_in_the_acceptance_file_is_still_an_error(
        self, cli: Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pretend this file is the frozen acceptance file, with one query too few.
        broken = tmp_path / "queries.yaml"
        lines = QUERIES_PATH.read_text(encoding="utf-8").split("  - id: q10")[0]
        broken.write_text(lines, encoding="utf-8")
        monkeypatch.setattr(queries_module, "QUERIES_PATH", broken)

        code = cli.run("--mock", "--queries", str(broken))

        assert code == 2
        assert "the mix must be" in cli.errors

    def test_the_default_run_is_labelled_as_the_acceptance_run(self, cli: Cli) -> None:
        cli.run("--mock")

        text = results_text(cli, "mock")
        assert text.startswith("# Acceptance results: run mock")
        assert "Extra set" not in text
        assert load_run(cli.root / "eval" / "results" / "mock").meta.query_set == "acceptance"


class TestAnExtraSetRuns:
    def test_the_extra_photos_run_without_the_mix_check(self, cli: Cli) -> None:
        code = cli.run("--mock", "--queries", EXTRA)

        assert code == 0, cli.errors
        out = cli.root / "eval" / "results" / "mock-extras"
        assert len(list((out / "responses").glob("*.json"))) == 11
        assert "11 of 11 queries answered" in cli.printed

    def test_the_verdict_counts_of_eleven_and_gives_no_demo_verdict(self, cli: Cli) -> None:
        cli.run("--mock", "--queries", EXTRA)

        assert "Extra set, not the acceptance result: 0 of 11 queries pass" in cli.printed
        assert "does not count towards the 7 of 10 rule" in cli.printed
        assert "Verdict: PASS" not in cli.printed
        assert "Verdict: FAIL" not in cli.printed
        assert "Verdict: PENDING" not in cli.printed

    def test_the_report_says_it_is_an_extra_set_not_the_acceptance_result(self, cli: Cli) -> None:
        cli.run("--mock", "--queries", EXTRA)

        text = results_text(cli, "mock-extras")
        assert text.startswith("# Extra set results: run mock")
        assert "> Extra set: not the acceptance result." in text
        assert "never count towards the 7 of 10 pass rule" in text
        assert "Verdict: none (extra set, not the acceptance result)" in text
        assert "of 11 queries pass" in text
        assert "The demo passes if at least" not in text
        assert "Acceptance results" not in text

    def test_the_report_keeps_the_results_table_of_the_acceptance_report(self, cli: Cli) -> None:
        cli.run("--mock", "--queries", EXTRA)

        text = results_text(cli, "mock-extras")
        assert (
            "| Query | Results | Stores | Seconds | Links ok | good@10 | Price ranges ok |" in text
        )
        for query in load_queries(EXTRA_QUERIES_PATH, require_images=False, check_mix=False):
            assert f"| {query.id} |" in text

    def test_the_run_is_saved_as_an_extra_set(self, cli: Cli) -> None:
        cli.run("--mock", "--queries", EXTRA)

        saved = json.loads(
            (cli.root / "eval" / "results" / "mock-extras" / RUN_FILE).read_text(encoding="utf-8")
        )
        assert saved["meta"]["query_set"] == "extra"

    def test_an_extra_run_never_replaces_the_acceptance_mock_folder(self, cli: Cli) -> None:
        cli.run("--mock")
        before = results_text(cli, "mock")

        cli.run("--mock", "--queries", EXTRA)

        assert results_text(cli, "mock") == before
        assert (cli.root / "eval" / "results" / "mock-extras").is_dir()

    def test_a_labelling_sheet_is_exported_for_the_extras_too(self, cli: Cli) -> None:
        cli.run("--mock", "--queries", EXTRA)

        rows = read_rows(cli.root / "eval" / "results" / "mock-extras" / "labels.csv")

        assert {row["query_id"][:1] for row in rows} == {"x"}
        assert {row["photo"] for row in rows} >= {"dress_floral_kaftan.png"}


class TestNoPassRuleAppliesToAnExtraSet:
    def evaluations(self, passed: int, failed: int, pending: int) -> list[QueryEvaluation]:
        states = [Status.PASS] * passed + [Status.FAIL] * failed + [Status.PENDING] * pending
        return [
            QueryEvaluation(
                QueryRun(make_query(f"x{i:02d}"), make_response(), None, 1.0, 1.0),
                (CriterionResult(Criterion.RESULTS, state, "x"),),
            )
            for i, state in enumerate(states, start=1)
        ]

    @pytest.mark.parametrize(("passed", "failed", "pending"), [(11, 0, 0), (0, 11, 0), (7, 2, 2)])
    def test_the_label_and_headline_count_only(
        self, passed: int, failed: int, pending: int
    ) -> None:
        verdict = overall_verdict(self.evaluations(passed, failed, pending), required=None)

        assert verdict.label == "EXTRA SET"
        assert verdict.required is None
        assert verdict.total == 11
        assert verdict.headline.startswith(f"{passed} of 11 queries pass")

    def test_seven_of_eleven_is_not_a_pass_here(self) -> None:
        # The acceptance rule would call 7 passing queries a PASS; an extra set never does.
        assert overall_verdict(self.evaluations(7, 4, 0)).label == "PASS"
        assert overall_verdict(self.evaluations(7, 4, 0), required=None).label == "EXTRA SET"


class TestRecordAndReplayAnExtraSet:
    def record(self, cli: Cli, live: LiveParts, *extra: str) -> int:
        put_extra_photos(cli.root)
        return cli.run(
            "--record",
            str(cli.root / "rec"),
            "--queries",
            EXTRA,
            *extra,
            wiring=wiring_over(live),
        )

    def test_a_live_extra_run_lands_in_extras_n_and_leaves_run_numbering_alone(
        self, cli: Cli
    ) -> None:
        assert self.record(cli, LiveParts()) == 0

        results = cli.root / "eval" / "results"
        assert (results / "extras-1" / REPORT_FILE).is_file()
        assert not (results / "run-1").exists()
        assert len(list((results / "extras-1" / "responses").glob("*.json"))) == 11

    def test_the_recording_may_live_inside_the_extras_folder(self, cli: Cli) -> None:
        put_extra_photos(cli.root)
        recording = cli.root / "eval" / "results" / "extras-1" / "recording"

        code = cli.run(
            "--record", str(recording), "--queries", EXTRA, wiring=wiring_over(LiveParts())
        )

        assert code == 0, cli.errors
        assert (recording / "manifest.json").is_file()
        assert (recording.parent / REPORT_FILE).is_file()
        assert not (cli.root / "eval" / "results" / "run-1").exists()

    def test_the_report_of_a_live_extra_run_is_not_the_acceptance_report(self, cli: Cli) -> None:
        self.record(cli, LiveParts())

        text = results_text(cli, "extras-1")
        assert text.startswith("# Extra set results: run 1")
        assert "| Run | 1 (live, recorded, extra set) |" in text
        assert "Verdict: none (extra set, not the acceptance result)" in text

    def test_acceptance_and_extra_runs_are_numbered_separately(self, cli: Cli) -> None:
        results = cli.root / "eval" / "results"
        (results / "run-1").mkdir(parents=True)
        (results / "run-2").mkdir()
        (results / "extras-1").mkdir()

        assert _next_run_number(results) == 3
        assert _next_run_number(results, "extras") == 2

    def test_a_replay_of_the_extras_makes_no_call_and_has_its_own_folder(self, cli: Cli) -> None:
        live = LiveParts()
        self.record(cli, live)
        before = live.calls()

        code = cli.run(
            "--replay", str(cli.root / "rec"), "--queries", EXTRA, wiring=wiring_over(live)
        )

        assert code == 0, cli.errors
        assert live.calls() == before
        text = results_text(cli, "replay-extras")
        assert text.startswith("# Extra set results: run replay")
        assert "> Replay of a recording: no live data was fetched in this run." in text
        assert not (cli.root / "eval" / "results" / "replay").exists()

    def test_rescoring_an_extra_run_keeps_it_an_extra_set(self, cli: Cli) -> None:
        self.record(cli, LiveParts())
        run_dir = cli.root / "eval" / "results" / "extras-1"
        fill_sheet_all_good(run_dir)

        code = cli.run("--rescore", str(run_dir), "--labels", str(run_dir / "labels.csv"))

        assert code == 0, cli.errors
        assert "Extra set, not the acceptance result:" in cli.printed
        assert "Verdict: none (extra set" in (run_dir / REPORT_FILE).read_text(encoding="utf-8")

    def test_a_run_saved_before_extra_sets_existed_is_read_as_the_acceptance_run(
        self, cli: Cli
    ) -> None:
        cli.run("--mock")
        run_file = cli.root / "eval" / "results" / "mock" / RUN_FILE
        saved = json.loads(run_file.read_text(encoding="utf-8"))
        del saved["meta"]["query_set"]
        run_file.write_text(json.dumps(saved), encoding="utf-8")

        assert load_run(run_file.parent).meta.query_set == "acceptance"


def fill_sheet_all_good(run_dir: Path) -> None:
    """Label every row 1 (the helper in ``cli_support`` knows only the acceptance query ids)."""
    sheet = run_dir / "labels.csv"
    rows = read_rows(sheet)
    for row in rows:
        row["label"] = "1"
    write_rows(sheet, rows)
