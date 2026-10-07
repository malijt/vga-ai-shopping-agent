"""11.3.2: export a blank labelling sheet, import it filled, compute good@10."""

import csv
from collections.abc import Callable
from pathlib import Path

import pytest

from eval.harness.errors import LabelSheetError
from eval.harness.groups import TOP_N
from eval.harness.labels import (
    LABEL_COLUMNS,
    export_label_sheet,
    good_at_10,
    import_label_sheet,
    label_rows,
)
from eval.harness.runner import PipelineFailure, QueryRun
from tests.factories import make_product, make_scored_product, make_scores
from tests.harness.helpers import make_group, make_query, make_response
from vga.models import Category, GarmentGroup, Tier, TierResult


def run_of(query_id: str, *groups: GarmentGroup) -> QueryRun:
    return QueryRun(make_query(query_id), make_response(list(groups)), None, 1.0, 1.0)


def sample_runs() -> list[QueryRun]:
    """A one-group query (30 results) and an outfit query (tops 30, shoes 6)."""
    return [
        run_of("q06_text", make_group(Category.OUTERWEAR, counts=(8, 8, 7, 7))),
        run_of(
            "q04_outfit",
            make_group(Category.TOPS, counts=(8, 8, 7, 7)),
            make_group(Category.SHOES, counts=(2, 2, 1, 1), item_index=1),
        ),
    ]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LABEL_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def fill(path: Path, decide: Callable[[dict[str, str]], str]) -> None:
    rows = read_rows(path)
    for row in rows:
        row["label"] = decide(row)
    write_rows(path, rows)


