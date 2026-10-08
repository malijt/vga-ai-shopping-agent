"""Category inference from product titles (plan 7.1.2).

The labelled set has three kinds of titles:
- real titles copied from the saved store-qualification samples (Oh Polly, Club L London, Luxury
  For You), including the shoes, a blazer-mini-dress and a dress search that returned mostly
  dresses;
- titles from the bundled sample response (``tests/fixtures/response_sample.json``);
- hand-written edge cases: plurals, one-pieces, accessories, sets and ambiguous titles.

The lexicon was written with these cases in view, so the measured accuracy says the rules cover the
cases we thought of, not how well they do on titles we have not seen. ``test_real_titles_are_in_the
_saved_samples`` keeps the "real" labels honest.
"""

import html
import json
import re
from pathlib import Path

import pytest

from vga.models import Category
from vga.rank import classify_title, infer_category, resolve_category
from vga.rank.category import OUT_OF_SCOPE, TitleKind

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "store-qualification" / "samples"
FIXTURE_RESPONSE = Path(__file__).resolve().parents[1] / "fixtures" / "response_sample.json"

TOPS, OUTERWEAR, BOTTOMS, SHOES, DRESSES = (
    Category.TOPS,
    Category.OUTERWEAR,
    Category.BOTTOMS,
    Category.SHOES,
    Category.DRESSES,
)
OOS = OUT_OF_SCOPE
EN_DASH = chr(0x2013)  # Hanayen writes "Sheila - Custom Size" with a real en dash
CURLY_QUOTE = chr(0x2019)  # Al Jazeera Clothing writes its apostrophes this way

