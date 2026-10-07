"""11.2.1: each criterion, with passing and failing responses, and the boundary cases."""

import pytest

from eval.harness.criteria import (
    Cause,
    CriteriaConfig,
    Criterion,
    CriterionResult,
    QueryEvaluation,
    Status,
    check_price_ranges,
    check_results,
    check_seconds,
    check_stores,
    evaluate_query,
    failure_rows,
    price_range_problems,
)
from eval.harness.runner import DurationSource, PipelineFailure, QueryRun
from tests.factories import make_store_report
from tests.harness.helpers import labels_for, make_group, make_query, make_response, ok_links
from vga.models import Category, Flag, SearchResponse, StepTiming, Tier

CONFIG = CriteriaConfig()


def run_of(
    response: SearchResponse | None,
    kind: str = "text",
    *,
    seconds: float | None = None,
    source: DurationSource = "measured",
) -> QueryRun:
    duration = (response.duration_ms if response else 0.0) if seconds is None else seconds * 1000
    return QueryRun(
        make_query("q06_text", kind),
        response,
        None,
        duration,
        duration,
        source,
    )


class TestResults:
    def test_thirty_results_pass(self) -> None:
        response = make_response()

        result = check_results(run_of(response), response, CONFIG)

        assert (result.status, result.cell) == (Status.PASS, "30")

    @pytest.mark.parametrize(
        ("counts", "status"), [((5, 5, 5, 5), Status.PASS), ((5, 5, 5, 4), Status.FAIL)]
    )
    def test_exactly_twenty_results_pass_and_nineteen_fail(
        self, counts: tuple[int, int, int, int], status: Status
    ) -> None:
        response = make_response([make_group(counts=counts)])

        assert check_results(run_of(response), response, CONFIG).status is status

    def test_too_few_results_blamed_on_the_stores_when_they_returned_little(self) -> None:
        response = make_response([make_group(counts=(2, 2, 2, 2))])

        result = check_results(run_of(response), response, CONFIG)

        assert result.status is Status.FAIL
        assert result.cause is Cause.STORE
        assert "8 results in total, at least 20 needed" in result.evidence

    def test_too_few_results_blamed_on_ranking_when_the_stores_returned_plenty(self) -> None:
        response = make_response(
            [make_group(counts=(2, 2, 2, 2))],
            stores_used=[make_store_report(store_id="alpha", product_count=60)],
        )

        result = check_results(run_of(response), response, CONFIG)

        assert result.cause is Cause.RANKING
        assert "alpha: 60 products (ok)" in result.evidence

    def test_an_outfit_shows_one_figure_per_garment_and_the_floor_is_the_total(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(3, 3, 3, 3)),
            make_group(Category.BOTTOMS, counts=(3, 3, 3, 3), item_index=1),
            make_group(Category.SHOES, counts=(3, 3, 3, 2), item_index=2),
        ]
        response = make_response(groups)

        result = check_results(run_of(response, "outfit_photo"), response, CONFIG)

        assert result.cell == "12 / 12 / 11"  # the figure format the template shows
        assert result.status is Status.PASS

    def test_an_outfit_garment_with_no_results_fails_even_if_the_total_is_enough(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(8, 8, 7, 7)),
            make_group(Category.SHOES, counts=(0, 0, 0, 0), item_index=1),
        ]
        response = make_response(groups)

        result = check_results(run_of(response, "outfit_photo"), response, CONFIG)

        assert result.status is Status.FAIL
        assert "no results for shoes" in result.evidence
        assert "per garment: tops 30, shoes 0" in result.evidence

    def test_a_response_with_no_groups_has_zero_results(self) -> None:
        response = make_response([])

        result = check_results(run_of(response), response, CONFIG)

        assert (result.status, result.cell) == (Status.FAIL, "0")


