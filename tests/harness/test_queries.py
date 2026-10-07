"""11.1.1: the query loader validates the frozen acceptance queries and says what is wrong."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from eval.harness.errors import MissingImageError, QueryFileError
from eval.harness.queries import (
    EXPECTED_MIX,
    QUERIES_PATH,
    AcceptanceQuery,
    check_images_exist,
    load_queries,
    parse_queries,
    read_query_image,
)

from vga.models import InputType

JACKET = "eval/data/assets/private/product_jacket.jpg"


def entry(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "q01_product_jacket",
        "type": "product_photo",
        "text": None,
        "image": JACKET,
        "notes": "One jacket on a plain background.",
    }
    return {**fields, **overrides}


def mix_of_ten() -> list[dict[str, Any]]:
    """Ten valid entries with the PRD mix: 3 product, 2 outfit, 3 text, 2 photo + text."""
    entries: list[dict[str, Any]] = []
    shapes = [
        ("product_photo", None, JACKET, 3),
        ("outfit_photo", None, "eval/data/assets/private/outfit_casual.jpg", 2),
        ("text", "black blazer", None, 3),
        ("photo_text", "but in black", JACKET, 2),
    ]
    for kind, text, image, count in shapes:
        for _ in range(count):
            entries.append(
                entry(id=f"q{len(entries) + 1:02d}_{kind}", type=kind, text=text, image=image)
            )
    return entries


def write_yaml(tmp_path: Path, queries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "queries.yaml"
    path.write_text(yaml.safe_dump({"queries": queries}, allow_unicode=True), encoding="utf-8")
    return path


class TestTheFrozenQueryFile:
    def test_loads_ten_queries_with_the_prd_mix_without_the_private_photos(self) -> None:
        queries = load_queries(QUERIES_PATH, require_images=False)

        assert len(queries) == 10
        kinds = {kind: sum(q.type is kind for q in queries) for kind in InputType}
        assert kinds == EXPECTED_MIX

    def test_keeps_the_arabic_text_intact(self) -> None:
        queries = {q.id: q for q in load_queries(QUERIES_PATH, require_images=False)}

        assert (
            queries["q07_text_arabic_shirt"].text
            == "أريد قميصاً أبيض من القطن للرجال بأقل من 200 درهم"
        )

    def test_photo_plus_text_queries_reuse_the_product_photos(self) -> None:
        queries = {q.id: q for q in load_queries(QUERIES_PATH, require_images=False)}

        assert queries["q09_photo_text_jacket_brown"].image == queries["q01_product_jacket"].image
        assert queries["q10_photo_text_jeans_black"].image == queries["q03_product_jeans"].image


class TestAMissingPhoto:
    def test_names_the_file_and_points_to_the_assets_guide(self, tmp_path: Path) -> None:
        path = write_yaml(tmp_path, mix_of_ten())

        with pytest.raises(MissingImageError) as caught:
            load_queries(path, repo_root=tmp_path, require_images=True)

        message = str(caught.value)
        assert JACKET in message
        assert "eval/data/ASSETS.md" in message

    def test_lists_each_missing_file_once_with_the_queries_that_use_it(
        self, tmp_path: Path
    ) -> None:
        path = write_yaml(tmp_path, mix_of_ten())

        with pytest.raises(MissingImageError) as caught:
            load_queries(path, repo_root=tmp_path)

        message = str(caught.value)
        assert message.count(JACKET) == 1
        assert "q01_product_photo" in message
        assert "q09_photo_text" in message

    def test_is_not_an_error_when_photos_are_not_required(self, tmp_path: Path) -> None:
        path = write_yaml(tmp_path, mix_of_ten())

        queries = load_queries(path, repo_root=tmp_path, require_images=False)

        assert len(queries) == 10

    def test_passes_when_every_photo_exists(self, tmp_path: Path) -> None:
        path = write_yaml(tmp_path, mix_of_ten())
        for query in load_queries(path, repo_root=tmp_path, require_images=False):
            if query.image:
                target = tmp_path / query.image
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"photo")

        assert len(load_queries(path, repo_root=tmp_path)) == 10

    def test_reading_an_absent_photo_raises_the_same_clear_error(self, tmp_path: Path) -> None:
        query = AcceptanceQuery.model_validate(entry())

        with pytest.raises(MissingImageError, match=r"ASSETS\.md"):
            read_query_image(query, tmp_path)

    def test_reading_a_present_photo_returns_its_bytes_and_a_text_query_has_none(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / JACKET
        target.parent.mkdir(parents=True)
        target.write_bytes(b"jacket-bytes")
        photo = AcceptanceQuery.model_validate(entry())
        text = AcceptanceQuery.model_validate(
            entry(id="q06_text", type="text", text="blazer", image=None)
        )

        assert read_query_image(photo, tmp_path) == b"jacket-bytes"
        assert read_query_image(text, tmp_path) is None

    def test_check_images_exist_accepts_text_only_queries(self, tmp_path: Path) -> None:
        text = AcceptanceQuery.model_validate(
            entry(id="q06_text", type="text", text="blazer", image=None)
        )

        check_images_exist([text], tmp_path)


class TestValidation:
    def test_a_bad_type_names_the_query_and_the_field(self) -> None:
        raw = {"queries": [entry(type="photo")]}

        with pytest.raises(QueryFileError) as caught:
            parse_queries(raw, check_mix=False)

        message = str(caught.value)
        assert "q01_product_jacket" in message
        assert "field 'type'" in message

    def test_a_missing_field_is_named(self) -> None:
        bad = entry()
        del bad["notes"]

        with pytest.raises(QueryFileError, match="field 'notes'"):
            parse_queries({"queries": [bad]}, check_mix=False)

    def test_an_extra_field_is_rejected(self) -> None:
        with pytest.raises(QueryFileError, match="field 'colour'"):
            parse_queries({"queries": [entry(colour="black")]}, check_mix=False)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"text": "a jacket"},
            {"type": "text", "text": None, "image": None},
            {"type": "text", "text": "jacket"},
            {"type": "photo_text", "text": None},
            {"type": "photo_text", "text": "darker", "image": None},
            {"type": "outfit_photo", "image": None},
        ],
        ids=[
            "photo_only_with_text",
            "text_without_words",
            "text_with_image",
            "photo_text_without_words",
            "photo_text_without_image",
            "outfit_without_image",
        ],
    )
    def test_a_type_that_does_not_match_its_inputs_is_rejected(
        self, overrides: dict[str, Any]
    ) -> None:
        with pytest.raises(QueryFileError, match="needs"):
            parse_queries({"queries": [entry(**overrides)]}, check_mix=False)

    @pytest.mark.parametrize(
        "image",
        [
            "/etc/passwd.jpg",
            "eval/data/assets/../../secret.jpg",
            "other/folder/jacket.jpg",
            "eval/data/assets/private/jacket.gif",
        ],
    )
    def test_an_image_path_outside_the_assets_folder_is_rejected(self, image: str) -> None:
        with pytest.raises(QueryFileError, match="field 'image'"):
            parse_queries({"queries": [entry(image=image)]}, check_mix=False)

    def test_an_empty_text_string_is_rejected(self) -> None:
        bad = entry(type="text", text="", image=None)

        with pytest.raises(QueryFileError, match="field 'text'"):
            parse_queries({"queries": [bad]}, check_mix=False)

    def test_a_bad_id_is_rejected(self) -> None:
        with pytest.raises(QueryFileError, match="field 'id'"):
            parse_queries({"queries": [entry(id="Q 01!")]}, check_mix=False)

    def test_repeated_ids_are_reported(self) -> None:
        raw = {"queries": [entry(), entry()]}

        with pytest.raises(QueryFileError, match=r"unique.*q01_product_jacket"):
            parse_queries(raw, check_mix=False)

    def test_every_problem_is_reported_in_one_message(self) -> None:
        raw = {"queries": [entry(type="photo"), entry(id="q02_x", image="elsewhere/a.jpg")]}

        with pytest.raises(QueryFileError) as caught:
            parse_queries(raw, check_mix=False)

        message = str(caught.value)
        assert "query #1" in message
        assert "query #2" in message

    def test_the_mix_must_follow_the_prd(self) -> None:
        raw = {"queries": mix_of_ten()[:9]}

        with pytest.raises(QueryFileError, match="mix must be"):
            parse_queries(raw)

    def test_a_different_mix_is_allowed_when_not_checked(self) -> None:
        assert len(parse_queries({"queries": mix_of_ten()[:9]}, check_mix=False)) == 9

    @pytest.mark.parametrize("raw", [None, [], {"other": []}, {"queries": []}, {"queries": "x"}])
    def test_the_top_level_shape_is_checked(self, raw: Any) -> None:
        with pytest.raises(QueryFileError, match="queries"):
            parse_queries(raw)

    def test_an_entry_that_is_not_a_mapping_is_reported(self) -> None:
        with pytest.raises(QueryFileError, match="query #1"):
            parse_queries({"queries": ["q01"]}, check_mix=False)


class TestTheFile:
    def test_a_missing_file_has_a_plain_message(self, tmp_path: Path) -> None:
        with pytest.raises(QueryFileError, match="could not be read"):
            load_queries(tmp_path / "nope.yaml")

    def test_broken_yaml_has_a_plain_message(self, tmp_path: Path) -> None:
        path = tmp_path / "queries.yaml"
        path.write_text("queries: [unclosed", encoding="utf-8")

        with pytest.raises(QueryFileError, match="not valid YAML"):
            load_queries(path)
