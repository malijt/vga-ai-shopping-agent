"""A query whose stores were all blocked or in cooldown was not run: neither a pass nor a fail.

The first recorded run (2026-10-08) sent ten queries back to back. The platform turned all
thirteen stores away during the first, and the other nine found every store in its cooldown. The
report said ``0 of 10 queries pass`` and ``FAIL``. That describes nine queries that were never
really run. These tests pin the other reading: a query like that is "not run", the verdict says
``INCOMPLETE`` and why, and a query that got results from some stores is judged as it always was.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from eval.harness.criteria import Criterion, QueryEvaluation, Status, evaluate_query, failure_rows
from eval.harness.labels import label_rows
from eval.harness.notrun import NotRun, describe_wait, not_sent, stores_unavailable
from eval.harness.queries import AcceptanceQuery
from eval.harness.report import render_report
from eval.harness.runner import QueryRun, run_queries, run_query
from eval.harness.runstore import LoadedRun, load_run, save_run
from eval.harness.scoring import ScoredRun, score_run
from eval.harness.verdict import overall_verdict
from tests.factories import make_settings, make_store_report
from tests.fakes import FakeClock, FakePipeline
from tests.harness.helpers import make_query, make_response
from tests.harness.test_report import meta, table_after
from tests.harness.test_verdict import evaluations
from vga.errors import LlmError
from vga.models import RunOverrides, SearchRequest, SearchResponse, StoreReport, StoreStatus
from vga.settings import Settings

BLOCKED_REASON = "This store did not allow the search, so we skipped it."
COOLDOWN_REASON = "This store turned down a recent request, so we are leaving it alone for a while."


def blocked(store_id: str) -> StoreReport:
    return make_store_report(StoreStatus.BLOCKED, store_id=store_id, reason=BLOCKED_REASON)


def cooling(store_id: str) -> StoreReport:
    return make_store_report(StoreStatus.COOLDOWN, store_id=store_id, reason=COOLDOWN_REASON)


def left_out(store_id: str) -> StoreReport:
    return make_store_report(
        StoreStatus.EMPTY, store_id=store_id, reason="Not searched: Beta does not sell dresses."
    )


def found_nothing(store_id: str) -> StoreReport:
    return make_store_report(
        StoreStatus.EMPTY, store_id=store_id, reason="This store had no products matching."
    )


def with_stores(*skipped: StoreReport, used: list[StoreReport] | None = None) -> SearchResponse:
    """A response with no results, whose stores are ``skipped`` (and ``used``)."""
    return make_response([], stores_skipped=list(skipped), stores_used=used or [])


def run_of(query: AcceptanceQuery, response: SearchResponse | None) -> QueryRun:
    return QueryRun(query, response, None, 1.0, 1.0)


class Scripted:
    """A pipeline that answers with the given responses, one after another."""

    def __init__(self, *responses: SearchResponse) -> None:
        self._responses = iter(responses)

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: object = None,
    ) -> SearchResponse:
        return next(self._responses)


class TestWhichQueriesWereNotRun:
    def test_every_store_blocked_is_not_run(self) -> None:
        response = with_stores(blocked("a"), blocked("b"), blocked("c"))

        found = stores_unavailable(response, 900)

        assert found is not None
        assert found.kind == "stores_unavailable"
        assert [(s.store_id, s.status) for s in found.stores] == [
            ("a", StoreStatus.BLOCKED),
            ("b", StoreStatus.BLOCKED),
            ("c", StoreStatus.BLOCKED),
        ]
        assert found.stores[0].reason == BLOCKED_REASON
        assert found.cooldown_s == 900

    def test_blocked_and_in_cooldown_together_are_not_run(self) -> None:
        assert stores_unavailable(with_stores(blocked("a"), cooling("b")), 900) is not None

    def test_a_store_that_was_left_out_for_the_garment_does_not_stop_it(self) -> None:
        response = with_stores(blocked("a"), blocked("b"), left_out("c"))

        found = stores_unavailable(response, 900)

        assert found is not None
        assert [s.store_id for s in found.stores] == ["a", "b"]  # the left-out one is not listed

    def test_a_store_that_found_nothing_does_not_stop_it_either(self) -> None:
        # One store answered "nothing matched"; twelve could not be asked. There is nothing to
        # judge: the answer of the one that did answer is no evidence against the app.
        assert stores_unavailable(with_stores(blocked("a"), found_nothing("b")), 900) is not None

    def test_a_query_that_got_results_from_some_stores_is_judged_as_before(self) -> None:
        response = make_response(skipped=["x", "y"])  # a full group of results, two stores blocked

        assert stores_unavailable(response, 900) is None

    def test_a_query_with_a_used_store_is_judged_as_before(self) -> None:
        response = with_stores(blocked("a"), used=[make_store_report(store_id="b")])

        assert stores_unavailable(response, 900) is None

    @pytest.mark.parametrize(
        "other",
        [
            make_store_report(StoreStatus.TIMEOUT, store_id="z"),
            make_store_report(StoreStatus.ERROR, store_id="z"),
            make_store_report(StoreStatus.ROBOTS_DENIED, store_id="z"),
        ],
        ids=["timeout", "error", "robots"],
    )
    def test_a_store_that_failed_in_another_way_makes_it_a_real_failure(
        self, other: StoreReport
    ) -> None:
        assert stores_unavailable(with_stores(blocked("a"), other), 900) is None

    def test_no_result_and_no_blocked_store_is_a_real_failure(self) -> None:
        assert stores_unavailable(with_stores(found_nothing("a"), found_nothing("b")), 900) is None

    def test_no_stores_at_all_is_a_real_failure(self) -> None:
        assert stores_unavailable(with_stores(), 900) is None


class TestTheRunnerMarksIt:
    async def test_a_throttled_search_is_a_query_that_was_not_run(self) -> None:
        pipeline = FakePipeline(with_stores(blocked("a"), blocked("b")))

        run = await run_query(
            make_query("q01_text"),
            pipeline,
            make_settings(store_cooldown_s=600),
            clock=FakeClock(),
            image=None,
        )

        assert run.not_run is not None
        assert run.not_run.kind == "stores_unavailable"
        assert run.not_run.cooldown_s == 600  # the setting of this run, not a built-in figure
        assert run.failure is None
        assert run.response is not None  # the stores and their reasons stay available

    async def test_an_ordinary_search_is_not_marked(self) -> None:
        run = await run_query(
            make_query("q01_text"),
            FakePipeline(make_response()),
            make_settings(),
            clock=FakeClock(),
            image=None,
        )

        assert run.not_run is None

    async def test_a_pipeline_that_raised_is_a_failure_not_a_query_that_was_not_run(self) -> None:
        run = await run_query(
            make_query("q01_text"),
            FakePipeline(error=LlmError()),
            make_settings(),
            clock=FakeClock(),
            image=None,
        )

        assert run.not_run is None
        assert run.failure is not None

    async def test_the_shoppers_answer_is_not_sent_after_a_search_that_found_nothing(self) -> None:
        pipeline = FakePipeline(with_stores(blocked("a"), blocked("b")))
        query = make_query("q01_gown", "product_photo", shopper_gender="women")

        run = await run_query(
            query, pipeline, make_settings(), clock=FakeClock(), image=b"photo-bytes"
        )

        assert len(pipeline.calls) == 1  # no second search for the same blocked stores
        assert run.not_run is not None

    async def test_the_other_queries_still_run(self) -> None:
        runs = await run_queries(
            [make_query("q01_a"), make_query("q02_b"), make_query("q03_c")],
            Scripted(make_response(), with_stores(blocked("a")), make_response()),
            make_settings(),
            clock=FakeClock(),
            load_image=lambda query: None,
        )

        assert [run.not_run is not None for run in runs] == [False, True, False]


def throttled_run(query_id: str) -> QueryRun:
    response = with_stores(blocked("a"), blocked("b"))
    return QueryRun(
        make_query(query_id), response, None, 1.0, 1.0, not_run=stores_unavailable(response, 900)
    )


def passing_run(query_id: str) -> QueryRun:
    return QueryRun(make_query(query_id), make_response(), None, 1.0, 1.0)


def never_sent(query_id: str) -> QueryRun:
    return QueryRun(
        make_query(query_id),
        None,
        None,
        0.0,
        0.0,
        not_run=not_sent("Not sent: the run stopped after q04."),
    )


def evaluations_of(runs: list[QueryRun]) -> list[QueryEvaluation]:
    return [evaluate_query(run) for run in runs]


class TestJudging:
    def test_a_query_that_was_not_run_has_no_verdict_on_any_criterion(self) -> None:
        evaluation = evaluate_query(throttled_run("q04_x"))

        assert evaluation.status is Status.NOT_RUN
        assert [r.status for r in evaluation.criteria] == [Status.NOT_RUN] * 6
        assert [r.cell for r in evaluation.criteria] == ["not run"] * 6
        assert [r.criterion for r in evaluation.criteria] == list(Criterion)

    def test_it_adds_nothing_to_the_failures_table(self) -> None:
        assert failure_rows([evaluate_query(throttled_run("q04_x"))]) == []

    def test_it_has_no_rows_in_the_labelling_sheet(self) -> None:
        throttled = replace(
            run_of(make_query("q04_x"), with_stores(blocked("a"))), not_run=not_sent("no")
        )
        normal = run_of(make_query("q05_y"), make_response())

        rows = label_rows([throttled, normal])

        assert {row.query_id for row in rows} == {"q05_y"}

    def test_a_query_that_was_never_sent_has_no_response_and_no_failure(self) -> None:
        run = QueryRun(make_query("q05_y"), None, None, 0.0, 0.0, not_run=not_sent("later"))

        evaluation = evaluate_query(run)

        assert evaluation.status is Status.NOT_RUN
        assert run.failure is None


class TestTheVerdictSaysWhatWasRun:
    def test_any_query_not_run_makes_the_verdict_incomplete(self) -> None:
        runs = [passing_run(f"q0{n}") for n in range(1, 4)] + [throttled_run("q04")]

        verdict = overall_verdict(evaluations_of(runs))

        assert verdict.label == "INCOMPLETE"

    def test_it_is_not_fail_even_when_every_query_that_ran_failed_the_rule(self) -> None:
        # The run that went wrong: nine queries were never really run, so "0 of 10 pass" and FAIL
        # described something else.
        runs = [throttled_run("q01")] + [throttled_run(f"q{n:02d}") for n in range(2, 11)]

        verdict = overall_verdict(evaluations_of(runs))

        assert verdict.label == "INCOMPLETE"
        assert verdict.passed == ()
        assert verdict.failed == ()

    def test_it_is_not_pending_either(self) -> None:
        runs = [passing_run("q01"), never_sent("q02")]

        assert overall_verdict(evaluations_of(runs)).label != "PENDING"

    def test_the_sentence_says_how_many_ran_how_many_did_not_and_why(self) -> None:
        runs = (
            [passing_run(f"q0{n}") for n in range(1, 4)]
            + [throttled_run("q04")]
            + [never_sent(f"q0{n}") for n in range(5, 10)]
        )

        verdict = overall_verdict(evaluations_of(runs))

        assert verdict.headline == (
            "3 of 9 queries ran and 6 did not (1 because the stores were blocked or in "
            "cooldown, 5 because the run stopped before sending them)"
        )

    def test_one_reason_alone_is_named_alone(self) -> None:
        runs = [passing_run("q01"), throttled_run("q02")]

        sentence = overall_verdict(evaluations_of(runs)).headline

        assert (
            sentence
            == "1 of 2 queries ran and 1 did not (1 because the stores were blocked or in cooldown)"
        )

    def test_the_verdict_names_the_queries_that_did_not_run(self) -> None:
        runs = [passing_run("q01"), throttled_run("q02"), never_sent("q03")]

        verdict = overall_verdict(evaluations_of(runs))

        assert [(q.query_id, q.kind) for q in verdict.not_run] == [
            ("q02", "stores_unavailable"),
            ("q03", "not_sent"),
        ]
        assert verdict.ran == 1

    def test_a_complete_run_keeps_todays_rules(self) -> None:
        verdict = overall_verdict(evaluations(passed=7, failed=3))

        assert verdict.label == "PASS"
        assert verdict.not_run == ()
        assert verdict.headline.startswith("7 of 10 queries pass (list their ids: q01, q02")

    def test_an_extra_set_keeps_its_label_and_names_what_did_not_run(self) -> None:
        runs = [passing_run("x01"), throttled_run("x02")]

        verdict = overall_verdict(evaluations_of(runs), required=None)

        assert verdict.label == "EXTRA SET"
        assert verdict.headline.startswith("1 of 2 queries ran and 1 did not")


def scored(runs: list[QueryRun]) -> ScoredRun:
    return score_run(LoadedRun(meta(), runs, {}))


class TestTheReport:
    def runs(self) -> list[QueryRun]:
        return [passing_run("q01"), throttled_run("q02"), never_sent("q03")]

    def test_the_rows_of_queries_not_run_say_so_in_every_column(self) -> None:
        text = render_report(scored(self.runs()))

        rows = {row[0]: row for row in table_after(text, "## Results")[1:]}
        assert rows["q02"][1:] == ["not run"] * 6
        assert rows["q03"][1:] == ["not run"] * 6

    def test_the_verdict_line_is_incomplete(self) -> None:
        text = render_report(scored(self.runs()))

        line = next(line for line in text.splitlines() if line.startswith("Verdict:"))
        assert line.startswith("Verdict: INCOMPLETE (2 of 3 queries did not run")
        assert "**Overall verdict:** 1 of 3 queries ran and 2 did not" in text

    def test_a_section_lists_what_ran_what_did_not_and_the_stores_reasons(self) -> None:
        text = render_report(scored(self.runs()))

        assert "## Queries not run" in text
        assert "Ran (1): q01. Did not run (2): q02, q03." in text
        rows = table_after(text, "## Queries not run")
        assert rows[0] == ["Query", "What happened"]
        assert (
            "blocked (This store did not allow the search, so we skipped it.): a, b" in rows[1][1]
        )
        assert rows[2][0] == "q03"
        assert "Not sent: the run stopped after q04." in rows[2][1]

    def test_the_section_says_the_cooldown_and_that_the_run_must_be_repeated(self) -> None:
        text = render_report(scored(self.runs()))

        assert "left alone for 15 minutes (the `store_cooldown_s` setting)" in text
        assert "a new run does not remember it" in text
        assert "must be repeated later" in text
        assert "`--only q02,q03`" in text

    def test_a_query_not_run_is_not_in_the_failures_table(self) -> None:
        text = render_report(scored(self.runs()))

        assert table_after(text, "## Failures")[1] == ["none", "", "", ""]

    def test_the_fetch_stage_still_lists_the_stores_of_the_throttled_query(self) -> None:
        text = render_report(scored(self.runs()))

        rows = table_after(text, "## Fetch stage")
        assert ["q02", "a", "blocked"] in [row[:3] for row in rows]
        assert ["q02", "b", "blocked"] in [row[:3] for row in rows]

    def test_a_query_that_got_results_from_some_stores_is_judged_and_lists_the_skipped_ones(
        self,
    ) -> None:
        partial = run_of(make_query("q01"), make_response(skipped=["x", "y"]))

        text = render_report(scored([partial]))

        assert "Queries not run" not in text
        assert "Verdict: INCOMPLETE" not in text
        fetch = [row[:3] for row in table_after(text, "## Fetch stage")]
        assert ["q01", "x", "blocked"] in fetch
        assert ["q01", "y", "blocked"] in fetch
        results = {row[0]: row for row in table_after(text, "## Results")[1:]}
        assert results["q01"][1:] != ["not run"] * 6

    def test_a_complete_run_has_no_such_section(self) -> None:
        text = render_report(scored([passing_run("q01"), passing_run("q02")]))

        assert "Queries not run" not in text

    def test_the_wait_is_said_the_way_a_person_would(self) -> None:
        assert describe_wait(900) == "15 minutes"
        assert describe_wait(3600) == "60 minutes"
        assert describe_wait(90) == "90 s"


class TestTheRunFileKeepsIt:
    def test_a_saved_run_loads_back_with_its_queries_not_run(self, tmp_path: Path) -> None:
        runs = [passing_run("q01"), throttled_run("q02"), never_sent("q03")]
        save_run(tmp_path / "run", LoadedRun(meta(), runs, {}))

        loaded = load_run(tmp_path / "run")

        first, second, third = loaded.runs
        assert first.not_run is None
        assert isinstance(second.not_run, NotRun)
        assert second.not_run.kind == "stores_unavailable"
        assert [s.store_id for s in second.not_run.stores] == ["a", "b"]
        assert second.response is not None
        assert third.not_run is not None
        assert third.not_run.reason == "Not sent: the run stopped after q04."
        assert third.response is None

    def test_a_run_saved_before_this_change_still_loads(self, tmp_path: Path) -> None:
        save_run(tmp_path / "run", LoadedRun(meta(), [passing_run("q01")], {}))
        text = (tmp_path / "run" / "run.json").read_text(encoding="utf-8")
        assert '"not_run": null' in text

        (tmp_path / "run" / "run.json").write_text(
            text.replace('"not_run": null,', ""), encoding="utf-8"
        )

        assert load_run(tmp_path / "run").runs[0].not_run is None
