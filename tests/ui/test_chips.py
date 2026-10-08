"""Chips (plan 10.2.1): editable category, colour, gender and budget; apply; reset."""

import pytest
from streamlit.testing.v1 import AppTest

from app.components.chips import ItemValues, build_chip_edits
from tests.factories import (
    load_sample_response,
    make_budget,
    make_item_intent,
    make_understand_result,
)
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import (
    SEARCH_BUTTON,
    TEXT_BOX,
    chip_budget,
    chip_category,
    chip_colour,
    chip_gender,
    search,
)
from vga.errors import LlmError
from vga.models import (
    Budget,
    Category,
    ChipEdits,
    Gender,
    GenderSource,
    ItemEdit,
    MixPreset,
)

APPLY = "chips_apply"
RESET = "chips_reset"
SAMPLE = load_sample_response()


def last_chips(pipeline: FakePipeline) -> ChipEdits:
    overrides = pipeline.calls[-1].overrides
    assert overrides is not None
    assert overrides.chips is not None
    return overrides.chips


class TestChipsAreShown:
    def test_nothing_is_shown_before_the_first_search(self, at: AppTest) -> None:
        at.run()

        assert not [header for header in at.header if header.value == "Detected by AI"]
        assert not at.selectbox

    def test_they_are_labelled_detected_by_ai(self, results_at: AppTest) -> None:
        assert "Detected by AI" in [header.value for header in results_at.header]

    def test_each_detected_item_gets_category_colour_and_gender_chips(
        self, results_at: AppTest
    ) -> None:
        assert chip_category(results_at, 0).value is Category.OUTERWEAR
        assert chip_colour(results_at, 0).value == "black"
        assert chip_category(results_at, 1).value is Category.SHOES
        assert chip_colour(results_at, 1).value == "white"
        assert chip_gender(results_at, 0) is not None
        assert chip_gender(results_at, 1) is not None

    def test_the_category_chip_offers_all_five_categories_dresses_last(
        self, results_at: AppTest
    ) -> None:
        offered = chip_category(results_at, 0).options

        assert offered == [
            "Tops",
            "Outerwear",
            "Bottoms",
            "Shoes",
            "Dresses and ethnic wear",
        ]

    def test_a_detected_dress_is_shown_with_the_dresses_label(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        understood = make_understand_result(
            items=[make_item_intent(category=Category.DRESSES, search_keywords=["abaya"])]
        )
        install_pipeline(SAMPLE.model_copy(update={"understood": understood}))
        at.run()

        search(at)

        assert chip_category(at, 0).value is Category.DRESSES
        assert chip_category(at, 0).options[-1] == "Dresses and ethnic wear"

    def test_every_chip_has_a_visible_label(self, results_at: AppTest) -> None:
        labels = [widget.label for widget in results_at.selectbox]
        labels += [widget.label for widget in results_at.text_input]
        labels += [widget.label for widget in results_at.number_input]

        assert all(labels)
        assert len(set(labels)) == len(labels)

    def test_the_budget_chip_shows_the_detected_budget(self, results_at: AppTest) -> None:
        assert chip_budget(results_at).value == 400.0
        assert chip_budget(results_at).label == "Budget in AED (optional)"


class TestInferredGenderStaysUnset:
    def test_an_inferred_gender_starts_not_set_and_is_called_not_confirmed(
        self, results_at: AppTest
    ) -> None:
        assert SAMPLE.understood.items[0].gender_source is GenderSource.INFERRED

        assert chip_gender(results_at, 0).value == "unset"
        notes = [markdown.value for markdown in results_at.markdown]
        assert any("not confirmed. The AI guessed Men" in note for note in notes)

    def test_applying_without_choosing_a_gender_sends_no_gender(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.button(key=APPLY).click().run()

        assert all(edit.gender is None for edit in last_chips(pipeline).items)

    def test_choosing_the_guessed_gender_is_sent_as_the_shoppers_confirmation(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_gender(results_at, 0).set_value("men").run()
        assert any("confirmed by you" in m.value for m in results_at.markdown)

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline).items == [ItemEdit(index=0, gender=Gender.MEN)]

    def test_a_gender_stated_in_the_request_is_shown_as_taken_from_it(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        understood = make_understand_result(
            items=[make_item_intent(gender=Gender.WOMEN, gender_source=GenderSource.EXPLICIT)]
        )
        install_pipeline(SAMPLE.model_copy(update={"understood": understood}))
        at.run()

        search(at)

        assert chip_gender(at, 0).value == "women"
        assert any("taken from your request" in m.value for m in at.markdown)
        assert "Not set" not in chip_gender(at, 0).options


class TestApply:
    def test_applying_with_no_edits_sends_empty_chip_edits(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits()

    def test_editing_a_colour_and_applying_sends_exactly_that_edit(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_colour(results_at, 0).set_value("navy").run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits(items=[ItemEdit(index=0, colour="navy")])

    def test_several_edits_to_several_items_arrive_together(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_colour(results_at, 0).set_value("navy").run()
        chip_category(results_at, 1).set_value(Category.BOTTOMS).run()
        chip_gender(results_at, 1).set_value("women").run()
        chip_budget(results_at).set_value(300.0).run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits(
            items=[
                ItemEdit(index=0, colour="navy"),
                ItemEdit(index=1, category=Category.BOTTOMS, gender=Gender.WOMEN),
            ],
            budget=Budget(max_price=300.0, currency="AED"),
        )

    def test_changing_a_category_to_dresses_sends_that_edit(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_category(results_at, 1).set_value(Category.DRESSES).run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits(
            items=[ItemEdit(index=1, category=Category.DRESSES)]
        )

    def test_clearing_the_budget_box_removes_the_budget(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_budget(results_at).set_value(None).run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits(clear_budget=True)

    def test_an_emptied_colour_box_clears_the_colour(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_colour(results_at, 0).set_value("   ").run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits(items=[ItemEdit(index=0, colour="")])

    def test_the_search_again_reuses_the_detection_and_carries_the_sidebar_settings(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.sidebar.radio(key="mix_preset").set_value(MixPreset.VALUE_FIRST).run()

        results_at.button(key=APPLY).click().run()

        overrides = pipeline.calls[-1].overrides
        assert overrides is not None
        assert overrides.understood == SAMPLE.understood
        assert overrides.settings is not None
        assert overrides.settings.tier_mix == MixPreset.VALUE_FIRST.mix

    def test_the_search_again_names_the_earlier_search_and_sends_no_text_and_no_photo(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        first = pipeline.calls[-1].req
        results_at.text_input(key=TEXT_BOX).set_value("something else").run()

        results_at.button(key=APPLY).click().run()

        again = pipeline.calls[-1].req
        assert again.rerun_of == first.request_id
        assert again.text is None
        assert again.image is None
        assert again.request_id != first.request_id

    def test_each_search_again_names_the_one_before_it(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.button(key=APPLY).click().run()
        second = pipeline.calls[-1].req

        results_at.button(key=APPLY).click().run()

        assert pipeline.calls[-1].req.rerun_of == second.request_id

    def test_the_search_again_carries_the_photos_embedding_not_the_photo(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        embedding = [0.25, -0.5, 0.75]
        fake = install_pipeline(SAMPLE.model_copy(update={"query_embedding": embedding}))
        at.run()
        search(at)

        at.button(key=APPLY).click().run()

        overrides = fake.calls[-1].overrides
        assert overrides is not None
        assert overrides.query_embedding == embedding
        assert fake.calls[-1].req.image is None

    def test_search_again_works_with_empty_boxes_because_it_needs_neither(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.text_input(key=TEXT_BOX).set_value("").run()
        calls_before = len(pipeline.calls)

        assert results_at.button(key=APPLY).disabled is False
        assert (
            results_at.button(key=SEARCH_BUTTON).disabled is True
        )  # a NEW search still needs input
        results_at.button(key=APPLY).click().run()

        assert len(pipeline.calls) == calls_before + 1
        assert not any("keep your photo or description" in m.value for m in results_at.markdown)

    def test_after_a_successful_apply_the_chips_start_again_from_the_new_detection(
        self, results_at: AppTest
    ) -> None:
        chip_colour(results_at, 0).set_value("navy").run()

        results_at.button(key=APPLY).click().run()

        assert chip_colour(results_at, 0).value == "black"

    def test_edits_survive_a_failed_search_again(
        self, results_at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        chip_colour(results_at, 0).set_value("navy").run()
        install_pipeline(error=LlmError())

        results_at.button(key=APPLY).click().run()

        assert results_at.error
        assert chip_colour(results_at, 0).value == "navy"
        assert results_at.button(key=APPLY).disabled is False


class TestReset:
    def test_reset_to_detected_restores_every_chip(self, results_at: AppTest) -> None:
        chip_colour(results_at, 0).set_value("navy").run()
        chip_category(results_at, 0).set_value(Category.TOPS).run()
        chip_gender(results_at, 1).set_value("women").run()
        chip_budget(results_at).set_value(999.0).run()

        results_at.button(key=RESET).click().run()

        assert chip_colour(results_at, 0).value == "black"
        assert chip_category(results_at, 0).value is Category.OUTERWEAR
        assert chip_gender(results_at, 1).value == "unset"
        assert chip_budget(results_at).value == 400.0

    def test_after_a_reset_applying_sends_no_edits(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        chip_colour(results_at, 0).set_value("navy").run()
        results_at.button(key=RESET).click().run()

        results_at.button(key=APPLY).click().run()

        assert last_chips(pipeline) == ChipEdits()

    def test_reset_does_not_search(self, results_at: AppTest, pipeline: FakePipeline) -> None:
        calls_before = len(pipeline.calls)

        results_at.button(key=RESET).click().run()

        assert len(pipeline.calls) == calls_before


class TestBuildChipEdits:
    """The comparison itself, without a page: only differences are sent."""

    understood = make_understand_result(
        items=[
            make_item_intent(
                colour="black", gender=Gender.MEN, gender_source=GenderSource.INFERRED
            ),
            make_item_intent(
                category=Category.SHOES,
                colour=None,
                gender=Gender.WOMEN,
                gender_source=GenderSource.EXPLICIT,
            ),
        ],
        budget=make_budget(max_price=400, currency="SAR"),
    )

    def values(self, **second: object) -> list[ItemValues]:
        first = ItemValues(category=Category.OUTERWEAR, colour="black", gender=None)
        base = {"category": Category.SHOES, "colour": "", "gender": Gender.WOMEN}
        return [first, ItemValues(**{**base, **second})]  # type: ignore[arg-type]

    def test_unchanged_chips_give_no_edits(self) -> None:
        assert build_chip_edits(self.understood, self.values(), 400.0) == ChipEdits()

    def test_a_stated_gender_changed_to_another_is_an_edit(self) -> None:
        edits = build_chip_edits(self.understood, self.values(gender=Gender.UNISEX), 400.0)

        assert edits.items == [ItemEdit(index=1, gender=Gender.UNISEX)]

    def test_a_colour_added_where_none_was_detected_is_an_edit(self) -> None:
        edits = build_chip_edits(self.understood, self.values(colour="  red "), 400.0)

        assert edits.items == [ItemEdit(index=1, colour="red")]

    def test_a_changed_budget_keeps_the_detected_currency(self) -> None:
        edits = build_chip_edits(self.understood, self.values(), 250.0)

        assert edits.budget == Budget(max_price=250.0, currency="SAR")

    def test_a_budget_added_where_none_was_detected_uses_the_default_currency(self) -> None:
        no_budget = self.understood.model_copy(update={"budget": None})

        edits = build_chip_edits(no_budget, self.values(), 250.0)

        assert edits.budget == Budget(max_price=250.0, currency="AED")

    def test_no_budget_where_none_was_detected_is_not_an_edit(self) -> None:
        no_budget = self.understood.model_copy(update={"budget": None})

        assert build_chip_edits(no_budget, self.values(), None) == ChipEdits()

    @pytest.mark.parametrize("new_budget", [None])
    def test_removing_the_detected_budget_is_clear_budget(self, new_budget: None) -> None:
        edits = build_chip_edits(self.understood, self.values(), new_budget)

        assert edits.clear_budget is True
        assert edits.budget is None
