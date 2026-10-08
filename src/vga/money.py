"""Money: converting a store's price into the base currency, and showing it to the shopper.

The demo compares everything in one base currency (``Settings.base_currency``, AED). A store that
prices in another currency (the Kuwaiti stores, in dinars) keeps its own price on the product, and
the base-currency figure is worked out here from a fixed rate in settings (``Settings.fx_rates``).
There is no live exchange-rate call, and a currency with no rate is never converted: ``to_base``
returns ``None`` rather than guess.

Two places turn a price into text, and both go through this module so the page, the command line,
the harness and the labelling sheet read alike: ``format_price`` for one product and
``format_amount`` for a bare number. The rounding of the "about" figure is explained at
``approximate_amount``.
"""

import math

from vga.settings import Settings

THREE_DECIMAL_CURRENCIES = frozenset({"KWD", "BHD", "OMR"})
"""The Gulf currencies divided into 1,000 sub-units (dinar and fils, rial and baisa), so a price is
written with three decimals (``"260.000"``). Every other currency the app sees has two."""

_APPROXIMATION_STEPS = ((100.0, 10), (20.0, 5), (0.0, 1))
"""``(from this amount up, round to the nearest this)`` in the base currency, largest first."""


def decimal_places(currency: str) -> int:
    """How many decimals a price in ``currency`` is written with: 3 for KWD, BHD and OMR, else 2."""
    return 3 if currency in THREE_DECIMAL_CURRENCIES else 2


def to_base(amount: float, currency: str, settings: Settings) -> float | None:
    """``amount`` in ``currency`` expressed in the base currency, or ``None`` when there is no rate.

    An amount already in the base currency is returned as it is. Otherwise it is multiplied by the
    fixed rate in ``settings.fx_rates`` and rounded to the base currency's own decimals, so the
    stored figure carries no floating-point noise. A currency with no rate gives ``None``: the
    caller leaves the product out of anything that needs a base-currency figure.
    """
    if currency == settings.base_currency:
        return amount
    rate = settings.fx_rates.get(currency)
    if rate is None:
        return None
    places = decimal_places(settings.base_currency)
    # A positive price stays positive however low the rate (the contract needs base_price > 0).
    return max(round(amount * rate, places), 10.0**-places)


def approximate_amount(base_amount: float) -> int:
    """The base-currency figure rounded for the shopper's eye: 10 AED steps from 100 AED up,
    5 from 20, 1 below, rounding halves up and never down to zero.

    Why round at all: the rate is fixed and drifts (the dinar floats against a basket, so a rate
    read today is good to about 1%), and a figure such as ``2,920.40`` would read as exact. Ten
    dirhams is about 1% of a 1,000 AED price, the usual size here. The unrounded figure stays on
    the result (``ScoredProduct.base_price``) and is the one ranges and budgets use; only the text
    is rounded. The steps assume a base currency of about a dirham's size; a different base would
    want its own table.
    """
    step = next((step for floor, step in _APPROXIMATION_STEPS if base_amount >= floor), 1)
    return max(step, math.floor(base_amount / step + 0.5) * step)


def format_amount(amount: float, currency: str) -> str:
    """A bare number as the shopper reads it, with thousands separators and no currency code.

    A three-decimal currency always shows its three places (``245.000``, as stores write it); any
    other shows a whole number plainly (``1,499``) and a fraction with two places (``89.50``).
    """
    if decimal_places(currency) == 3:
        return f"{amount:,.3f}"
    return f"{amount:,.0f}" if amount == round(amount) else f"{amount:,.2f}"


def format_price(
    price: float,
    currency: str,
    *,
    base_price: float | None = None,
    base_currency: str | None = None,
) -> str:
    """A product's price for the shopper: ``535 AED``, or for a price in another currency its own
    amount and an approximate figure in the base currency, ``245.000 KWD (about 2,920 AED)``.

    ``price`` and ``currency`` are the product's own. ``base_price`` is ``ScoredProduct.base_price``
    (already worked out and stored: nothing is converted here) and ``base_currency`` is
    ``Settings.base_currency``. Without a base price, or when the product is already priced in the
    base currency, the plain form is returned. A base price needs its currency.
    """
    text = f"{format_amount(price, currency)} {currency}"
    if base_price is None:
        return text
    if base_currency is None:
        msg = "base_currency is needed to show a base_price"
        raise ValueError(msg)
    if currency == base_currency:
        return text
    about = format_amount(approximate_amount(base_price), base_currency)
    return f"{text} (about {about} {base_currency})"
