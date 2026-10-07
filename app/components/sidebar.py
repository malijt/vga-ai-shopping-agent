"""Sidebar settings: the price-range mix presets and an optional budget (plan 10.1.3).

Only the three presets from the PRD, no custom sliders and no result-count control (those are on
the deferred list until a stakeholder asks for them). The choice is returned as a
``SettingsOverride`` that goes to the pipeline with the next search.
"""

import streamlit as st
from app import state

from vga.models import DEFAULT_CURRENCY, Budget, MixPreset, SettingsOverride, TierMix

BUDGET_MAX = 1_000_000.0


def preset_caption(mix: TierMix) -> str:
    """``Budget 25% · Mid-range 25% · Premium 25% · Luxury 25%`` for one preset."""
    return (
        f"Budget {mix.budget}% · Mid-range {mix.mid_range}% · "
        f"Premium {mix.premium}% · Luxury {mix.luxury}%"
    )


def render_sidebar(*, disabled: bool) -> SettingsOverride:
    """Draw the settings and return what the shopper chose. ``disabled`` is true during a search."""
    presets = list(MixPreset)
    with st.sidebar:
        st.header("Search settings", anchor=False)
        preset = st.radio(
            "Share of results in each price range",
            options=presets,
            index=presets.index(MixPreset.EVEN),
            format_func=lambda option: option.label,
            captions=[preset_caption(option.mix) for option in presets],
            key=state.MIX_KEY,
            disabled=disabled,
        )
        budget = st.number_input(
            f"Budget for your next search in {DEFAULT_CURRENCY} (optional)",
            min_value=1.0,
            max_value=BUDGET_MAX,
            value=None,
            step=10.0,
            format="%g",
            placeholder="For example: 400",
            key=state.SIDEBAR_BUDGET_KEY,
            disabled=disabled,
        )
        st.markdown("These settings apply to your next search.")
    return SettingsOverride(
        tier_mix=preset.mix,
        budget=Budget(max_price=budget, currency=DEFAULT_CURRENCY) if budget else None,
    )
