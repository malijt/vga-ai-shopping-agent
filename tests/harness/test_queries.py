"""11.1.1: the query loader validates the frozen acceptance queries and says what is wrong."""

from pathlib import Path, PurePosixPath
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

GOWN_PHOTO = "eval/data/assets/private/dress_burgundy_gown.png"
EXTRA_QUERIES_PATH = QUERIES_PATH.parent / "extra_queries.yaml"


def entry(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "q01_product_gown",
        "type": "product_photo",
        "text": None,
        "image": GOWN_PHOTO,
        "notes": "One gown on a plain background.",
    }
    return {**fields, **overrides}


def mix_of_ten() -> list[dict[str, Any]]:
    """Ten valid entries with the PRD mix: 3 product, 2 outfit, 3 text, 2 photo + text."""
    entries: list[dict[str, Any]] = []
    shapes = [
        ("product_photo", None, GOWN_PHOTO, 3),
        (
            "outfit_photo",
            None,
            "eval/data/assets/private/outfit_navy_print_palazzo_white_top.png",
            2,
        ),
        ("text", "black blazer", None, 3),
        ("photo_text", "but in black", GOWN_PHOTO, 2),
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

        assert queries["q09_photo_text_gown_green"].image == queries["q01_product_gown"].image
        assert (
            queries["q10_photo_text_jeans_black"].image == queries["q03_product_skinny_jeans"].image
        )

    def test_the_seven_photo_queries_use_the_photos_the_business_supplied(self) -> None:
        queries = {q.id: q for q in load_queries(QUERIES_PATH, require_images=False)}
        private = "eval/data/assets/private/"

        assert {qid: q.image for qid, q in queries.items() if q.image} == {
            "q01_product_gown": private + "dress_burgundy_gown.png",
            "q02_product_abaya": private + "dress_pink_embellished_abaya.png",
            "q03_product_skinny_jeans": private + "bottoms_light_blue_skinny_jeans.png",
            "q04_outfit_palazzo_top": private + "outfit_navy_print_palazzo_white_top.png",
            "q05_outfit_dress_heels": private + "outfit_black_dress_heels.png",
            "q09_photo_text_gown_green": private + "dress_burgundy_gown.png",
            "q10_photo_text_jeans_black": private + "bottoms_light_blue_skinny_jeans.png",
        }

    def test_the_photo_and_text_queries_carry_the_requested_words(self) -> None:
        queries = {q.id: q for q in load_queries(QUERIES_PATH, require_images=False)}

        assert queries["q09_photo_text_gown_green"].text == "similar but dark green and cheaper"
        assert queries["q10_photo_text_jeans_black"].text == "same cut but in black, under 250 AED"

    def test_the_three_text_queries_are_exactly_as_they_were_before_the_scope_change(
        self,
    ) -> None:
        queries = {q.id: q for q in load_queries(QUERIES_PATH, require_images=False)}

        assert (
            queries["q06_text_blazer_budget"].text == "black oversized blazer for men under 400 AED"
        )
        assert (
            queries["q07_text_arabic_shirt"].text
            == "أريد قميصاً أبيض من القطن للرجال بأقل من 200 درهم"
        )
        assert queries["q08_text_wide_leg_jeans"].text == (
            "women's high-waisted wide-leg jeans in light blue"
        )

    def test_the_old_query_ids_and_photo_names_are_gone(self) -> None:
        raw = QUERIES_PATH.read_text(encoding="utf-8")

        for old in ("product_jacket", "product_sneakers", "outfit_casual", "outfit_layered"):
            assert old not in raw


class TestTheExtraQueryFile:
    """The 11 photos that are not part of the 10-query pass rule."""

    EXTRA = [
        "dress_floral_kaftan.png",
        "dress_taupe_button_abaya.png",
        "dress_blue_embroidered_abaya.png",
        "dress_grey_pintuck_abaya.png",
        "dress_brown_belted_abaya.png",
        "outfit_coral_embroidered_set.png",
        "outfit_white_kurta_heels.png",
        "outfit_teal_colourblock_maxi_heels.png",
        "bottoms_green_embroidered_palazzo.png",
        "bottoms_grey_pleated_skirt.png",
        "top_cream_satin_wrap_blouse.png",
    ]

    def load(self) -> list[AcceptanceQuery]:
        return load_queries(EXTRA_QUERIES_PATH, require_images=False, check_mix=False)

    def test_holds_the_other_eleven_photos_and_nothing_else(self) -> None:
        photos = sorted(PurePosixPath(str(q.image)).name for q in self.load())

        assert photos == sorted(self.EXTRA)

    def test_every_extra_query_is_photo_only(self) -> None:
        assert {q.type for q in self.load()} <= {InputType.PRODUCT_PHOTO, InputType.OUTFIT_PHOTO}
        assert all(q.text is None for q in self.load())

    def test_the_three_outfit_photos_are_outfit_queries(self) -> None:
        outfits = {
            PurePosixPath(str(q.image)).name
            for q in self.load()
            if q.type is InputType.OUTFIT_PHOTO
        }

        assert outfits == {name for name in self.EXTRA if name.startswith("outfit_")}

    def test_it_shares_no_id_and_no_photo_with_the_ten_acceptance_queries(self) -> None:
        ten = load_queries(QUERIES_PATH, require_images=False)
        extra = self.load()

        assert not {q.id for q in ten} & {q.id for q in extra}
        assert not {q.image for q in ten} & {q.image for q in extra}

    def test_it_is_not_an_acceptance_set_it_does_not_have_the_prd_mix(self) -> None:
        # The pass rule counts 7 of 10. These 11 must never be mistaken for, or added to, that set.
        raw = yaml.safe_load(EXTRA_QUERIES_PATH.read_text(encoding="utf-8"))

        with pytest.raises(QueryFileError, match="mix must be"):
            parse_queries(raw)

    def test_every_photo_of_both_files_is_described_in_the_assets_guide(self) -> None:
        guide = (QUERIES_PATH.parent / "ASSETS.md").read_text(encoding="utf-8")
        photos = {PurePosixPath(str(q.image)).name for q in self.load()}
        photos |= {
            PurePosixPath(str(q.image)).name
            for q in load_queries(QUERIES_PATH, require_images=False)
            if q.image
        }

        assert [name for name in sorted(photos) if name not in guide] == []


class TestAMissingPhoto:
    def test_names_the_file_and_points_to_the_assets_guide(self, tmp_path: Path) -> None:
        path = write_yaml(tmp_path, mix_of_ten())

        with pytest.raises(MissingImageError) as caught:
            load_queries(path, repo_root=tmp_path, require_images=True)

        message = str(caught.value)
        assert GOWN_PHOTO in message
        assert "eval/data/ASSETS.md" in message

    def test_lists_each_missing_file_once_with_the_queries_that_use_it(
        self, tmp_path: Path
    ) -> None:
        path = write_yaml(tmp_path, mix_of_ten())

        with pytest.raises(MissingImageError) as caught:
            load_queries(path, repo_root=tmp_path)

        message = str(caught.value)
        assert message.count(GOWN_PHOTO) == 1
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
        target = tmp_path / GOWN_PHOTO
        target.parent.mkdir(parents=True)
        target.write_bytes(b"gown-bytes")
        photo = AcceptanceQuery.model_validate(entry())
        text = AcceptanceQuery.model_validate(
            entry(id="q06_text", type="text", text="blazer", image=None)
        )

        assert read_query_image(photo, tmp_path) == b"gown-bytes"
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
        assert "q01_product_gown" in message
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

        with pytest.raises(QueryFileError, match=r"unique.*q01_product_gown"):
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