# (title, expected, where the title comes from)
REAL_TITLES: list[tuple[str, TitleKind, str]] = [
    ("Feathered Satin Heeled Mule in Blossom Pink", SHOES, "oh-polly/suggest-shoes.json"),
    ("Feathered Satin Heeled Mule in Black", SHOES, "oh-polly/suggest-shoes.json"),
    ("Embellished Satin Heeled Mule in Black", SHOES, "oh-polly/suggest-shoes.json"),
    ("Embellished Satin Heeled Mule in Fuchsia Pink", SHOES, "oh-polly/suggest-shoes.json"),
    ("Single-Breasted Blazer Mini Dress in Black", DRESSES, "oh-polly/suggest-black-blazer.json"),
    ("Oversized Single-Breasted Blazer in Soft Lilac", OUTERWEAR, "oh-polly/..blazer.json"),
    ("Structured Double-Breasted Blazer in Burgundy", OUTERWEAR, "oh-polly/..blazer.json"),
    ("Oversized Single-Breasted Blazer in White", OUTERWEAR, "oh-polly/..blazer.json"),
    (
        "Covergirl | Black Diamante Sling Back Pointed Heels",
        SHOES,
        "club-l-london/suggest-shoes.json",
    ),
    (
        "Soho | Black Satin Pointed Heeled Boots With Feather Trims",
        SHOES,
        "club-l-london/suggest-shoes.json",
    ),
    (
        "Doll Drama | Black Satin Diamante Strappy Platform Heels",
        SHOES,
        "club-l-london/suggest-shoes.json",
    ),
    (
        "Lawless | Hot Pink Satin Pointed Court Heels With Diamante Brooches",
        SHOES,
        "club-l-london/suggest-shoes.json",
    ),
    (
        "Carlin | Black Plunge-Neck Tailored Mini Dress With Button Detailing",
        DRESSES,
        "club-l-london/suggest-black-blazer.json",
    ),
    (
        "Angel | Black Plunge-Neck Tailored Mini Dress With Gold-Detailing",
        DRESSES,
        "club-l-london/suggest-black-blazer.json",
    ),
    (
        "Friya | Black Velvet Sweetheart-Neck Tailored Mini Dress",
        DRESSES,
        "club-l-london/suggest-black-blazer.json",
    ),
    (
        "Vergia | Black Lace Tailored-Blazer",
        OUTERWEAR,
        "club-l-london/suggest-black-blazer.json",
    ),
    (
        "Unbeaten | White Fitted Corset Blazer Jacket",
        OUTERWEAR,
        "club-l-london/product-jsonld.json",
    ),
    ("Stella McCartney OVERSIZED BLAZER", OUTERWEAR, "luxury-for-you/search-black-blazer.html"),
    ("SEFR AMARE BLAZER", OUTERWEAR, "luxury-for-you/search-black-blazer.html"),
    ("Fendi Fendi Jackets Black", OUTERWEAR, "luxury-for-you/search-black-blazer.html"),
    ("ANINE BING HUDA BLAZER - BLACK", OUTERWEAR, "luxury-for-you/search-black-blazer.html"),
    (
        "Dolce & Gabbana black Blazer with all-over stripe motif and notched revers in wool "
        "for women",
        OUTERWEAR,
        "luxury-for-you/search-black-blazer.html",
    ),
    (
        "Emporio Armani Blazer with lapel collar and long sleeves in black wool for men",
        OUTERWEAR,
        "luxury-for-you/search-black-blazer.html",
    ),
    (
        "Semicouture Velvet blazer with elegant details and black color for women",
        OUTERWEAR,
        "luxury-for-you/search-black-blazer.html",
    ),
    ('BLAZER "DELILAH"', OUTERWEAR, "luxury-for-you/product-jsonld.json"),
    # Dresses, abayas, kaftans, kurtas and sheilas, from the stores found for the fifth category
    # (docs/store-qualification/dress-store-discovery.md).
    (
        "Neda Plain Abaya Front Open with Buttons",
        DRESSES,
        "hanayen/suggest-abaya.json",
    ),
    ("Asymmetric Modern Crystalized Abaya", DRESSES, "hanayen/suggest-abaya.json"),
    ("Off-White Under Abaya Dress In Satin", DRESSES, "hanayen/suggest-dress.json"),
    ("Embroidered Black Abaya Dress Design", DRESSES, "hanayen/suggest-dress.json"),
    ("Kaftan Style Under Abaya", DRESSES, "hanayen/suggest-kaftan.json"),
    ("GIGI BURGUNDY ABAYA", DRESSES, "maison-arabelle/suggest-abaya.json"),
    ("JALILA GREEN FLORAL KAFTAN", DRESSES, "maison-arabelle/suggest-kaftan.json"),
    ("ZAHRA GOLD DRESS WITH CAPE", DRESSES, "maison-arabelle/suggest-dress.json"),
    ("Printed Dress - AS26-92", DRESSES, "nishat-linen-uae/suggest-dress.json"),
    ("Printed Kaftan - FW24-45", DRESSES, "nishat-linen-uae/suggest-kaftan.json"),
    ("2 Piece - Embroidered Gown - FE26-128", DRESSES, "nishat-linen-uae/suggest-abaya.json"),
    ("Embroidered Kurta - NQ26-008", DRESSES, "nishat-linen-uae/suggest-kurta.json"),
    ("ZAH STUDIO - Vela Kaftan & Izaar", DRESSES, "signature-studio/suggest-kaftan.json"),
    ("Black Chiffon Sheila " + EN_DASH + " Custom Size", OOS, "hanayen/suggest-kaftan.json"),
    # The six stores of the modest and ethnic wear pass (Module 2.7,
    # docs/store-qualification/modest-ethnic-wear-discovery.md): regional garment names, and two
    # accessory spellings the list did not have.
    ("Pink and Black Zigzag Cotton Kaftan", DRESSES, "daraat/suggest-kaftan.json"),
    ("Sumou Abaya (Linen)", DRESSES, "shadow-kw/suggest-abaya.json"),
    ("Special Chiffon Crystalized Shaila", OOS, "shadow-kw/suggest-kaftan.json"),
    ("Cotton Plain Taqiyah Triangle", OOS, "shadow-kw/suggest-kaftan.json"),
    ("Dara'a 2026", DRESSES, "her-highness-q8/suggest-daraa.json"),
    ("Ayesha Jilbab", DRESSES, "veil-essentials-kw/suggest-jilbab.json"),
    (
        "Men" + CURLY_QUOTE + "s Summer Dishdasha by Al Jazeera",
        DRESSES,
        "al-jazeera-clothing/suggest-dishdasha.json",
    ),
    ("UAE-Regular Fit Embroidered Kurta", DRESSES, "gul-ahmed-uae/suggest-kurta.json"),
    # "suit" is a South Asian suit at Nishat Linen and a men's suit at Sacoor Brothers; the
    # lexicon leaves the word out, so both stay uncategorised (kept, no category bonus).
    ("2 Piece - Embroidered Suit - FE26-130", None, "nishat-linen-uae/suggest-abaya.json"),
    (
        "Single Breasted Black Suit In Wool Blend",
        None,
        "sacoor-brothers-uae/suggest-black-blazer.json",
    ),
    # A kurta sold with trousers is a set, not a pair of trousers.
    ("KUNZUL CHANNAR - Light blue kurta trouser", None, "signature-studio/suggest-kurta.json"),
]

