"""A live run in which the stores turned one query away: the run says so, plainly.

The throttled query's pipeline answers that every store was blocked; the others answer normally.
This is the command line end to end, on the toy pipeline and fakes: no network, no OpenAI.
"""

from eval.harness.runstore import LABELS_FILE, REPORT_FILE, load_run
from tests.harness.cli_support import Cli, put_photos, read_rows
from tests.harness.live_parts import LiveParts
from tests.harness.live_run_support import stepped_wiring
from tests.harness.test_not_run import blocked, with_stores
from tests.harness.test_report import table_after

RUN = "eval/results/run-1"
THIRD = "q04_outfit_palazzo_top"


def record(cli: Cli, *extra: str, throttled: int = 3) -> int:
    """Record a run in which the query at position ``throttled`` (0 is the first) found every
    store blocked."""
    put_photos(cli.root)
    return cli.run(
        "--record",
        str(cli.root / RUN / "recording"),
        "--pause",
        "0",
        "--links",
        "none",
        *extra,
        wiring=stepped_wiring(
            LiveParts(),
            answer=lambda position: (
                with_stores(blocked("alpha"), blocked("beta")) if position == throttled else None
            ),
        ),
    )


class TestAThrottledQueryIsNotAFailure:
    def test_it_is_reported_as_not_run_and_the_verdict_is_incomplete(self, cli: Cli) -> None:
        assert record(cli) == 0, cli.errors

        assert (
            f"{THIRD}: NOT RUN (Every store that could be asked turned the search away "
            "(2 blocked or in cooldown), so there is nothing to judge.)"
        ) in cli.printed
        assert "9 of 10 queries answered (1 not run)" in cli.printed
        assert (
            "Verdict: INCOMPLETE. 9 of 10 queries ran and 1 did not "
            "(1 because the stores were blocked or in cooldown)."
        ) in cli.printed

    def test_it_is_not_a_row_in_the_failures_table(self, cli: Cli) -> None:
        record(cli)

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        failed_queries = {row[0] for row in table_after(text, "## Failures")[1:]}
        assert failed_queries  # the toy pipeline's other queries do fail some criteria
        assert THIRD not in failed_queries
        rows = {row[0]: row for row in table_after(text, "## Results")[1:]}
        assert rows[THIRD][1:] == ["not run"] * 6
        assert "## Queries not run" in text
        assert f"Did not run (1): {THIRD}." in text

    def test_it_has_no_rows_in_the_labelling_sheet(self, cli: Cli) -> None:
        record(cli)

        queries = {row["query_id"] for row in read_rows(cli.root / RUN / LABELS_FILE)}
        assert THIRD not in queries
        assert "q05_outfit_dress_heels" in queries

    def test_the_saved_run_keeps_it_so_a_rescore_says_the_same(self, cli: Cli) -> None:
        record(cli)
        run_dir = cli.root / RUN
        saved = {run.query.id: run for run in load_run(run_dir).runs}
        assert saved[THIRD].not_run is not None

        assert cli.run("--rescore", str(run_dir)) == 0

        assert "Verdict: INCOMPLETE" in cli.printed.rsplit("Rescored", 1)[1]

    def test_the_other_queries_were_judged_as_always(self, cli: Cli) -> None:
        record(cli)

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        rows = {row[0]: row for row in table_after(text, "## Results")[1:]}
        assert rows["q05_outfit_dress_heels"][1:] != ["not run"] * 6
        assert rows["q01_product_gown"][5] == "not labelled"  # good@10 still waits for the labels
