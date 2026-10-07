"""11.3.1 and 11.2.2: the Markdown report follows the template, and shows the two stages apart."""

import re
from datetime import date
from typing import Any

import pytest
from eval.harness.labels import LabelRow, LabelSet
from eval.harness.links import LinkCheck, LinksMode
from eval.harness.report import escape, render_report
from eval.harness.runner import PipelineFailure, QueryRun
from eval.harness.runstore import LoadedRun, RunMeta
from eval.harness.scoring import ScoredRun, score_run

from tests.factories import make_product, make_store_report, make_understand_result
from tests.harness.helpers import (
    labels_for,
    make_group,
    make_query,
    make_response,
    ok_links,
)
from vga.models import Category, StepTiming
from vga.settings import PROJECT_ROOT

TEMPLATE = (PROJECT_ROOT / "eval" / "data" / "results-template.md").read_text(encoding="utf-8")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in UNESCAPED_PIPE.split(line.strip())[1:-1]]


def table_after(text: str, heading: str) -> list[list[str]]:
    """Rows (header first, separator dropped) of the first table after ``heading``."""
    lines = text.splitlines()
    start = lines.index(heading)
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("|"):
            rows.append(cells(line))
        elif rows:
            break
    return [row for row in rows if not all(set(cell) <= {"-"} for cell in row)]


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("#")]


def meta(**overrides: object) -> RunMeta:
    fields: dict[str, object] = {
        "number": 1,
        "mode": "record",
        "date": date(2026, 10, 7),
        "links": LinksMode.ALL,
        "price_range_mix": [25, 25, 25, 25],
    }
    return RunMeta.model_validate({**fields, **overrides})


def good_run(query_id: str, kind: str = "text") -> QueryRun:
    response = make_response(
        [make_group()],
        timings=[
            StepTiming(step="understand", duration_ms=1800.0),
            StepTiming(step="search", duration_ms=3200.0),
            StepTiming(step="rank", duration_ms=400.0),
        ],
    )
    return QueryRun(make_query(query_id, kind), response, None, 5400.0, 5400.0)


def outfit_run(query_id: str = "q04_outfit_casual") -> QueryRun:
    groups = [
        make_group(Category.TOPS, counts=(3, 3, 3, 3)),
        make_group(Category.BOTTOMS, counts=(3, 3, 3, 3), item_index=1),
        make_group(Category.SHOES, counts=(3, 3, 3, 2), item_index=2),
    ]
    response = make_response(groups, understood=make_understand_result(input_type="outfit_photo"))
    return QueryRun(make_query(query_id, "outfit_photo"), response, None, 9000.0, 9000.0)


def weak_run(query_id: str = "q06_text_blazer_budget") -> QueryRun:
    group = make_group(
        counts=(4, 4, 3, 3), targets=(8, 8, 7, 7), stores=("Alpha Store", "Beta Store")
    )
    response = make_response([group], skipped=["gamma-shop"])
    return QueryRun(make_query(query_id), response, None, 31_000.0, 31_000.0)


def scored(
    runs: list[QueryRun], *, labelled: bool = True, with_links: bool = True, **meta_args: Any
) -> ScoredRun:
    link_checks: dict[str, list[LinkCheck]] = {}
    if with_links:
        link_checks = {run.query.id: ok_links(run.response) for run in runs if run.response}
    loaded = LoadedRun(meta(**meta_args), runs, link_checks)
    label_set = None
    if labelled:
        rows: list[LabelRow] = []
        for run in runs:
            wanted = dict.fromkeys(("outerwear", "tops", "bottoms", "shoes"), 8)
            rows.extend(labels_for(run, wanted).rows)
        label_set = LabelSet(tuple(rows))
    return score_run(loaded, labels=label_set)