FIXTURE_TITLES: list[tuple[str, TitleKind]] = [
    ("Oversized Blazer", OUTERWEAR),
    ("Silk-Lined Tuxedo Blazer", OUTERWEAR),
    ("Cashmere Blend Oversized Blazer", OUTERWEAR),
    ("Low-Top Canvas Sneakers", SHOES),
    ("Everyday White Trainers", SHOES),
    ("Platform Leather Sneakers", SHOES),
    (
        "Oversized Double-Breasted Relaxed-Fit Tailored Wool Blend Blazer Jacket With Notch "
        "Lapel, Structured Padded Shoulders, Two Flap Pockets, Functional Cuff Buttons, Full "
        "Satin Lining And Interior Chest Pocket, Machine Washable, Available In Regular And "
        "Extended Sizes, Black Charcoal Pinstripe",
        OUTERWEAR,
    ),
]

HAND_WRITTEN: list[tuple[str, TitleKind]] = [
    # tops
    ("Women's Cotton Crew Neck T-Shirt", TOPS),
    ("Men's Oxford Button-Down Shirt", TOPS),
    ("Ribbed Knit Tank Top", TOPS),
    ("Oversized Hoodie", TOPS),
    ("Fine Knit Crew Neck Jumper", TOPS),
    ("Satin Cami Top", TOPS),
    ("Long Sleeve Polo Shirt", TOPS),
    ("Striped Linen Blouses", TOPS),
    ("Graphic Tee", TOPS),
    ("Cropped Sweatshirt", TOPS),
    ("Dress Shirt", TOPS),
    ("Short Sleeve Shirt", TOPS),
    # outerwear
    ("Faux Leather Biker Jacket", OUTERWEAR),
    ("Wool Blend Overcoat", OUTERWEAR),
    ("Padded Puffer Jacket", OUTERWEAR),
    ("Classic Trench Coat", OUTERWEAR),
    ("Bomber Jacket for Men", OUTERWEAR),
    ("Water-Resistant Parka", OUTERWEAR),
    ("Denim Jacket", OUTERWEAR),
    ("Jean Jacket", OUTERWEAR),
    ("Oversized Wool Cape", OUTERWEAR),
    ("Belted Wool Coat", OUTERWEAR),
    # bottoms
    ("High-Waisted Wide-Leg Jeans", BOTTOMS),
    ("Pleated Midi Skirt", BOTTOMS),
    ("Tailored Trousers", BOTTOMS),
    ("Cargo Pants", BOTTOMS),
    ("Denim Shorts", BOTTOMS),
    ("Jogger Sweatpants", BOTTOMS),
    ("Faux Leather Leggings", BOTTOMS),
    ("Boot Cut Jeans", BOTTOMS),
    ("Dress Pants", BOTTOMS),
    # "khakis" is the plural noun for trousers; "khaki" alone is a colour
    ("Men Loose Straight Cotton Poplin Khakis", BOTTOMS),
    ("Men's Relaxed Stretch Twill Cargo Khakis", BOTTOMS),
    ("Slim Fit Khakis in Stone", BOTTOMS),
    ("Khaki Chinos", BOTTOMS),
    ("Khaki Bomber Jacket", OUTERWEAR),
    ("Khaki Linen Shirt", TOPS),
    ("Khaki", None),
    # shoes
    ("Leather Chelsea Boots", SHOES),
    ("White Leather Low-Top Sneakers", SHOES),
    ("Strappy Block Heel Sandals", SHOES),
    ("Slip-On Loafers", SHOES),
    ("Running Trainers", SHOES),
    ("Ballet Flats", SHOES),
    ("Suede Ankle Boots", SHOES),
    ("Dress Shoes", SHOES),
    # dresses and ethnic wear
    ("Satin Midi Dress", DRESSES),
    ("Floral Maxi Dress", DRESSES),
    ("Evening Gown", DRESSES),
    ("Black Abaya", DRESSES),
    ("Shirt Dress", DRESSES),
    ("Sweater Dress", DRESSES),
    ("Blazer Dress", DRESSES),
    ("Floral Print Kaftan", DRESSES),
    ("Moroccan Jalabiya", DRESSES),
    ("Open Front Abayas", DRESSES),
    ("White Cotton Kurta Set", DRESSES),
    ("Embroidered Kurti", DRESSES),
    ("Embroidered Lehenga Choli", DRESSES),
    ("Men's Kandura", DRESSES),
    ("Two-Piece Embroidered Gown", DRESSES),
    ("Co-ord Set Dress", DRESSES),
    ("Dresses", DRESSES),
    # a garment or accessory outside the five categories
    ("Linen Jumpsuit", OOS),
    ("Leather Tote Bag", OOS),
    ("Chain Belt", OOS),
    ("Wool Beanie Hat", OOS),
    ("Silk Scarf", OOS),
    ("Gold Hoop Earrings", OOS),
    ("Black Chiffon Sheila", OOS),
    ("Satin Hijab", OOS),
    ("Embroidered Dupatta", OOS),
    ("Bikini Top", OOS),
    ("Cotton Pyjama Set", OOS),
    ("Cotton Nightdress", OOS),
    ("Satin Night Dress", OOS),
    ("Satin Dressing Gown", OOS),
    ("Terry Bathrobe", OOS),
    ("Swim Dress", OOS),
    ("Aviator Sunglasses", OOS),
    ("Shoe Bag", OOS),
    ("Boxer Shorts", OOS),
    ("Coat Hanger", OOS),
    ("Boot Polish", OOS),
    # ambiguous, a set, or no garment named: no category
    ("Two-Piece Suit Set", None),
    ("Embroidered Three Piece Suit", None),
    ("Kurta and Trousers Set", None),
    ("Abaya and Sheila", None),
    ("Co-ord Set in Linen", None),
    ("Linen Blazer and Trousers Set", None),
    ("Shirt & Trousers", None),
    ("Black Oversized", None),
    ("Essential Capsule Collection", None),
    ("Longline Cardigan", None),
    ("Tailored Tuxedo", None),
    ("Zip-Up Gilet", None),
    ("Gift Card", None),
]

