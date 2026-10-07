"""Sidebar settings (plan 10.1.3): the three price-range presets, nothing else. The budget lives
in one place, the "Detected by AI" chip."""

import pytest
from streamlit.testing.v1 import AppTest

from app.components.sidebar import preset_caption
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import search
from vga.errors import LlmError
from vga.models import ChipEdits, MixPreset, SettingsOverride

MIX_KEY = "mix_preset"


def settings_sent(pipeline: FakePipeline) -> SettingsOverride:
    overrides = pipeline.calls[-1].overrides
    assert overrides is not None
    assert overrides.settings is not None
    return overrides.settings


class TestSidebarControls:
    def test_it_offers_exactly_the_three_presets_with_even_selected(self, at: AppTest) -> None:
        at.run()

        radio = at.sidebar.radio(key=MIX_KEY)
        assert radio.options == ["Even", "Value first", "Luxury first"]
        assert radio.value is MixPreset.EVEN

    def test_each_preset_shows_its_percentages_from_the_contract(self) -> None:
        assert preset_caption(MixPreset.VALUE_FIRST.mix) == (
            "Budget 40% · Mid-range 30% · Premium 20% · Luxury 10%"
        )

    def test_there_are_no_custom_sliders_and_no_result_count_control(self, at: AppTest) -> None:
        at.run()

        assert not at.sidebar.slider
        assert not at.sidebar.number_input

    def test_the_sidebar_has_no_budget_so_there_is_one_budget_box_not_two(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        assert not at.number_input  # nothing to set a budget in before a search

        search(at)

        assert [box.key for box in at.number_input] == ["chip_budget"]
        assert not at.sidebar.number_input


class TestSettingsOverride:
    def test_the_default_search_sends_the_even_mix_and_nothing_else(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        search(at)

        assert settings_sent(pipeline) == SettingsOverride(tier_mix=MixPreset.EVEN.mix)

    @pytest.mark.parametrize("preset", [MixPreset.VALUE_FIRST, MixPreset.LUXURY_FIRST])
    def test_the_chosen_preset_lands_in_the_settings_override(
        self, at: AppTest, pipeline: FakePipeline, preset: MixPreset
    ) -> None:
        at.run()
        at.sidebar.radio(key=MIX_KEY).set_value(preset).run()

        search(at)

        assert settings_sent(pipeline).tier_mix == preset.mix

    def test_the_settings_are_kept_after_the_search(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.LUXURY_FIRST).run()

        search(at)

        assert at.sidebar.radio(key=MIX_KEY).value is MixPreset.LUXURY_FIRST
        assert at.sidebar.radio(key=MIX_KEY).disabled is False


class TestChangingTheMixShowsTheSameResultsReSorted:
    """Plan 15.2.3. With results on the page, a new mix is a search again that changes nothing but
    the mix: no text, no photo, the earlier detection, no chip edits."""

    def test_a_new_mix_with_results_on_the_page_searches_again_without_text_or_photo(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        first = pipeline.calls[-1].req
        calls_before = len(pipeline.calls)

        results_at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.LUXURY_FIRST).run()

        assert len(pipeline.calls) == calls_before + 1
        again = pipeline.calls[-1]
        assert again.req.rerun_of == first.request_id
        assert again.req.text is None
        assert again.req.image is None
        assert again.overrides is not None
        assert again.overrides.settings == SettingsOverride(tier_mix=MixPreset.LUXURY_FIRST.mix)
        assert again.overrides.chips == ChipEdits()
        assert again.overrides.understood is not None  # the earlier detection, not a new one

    def test_the_choice_is_still_selected_after_the_results_are_re_sorted(
        self, results_at: AppTest
    ) -> None:
        results_at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.VALUE_FIRST).run()

        radio = results_at.sidebar.radio(key=MIX_KEY)
        assert radio.value is MixPreset.VALUE_FIRST
        assert radio.disabled is False

    def test_the_results_are_drawn_again_from_the_new_response(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.VALUE_FIRST).run()

        assert not results_at.exception
        assert [header.value for header in results_at.subheader]  # price ranges are on the page
        assert pipeline.calls[-1].req.request_id != pipeline.calls[0].req.request_id

    def test_a_new_mix_before_any_search_only_waits_for_the_first_search(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.VALUE_FIRST).run()

        assert not pipeline.calls
        assert not at.error

    def test_chip_edits_the_shopper_has_not_applied_survive_a_new_mix(
        self, results_at: AppTest, pipeline: FakePipeline
    ) -> None:
        results_at.text_input(key="chip_0_colour").set_value("navy").run()

        results_at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.VALUE_FIRST).run()

        assert results_at.text_input(key="chip_0_colour").value == "navy"
        assert pipeline.calls[-1].overrides is not None
        assert pipeline.calls[-1].overrides.chips == ChipEdits()  # the edit was not applied

    def test_the_caption_says_what_the_mix_does_in_each_state(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        before = [markdown.value for markdown in at.sidebar.markdown]

        search(at)
        after = [markdown.value for markdown in at.sidebar.markdown]

        assert "This applies to your next search." in before
        assert "Changing this re-sorts the results below. No store is searched again." in after

    def test_the_mix_is_not_dropped_when_a_search_fails_afterwards(
        self, results_at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(error=LlmError())

        results_at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.LUXURY_FIRST).run()

        assert results_at.error
        assert results_at.sidebar.radio(key=MIX_KEY).value is MixPreset.LUXURY_FIRST
