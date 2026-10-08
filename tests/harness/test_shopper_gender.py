"""The shopper's answer to "Who is this for?" in the query files.

A query may record what the shopper would answer if the app asked (``shopper_gender``: women or
men). Absent means no answer, which is today's behaviour. The seven photo-based acceptance queries
and the eleven extra photos all show women's clothing, so they record women; the three text queries
state or omit their gender in their own words and record nothing.
"""

from typing import Any

import pytest
import yaml

from eval.harness.errors import QueryFileError
from eval.harness.queries import (
    EXTRA_QUERIES_PATH,
    QUERIES_PATH,
    AcceptanceQuery,
    load_queries,
    parse_queries,
)
from tests.harness.helpers import make_query
from vga.models import Gender, InputType

PHOTO_BASED = [
    "q01_product_gown",
    "q02_product_abaya",
    "q03_product_skinny_jeans",
    "q04_outfit_palazzo_top",
    "q05_outfit_dress_heels",
    "q09_photo_text_gown_green",
    "q10_photo_text_jeans_black",
]
TEXT_ONLY = ["q06_text_blazer_budget", "q07_text_arabic_shirt", "q08_text_wide_leg_jeans"]


def entry(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "q01_product_gown",
        "type": "product_photo",
        "text": None,
        "image": "eval/data/assets/private/dress_burgundy_gown.png",
        "notes": "A burgundy gown.",
    }
    return {**fields, **overrides}


class TestTheField:
    def test_absent_means_the_shopper_gives_no_answer(self) -> None:
        [query] = parse_queries({"queries": [entry()]}, check_mix=False)

        assert query.shopper_gender is None

    @pytest.mark.parametrize(("word", "gender"), [("women", Gender.WOMEN), ("men", Gender.MEN)])
    def test_women_and_men_are_read_from_the_file(self, word: str, gender: Gender) -> None:
        [query] = parse_queries({"queries": [entry(shopper_gender=word)]}, check_mix=False)

        assert query.shopper_gender is gender

    def test_an_explicit_null_is_the_same_as_leaving_it_out(self) -> None:
        [query] = parse_queries({"queries": [entry(shopper_gender=None)]}, check_mix=False)

        assert query.shopper_gender is None

    def test_unisex_is_refused_and_the_message_says_how_to_show_both(self) -> None:
        with pytest.raises(QueryFileError) as caught:
            parse_queries({"queries": [entry(shopper_gender="unisex")]}, check_mix=False)

        message = str(caught.value)
        assert "q01_product_gown" in message
        assert "field 'shopper_gender'" in message
        assert "'women' or 'men'" in message
        assert "leave it out" in message

    @pytest.mark.parametrize("word", ["woman", "female", "both", "", "Women"])
    def test_any_other_word_is_refused_naming_the_query_and_the_field(self, word: str) -> None:
        with pytest.raises(QueryFileError) as caught:
            parse_queries({"queries": [entry(shopper_gender=word)]}, check_mix=False)

        assert "q01_product_gown" in str(caught.value)
        assert "field 'shopper_gender'" in str(caught.value)

    def test_it_is_allowed_on_a_query_of_any_type(self) -> None:
        for kind in ("product_photo", "outfit_photo", "text", "photo_text"):
            query = make_query(f"q_{kind}", kind, shopper_gender="men")

            assert query.shopper_gender is Gender.MEN

    def test_it_survives_a_round_trip_through_json(self) -> None:
        query = make_query("q01_photo", "product_photo", shopper_gender="women")

        again = AcceptanceQuery.model_validate_json(query.model_dump_json())

        assert again == query


def by_id(path: object) -> dict[str, AcceptanceQuery]:
    return {q.id: q for q in load_queries(path, require_images=False, check_mix=False)}  # type: ignore[arg-type]


class TestTheAcceptanceFile:
    def test_the_seven_photo_based_queries_record_women(self) -> None:
        queries = by_id(QUERIES_PATH)

        assert {qid: queries[qid].shopper_gender for qid in PHOTO_BASED} == dict.fromkeys(
            PHOTO_BASED, Gender.WOMEN
        )
        assert all(queries[qid].image is not None for qid in PHOTO_BASED)

    def test_the_three_text_queries_record_nothing(self) -> None:
        queries = by_id(QUERIES_PATH)

        assert {qid: queries[qid].shopper_gender for qid in TEXT_ONLY} == dict.fromkeys(TEXT_ONLY)
        assert all(queries[qid].type is InputType.TEXT for qid in TEXT_ONLY)

    def test_every_query_with_a_photo_records_an_answer_and_every_one_without_does_not(
        self,
    ) -> None:
        for query in by_id(QUERIES_PATH).values():
            assert (query.shopper_gender is not None) == (query.image is not None), query.id

    def test_the_file_still_has_the_prd_mix(self) -> None:
        assert len(load_queries(QUERIES_PATH, require_images=False)) == 10

    def test_the_header_documents_the_field(self) -> None:
        header = QUERIES_PATH.read_text(encoding="utf-8").split("queries:\n", 1)[0]

        assert "shopper_gender" in header
        assert "Who is this for?" in header

    def test_no_other_field_was_added_to_any_entry(self) -> None:
        raw = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))

        for entry_ in raw["queries"]:
            assert set(entry_) <= {"id", "type", "text", "image", "shopper_gender", "notes"}


class TestTheExtraFile:
    def test_all_eleven_extra_photos_record_women(self) -> None:
        queries = by_id(EXTRA_QUERIES_PATH)

        assert len(queries) == 11
        assert {q.shopper_gender for q in queries.values()} == {Gender.WOMEN}

    def test_no_other_field_was_added_to_any_entry(self) -> None:
        raw = yaml.safe_load(EXTRA_QUERIES_PATH.read_text(encoding="utf-8"))

        for entry_ in raw["queries"]:
            assert set(entry_) <= {"id", "type", "text", "image", "shopper_gender", "notes"}


class TestWhatALabellerIsToldAboutIt:
    @pytest.mark.parametrize("name", ["rubric.md", "results-template.md"])
    def test_the_labelling_documents_say_the_results_are_the_ones_after_the_answer(
        self, name: str
    ) -> None:
        text = (QUERIES_PATH.parent / name).read_text(encoding="utf-8")

        assert "Who is this for?" in text
        assert "shown after" in text