class TestExport:
    def test_the_sheet_has_exactly_the_agreed_columns_and_a_blank_label(
        self, tmp_path: Path
    ) -> None:
        export_label_sheet(sample_runs(), tmp_path / "labels.csv")

        with (tmp_path / "labels.csv").open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        rows = read_rows(tmp_path / "labels.csv")

        assert header == [
            "query_id",
            "photo",
            "group",
            "rank",
            "title",
            "price",
            "store",
            "price_range",
            "url",
            "label",
        ]
        assert all(row["label"] == "" for row in rows)

    def test_each_row_has_what_a_person_needs_to_judge_the_product(self, tmp_path: Path) -> None:
        group = make_group(Category.DRESSES, counts=(3, 3, 2, 2))
        photo_run = QueryRun(
            make_query("q01_product_gown", "product_photo"), make_response([group]), None, 1.0, 1.0
        )
        export_label_sheet([photo_run], tmp_path / "labels.csv")

        by_title = {row["title"]: row for row in read_rows(tmp_path / "labels.csv")}

        first = by_title["Dresses item 1"]
        assert first["photo"] == "dress_burgundy_gown.png"  # the file name, not the whole path
        assert first["price"] == "100 AED"
        assert first["price_range"] == "Budget"
        assert first["store"] == "Alpha Store"
        assert first["url"] == "https://www.alpha-store.example/p/dresses-0-1"
        assert by_title["Dresses item 7"]["price_range"] == "Premium"
        assert by_title["Dresses item 10"]["price_range"] == "Luxury"
        assert {row["price_range"] for row in by_title.values()} == {
            "Budget",
            "Mid-range",
            "Premium",
            "Luxury",
        }

    def test_a_text_only_query_has_an_empty_photo_cell(self, tmp_path: Path) -> None:
        export_label_sheet(
            [run_of("q06_text", make_group(Category.OUTERWEAR))], tmp_path / "labels.csv"
        )

        assert {row["photo"] for row in read_rows(tmp_path / "labels.csv")} == {""}

    def test_a_price_with_cents_keeps_them(self, tmp_path: Path) -> None:
        group = make_group(Category.OUTERWEAR, counts=(1, 0, 0, 0))
        priced = group.tiers[0].results[0].product.model_copy(update={"price": 349.5})
        group.tiers[0].results[0] = group.tiers[0].results[0].model_copy(update={"product": priced})
        group.tiers[0] = group.tiers[0].model_copy(update={"price_min": 349.5, "price_max": 349.5})

        export_label_sheet([run_of("q06_text", group)], tmp_path / "labels.csv")

        assert read_rows(tmp_path / "labels.csv")[0]["price"] == "349.50 AED"

    def test_an_outfit_has_one_block_of_rows_per_garment_each_with_the_same_photo(
        self, tmp_path: Path
    ) -> None:
        # Assumption A20: an outfit is judged garment by garment, so rows are grouped by garment.
        outfit = QueryRun(
            make_query("q05_outfit_dress_heels", "outfit_photo"),
            make_response(
                [
                    make_group(Category.DRESSES, counts=(3, 3, 2, 2)),
                    make_group(Category.SHOES, counts=(3, 3, 2, 2), item_index=1),
                ]
            ),
            None,
            1.0,
            1.0,
        )
        export_label_sheet([outfit], tmp_path / "labels.csv")

        rows = read_rows(tmp_path / "labels.csv")

        assert [row["group"] for row in rows] == ["dresses"] * 10 + ["shoes"] * 10
        assert {row["photo"] for row in rows} == {"dress_burgundy_gown.png"}
        assert [int(row["rank"]) for row in rows] == list(range(1, 11)) * 2

    def test_every_group_gets_its_top_ten_and_a_short_group_gets_what_it_has(
        self, tmp_path: Path
    ) -> None:
        count = export_label_sheet(sample_runs(), tmp_path / "labels.csv")
        rows = read_rows(tmp_path / "labels.csv")

        per_group: dict[tuple[str, str], int] = {}
        for row in rows:
            key = (row["query_id"], row["group"])
            per_group[key] = per_group.get(key, 0) + 1
        assert per_group == {
            ("q06_text", "outerwear"): 10,
            ("q04_outfit", "tops"): 10,
            ("q04_outfit", "shoes"): 6,
        }
        assert count == 26

    def test_rows_follow_query_order_then_group_then_rank(self, tmp_path: Path) -> None:
        export_label_sheet(sample_runs(), tmp_path / "labels.csv")

        rows = read_rows(tmp_path / "labels.csv")

        assert [row["query_id"] for row in rows][:1] == ["q06_text"]
        outfit = [row for row in rows if row["query_id"] == "q04_outfit"]
        assert [row["group"] for row in outfit] == ["tops"] * 10 + ["shoes"] * 6
        assert [int(row["rank"]) for row in outfit[:10]] == list(range(1, 11))

    def test_the_top_ten_is_by_match_score_across_price_ranges_not_by_price(
        self, tmp_path: Path
    ) -> None:
        # The best match sits in the most expensive price range, the worst in the cheapest.
        group = make_group(Category.OUTERWEAR, counts=(4, 4, 4, 4), total=lambda i: i / 100)

        rows = label_rows([run_of("q06_text", group)])

        price_of = {
            scored.product.title: scored.product.price
            for tier in group.tiers
            for scored in tier.results
        }
        sheet_prices = [price_of[row.title] for row in rows]
        assert len(rows) == TOP_N
        assert rows[0].title == "Outerwear item 16"  # the best match is in the Luxury range
        assert sheet_prices == sorted(sheet_prices, reverse=True)  # best match first, dearest here

    def test_a_query_without_a_response_has_no_rows(self) -> None:
        failed = QueryRun(make_query("q06_text"), None, PipelineFailure("x", "y", "Z"), 1.0, 1.0)

        assert label_rows([failed]) == []

    def test_a_malicious_title_cannot_become_a_spreadsheet_formula(self, tmp_path: Path) -> None:
        evil = make_product(
            1, title='=HYPERLINK("https://evil.example","click")', store="+cmd", price=120.0
        )
        tier = TierResult(
            name=Tier.BUDGET,
            price_min=120.0,
            price_max=120.0,
            currency="AED",
            target_count=1,
            count=1,
            results=[make_scored_product(evil, scores=make_scores(total=0.9))],
        )
        empty = [TierResult(name=name, target_count=0, count=0) for name in list(Tier)[1:]]
        group = GarmentGroup(item_index=0, category=Category.OUTERWEAR, tiers=[tier, *empty])

        export_label_sheet([run_of("q06_text", group)], tmp_path / "labels.csv")

        row = read_rows(tmp_path / "labels.csv")[0]
        assert row["title"].startswith("'=")
        assert row["store"].startswith("'+")

    def test_arabic_and_awkward_characters_survive_the_file(self, tmp_path: Path) -> None:
        awkward = make_product(1, title='قميص "قطن", أبيض\nللرجال', price=120.0)  # noqa: RUF001
        tier = TierResult(
            name=Tier.BUDGET,
            price_min=120.0,
            price_max=120.0,
            currency="AED",
            target_count=1,
            count=1,
            results=[make_scored_product(awkward, scores=make_scores(total=0.9))],
        )
        empty = [TierResult(name=name, target_count=0, count=0) for name in list(Tier)[1:]]
        group = GarmentGroup(item_index=0, category=Category.TOPS, tiers=[tier, *empty])

        export_label_sheet([run_of("q07", group)], tmp_path / "labels.csv")

        assert read_rows(tmp_path / "labels.csv")[0]["title"] == 'قميص "قطن", أبيض للرجال'


