"""The one-sentence reason shown on each result card (plan 7.2.5, PRD R11).

The sentence may only use facts the code holds about this product and request:
- the colour on the product (its colour field or title) matches the colour asked for,
- the price is within or above the budget (compared in the base currency, the budget named in its
  own currency), and
- the store that sells it.

It never repeats text from the request or the model (the colour name comes from the colour
lexicon, the numbers from the product and the budget, the store name from the store's config), and
it never claims a colour or a budget fit that was not established. If nothing specific is known
the sentence is a plain template.
"""

from collections.abc import Sequence

from vga.models import Budget, Flag, Product
from vga.rank.price import budget_fit
from vga.rank.text import TextMatch
from vga.settings import Settings

EXACT_COLOUR_FIT = 0.85
"""Colour fit at or above this reads as "the colour you asked for"; below it, "close to"."""


def _amount(value: float) -> str:
    return f"{value:,.0f}" if value == round(value) else f"{value:,.2f}"


def build_reason(
    product: Product, match: TextMatch, budget: Budget | None, settings: Settings
) -> str:
    """The reason sentence for ``product``, from ``match``, ``budget`` and the fixed rates in
    ``settings`` and nothing else. A product in another currency is compared with the budget in
    the base currency (the same figure as the over-budget flag); the budget is still named in its
    own currency."""
    facts: list[str] = []

    if match.colour is not None and match.colour_fit is not None:
        if match.colour_fit >= EXACT_COLOUR_FIT:
            facts.append(f"{match.colour.label}, the colour you asked for.")
        else:
            facts.append(f"{match.colour.label}, close to the colour you asked for.")

    fit = budget_fit(product.price, product.currency, budget, settings)
    if budget is not None and fit is not None:
        position = "Above" if fit.over else "Within"
        facts.append(f"{position} your {_amount(budget.max_price)} {budget.currency} budget.")

    if not facts:
        # Nothing specific is established: a plain template, true only as far as it goes.
        if match.overlap:
            facts.append("Matches your search words.")
        else:
            facts.append("A possible match for your search.")

    facts.append(f"Sold by {product.store}.")
    return " ".join(facts)


def plain_reason(product: Product, flags: Sequence[Flag] = ()) -> str:
    """A reason built from the product and its flags alone, for a result that has none."""
    facts: list[str] = []
    if Flag.OVER_BUDGET in flags:
        facts.append("Above your budget.")
    facts.append(f"Sold by {product.store}.")
    return " ".join(facts)
