"""Garment groups: the four price ranges for each garment (plan 10.2.4).

A single-garment request shows one "Results" heading and its four price ranges. An outfit photo
shows one group per garment, each under its own heading with the same four price ranges.
"""

import streamlit as st

from app.components.price_range import render_price_range
from app.copy import CATEGORY_LABELS
from vga.models import GarmentGroup, SearchResponse


def group_heading(position: int, group: GarmentGroup) -> str:
    """``Item 1: Outerwear``. The category is one of four fixed names, never free text."""
    return f"Item {position}: {CATEGORY_LABELS[group.category]}"


def render_groups(response: SearchResponse, *, base_currency: str) -> None:
    """Draw every garment group in the response, each with its four price ranges in order.
    ``base_currency`` is ``Settings.base_currency``, the currency the price ranges are in."""
    multiple = len(response.groups) > 1
    if not multiple:
        st.header("Results", anchor=False)
    for position, group in enumerate(response.groups, start=1):
        if multiple:
            st.header(group_heading(position, group), anchor=False)
        for tier in group.tiers:
            render_price_range(
                tier, key=f"{group.item_index}_{tier.name.value}", base_currency=base_currency
            )
