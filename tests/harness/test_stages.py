"""11.2.2 and the shared top-10 rule (A15): stage metrics and group helpers."""

from eval.harness.criteria import evaluate_query
from eval.harness.groups import TOP_N, distinct_stores, group_names, top_results
from eval.harness.runner import PipelineFailure, QueryRun
from eval.harness.stages import (
    fetch_rows,
    format_dropped,
    rank_rows,
    step_summaries,
    store_summaries,
)
from tests.factories import make_store_report
from tests.harness.helpers import labels_for, make_group, make_query, make_response
from vga.models import Category, SearchResponse, StepTiming, StoreStatus


def run_of(query_id: str, response: SearchResponse) -> QueryRun:
    return QueryRun(make_query(query_id), response, None, 1.0, 1.0)


class TestTheTopTen:
    def test_it_is_the_ten_best_by_overall_score_across_all_price_ranges(self) -> None:
        # Scores rise with position, so the best are the last displayed: the Luxury range.
        group = make_group(counts=(8, 8, 7, 7), total=lambda position: position / 100)

        top = top_results(group)

        assert len(top) == TOP_N
        assert [s.product.title for s in top][:2] == ["Outerwear item 30", "Outerwear item 29"]
        assert [s.scores.total for s in top] == sorted((s.scores.total for s in top), reverse=True)

    def test_ties_keep_the_displayed_order_so_the_list_is_deterministic(self) -> None:
        group = make_group(counts=(4, 4, 4, 4), total=lambda position: 0.5)

        titles = [s.product.title for s in top_results(group)]

        assert titles == [f"Outerwear item {n}" for n in range(1, 11)]

    def test_a_group_with_fewer_than_ten_results_returns_what_it_has(self) -> None:
        group = make_group(counts=(2, 2, 1, 0))

        assert len(top_results(group)) == 5

    def test_a_different_n_is_possible(self) -> None:
        assert len(top_results(make_group(), n=3)) == 3


class TestGroups:
    def test_a_garment_is_named_by_its_category(self) -> None:
        response = make_response(
            [make_group(Category.TOPS), make_group(Category.SHOES, item_index=1)]
        )

        assert group_names(response) == ["tops", "shoes"]

    def test_two_garments_of_one_category_get_their_position_so_names_stay_unique(self) -> None:
        response = make_response(
            [make_group(Category.TOPS), make_group(Category.TOPS, item_index=1)]
        )

        assert group_names(response) == ["tops-1", "tops-2"]

    def test_stores_are_those_with_results_not_those_that_merely_answered(self) -> None:
        response = make_response(
            [make_group(stores=("B Store", "A Store"))],
            stores_used=[make_store_report(store_id=name) for name in ("a", "b", "c")],
        )

        assert distinct_stores(response) == ["A Store", "B Store"]


class TestTheFetchStage:
    def response(self) -> SearchResponse:
        used = [
            make_store_report(
                store_id="alpha",
                product_count=12,
                strategy="shopify",
                dropped={"missing_price": 2, "off_domain_link": 1},
                duration_ms=1000.0,
            ),
            make_store_report(
                store_id="beta",
                product_count=9,
                strategy="css",
                from_cache=True,
                duration_ms=3000.0,
            ),
        ]
        return make_response(stores_used=used, skipped=["gamma"])

    def test_each_store_reports_count_strategy_drops_and_cache(self) -> None:
        rows = {row.store_id: row for row in fetch_rows([run_of("q01", self.response())])}

        assert (rows["alpha"].valid_products, rows["alpha"].strategy) == (12, "shopify")
        assert rows["alpha"].dropped == {"missing_price": 2, "off_domain_link": 1}
        assert rows["beta"].from_cache is True
        assert rows["gamma"].status is StoreStatus.BLOCKED
        assert rows["gamma"].reason

    def test_dropped_records_are_listed_by_reason_or_none(self) -> None:
        assert format_dropped({"off_domain_link": 1, "missing_price": 2}) == (
            "missing_price: 2, off_domain_link: 1"
        )
        assert format_dropped({}) == "none"

    def test_a_query_that_failed_has_no_fetch_rows(self) -> None:
        failed = QueryRun(make_query("q01"), None, PipelineFailure("x", "y", "Z"), 1.0, 1.0)

        assert fetch_rows([failed]) == []

    def test_stores_are_summarised_over_the_whole_run(self) -> None:
        runs = [run_of("q01", self.response()), run_of("q02", self.response())]

        summary = {s.store_id: s for s in store_summaries(runs)}

        assert summary["alpha"].queries_ok == 2
        assert summary["alpha"].valid_products == 24
        assert summary["alpha"].dropped == {"missing_price": 4, "off_domain_link": 2}
        assert summary["alpha"].mean_ms == 1000.0
        assert summary["beta"].cache_hits == 2
        assert summary["beta"].max_ms == 3000.0
        assert summary["gamma"].queries_ok == 0
        assert summary["gamma"].queries_total == 2


class TestTheStepSummary:
    def test_mean_and_slowest_time_of_each_whole_request_step(self) -> None:
        def with_times(understand: float, store_fetch: float) -> SearchResponse:
            return make_response(
                timings=[
                    StepTiming(step="understand", duration_ms=understand),
                    StepTiming(step="fetch", store="alpha", duration_ms=store_fetch),
                    StepTiming(step="rank", duration_ms=100.0),
                ]
            )

        runs = [run_of("q01", with_times(1000.0, 5.0)), run_of("q02", with_times(3000.0, 5.0))]

        steps = {s.step: s for s in step_summaries(runs)}

        assert (steps["understand"].runs, steps["understand"].mean_ms) == (2, 2000.0)
        assert steps["understand"].max_ms == 3000.0
        assert "fetch" not in steps  # per-store fetch times live in the per-store summary


class TestTheRankStage:
    def test_labelled_groups_show_their_count_and_whether_they_reach_seven(self) -> None:
        run = run_of("q01", make_response())
        evaluation = evaluate_query(run, labels=labels_for(run, {"outerwear": 6}))

        rows = rank_rows([evaluation])

        assert [(r.group, r.results, r.good, r.reaches_bar) for r in rows] == [
            ("outerwear", 30, "6/10", "no")
        ]

    def test_exactly_seven_reaches_the_bar(self) -> None:
        run = run_of("q01", make_response())

        rows = rank_rows([evaluate_query(run, labels=labels_for(run, {"outerwear": 7}))])

        assert rows[0].reaches_bar == "yes"

    def test_without_labels_a_full_group_is_pending_and_a_tiny_one_cannot_reach_the_bar(
        self,
    ) -> None:
        full = evaluate_query(run_of("q01", make_response()))
        tiny = evaluate_query(run_of("q02", make_response([make_group(counts=(1, 1, 1, 1))])))

        rows = rank_rows([full, tiny])

        assert (rows[0].good, rows[0].reaches_bar) == ("not labelled", "pending")
        assert (rows[1].good, rows[1].reaches_bar) == ("max 4/10", "no")
