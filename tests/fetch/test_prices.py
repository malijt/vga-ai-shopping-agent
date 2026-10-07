"""Price parsing (plan 6.5.1), built from the real saved samples."""

import json
import re

import pytest

from tests.fetch.conftest import FIXTURES, fixture_text
from vga.stores.prices import ParsedPrice, PriceFormatError, parse_price

# The Unicode bidirectional isolates U+2066 to U+2069, built from code points so that the invisible
# characters are visible in this file.
LRI, RLI, FSI, PDI = (chr(code) for code in range(0x2066, 0x206A))
BIDI = LRI + RLI + FSI + PDI
NBSP = chr(0xA0)
ARABIC_DIRHAM = "".join(chr(code) for code in (0x62F, 0x2E, 0x625))


def suggest_prices(name: str) -> list[tuple[str, str]]:
    """Every ``price`` and ``compare_at_price_max`` string in a saved Shopify response."""
    data = json.loads(fixture_text(name))
    pairs: list[tuple[str, str]] = []
    for product in data["resources"]["results"]["products"]:
        pairs.append((product["price"], product["title"]))
        pairs.append((product["compare_at_price_max"], product["title"]))
    return pairs


@pytest.mark.parametrize(
    "name",
    [
        "ohpolly-suggest-black-blazer.json",
        "ohpolly-suggest-shoes.json",
        "clubl-suggest-black-blazer.json",
        "clubl-suggest-shoes.json",
    ],
)
def test_every_price_string_in_the_saved_shopify_samples_parses(name: str) -> None:
    for text, title in suggest_prices(name):
        parsed = parse_price(text)

        assert parsed.currency is None, title
        assert parsed.amount == float(text), title


@pytest.mark.parametrize(
    ("text", "amount"),
    [("535.00", 535.0), ("230.00", 230.0), ("1499.00", 1499.0), ("0.00", 0.0), ("999.00", 999.0)],
)
def test_shopify_price_strings(text: str, amount: float) -> None:
    assert parse_price(text) == ParsedPrice(amount, None)


def lfy_card_prices() -> list[str]:
    """The price strings of the saved Luxury For You sample, exactly as served (bidi marks and
    all)."""
    html = (FIXTURES / "lfy-search-black-blazer.html").read_text(encoding="utf-8")
    isolates = f"[{BIDI}]*"
    return re.findall(f"{isolates}AED{isolates} [\\d,]+{isolates}", html)


def test_the_saved_luxury_for_you_sample_really_contains_bidi_wrapped_prices() -> None:
    prices = lfy_card_prices()

    assert len(prices) >= 16  # 8 cards, two prices each (plus the repeated boxed one)
    assert all(any(ch in price for ch in BIDI) for price in prices)


def test_every_price_in_the_saved_luxury_for_you_sample_parses_as_aed() -> None:
    for text in lfy_card_prices():
        parsed = parse_price(text)

        assert parsed.currency == "AED"
        assert parsed.amount == float(re.sub(r"[^\d]", "", text))


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        (LRI + LRI + "AED" + PDI + " 6,900" + PDI, 6900.0),
        (LRI + LRI + "AED" + PDI + " 3,250" + PDI, 3250.0),
        (LRI + LRI + "AED" + PDI + " 23,698" + PDI, 23698.0),
        (LRI + LRI + "AED" + PDI + " 450" + PDI, 450.0),
        ("AED 6,900", 6900.0),
        ("  AED   6,900  ", 6900.0),
        ("AED" + NBSP + "6,900", 6900.0),
    ],
)
def test_luxury_for_you_prices_with_bidi_marks(text: str, amount: float) -> None:
    assert parse_price(text) == ParsedPrice(amount, "AED")


@pytest.mark.parametrize("mark", list(BIDI))
def test_each_bidi_isolate_character_is_stripped(mark: str) -> None:
    assert parse_price(f"{mark}AED 450{mark}").amount == 450.0


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "free",
        "AED",
        "6,900",  # comma thousands without a currency: not a format any store was seen to use
        "6900",
        "230.0",
        "230.000",
        "1,499.00",
        "1.234,50",
        "AED1,200",
        "AED 1,20",
        "AED 1.200",
        "AED 6,900.50",
        "aed 450",
        "$450",
        "450 AED",
        f"{ARABIC_DIRHAM} 450",
        f"450 {ARABIC_DIRHAM}",
        "AED 450 - AED 600",
        "-12.00",
        "12.00 AED",
        "NaN",
        "inf",
        "1e3",
    ],
)
def test_an_unknown_format_is_refused_not_guessed(text: str) -> None:
    with pytest.raises(PriceFormatError):
        parse_price(text)


@pytest.mark.parametrize("value", [None, 535, 535.0, ["535.00"], {"price": "1.00"}, b"535.00"])
def test_a_value_that_is_not_text_is_refused(value: object) -> None:
    with pytest.raises(PriceFormatError):
        parse_price(value)
