"""Text, price and combined ranking of candidate products (Phase 7)."""

from vga.rank.category import classify_title, infer_category, resolve_category
from vga.rank.filters import DropReason, FilterResult, apply_hard_filters
from vga.rank.lexicon import Colour, colour_affinity, find_colours, normalise_colour
from vga.rank.price import is_over_budget, price_score
from vga.rank.text import TextMatch, match_text, text_score

__all__ = [
    "Colour",
    "DropReason",
    "FilterResult",
    "TextMatch",
    "apply_hard_filters",
    "classify_title",
    "colour_affinity",
    "find_colours",
    "infer_category",
    "is_over_budget",
    "match_text",
    "normalise_colour",
    "price_score",
    "resolve_category",
    "text_score",
]