ALL_CASES: list[tuple[str, TitleKind]] = (
    [(title, expected) for title, expected, _ in REAL_TITLES] + FIXTURE_TITLES + HAND_WRITTEN
)


def _label(expected: TitleKind) -> str:
    return "out of scope" if expected == OOS else str(expected)


@pytest.mark.parametrize(
    ("title", "expected"),
    [pytest.param(t, e, id=f"{t[:50]} -> {_label(e)}") for t, e in ALL_CASES],
)
def test_title_is_classified(title: str, expected: TitleKind) -> None:
    assert classify_title(title) == expected


def test_the_labelled_set_is_big_enough_and_at_least_90_percent_correct() -> None:
    wrong = [(t, e, classify_title(t)) for t, e in ALL_CASES if classify_title(t) != e]
    accuracy = 1 - len(wrong) / len(ALL_CASES)

    assert len(ALL_CASES) >= 40
    assert accuracy >= 0.90, f"{accuracy:.0%} on {len(ALL_CASES)} titles; wrong: {wrong}"


def test_the_set_covers_every_outcome_and_all_three_sources() -> None:
    expected = {e for _, e in ALL_CASES}

    assert expected == {TOPS, OUTERWEAR, BOTTOMS, SHOES, DRESSES, OOS, None}
    assert len(REAL_TITLES) >= 20
    assert len(HAND_WRITTEN) >= 40


