"""The two steps the pipeline calls (plan Phase 7; used by Phase 13).

1. ``prefilter_and_score``: hard filters, then the text and price scores. Run it on everything the
   stores returned. The pipeline then picks the best candidates for image scoring.
2. ``apply_image_scores``: add the image scores (or none), recompute the totals, drop products
   below ``min_match_score`` and return the rest best first.

Both are pure: no network, no model, no clock, no I/O. Inputs are never modified.
"""

import math
from collections.abc import Mapping, Sequence

from vga.models import Budget, Flag, ItemIntent, Product, ScoredProduct, Scores
from vga.rank.combine import combine_scores
from vga.rank.filters import apply_hard_filters
from vga.rank.price import is_over_budget, price_score
from vga.rank.reason import build_reason, plain_reason
from vga.rank.text import match_text
from vga.settings import Settings


def _order(scored: ScoredProduct) -> tuple[float, float, str]:
    """Best total first; then the better text score; then the product URL, so equal scores always
    come out in the same order."""
    return (-scored.scores.total, -scored.scores.text, scored.product.key)


def prefilter_and_score(
    item: ItemIntent,
    products: Sequence[Product],
    budget: Budget | None,
    settings: Settings,
) -> list[ScoredProduct]:
    """Filter ``products`` for ``item`` and score what is left on text and price.

    - Dropped: out of stock (``in_stock is False``), a garment outside the five categories, the
      wrong category, and, when the request's gender is explicit, a children's product and one
      that clearly states the other gender. Never dropped: over budget (flagged ``over_budget``
      instead), unknown stock, unknown category (kept without a category bonus).
    - ``scores.image`` is ``None``; ``scores.total`` combines text and price with the image weight
      left out. Nothing is removed for a low score yet, because the image score may still lift it.
    - ``product.category`` is filled with the inferred category when there is one.
    - ``reason`` is set here, because only this step knows the request and the budget.

    Returns the products best first (ties broken by text score, then URL).
    """
    scored: list[ScoredProduct] = []
    for product in products:
        decision = apply_hard_filters(item, product)
        if not decision.keep:
            continue
        match = match_text(item, product)
        price = price_score(product.price, product.currency, budget, settings)
        over_budget = is_over_budget(product.price, product.currency, budget, settings)
        flags = [Flag.OVER_BUDGET] if over_budget else []
        kept = product
        if decision.category is not None and product.category is not decision.category:
            kept = product.model_copy(update={"category": decision.category})
        scored.append(
            ScoredProduct(
                product=kept,
                scores=Scores(
                    text=match.score,
                    image=None,
                    price=price,
                    total=combine_scores(match.score, None, price, settings.ranking_weights),
                ),
                reason=build_reason(kept, match, budget, settings),
                flags=flags,
            )
        )
    scored.sort(key=_order)
    return scored


def _usable(score: float | None) -> float | None:
    """An image score clamped to 0-1; ``None`` and non-numbers (NaN) mean "not scored"."""
    if score is None or not math.isfinite(score):
        return None
    return min(1.0, max(0.0, score))


def apply_image_scores(
    scored: Sequence[ScoredProduct],
    image_scores: Mapping[str, float | None],
    settings: Settings,
) -> list[ScoredProduct]:
    """Add image scores, recompute each total, drop weak matches and sort best first.

    ``image_scores`` is keyed by ``Product.key``. A missing key or a ``None`` value means that
    product has no image score, and its total renormalises over the text and price weights. An
    empty mapping gives text and price only. Products whose new total is below
    ``settings.min_match_score`` are removed. The reason set by ``prefilter_and_score`` is kept; a
    product without one gets a plain reason from its own facts.
    """
    result: list[ScoredProduct] = []
    for entry in scored:
        image = _usable(image_scores.get(entry.product.key))
        scores = entry.scores
        total = combine_scores(scores.text, image, scores.price, settings.ranking_weights)
        if total < settings.min_match_score:
            continue
        new_scores = Scores(text=scores.text, image=image, price=scores.price, total=total)
        reason = entry.reason or plain_reason(entry.product, entry.flags)
        result.append(entry.model_copy(update={"scores": new_scores, "reason": reason}))
    result.sort(key=_order)
    return result