class TestStores:
    def test_three_stores_pass_and_two_fail(self) -> None:
        three = make_response([make_group(stores=("A Store", "B Store", "C Store"))])
        two = make_response([make_group(stores=("A Store", "B Store"))])

        assert check_stores(three, CONFIG).status is Status.PASS
        failed = check_stores(two, CONFIG)
        assert (failed.status, failed.cell) == (Status.FAIL, "2")
        assert "A Store, B Store" in failed.evidence

    def test_stores_are_counted_over_the_results_not_over_the_reports(self) -> None:
        response = make_response(
            [make_group(stores=("A Store", "B Store"))],
            stores_used=[make_store_report(store_id=name) for name in ("a", "b", "c", "d")],
        )

        result = check_stores(response, CONFIG)

        assert result.cell == "2"
        assert result.cause is Cause.RANKING  # four stores answered; the results use two

    def test_two_stores_is_a_store_failure_when_only_two_answered(self) -> None:
        response = make_response([make_group(stores=("A Store", "B Store"))], skipped=["gamma"])

        assert check_stores(response, CONFIG).cause is Cause.STORE

    def test_an_outfit_counts_stores_across_all_garments(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(4, 4, 4, 4), stores=("A Store", "B Store")),
            make_group(Category.SHOES, counts=(4, 4, 4, 4), stores=("C Store",), item_index=1),
        ]

        assert check_stores(make_response(groups), CONFIG).cell == "3"


class TestSeconds:
    @pytest.mark.parametrize(
        ("seconds", "status"), [(30.0, Status.PASS), (30.1, Status.FAIL), (0.0, Status.PASS)]
    )
    def test_exactly_thirty_seconds_passes_and_a_hair_more_fails(
        self, seconds: float, status: Status
    ) -> None:
        response = make_response()

        assert check_seconds(run_of(response, seconds=seconds), response, CONFIG).status is status

    def test_the_cell_is_one_decimal(self) -> None:
        response = make_response()

        assert check_seconds(run_of(response, seconds=12.345), response, CONFIG).cell == "12.3"

    @pytest.mark.parametrize(
        ("slow_step", "cause"),
        [("understand", Cause.LLM), ("search", Cause.STORE), ("rank", Cause.RANKING)],
    )
    def test_the_slowest_stage_is_the_cause(self, slow_step: str, cause: Cause) -> None:
        timings = [
            StepTiming(step="understand", duration_ms=1000.0),
            StepTiming(step="search", duration_ms=2000.0),
            StepTiming(step="fetch", store="alpha", duration_ms=1900.0),
            StepTiming(step="rank", duration_ms=500.0),
            StepTiming(step="shape", duration_ms=10.0),
        ]
        timings = [
            t.model_copy(update={"duration_ms": 30_000.0}) if t.step == slow_step else t
            for t in timings
        ]
        response = make_response(timings=timings)

        result = check_seconds(run_of(response, seconds=35.0), response, CONFIG)

        assert result.status is Status.FAIL
        assert result.cause is cause
        assert "took 35.0 s" in result.evidence

    def test_without_step_timings_the_cause_defaults_to_the_store(self) -> None:
        response = make_response()

        result = check_seconds(run_of(response, seconds=40.0), response, CONFIG)

        assert result.cause is Cause.STORE
        assert "no step timings" in result.evidence

    def test_a_replay_uses_the_recorded_duration_and_says_so(self) -> None:
        response = make_response()

        result = check_seconds(run_of(response, seconds=12.0, source="recorded"), response, CONFIG)

        assert result.cell == "12.0 (recorded)"

    def test_the_checked_duration_is_the_runs_not_the_responses(self) -> None:
        response = make_response(duration_ms=1000.0)

        slow_wall_time = check_seconds(run_of(response, seconds=31.0), response, CONFIG)

        assert slow_wall_time.status is Status.FAIL