def test_real_titles_are_in_the_saved_samples() -> None:
    """Every title labelled "real" really is in the store-qualification samples."""
    found: set[str] = set()
    for path in SAMPLES.glob("*/suggest-*.json"):
        products = json.loads(path.read_text(encoding="utf-8"))["resources"]["results"]["products"]
        found.update(product["title"] for product in products)
    for path in SAMPLES.glob("*/product-jsonld.json"):
        found.add(json.loads(path.read_text(encoding="utf-8"))["name"])
    cards = (SAMPLES / "luxury-for-you" / "search-black-blazer.html").read_text(encoding="utf-8")
    found.update(
        html.unescape(label).removeprefix("Open product ")
        for label in re.findall(r'aria-label="(Open product [^"]*)"', cards)
    )

    missing = [title for title, _, _ in REAL_TITLES if title not in found]

    assert not missing, f"not in the saved samples: {missing}"


def test_fixture_titles_are_in_the_bundled_sample_response() -> None:
    sample = json.loads(FIXTURE_RESPONSE.read_text(encoding="utf-8"))
    titles = {
        scored["product"]["title"]
        for group in sample["groups"]
        for tier in group["tiers"]
        for scored in tier["results"]
    }

    assert {title for title, _ in FIXTURE_TITLES} <= titles


# --------------------------------------------------------------------------------------------
# The rules behind the labels
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        pytest.param("Blazer Mini Dress", DRESSES, id="the last garment noun wins: a dress"),
        pytest.param("Dress Shirt", TOPS, id="the last garment noun wins: a shirt"),
        pytest.param("Dress Pants", BOTTOMS, id="'dress' before another noun is only a modifier"),
        pytest.param("Dress Shoes", SHOES, id="'dress' before shoes is only a modifier"),
        pytest.param("Blazer Jacket", OUTERWEAR, id="two nouns of one category"),
        pytest.param("Heels With Diamante Brooches", SHOES, id="detail after 'with' is ignored"),
        pytest.param("Jacket in Black Wool", OUTERWEAR, id="detail after 'in' is ignored"),
        pytest.param("Sneakers for Men", SHOES, id="detail after 'for' is ignored"),
        pytest.param("Short Sleeve Dress", DRESSES, id="'short' alone is not shorts"),
        pytest.param("SHIRTS", TOPS, id="upper case and plural"),
        pytest.param("   ", None, id="blank"),
        pytest.param("", None, id="empty"),
        pytest.param("With Belt Bag", OOS, id="a title that starts with a cut word"),
    ],
)
def test_the_last_garment_noun_decides(title: str, expected: TitleKind) -> None:
    assert classify_title(title) == expected


def test_a_swimwear_or_sleepwear_word_makes_the_title_out_of_scope_anywhere() -> None:
    assert classify_title("Bikini Top") == OOS
    assert classify_title("Swim Shorts") == OOS
    assert classify_title("Pyjama Shirt") == OOS


@pytest.mark.parametrize(
    "title",
    [
        "Cotton Nightdress",
        "Night Dress",
        "Night-Gown in Satin",
        "Sleep Dress",
        "Satin Dressing Gown",
        "Swim Dress",
        "Terry Bathrobe",
    ],
)
def test_nightwear_swimwear_and_robes_stay_out_of_scope_even_when_they_name_a_dress(
    title: str,
) -> None:
    # Dresses and gowns are a category now, so these are the titles that must not leak into it.
    assert classify_title(title) == OOS


