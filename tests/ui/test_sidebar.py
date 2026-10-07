"""Sidebar settings (plan 10.1.3): three presets and an optional budget, nothing else."""

import pytest
from app.components.sidebar import preset_caption
from streamlit.testing.v1 import AppTest

from tests.fakes import FakePipeline
from tests.ui.helpers import search
from vga.models import Budget, MixPreset, SettingsOverride

MIX_KEY = "mix_preset"
BUDGET_KEY = "budget_amount"


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
        assert len(at.sidebar.number_input) == 1  # the budget only
        assert at.sidebar.number_input[0].label == "Budget for your next search in AED (optional)"

    def test_the_budget_is_optional_and_starts_empty(self, at: AppTest) -> None:
        at.run()

        assert at.sidebar.number_input(key=BUDGET_KEY).value is None


class TestSettingsOverride:
    def test_the_default_search_sends_the_even_mix_and_no_budget(
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

    def test_the_budget_lands_in_the_settings_override_in_dirhams(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        at.sidebar.number_input(key=BUDGET_KEY).set_value(400.0).run()

        search(at)

        assert settings_sent(pipeline).budget == Budget(max_price=400.0, currency="AED")

    def test_the_settings_are_kept_after_the_search(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()
        at.sidebar.radio(key=MIX_KEY).set_value(MixPreset.LUXURY_FIRST).run()

        search(at)

        assert at.sidebar.radio(key=MIX_KEY).value is MixPreset.LUXURY_FIRST
        assert at.sidebar.radio(key=MIX_KEY).disabled is False