class TestPriceRanges:
    def test_every_range_on_target_passes(self) -> None:
        response = make_response()

        result = check_price_ranges(response, CONFIG)

        assert (result.status, result.cell) == (Status.PASS, "yes")

    @pytest.mark.parametrize(
        ("counts", "status"),
        [
            ((7, 8, 7, 7), Status.PASS),  # one short
            ((9, 8, 7, 7), Status.PASS),  # one over
            ((6, 8, 7, 7), Status.FAIL),  # two short
            ((10, 8, 7, 7), Status.FAIL),  # two over
        ],
    )
    def test_within_one_of_the_target_passes_and_two_away_fails(
        self, counts: tuple[int, ...], status: Status
    ) -> None:
        response = make_response([make_group(counts=counts, targets=(8, 8, 7, 7))])

        assert check_price_ranges(response, CONFIG).status is status

    def test_a_range_flagged_few_options_is_ok_however_thin(self) -> None:
        group = make_group(
            counts=(8, 8, 7, 2), targets=(8, 8, 7, 7), flags={Tier.LUXURY: [Flag.FEW_OPTIONS]}
        )

        assert check_price_ranges(make_response([group]), CONFIG).status is Status.PASS

    def test_a_flag_on_another_range_does_not_excuse_a_thin_one(self) -> None:
        group = make_group(
            counts=(8, 8, 3, 7), targets=(8, 8, 7, 7), flags={Tier.LUXURY: [Flag.FEW_OPTIONS]}
        )

        result = check_price_ranges(make_response([group]), CONFIG)

        assert result.status is Status.FAIL
        assert result.cell == "no: Premium 3/7 (gap 4)"
        assert result.cause is Cause.PRICE_RANGE

    def test_the_evidence_gives_the_range_the_gap_and_the_span(self) -> None:
        group = make_group(counts=(8, 8, 3, 7), targets=(8, 8, 7, 7))

        result = check_price_ranges(make_response([group]), CONFIG)

        assert "Premium: 3 results for a target of 7 (gap 4)" in result.evidence
        assert "300-302 AED" in result.evidence

    def test_an_outfit_is_checked_per_garment_and_the_cell_names_the_garment(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(3, 3, 3, 3), targets=(3, 3, 3, 3)),
            make_group(Category.SHOES, counts=(3, 3, 0, 3), targets=(3, 3, 3, 3), item_index=1),
        ]

        result = check_price_ranges(make_response(groups), CONFIG)

        assert result.cell == "no: shoes Premium 0/3 (gap 3)"
        assert [p.group for p in price_range_problems(make_response(groups))] == ["shoes"]

    def test_a_different_tolerance_is_a_setting(self) -> None:
        response = make_response([make_group(counts=(6, 8, 7, 7), targets=(8, 8, 7, 7))])

        assert (
            check_price_ranges(response, CriteriaConfig(price_range_tolerance=2)).status
            is Status.PASS
        )

    def test_a_response_without_groups_fails(self) -> None:
        result = check_price_ranges(make_response([]), CONFIG)

        assert result.status is Status.FAIL
        assert result.cell == "no: no price ranges returned"


class TestEvaluateOneQuery:
    def test_a_fully_good_query_passes_every_criterion(self) -> None:
        response = make_response()
        run = run_of(response)

        evaluation = evaluate_query(
            run, link_checks=ok_links(response), labels=labels_for(run, {"outerwear": 8})
        )

        assert evaluation.status is Status.PASS
        assert [result.cell for result in evaluation.criteria] == [
            "30",
            "3",
            "5.0",
            "30/30",
            "8/10",
            "yes",
        ]

    def test_the_cells_are_in_the_templates_column_order(self) -> None:
        evaluation = evaluate_query(run_of(make_response()))

        assert [result.criterion.value for result in evaluation.criteria] == [
            "Results",
            "Stores",
            "Seconds",
            "Links ok",
            "good@10",
            "Price ranges ok",
        ]

    def test_without_labels_or_links_everything_else_can_pass_but_the_query_is_pending(
        self,
    ) -> None:
        evaluation = evaluate_query(run_of(make_response()))

        assert evaluation.status is Status.PENDING
        assert evaluation.result(Criterion.LINKS).cell == "not checked"
        assert evaluation.result(Criterion.GOOD_AT_10).cell == "not labelled"

    def test_a_hard_failure_beats_pending(self) -> None:
        response = make_response([make_group(counts=(2, 2, 2, 2))])

        evaluation = evaluate_query(run_of(response))

        assert evaluation.status is Status.FAIL

    def test_one_failure_fails_the_query_however_much_else_passes(self) -> None:
        response = make_response()
        run = run_of(response, seconds=31.0)

        evaluation = evaluate_query(
            run, link_checks=ok_links(response), labels=labels_for(run, {"outerwear": 10})
        )

        assert evaluation.status is Status.FAIL
        assert [r.criterion for r in evaluation.criteria if r.status is Status.FAIL] == [
            Criterion.SECONDS
        ]


