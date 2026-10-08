"""Price fit and the over-budget test (plan 7.2.3, assumption A4).

The price score says how well a price fits the shopper's budget: 1 inside it, falling smoothly
above it, and a neutral value from settings when there is no budget. A product is never dropped
for being over budget; it is flagged (``Flag.OVER_BUDGET``) and the tier shaper decides where it
may appear.

The comparison is made in the base currency (``Settings.base_currency``, AED). A price and a
budget in any other currency are first converted at the fixed rate in ``Settings.fx_rates``
(``vga.money.to_base``): KWD 35 against a 400 AED budget is AED 417.20, over it. When either side
is in a currency with no rate they cannot be compared (the app does not guess one), so the product
gets the neutral score and no over-budget flag instead of a wrong claim. The same ``budget_fit``
feeds the score, the flag and the reason sentence, so the three always agree.
"""

import math
from dataclasses import dataclass

from vga.models import Budget
from vga.money import to_base
from vga.settings import Settings

PRICE_DECAY = 2.0
"""How fast the score falls above the budget: ``exp(-PRICE_DECAY * overshoot)``, where the
overshoot is the part of the price above the budget as a fraction of the budget. 10% over scores
about 0.82, 50% over about 0.37, double the budget about 0.14."""


@dataclass(frozen=True, slots=True)
class BudgetFit:
    """A price and a budget ceiling, both in the base currency."""

    price: float
    ceiling: float

    @property
    def over(self) -> bool:
        return self.price > self.ceiling


def budget_fit(
    price: float, currency: str, budget: Budget | None, settings: Settings
) -> BudgetFit | None:
    """The price and the budget in the base currency, or ``None`` when there is no budget or
    either side is in a currency with no rate."""
    if budget is None:
        return None
    base_price = to_base(price, currency, settings)
    ceiling = to_base(budget.max_price, budget.currency, settings)
    if base_price is None or ceiling is None:
        return None
    return BudgetFit(base_price, ceiling)


def is_over_budget(price: float, currency: str, budget: Budget | None, settings: Settings) -> bool:
    """True only when the price can be compared with the budget and is above it."""
    fit = budget_fit(price, currency, budget, settings)
    return fit is not None and fit.over


def price_score(price: float, currency: str, budget: Budget | None, settings: Settings) -> float:
    """Price fit from 0 to 1: 1 within budget, decaying above it, neutral with no usable budget."""
    fit = budget_fit(price, currency, budget, settings)
    if fit is None:
        return settings.neutral_price_score
    if not fit.over:
        return 1.0
    overshoot = (fit.price - fit.ceiling) / fit.ceiling
    return math.exp(-PRICE_DECAY * overshoot)