@pytest.mark.parametrize("title", ["Linen Jumpsuit", "Cotton Playsuit", "Denim Romper"])
def test_a_jumpsuit_playsuit_or_romper_is_not_a_dress(title: str) -> None:
    # The BRD lists dresses, gowns, kaftans, abayas, kurtas "and similar one-piece or ethnic
    # garments". A jumpsuit has legs, so it is not similar to those and stays out of scope.
    assert classify_title(title) == OOS


@pytest.mark.parametrize(
    "title",
    [
        "Black Chiffon Sheila",
        "Chiffon Shayla Scarf",
        "Satin Hijab",
        "Silk Headscarf",
        "Embroidered Dupatta",
        "Cotton Niqab",
        "Red Ghutra",
    ],
)
def test_head_coverings_and_scarves_are_accessories_not_dresses(title: str) -> None:
    assert classify_title(title) == OOS


@pytest.mark.parametrize(
    "title",
    [
        "Abaya with Sheila",
        "Embroidered Abaya with Matching Hijab",
        "Kaftan Dress in Black",
        "Gown for Women",
    ],
)
def test_a_dress_with_an_accessory_named_after_a_cut_word_is_still_a_dress(title: str) -> None:
    assert classify_title(title) == DRESSES


@pytest.mark.parametrize(
    "title",
    [
        "2 Piece - Embroidered Gown",
        "Three Piece Kaftan Set",
        "Kurta Set",
        "Abaya Set",
        "Co-ord Dress Set",
    ],
)
def test_a_set_named_after_a_dress_is_still_dresses(title: str) -> None:
    # A two-piece gown or a kurta set is one outfit in the dresses category; for the other four
    # categories a set has no single category and gets none.
    assert classify_title(title) == DRESSES


@pytest.mark.parametrize(
    "title",
    [
        "Linen Shirt and Trousers Set",
        "Two-Piece Skirt Set",
        "Co-ord Set with Blazer",
    ],
)
def test_sets_of_the_other_categories_still_have_no_category(title: str) -> None:
    assert classify_title(title) is None


@pytest.mark.parametrize(
    "title", ["Light Blue Kurta Trouser", "Cotton Kurta Pants", "Kameez Trousers", "Kurta Shirt"]
)
def test_a_kurta_sold_with_trousers_is_a_set_not_a_pair_of_trousers(title: str) -> None:
    # Signature Studio sells "kurta trouser" sets. Read by the last-noun rule they would be
    # bottoms and would be offered to a shopper who asked for trousers.
    assert classify_title(title) is None


def test_a_kurta_with_trousers_after_a_cut_word_is_a_kurta() -> None:
    assert classify_title("Embroidered Kurti with Palazzo") == DRESSES


GULF_GARMENT_WORDS = [
    # (word, plural)
    ("dishdasha", "dishdashas"),
    ("dishdashah", "dishdashahs"),
    ("dishdash", "dishdashes"),
    ("kandura", "kanduras"),
    ("kandora", "kandoras"),
    ("kandoura", "kandouras"),
    ("thobe", "thobes"),
    ("thawb", "thawbs"),
    ("thoub", "thoubs"),
    ("jubba", "jubbas"),
    ("jubbah", "jubbahs"),
    ("daraa", "daraas"),
    ("burqa", "burqas"),
    ("burka", "burkas"),
    ("burkha", "burkhas"),
]


@pytest.mark.parametrize(("word", "plural"), GULF_GARMENT_WORDS)
def test_a_gulf_garment_name_is_a_dress_in_the_singular_and_the_plural(
    word: str, plural: str
) -> None:
    assert classify_title(word) == DRESSES
    assert classify_title(plural) == DRESSES