class TestLinks:
    def test_all_results_checked_and_ok_passes(self) -> None:
        response = make_response()
        run = run_of(response)

        result = evaluate_query(run, link_checks=ok_links(response)).result(Criterion.LINKS)

        assert (result.status, result.cell) == (Status.PASS, "30/30")

    def test_one_failing_link_fails_the_query_and_names_it(self) -> None:
        response = make_response()
        links = ok_links(response)
        links[3] = links[3].model_copy(update={"ok": False, "problems": ["HTTP 404, not 200"]})

        result = evaluate_query(run_of(response), link_checks=links).result(Criterion.LINKS)

        assert (result.status, result.cell, result.cause) == (Status.FAIL, "29/30", Cause.STORE)
        assert links[3].url in result.evidence
        assert "HTTP 404, not 200" in result.evidence

    def test_only_the_top_ten_checked_and_ok_is_not_yet_a_pass(self) -> None:
        response = make_response()

        result = evaluate_query(run_of(response), link_checks=ok_links(response, 10)).result(
            Criterion.LINKS
        )

        assert result.status is Status.PENDING
        assert result.cell == "10/10 (top 10 only; 30 results)"

    def test_a_failure_among_the_top_ten_fails_even_without_checking_the_rest(self) -> None:
        response = make_response()
        links = ok_links(response, 10)
        links[0] = links[0].model_copy(
            update={"ok": False, "problems": ["no page opened: timeout"]}
        )

        result = evaluate_query(run_of(response), link_checks=links).result(Criterion.LINKS)

        assert result.status is Status.FAIL


class TestGoodAtTen:
    def test_exactly_seven_good_of_ten_passes_and_six_fails(self) -> None:
        response = make_response()
        run = run_of(response)

        seven = evaluate_query(run, labels=labels_for(run, {"outerwear": 7}))
        six = evaluate_query(run, labels=labels_for(run, {"outerwear": 6}))

        assert seven.result(Criterion.GOOD_AT_10).status is Status.PASS
        assert six.result(Criterion.GOOD_AT_10).status is Status.FAIL

    def test_a_failure_lists_the_products_that_were_not_good(self) -> None:
        response = make_response()
        run = run_of(response)

        result = evaluate_query(run, labels=labels_for(run, {"outerwear": 6})).result(
            Criterion.GOOD_AT_10
        )

        assert result.cell == "6/10"
        assert result.cause is Cause.RANKING
        assert "outerwear: 6/10 good, at least 7 needed" in result.evidence
        assert 'rank 7 "Outerwear item 7"' in result.evidence
        assert "understood as text: outerwear" in result.evidence

    def test_an_outfit_passes_only_if_every_garment_reaches_seven(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(8, 8, 7, 7)),
            make_group(Category.BOTTOMS, counts=(8, 8, 7, 7), item_index=1),
            make_group(Category.SHOES, counts=(8, 8, 7, 7), item_index=2),
        ]
        run = run_of(make_response(groups), "outfit_photo")

        passing = evaluate_query(run, labels=labels_for(run, {"tops": 7, "bottoms": 7, "shoes": 7}))
        failing = evaluate_query(run, labels=labels_for(run, {"tops": 8, "bottoms": 7, "shoes": 6}))

        assert passing.result(Criterion.GOOD_AT_10).cell == "7 / 7 / 7"
        assert passing.result(Criterion.GOOD_AT_10).status is Status.PASS
        failed = failing.result(Criterion.GOOD_AT_10)
        assert failed.status is Status.FAIL
        assert "shoes: 6/10" in failed.evidence
        assert "tops: 8/10" not in failed.evidence

    def test_a_group_with_fewer_than_seven_results_fails_before_any_label(self) -> None:
        response = make_response([make_group(counts=(2, 2, 1, 1))])

        result = evaluate_query(run_of(response)).result(Criterion.GOOD_AT_10)

        assert result.status is Status.FAIL
        assert result.cell == "max 6/10"
        assert "missing places count as not good" in result.evidence

    def test_a_group_with_eight_results_all_good_passes_because_eight_is_at_least_seven(
        self,
    ) -> None:
        response = make_response([make_group(counts=(2, 2, 2, 2))])
        run = run_of(response)

        result = evaluate_query(run, labels=labels_for(run, {"outerwear": 8})).result(
            Criterion.GOOD_AT_10
        )

        assert (result.status, result.cell) == (Status.PASS, "8/10")

    def test_a_group_with_exactly_seven_results_needs_all_seven_good(self) -> None:
        response = make_response([make_group(counts=(2, 2, 2, 1))])
        run = run_of(response)

        all_good = evaluate_query(run, labels=labels_for(run, {"outerwear": 7}))
        one_bad = evaluate_query(run, labels=labels_for(run, {"outerwear": 6}))

        assert all_good.result(Criterion.GOOD_AT_10).status is Status.PASS
        assert one_bad.result(Criterion.GOOD_AT_10).status is Status.FAIL

    def test_a_short_group_still_awaiting_labels_is_pending_not_failed(self) -> None:
        response = make_response([make_group(counts=(2, 2, 2, 1))])  # 7 results

        assert (
            evaluate_query(run_of(response)).result(Criterion.GOOD_AT_10).status is Status.PENDING
        )

    def test_one_short_garment_fails_the_outfit_before_labels(self) -> None:
        groups = [
            make_group(Category.TOPS, counts=(8, 8, 7, 7)),
            make_group(Category.SHOES, counts=(2, 2, 1, 1), item_index=1),
        ]
        response = make_response(groups)

        result = evaluate_query(run_of(response, "outfit_photo")).result(Criterion.GOOD_AT_10)

        assert result.status is Status.FAIL
        assert result.cell == "? / max 6"

    def test_a_misdetected_input_type_makes_the_cause_the_llm(self) -> None:
        response = make_response()  # understood as text
        run = run_of(response, "product_photo")

        result = evaluate_query(run, labels=labels_for(run, {"outerwear": 2})).result(
            Criterion.GOOD_AT_10
        )

        assert result.cause is Cause.LLM
        assert "detected as text, the query is product_photo" in result.evidence

    def test_a_response_with_no_results_fails_good_at_ten(self) -> None:
        result = evaluate_query(run_of(make_response([]))).result(Criterion.GOOD_AT_10)

        assert (result.status, result.cell) == (Status.FAIL, "0/10")


