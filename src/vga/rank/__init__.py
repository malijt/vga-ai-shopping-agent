"""Text, price and combined ranking of candidate products (Phase 7).

The pipeline uses two functions: ``prefilter_and_score`` (hard filters, text and price scores) and,
after image scoring, ``apply_image_scores`` (totals, minimum score, best first). The rest is public
for tests and for other phases that need the same lexicons (colour names, category inference).

Image similarity lives in ``vga.rank.image`` and is not imported here.
"""

from vga.rank.category import classify_title, infer_category, resolve_category
from vga.rank.combine import combine_scores
from vga.rank.filters import DropReason, FilterResult, apply_hard_filters
from vga.rank.lexicon import Colour, colour_affinity, find_colours, normalise_colour
from vga.rank.price import is_over_budget, price_score
from vga.rank.ranking import apply_image_scores, prefilter_and_score
from vga.rank.reason import build_reason, plain_reason
from vga.rank.text import TextMatch, match_text, text_score

__all__ = [
    "Colour",
    "DropReason",
    "FilterResult",
    "TextMatch",
    "apply_hard_filters",
    "apply_image_scores",
    "build_reason",
    "classify_title",
    "colour_affinity",
    "combine_scores",
    "find_colours",
    "infer_category",
    "is_over_budget",
    "match_text",
    "normalise_colour",
    "plain_reason",
    "prefilter_and_score",
    "price_score",
    "resolve_category",
    "text_score",
]