class TestFollowsTheTemplate:
    def report(self) -> str:
        runs = [good_run("q01_product_jacket", "product_photo"), outfit_run(), weak_run()]
        return render_report(scored(runs))

    def test_it_has_the_templates_sections_in_the_templates_order(self) -> None:
        template = [h for h in headings(TEMPLATE) if h != "# Acceptance results: run N"]
        report = headings(self.report())

        assert report[0] == "# Acceptance results: run 1"
        positions = [report.index(heading) for heading in template]
        assert positions == sorted(positions)

    def test_the_field_table_has_the_templates_fields(self) -> None:
        template_rows = table_after(TEMPLATE, "# Acceptance results: run N")
        report_rows = table_after(self.report(), "# Acceptance results: run 1")

        assert [row[0] for row in report_rows] == [row[0] for row in template_rows]
        assert report_rows[0] == ["Field", "Value"]

    def test_the_results_table_has_the_templates_column_names_exactly(self) -> None:
        template_header = table_after(TEMPLATE, "## Results")[0]
        report_header = table_after(self.report(), "## Results")[0]

        assert report_header == template_header
        assert "Price ranges ok" in report_header

    def test_the_failures_table_has_the_templates_column_names_exactly(self) -> None:
        template_header = table_after(TEMPLATE, "## Failures")[0]

        assert table_after(self.report(), "## Failures")[0] == template_header

    def test_the_results_table_lists_the_queries_in_order(self) -> None:
        rows = table_after(self.report(), "## Results")[1:]

        assert [row[0] for row in rows] == [
            "q01_product_jacket",
            "q04_outfit_casual",
            "q06_text_blazer_budget",
        ]

    def test_the_words_price_range_are_used_never_tier(self) -> None:
        text = self.report()

        assert not re.search(r"\btiers?\b", text, re.IGNORECASE)
        assert "price range" in text.lower()


class TestTheResultsTable:
    def rows(self) -> dict[str, list[str]]:
        runs = [good_run("q01_product_jacket", "product_photo"), outfit_run(), weak_run()]
        table = table_after(render_report(scored(runs)), "## Results")
        return {row[0]: row for row in table[1:]}

    def test_a_good_query_fills_every_cell(self) -> None:
        assert self.rows()["q01_product_jacket"] == [
            "q01_product_jacket",
            "30",
            "3",
            "5.4",
            "30/30",
            "8/10",
            "yes",
        ]

    def test_an_outfit_shows_one_figure_per_garment_as_the_template_describes(self) -> None:
        row = self.rows()["q04_outfit_casual"]

        assert row[1] == "12 / 12 / 11"
        assert row[5] == "8 / 8 / 8"

    def test_a_weak_query_says_which_price_range_missed_and_by_how_much(self) -> None:
        row = self.rows()["q06_text_blazer_budget"]

        expected = (
            "no: Budget 4/8 (gap 4); Mid-range 4/8 (gap 4); Premium 3/7 (gap 4); Luxury 3/7 (gap 4)"
        )
        assert row[6] == expected
        assert row[2] == "2"  # two stores
        assert row[3] == "31.0"


class TestTheVerdict:
    def test_seven_passing_queries_print_pass(self) -> None:
        runs = [good_run(f"q{n:02d}") for n in range(1, 8)] + [
            weak_run(f"q{n:02d}") for n in range(8, 11)
        ]

        text = render_report(scored(runs))

        ids = "q01, q02, q03, q04, q05, q06, q07"
        assert f"**Overall verdict:** 7 of 10 queries pass (list their ids: {ids})" in text
        assert "The demo passes if at least 7 of 10 pass (the rule in `rubric.md`)." in text
        assert "\nVerdict: PASS\n" in text

    def test_six_passing_queries_print_fail(self) -> None:
        runs = [good_run(f"q{n:02d}") for n in range(1, 7)] + [
            weak_run(f"q{n:02d}") for n in range(7, 11)
        ]

        assert "\nVerdict: FAIL\n" in render_report(scored(runs))

    def test_an_unlabelled_run_is_pending_and_says_what_is_missing(self) -> None:
        runs = [good_run(f"q{n:02d}") for n in range(1, 11)]

        text = render_report(scored(runs, labelled=False))

        assert "Verdict: PENDING" in text
        assert "good@10 for 10" in text
        assert "Verdict: PASS" not in text

    def test_an_unlabelled_run_tells_you_how_to_label_it(self) -> None:
        text = render_report(scored([good_run("q01")], labelled=False))

        assert "good@10 is not labelled yet" in text
        assert "--rescore" in text


