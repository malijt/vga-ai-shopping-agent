"""One price-range section: its header, a line of facts, and a grid of result cards.

The header is ``TierResult.display_label`` (PRD R16): ``Budget · 45-139 AED · 8 results``. It is
built from the range's name, real prices and currency code, all validated by the contract, so it
is safe to give to ``st.subheader``. The target, how many are shown, and any flags follow as plain
text.
"""

from collections.abc import Sequence

import streamlit as st

from app.components.result_card import render_result_card
from app.copy import FLAG_TEXT
from vga.models import ScoredProduct, TierResult

CARDS_PER_ROW = 3


def _chunks(items: Sequence[ScoredProduct], size: int) -> list[Sequence[ScoredProduct]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def facts_line(tier: TierResult) -> str:
    """``Showing 2 of 3. Few options in this range.``: target, count and flags, as words."""
    parts = [f"Showing {tier.count} of {tier.target_count}."]
    parts.extend(f"{FLAG_TEXT[flag]}." for flag in tier.flags)
    return " ".join(parts)


def render_price_range(tier: TierResult, *, key: str) -> None:
    """Draw one price range. ``key`` is unique per garment group and range."""
    st.subheader(tier.display_label, anchor=False)
    st.text(facts_line(tier))
    if not tier.results:
        st.text("No products in this price range.")
        return
    for row_number, row in enumerate(_chunks(tier.results, CARDS_PER_ROW)):
        columns = st.columns(CARDS_PER_ROW, gap="medium")
        for column_number, (column, scored) in enumerate(zip(columns, row, strict=False)):
            with column:
                render_result_card(
                    scored, key=f"{key}_{row_number * CARDS_PER_ROW + column_number}"
                )