class TestAQueryThatProducedNothing:
    def failed_run(self, code: str = "llm_failure") -> QueryRun:
        failure = PipelineFailure(code, "We could not understand your request.", "LlmError")
        return QueryRun(make_query("q06_text"), None, failure, 400.0, 400.0)

    def test_every_criterion_but_the_time_fails_with_the_reason(self) -> None:
        evaluation = evaluate_query(self.failed_run())

        statuses = {r.criterion: r.status for r in evaluation.criteria}
        assert statuses[Criterion.SECONDS] is Status.PASS
        assert [c for c, s in statuses.items() if s is Status.FAIL] == [
            Criterion.RESULTS,
            Criterion.STORES,
            Criterion.LINKS,
            Criterion.GOOD_AT_10,
            Criterion.PRICE_RANGES,
        ]
        assert "code llm_failure): We could not understand your request." in (
            evaluation.result(Criterion.RESULTS).evidence
        )

    @pytest.mark.parametrize(
        ("code", "cause"),
        [
            ("llm_failure", Cause.LLM),
            ("call_budget_exceeded", Cause.LLM),
            ("store_blocked", Cause.STORE),
        ],
    )
    def test_the_cause_follows_the_error_code(self, code: str, cause: Cause) -> None:
        evaluation = evaluate_query(self.failed_run(code))

        assert evaluation.result(Criterion.RESULTS).cause is cause


class TestTheFailuresTable:
    def test_every_failed_criterion_gets_its_own_row_and_pending_ones_none(self) -> None:
        response = make_response(
            [make_group(counts=(1, 1, 1, 1), targets=(8, 8, 7, 7), stores=("A Store", "B Store"))]
        )
        evaluation = evaluate_query(run_of(response, seconds=31.0))

        rows = failure_rows([evaluation])

        failed = {row.criterion for row in rows}
        assert failed == {
            Criterion.RESULTS,
            Criterion.STORES,
            Criterion.SECONDS,
            Criterion.GOOD_AT_10,
            Criterion.PRICE_RANGES,
        }
        assert len(rows) == 5  # one row per failed criterion; links are pending, so no row
        assert {row.query_id for row in rows} == {"q06_text"}

    def test_a_passing_query_has_no_rows(self) -> None:
        response = make_response()
        run = run_of(response)
        evaluation = evaluate_query(
            run, link_checks=ok_links(response), labels=labels_for(run, {"outerwear": 9})
        )

        assert failure_rows([evaluation]) == []


def test_the_status_of_an_evaluation_is_the_worst_of_its_criteria() -> None:
    run = QueryRun(make_query(), make_response(), None, 1.0, 1.0)

    def evaluation(*states: Status) -> QueryEvaluation:
        results = tuple(CriterionResult(Criterion.RESULTS, state, "x") for state in states)
        return QueryEvaluation(run, results)

    assert evaluation(Status.PASS, Status.PASS).status is Status.PASS
    assert evaluation(Status.PASS, Status.PENDING).status is Status.PENDING
    assert evaluation(Status.PENDING, Status.FAIL, Status.PASS).status is Status.FAIL