class TestTheFailuresTable:
    def failures(self) -> list[list[str]]:
        runs = [good_run("q01_product_jacket", "product_photo"), weak_run()]
        return table_after(render_report(scored(runs)), "## Failures")[1:]

    def test_every_failed_criterion_is_a_row_with_a_cause_and_evidence(self) -> None:
        rows = self.failures()

        failed = {row[1] for row in rows}
        assert {"Results", "Seconds", "Stores", "Price ranges ok"} <= failed
        assert all(row[2] in {"store", "ranking", "LLM", "price range"} for row in rows)
        assert all(row[3] for row in rows)
        assert {row[0] for row in rows} == {"q06_text_blazer_budget"}

    def test_a_price_range_failure_is_blamed_on_the_price_range_with_its_span(self) -> None:
        rows = {row[1]: row for row in self.failures()}

        assert rows["Price ranges ok"][2] == "price range"
        assert "Budget: 4 results for a target of 8 (gap 4)" in rows["Price ranges ok"][3]

    def test_a_run_with_no_failures_says_none(self) -> None:
        text = render_report(scored([good_run("q01")]))

        assert table_after(text, "## Failures")[1] == ["none", "", "", ""]

    def test_a_query_that_failed_outright_is_listed_with_the_reason(self) -> None:
        failed = QueryRun(
            make_query("q07_text"),
            None,
            PipelineFailure("llm_failure", "No answer.", "LlmError"),
            200.0,
            200.0,
        )

        rows = table_after(
            render_report(scored([failed], labelled=False, with_links=False)), "## Failures"
        )[1:]

        assert {row[1] for row in rows} == {
            "Results",
            "Stores",
            "Links ok",
            "good@10",
            "Price ranges ok",
        }
        assert all(row[2] == "LLM" and "llm_failure" in row[3] for row in rows)


class TestTheFetchStageAndTheRankStageAreSeparate:
    def report(self) -> str:
        used = [
            make_store_report(
                store_id="alpha", product_count=12, strategy="shopify", dropped={"missing_price": 2}
            ),
            make_store_report(store_id="beta", product_count=9, strategy="css", from_cache=True),
        ]
        response = make_response(
            [make_group(counts=(8, 8, 7, 7))], stores_used=used, skipped=["gamma"]
        )
        run = QueryRun(
            make_query("q01_product_jacket", "product_photo"), response, None, 5000.0, 5000.0
        )
        return render_report(scored([run]))

    def test_the_fetch_stage_shows_each_store_with_strategy_drops_and_cache(self) -> None:
        table = table_after(self.report(), "## Fetch stage")

        assert table[0] == [
            "Query",
            "Store",
            "Status",
            "Valid products",
            "Strategy",
            "Dropped records (reason: count)",
            "Cache hit",
            "ms",
        ]
        rows = {row[1]: row for row in table[1:]}
        assert rows["alpha"][2:7] == ["ok", "12", "shopify", "missing_price: 2", "no"]
        assert rows["beta"][2:7] == ["ok", "9", "css", "none", "yes"]
        assert rows["gamma"][2] == "blocked"

    def test_the_rank_stage_is_a_different_table_with_good_at_10_per_garment_group(self) -> None:
        text = self.report()
        rank = table_after(text, "## Rank stage")

        assert rank[0] == ["Query", "Garment group", "Results in group", "good@10", "Reaches 7"]
        assert rank[1] == ["q01_product_jacket", "outerwear", "30", "8/10", "yes"]
        assert text.index("## Fetch stage") < text.index("## Rank stage")

    def test_an_unlabelled_rank_stage_says_so_and_flags_a_group_too_small_to_pass(self) -> None:
        small = QueryRun(
            make_query("q02"), make_response([make_group(counts=(2, 2, 1, 1))]), None, 1.0, 1.0
        )
        full = good_run("q03")

        rank = table_after(render_report(scored([small, full], labelled=False)), "## Rank stage")[
            1:
        ]

        assert rank[0] == ["q02", "outerwear", "6", "max 6/10", "no"]
        assert rank[1] == ["q03", "outerwear", "30", "not labelled", "pending"]


class TestTimings:
    def test_a_per_step_summary_and_a_per_store_summary(self) -> None:
        runs = [good_run("q01"), good_run("q02")]

        text = render_report(scored(runs))
        steps = {
            row[0]: row for row in table_after(text, "Per step, across all queries (seconds):")[1:]
        }
        stores = table_after(text, "Per store, across all queries:")[1:]

        assert steps["understand"] == ["understand", "2", "1.80", "1.80"]
        assert steps["search"][2] == "3.20"
        assert stores[0][0] == "alpha-store"
        assert stores[0][1] == "2/2"


