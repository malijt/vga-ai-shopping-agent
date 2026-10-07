"""Price parsing (plan 6.5.1): exactly the formats the qualified stores were seen to use.

Seen in the saved samples, and so handled here:

- Shopify search responses (Oh Polly, Club L London, and every Shopify store like them): a decimal
  string with no thousands separator and exactly the number of places the store's currency has:
  two for AED (``"535.00"``, ``"1499.00"``), three for the Kuwaiti dinar (``"260.000"``,
  ``"245.000"``, ``"55.000"``, ``"5.000"``, ``"29.000"``, seen at Bazza Alzouman, Hamsa and Manal
  Smaoui). There is no currency in the response; the store config supplies it.
- Luxury For You card text: a three-letter currency code, a space and a whole number with comma
  thousands separators (``AED 6,900``, ``AED 450``, ``AED 23,698``), wrapped in Unicode
  bidirectional isolate characters U+2066 to U+2069.

Anything else raises ``PriceFormatError`` and the record is dropped with a logged reason. New
formats are added when a store report shows one, not before: guessing at "1.234,50" or "AED1,200"
is how a price ends up wrong by a factor of 1000.

That is why the decimals depend on the store's currency (``parse_price``'s ``currency``). Three
decimals are a price only for a currency that has three (KWD, BHD, OMR: see
``vga.money.decimal_places``). For an AED store ``"260.000"`` far more likely means a thousands
separator, and reading it as 260 could leave a price wrong by a factor of 1000, so it stays
refused. The reverse holds too: a dinar store was only seen to write three decimals, so two
(``"260.00"``) is refused there until a store shows it.
"""

import re
from dataclasses import dataclass

from vga.money import decimal_places


class PriceFormatError(ValueError):
    """The text is not one of the price formats we have seen."""


@dataclass(frozen=True)
class ParsedPrice:
    amount: float
    currency: str | None
    """The currency written in the text (``"AED"``), or ``None`` for a bare number."""


_BIDI_ISOLATES = dict.fromkeys(range(0x2066, 0x206A))  # U+2066 .. U+2069
_DECIMAL_STRINGS = {places: re.compile(rf"^\d+\.\d{{{places}}}$") for places in (2, 3)}
_CODE_AND_AMOUNT = re.compile(r"^(?P<currency>[A-Z]{3}) (?P<amount>\d{1,3}(?:,\d{3})+|\d+)$")


def parse_price(raw: object, currency: str | None = None) -> ParsedPrice:
    """Turn price text from a store into a number and, when the text names one, a currency.

    ``currency`` is the store's configured currency. It decides how many decimals a bare decimal
    string must have (see the module docstring); without it the two-decimal form is expected.
    """
    if not isinstance(raw, str):
        msg = f"price is a {type(raw).__name__}, not text"
        raise PriceFormatError(msg)
    text = " ".join(raw.translate(_BIDI_ISOLATES).split())
    places = decimal_places(currency) if currency else 2
    if _DECIMAL_STRINGS[places].match(text):
        return ParsedPrice(float(text), None)
    match = _CODE_AND_AMOUNT.match(text)
    if match:
        return ParsedPrice(float(match["amount"].replace(",", "")), match["currency"])
    msg = f"unrecognised price format {text[:40]!r}"
    raise PriceFormatError(msg)
