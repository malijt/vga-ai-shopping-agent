"""Sidebar settings: the price-range mix presets (plan 10.1.3).

Only the three presets from the PRD, no custom sliders and no result-count control (those are on
the deferred list until a stakeholder asks for them). There is no budget here: a request has one
budget, and it lives in the "Detected by AI" chips, where it is shown and editable after a search.
The shopper can also state a budget in the request text. The choice is returned as a
``SettingsOverride`` that goes to the pipeline with every search.

Once results are on the page, changing the choice shows the same results in the new mix right away
(``state.request_mix_change``). That is a search again with nothing else changed: the pipeline
re-sorts the products it already has, so no store and no AI is asked (plan 15.2.3).
"""

import streamlit as st

from app import state
from vga.models import MixPreset, SettingsOverride, TierMix


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
            on_change=state.request_mix_change,
            disabled=disabled,
        )
        if state.get_response() is None:
            st.markdown("This applies to your next search.")
        else:
            st.markdown("Changing this re-sorts the results below. No store is searched again.")
    return SettingsOverride(tier_mix=preset.mix)