# Real titles from the newly qualified Kuwaiti stores and a UAE-made thobe store; the sources are
# in docs/store-qualification/ (Al Jazeera Clothing, Her Highness Q8, Veil Essentials).
@pytest.mark.parametrize(
    "title",
    [
        "Men's Summer Dishdasha by Al Jazeera",
        "Men's Elegant Winter Dishdasha by Al Jazeera",
        "Boys' Bright White Summer Dishdasha by Al Jazeera",
        "Youth Summer Dishdasha by Al Jazeera with Elegant Fit",
        "Newborn White Dishdasha by Al Jazeera",
        "Kids' Linen Dishdasha by Al Jazeera",
        "White Kuwaiti Dishdasha-Mens",
        "Khaki Green Emirati Kandora - Men",
        "White Emirati Kandora-Babies",
        "Mens Qatari Thobe 3 Pcs Set",
        "Dara'a 2026",
        "Burgundy Kaftan",
        "Ayesha Jilbab",
        "Abaya flora",
    ],
)
def test_the_new_kuwaiti_and_gulf_robe_titles_are_dresses(title: str) -> None:
    assert classify_title(title) == DRESSES


def test_a_daraa_written_with_a_curly_apostrophe_is_a_dress() -> None:
    assert classify_title(f"Dara{CURLY_QUOTE}a 2026") == DRESSES


@pytest.mark.parametrize(
    "title",
    [
        "Silk Kimono",
        "2 layer khimar Iqra",
        "Cotton Shalwar",
        "Embroidered Salwar",
        "Sherwal",
    ],
)
def test_words_left_for_the_project_owner_to_decide_stay_uncategorised(title: str) -> None:
    """Known open decisions, recorded and not solved: whether a khimar is a garment or a head
    covering, and how a shalwar (salwar, sherwal) on its own should be classed. A kimono is
    ambiguous in retail use. Each stays without a category: kept, with no category bonus."""
    assert classify_title(title) is None


def test_a_word_that_means_a_south_asian_suit_here_and_a_mens_suit_there_is_left_alone() -> None:
    """Known hard case, recorded and not solved: "suit" is a three-piece embroidered outfit at
    Nishat Linen UAE and a tailored men's suit at Sacoor Brothers. Nothing in a title tells the
    two apart, so neither gets a category: both are kept for any request, without a category bonus.
    (A women-only request still drops the men's suit through the store's own gender data.)"""
    assert classify_title("2 Piece - Embroidered Suit - FE26-130") is None
    assert classify_title("Single Breasted Black Suit In Wool Blend") is None


def test_infer_category_returns_none_only_for_out_of_scope_titles() -> None:
    assert infer_category("Satin Midi Dress") is DRESSES
    assert infer_category("Leather Tote Bag") is None
    assert infer_category("Black Chiffon Sheila") is None


@pytest.mark.parametrize(
    ("title", "breadcrumb", "expected"),
    [
        pytest.param("Gift Item", "Women > Clothing > Coats & Jackets", OUTERWEAR, id="coats"),
        pytest.param("Gift Item", "Men / Footwear / Boots", SHOES, id="boots"),
        pytest.param("Gift Item", "Women > Shoes & Bags", None, id="two categories"),
        pytest.param("Gift Item", "Women > Clothing", None, id="too general"),
        pytest.param("Gift Item", None, None, id="no breadcrumb"),
        pytest.param("Classic Shirt", "Women > Coats & Jackets", TOPS, id="the title wins"),
    ],
)
def test_breadcrumb_is_used_only_when_the_title_says_nothing(
    title: str, breadcrumb: str | None, expected: Category | None
) -> None:
    assert infer_category(title, breadcrumb) == expected


def test_the_stores_own_label_loses_to_the_title() -> None:
    # Oh Polly files "Single-Breasted Blazer Mini Dress" under "Coats & Jackets".
    assert resolve_category("Single-Breasted Blazer Mini Dress in Black", OUTERWEAR) == DRESSES
    assert resolve_category("Tailored Shirt", OUTERWEAR) == TOPS
    assert resolve_category("Black Chiffon Sheila", DRESSES) == OOS


def test_the_stores_own_label_is_used_when_the_title_names_no_garment() -> None:
    assert resolve_category("Black Oversized", OUTERWEAR) == OUTERWEAR
    assert resolve_category("Black Oversized", None) is None