class TestTheFieldTable:
    def fields(self, **kwargs: Any) -> dict[str, str]:
        table = table_after(
            render_report(scored([good_run("q01")], **kwargs)), "# Acceptance results: run 1"
        )
        return {row[0]: row[1] for row in table[1:]}

    def test_it_reports_the_date_model_prompt_version_stores_and_mix(self) -> None:
        fields = self.fields()

        assert fields["Date"] == "2026-10-07"
        assert fields["Run"] == "1 (live, recorded)"
        assert fields["Model snapshot"] == "test-model-2026-01-01"
        assert fields["Prompt version"] == "test-1"
        assert fields["Stores working"] == "3: alpha-store, beta-store, gamma-store"
        assert fields["Price-range mix"] == "25 / 25 / 25 / 25 (even)"

    def test_the_value_first_mix_is_named(self) -> None:
        assert (
            self.fields(price_range_mix=[40, 30, 20, 10])["Price-range mix"]
            == "40 / 30 / 20 / 10 (value first)"
        )

    def test_a_replay_says_what_it_replayed(self) -> None:
        run = self.fields(mode="replay", source="eval/results/run-1/recording")["Run"]

        assert run == "1 (replay of eval/results/run-1/recording)"

    def test_a_mock_run_says_it_is_not_real(self) -> None:
        text = render_report(scored([good_run("q01")], mode="mock", number=None))

        assert text.startswith("# Acceptance results: run mock\n")
        assert "not a real run" in text
        assert "Mock run:" in text

    def test_stores_that_never_worked_are_listed(self) -> None:
        runs = [weak_run()]

        text = render_report(scored(runs))

        assert "(never worked: gamma-shop)" in text


class TestNotes:
    def test_an_outfit_run_says_the_checks_are_per_garment(self) -> None:
        text = render_report(scored([outfit_run()]))

        assert "Outfit photos (q04_outfit_casual): the price-range check and good@10" in text
        assert "are applied per garment group" in text
        assert "20-result floor is applied to the total" in text

    def test_a_run_without_outfits_does_not_mention_them(self) -> None:
        assert "Outfit photos" not in render_report(scored([good_run("q01")]))

    @pytest.mark.parametrize(
        ("mode", "phrase"),
        [
            (LinksMode.ALL, "checked every result"),
            (LinksMode.TOP10, "top 10 of each garment group only"),
            (LinksMode.NONE, "not checked in this run"),
        ],
    )
    def test_the_link_scope_is_stated(self, mode: LinksMode, phrase: str) -> None:
        run = good_run("q01")

        text = render_report(scored([run], with_links=mode is not LinksMode.NONE, links=mode))

        assert "Point 4" in text
        assert phrase in text


class TestUntrustedText:
    def test_escape_keeps_text_on_one_line_and_neutralises_markup(self) -> None:
        assert escape("a | b\n<script>*x*` [l](u)") == "a \\| b \\<script\\>\\*x\\*\\` \\[l\\](u)"

    def test_a_hostile_title_cannot_add_columns_or_markup_to_the_failures_table(self) -> None:
        evil = make_product(
            1, title="Evil | Blazer <img src=x onerror=alert(1)> **bold**", price=120.0
        )
        group = make_group(counts=(8, 8, 7, 7))
        first = group.tiers[0].results[0].model_copy(update={"product": evil})
        tier = group.tiers[0].model_copy(update={"results": [first, *group.tiers[0].results[1:]]})
        group = group.model_copy(update={"tiers": [tier, *group.tiers[1:]]})
        response = make_response([group])
        run = QueryRun(make_query("q06"), response, None, 1.0, 1.0)
        labels = labels_for(run, {"outerwear": 0})
        loaded = LoadedRun(meta(), [run], {"q06": ok_links(response)})

        text = render_report(score_run(loaded, labels=labels))

        failures = table_after(text, "## Failures")
        assert all(len(row) == 4 for row in failures)
        assert not re.search(r"(?<!\\)<", text)  # every "<" is escaped
        assert not re.search(r"(?<!\\)\*\*bold", text)
        assert "Evil \\| Blazer" in text
