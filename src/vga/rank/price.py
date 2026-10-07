"""Price fit and the over-budget test (plan 7.2.3, assumption A4).

The price score says how well a price fits the shopper's budget: 1 inside it, falling smoothly
above it, and a neutral value from settings when there is no budget. A product is never dropped
for being over budget; it is flagged (``Flag.OVER_BUDGET``) and the tier shaper decides where it
may appear.

A budget and a price in different currencies cannot be compared (the app holds no exchange rates),
so such a product gets the neutral score and no over-budget flag instead of a wrong claim.
"""

import math

from vga.models import Budget
from vga.settings import Settings

PRICE_DECAY = 2.0
"""How fast the score falls above the budget: ``exp(-PRICE_DECAY * overshoot)``, where the
overshoot is the part of the price above the budget as a fraction of the budget. 10% over scores
about 0.82, 50% over about 0.37, double the budget about 0.14."""


def comparable(price_currency: str, budget: Budget | None) -> bool:
    """True when there is a budget and it is in the same currency as the price."""
    return budget is not None and budget.currency == price_currency


def is_over_budget(price: float, currency: str, budget: Budget | None) -> bool:
    """True only when the price can be compared with the budget and is above it."""
    return budget is not None and comparable(currency, budget) and price > budget.max_price


def price_score(price: float, currency: str, budget: Budget | None, settings: Settings) -> float:
    """Price fit from 0 to 1: 1 within budget, decaying above it, neutral with no usable budget."""
    if budget is None or not comparable(currency, budget):
        return settings.neutral_price_score
    if price <= budget.max_price:
        return 1.0
    overshoot = (price - budget.max_price) / budget.max_price
    return math.exp(-PRICE_DECAY * overshoot)
