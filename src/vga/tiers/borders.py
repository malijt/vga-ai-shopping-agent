"""Quartile price borders for one garment category (plan 9.1.1, PRD "Range borders").

The borders come from the prices of this search's candidates, so a t-shirt search and a coat search
get different ranges. Cut the price-sorted candidates into four equal parts: the cheapest quarter is
Budget, then Mid-range, Premium, and the top quarter is Luxury.

Rules (deterministic, no interpolation):

- A border is the price of an actual candidate, picked by nearest rank: with ``n`` candidates sorted
  by price, border ``k`` (1 to 3) is the ``ceil(k * n / 4)``-th cheapest price. A price at or below
  border 1 is Budget, at or below border 2 Mid-range, at or below border 3 Premium, above it Luxury.
- Tie rule: a product priced exactly at a border belongs to the cheaper range, so equal prices never
  straddle two ranges. When many candidates share one price the ranges above it can come out empty;
  the selection step then fills them from an adjacent range (see ``vga.tiers.shaper``).
- With 100 candidates each range holds 25. With fewer than 4 candidates not every range can hold a
  product: 1 candidate is Budget; 2 candidates are Budget and Premium; 3 are Budget, Mid-range and
  Premium. Luxury needs at least 4 candidates.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from vga.models import Tier


@dataclass(frozen=True, slots=True)
class PriceBorders:
    """The highest price that still belongs to each of the three cheaper ranges."""

    budget_max: float
    mid_range_max: float
    premium_max: float

    def tier_for(self, price: float) -> Tier:
        """The range a price belongs to. A price equal to a border goes to the cheaper range."""
        if price <= self.budget_max:
            return Tier.BUDGET
        if price <= self.mid_range_max:
            return Tier.MID_RANGE
        if price <= self.premium_max:
            return Tier.PREMIUM
        return Tier.LUXURY


def compute_borders(prices: Sequence[float]) -> PriceBorders:
    """Quartile borders of ``prices`` (any order). See the module docstring for the rules.

    Raises ``ValueError`` for an empty sequence or a price that is not a positive, finite number:
    those cannot come from a valid ``Product`` and would give meaningless borders.
    """
    if not prices:
        msg = "at least one price is needed to compute price borders"
        raise ValueError(msg)
    for price in prices:
        if not math.isfinite(price) or price <= 0:
            msg = f"prices must be positive finite numbers, got {price!r}"
            raise ValueError(msg)
    ordered = sorted(prices)
    count = len(ordered)

    def border(quarter: int) -> float:
        # ceil(quarter * count / 4) in integer arithmetic, as a 0-based index.
        return ordered[(quarter * count + 3) // 4 - 1]

    return PriceBorders(budget_max=border(1), mid_range_max=border(2), premium_max=border(3))
