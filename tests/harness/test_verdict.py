"""11.2.4: the "most queries" rule (assumption A6: at least 7 of 10) and its boundaries."""

from dataclasses import replace

import pytest
from eval.harness.criteria import (
    Criterion,
    CriterionResult,
    QueryEvaluation,
    Status,
    evaluate_query,
)
from eval.harness.labels import LabelSet, label_rows
from eval.harness.links import LinkCheck
from eval.harness.runner import QueryRun
from eval.harness.verdict import overall_verdict

from tests.harness.helpers import make_group, make_query, make_response


def evaluation(query_id: str, status: Status) -> QueryEvaluation:
    run = QueryRun(make_query(query_id), make_response(), None, 1.0, 1.0)
    return QueryEvaluation(run, (CriterionResult(Criterion.RESULTS, status, "x"),))


def evaluations(passed: int, failed: int, pending: int = 0) -> list[QueryEvaluation]:
    states = [Status.PASS] * passed + [Status.FAIL] * failed + [Status.PENDING] * pending
    return [evaluation(f"q{index + 1:02d}", state) for index, state in enumerate(states)]


class TestTheMostQueriesRule:
    def test_exactly_seven_of_ten_pass(self) -> None:
        verdict = overall_verdict(evaluations(passed=7, failed=3))

        assert verdict.status is Status.PASS
        assert verdict.label == "PASS"

    def test_six_of_ten_fail(self) -> None:
        verdict = overall_verdict(evaluations(passed=6, failed=4))

        assert verdict.status is Status.FAIL
        assert verdict.label == "FAIL"

    @pytest.mark.parametrize("passed", [7, 8, 9, 10])
    def test_seven_or_more_pass(self, passed: int) -> None:
        assert overall_verdict(evaluations(passed, 10 - passed)).status is Status.PASS

    @pytest.mark.parametrize("passed", [0, 1, 5, 6])
    def test_fewer_than_seven_fail_when_nothing_is_pending(self, passed: int) -> None:
        assert overall_verdict(evaluations(passed, 10 - passed)).status is Status.FAIL

    def test_the_verdict_names_who_passed_failed_and_is_pending(self) -> None:
        verdict = overall_verdict(evaluations(passed=2, failed=1, pending=1))

        assert verdict.passed == ("q01", "q02")
        assert verdict.failed == ("q03",)
        assert verdict.pending == ("q04",)
        assert (verdict.required, verdict.total) == (7, 4)

    def test_the_headline_lists_the_passing_ids(self) -> None:
        verdict = overall_verdict(evaluations(passed=2, failed=0))

        assert verdict.headline == "2 of 2 queries pass (list their ids: q01, q02)"

    def test_the_headline_with_no_passing_query_says_none(self) -> None:
        assert "none" in overall_verdict(evaluations(passed=0, failed=1)).headline


class TestUndecidedQueries:
    def test_six_pass_and_one_is_still_pending_so_it_could_still_reach_seven(self) -> None:
        verdict = overall_verdict(evaluations(passed=6, failed=3, pending=1))

        assert verdict.status is Status.PENDING

    def test_five_pass_and_one_pending_cannot_reach_seven(self) -> None:
        verdict = overall_verdict(evaluations(passed=5, failed=4, pending=1))

        assert verdict.status is Status.FAIL

    def test_seven_pass_with_three_pending_is_already_a_pass(self) -> None:
        verdict = overall_verdict(evaluations(passed=7, failed=0, pending=3))

        assert verdict.status is Status.PASS

    def test_a_run_with_nothing_labelled_yet_is_pending_never_pass(self) -> None:
        verdict = overall_verdict(evaluations(passed=0, failed=0, pending=10))

        assert verdict.status is Status.PENDING

    def test_four_failures_leave_exactly_six_possible_so_the_run_has_failed(self) -> None:
        # 4 failed means at most 6 can pass: seven can no longer be reached.
        assert overall_verdict(evaluations(passed=0, failed=4, pending=6)).status is Status.FAIL

    def test_three_failures_still_leave_seven_possible(self) -> None:
        assert overall_verdict(evaluations(passed=0, failed=3, pending=7)).status is Status.PENDING


class TestTheRuleAppliedToRealEvaluations:
    """Ten full queries scored end to end, so the rule is checked against the criteria too."""

    def scored(self, good_queries: int) -> list[QueryEvaluation]:
        results: list[QueryEvaluation] = []
        for index in range(10):
            response = make_response([make_group()])
            run = QueryRun(make_query(f"q{index + 1:02d}"), response, None, 5000.0, 5000.0)
            links = [
                LinkCheck(
                    url=s.product.product_url, store=s.product.store, product_title="t", ok=True
                )
                for s in response.products
            ]
            good = 8 if index < good_queries else 6
            labels = LabelSet(
                tuple(replace(row, label=1 if row.rank <= good else 0) for row in label_rows([run]))
            )
            results.append(evaluate_query(run, link_checks=links, labels=labels))
        return results

    def test_seven_queries_with_seven_or_more_good_pass_the_demo(self) -> None:
        verdict = overall_verdict(self.scored(good_queries=7))

        assert verdict.status is Status.PASS
        assert len(verdict.passed) == 7

    def test_six_such_queries_do_not(self) -> None:
        verdict = overall_verdict(self.scored(good_queries=6))

        assert verdict.status is Status.FAIL
        assert len(verdict.failed) == 4
