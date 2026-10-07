"""Price parsing (plan 6.5.1), built from the real saved samples."""

import json
import re
from pathlib import Path

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


# --------------------------------------------------------------------------------------------
# Three-decimal currencies (Kuwaiti dinar, 2026-10-08 decision): a bare number such as "260.000"
# is a price only for a store whose configured currency has three decimals.
# --------------------------------------------------------------------------------------------

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "store-qualification" / "samples"
KUWAITI_SAMPLES = (
    "bazza-alzouman/suggest-dress.json",
    "bazza-alzouman/suggest-gown.json",
    "hamsa-kw/suggest-abaya.json",
    "hamsa-kw/suggest-kaftan.json",
    "manal-smaoui/suggest-dress.json",
    "manal-smaoui/suggest-kaftan.json",
)
REAL_DINAR_PRICES = [
    ("260.000", 260.0),
    ("245.000", 245.0),
    ("55.000", 55.0),
    ("5.000", 5.0),
    ("29.000", 29.0),
]


def saved_kuwaiti_prices() -> list[str]:
    """Every ``price`` string in the six saved Kuwaiti search responses, exactly as served."""
    prices: list[str] = []
    for name in KUWAITI_SAMPLES:
        path = SAMPLES / name
        assert path.is_file(), f"saved sample missing: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        prices.extend(p["price"] for p in data["resources"]["results"]["products"])
    return prices


def test_the_saved_kuwaiti_samples_really_write_prices_with_three_decimals() -> None:
    prices = saved_kuwaiti_prices()

    assert len(prices) == 24
    assert all(re.fullmatch(r"\d+\.\d{3}", price) for price in prices)


def test_every_price_in_the_saved_kuwaiti_samples_parses_for_a_dinar_store() -> None:
    for text in saved_kuwaiti_prices():
        parsed = parse_price(text, "KWD")

        assert parsed == ParsedPrice(float(text), None), text


@pytest.mark.parametrize(("text", "amount"), REAL_DINAR_PRICES)
def test_real_dinar_price_strings_are_prices_for_a_dinar_store(text: str, amount: float) -> None:
    assert parse_price(text, "KWD") == ParsedPrice(amount, None)


@pytest.mark.parametrize(("text", "_amount"), REAL_DINAR_PRICES)
@pytest.mark.parametrize("currency", ["AED", None])
def test_the_same_strings_are_still_refused_for_a_dirham_store(
    text: str, _amount: float, currency: str | None
) -> None:
    # Three decimals on a two-decimal currency most likely means a thousands separator, so
    # "260.000" would be a price wrong by a factor of 1000.
    with pytest.raises(PriceFormatError):
        parse_price(text, currency)


def test_leaving_the_currency_out_keeps_the_two_decimal_rule() -> None:
    assert parse_price("535.00") == ParsedPrice(535.0, None)
    with pytest.raises(PriceFormatError):
        parse_price("535.000")


@pytest.mark.parametrize("currency", ["KWD", "BHD", "OMR"])
def test_each_three_decimal_currency_reads_three_decimals(currency: str) -> None:
    assert parse_price("19.500", currency) == ParsedPrice(19.5, None)


@pytest.mark.parametrize("currency", ["SAR", "QAR", "USD", "GBP"])
def test_two_decimal_currencies_refuse_three_decimals(currency: str) -> None:
    with pytest.raises(PriceFormatError):
        parse_price("19.500", currency)
    assert parse_price("19.50", currency) == ParsedPrice(19.5, None)


@pytest.mark.parametrize(
    "text",
    [
        "260.00",  # two decimals: not a format the dinar stores were seen to use
        "260.0",
        "260",
        "260.0000",
        "1,260.000",
        "260,000",
        "1.260,000",
        "KWD 260.000",
        ".260",
        "-5.000",
        "NaN",
    ],
)
def test_a_dinar_store_still_refuses_what_it_was_not_seen_to_write(text: str) -> None:
    with pytest.raises(PriceFormatError):
        parse_price(text, "KWD")


def test_a_zero_dinar_price_parses_and_is_left_to_the_positive_price_check() -> None:
    assert parse_price("0.000", "KWD").amount == 0.0


def test_a_price_written_with_its_own_code_is_read_the_same_whatever_the_stores_currency() -> None:
    # The store's currency only decides which bare decimal string is a price; the currency written
    # in the text is still returned, and the normaliser compares it with the store's.
    assert parse_price("AED 6,900", "KWD") == ParsedPrice(6900.0, "AED")
    assert parse_price("AED 450", "AED") == ParsedPrice(450.0, "AED")