class TestImport:
    def test_a_filled_sheet_round_trips_into_good_at_10(self, tmp_path: Path) -> None:
        runs = sample_runs()
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        # Good for ranks 1-8 of the outerwear group and ranks 1-7 of tops; shoes: 3 good.
        limits = {"outerwear": 8, "tops": 7, "shoes": 3}
        fill(sheet, lambda row: "1" if int(row["rank"]) <= limits[row["group"]] else "0")

        labels = import_label_sheet(sheet, runs)

        assert [g.cell for g in good_at_10("q06_text", runs[0], labels)] == ["8/10"]
        outfit = good_at_10("q04_outfit", runs[1], labels)
        assert [(g.group, g.good, g.rows) for g in outfit] == [("tops", 7, 10), ("shoes", 3, 6)]

    def test_exactly_the_labels_one_and_zero_are_accepted_with_padding(
        self, tmp_path: Path
    ) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: " 1 " if row["rank"] == "1" else "0 ")

        labels = import_label_sheet(sheet, runs)

        assert good_at_10("q06_text", runs[0], labels)[0].good == 1

    @pytest.mark.parametrize("bad", ["", "yes", "2", "1.0", "good", "-1", "true"])
    def test_any_other_label_is_an_error_naming_the_row(self, tmp_path: Path, bad: str) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: bad if row["rank"] == "3" else "1")

        with pytest.raises(LabelSheetError) as caught:
            import_label_sheet(sheet, runs)

        message = str(caught.value)
        assert "row 4" in message  # header is row 1, so rank 3 is row 4
        assert "q06_text, outerwear, rank 3" in message
        assert "label must be 1 or 0" in message

    def test_every_problem_is_listed_so_one_pass_fixes_them_all(self, tmp_path: Path) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: {"2": "maybe", "5": ""}.get(row["rank"], "1"))

        with pytest.raises(LabelSheetError) as caught:
            import_label_sheet(sheet, runs)

        message = str(caught.value)
        assert "rank 2" in message
        assert "rank 5" in message
        assert "got 'maybe'" in message
        assert "got blank" in message

    def test_a_row_that_was_removed_is_reported_as_missing(self, tmp_path: Path) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: "1")
        write_rows(sheet, [row for row in read_rows(sheet) if row["rank"] != "4"])

        with pytest.raises(LabelSheetError, match="missing row for q06_text, outerwear, rank 4"):
            import_label_sheet(sheet, runs)

    def test_a_row_that_appears_twice_is_reported(self, tmp_path: Path) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: "1")
        rows = read_rows(sheet)
        write_rows(sheet, [*rows, rows[0]])

        with pytest.raises(LabelSheetError, match="appears twice"):
            import_label_sheet(sheet, runs)

    def test_a_sheet_from_another_run_is_refused(self, tmp_path: Path) -> None:
        sheet = tmp_path / "labels.csv"
        export_label_sheet(sample_runs()[:1], sheet)
        fill(sheet, lambda row: "1")
        other = [
            run_of(
                "q06_text",
                make_group(Category.OUTERWEAR, counts=(8, 8, 7, 7), stores=("Other Shop",)),
            )
        ]

        with pytest.raises(LabelSheetError, match="from another run"):
            import_label_sheet(sheet, other)

    def test_a_row_for_a_query_the_run_does_not_have_is_refused(self, tmp_path: Path) -> None:
        sheet = tmp_path / "labels.csv"
        export_label_sheet(sample_runs(), sheet)
        fill(sheet, lambda row: "1")

        with pytest.raises(LabelSheetError, match="has no result there"):
            import_label_sheet(sheet, sample_runs()[:1])

    def test_a_rank_that_is_not_a_number_is_named(self, tmp_path: Path) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        rows = read_rows(sheet)
        rows[0]["rank"] = "first"
        write_rows(sheet, rows)

        with pytest.raises(LabelSheetError, match="rank must be a whole number"):
            import_label_sheet(sheet, runs)

    @pytest.mark.parametrize(
        "header",
        [
            "query_id,group,rank,title,store,url",
            "query_id,rank,group,title,store,url,label",
            "query_id,group,rank,title,store,url,label,notes",
        ],
    )
    def test_the_columns_must_be_exactly_the_agreed_ones(self, tmp_path: Path, header: str) -> None:
        sheet = tmp_path / "labels.csv"
        sheet.write_text(header + "\n", encoding="utf-8")

        with pytest.raises(LabelSheetError, match="exactly these columns"):
            import_label_sheet(sheet, sample_runs())

    def test_a_missing_file_has_a_plain_message(self, tmp_path: Path) -> None:
        with pytest.raises(LabelSheetError, match="could not be read"):
            import_label_sheet(tmp_path / "nothing.csv", sample_runs())

    def test_a_long_list_of_problems_is_cut_short_with_a_count(self, tmp_path: Path) -> None:
        runs = sample_runs()
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: "")

        with pytest.raises(LabelSheetError, match=r"\.\.\. and 11 more"):
            import_label_sheet(sheet, runs)

    def test_a_file_saved_without_the_byte_order_mark_is_read_too(self, tmp_path: Path) -> None:
        runs = sample_runs()[:1]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: "1")
        sheet.write_text(sheet.read_text(encoding="utf-8-sig"), encoding="utf-8")

        assert import_label_sheet(sheet, runs)


class TestGoodAtTen:
    def test_a_group_with_fewer_than_ten_results_still_counts_out_of_ten(
        self, tmp_path: Path
    ) -> None:
        runs = [run_of("q02", make_group(Category.SHOES, counts=(2, 2, 1, 1)))]
        sheet = tmp_path / "labels.csv"
        export_label_sheet(runs, sheet)
        fill(sheet, lambda row: "1")

        figure = good_at_10("q02", runs[0], import_label_sheet(sheet, runs))[0]

        assert (figure.good, figure.rows, figure.top_n, figure.cell) == (6, 6, 10, "6/10")

    def test_a_query_that_failed_has_no_figures(self, tmp_path: Path) -> None:
        failed = QueryRun(make_query("q06_text"), None, PipelineFailure("x", "y", "Z"), 1.0, 1.0)
        sheet = tmp_path / "labels.csv"
        export_label_sheet([failed], sheet)

        assert good_at_10("q06_text", failed, import_label_sheet(sheet, [failed])) == []
