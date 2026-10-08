"""``Product.gender`` from the ``shopify`` strategy: who a product is for, read from the store's own
``type`` and ``tags`` (the ``gender_fields`` option).

Why it exists: Sacoor Brothers, Nautica and Maison D'Vie sell for men and women in one search
result, and say which only in these two fields. A search for "black blazer" at Sacoor returned 7
men's and 3 women's blazers; many Nautica titles carry no gender word ("Nelson Pant - Black").

The saved responses under ``fixtures/gender/`` are byte copies of the six stores' real
``/search/suggest.json`` responses recorded on 2026-10-08 (the store adapters' own fixtures; copied
so this file does not depend on them). Nothing here touches the network.
"""

import json
from collections import Counter
from typing import Any

import pytest

from tests.fetch.conftest import (
    GENDER_FIXTURES,
    gender_fixture_text,
    gender_products,
    shopify_product,
    shopify_store,
    suggest_body,
)
from vga.models import Gender, StrategyConfig
from vga.stores.extractors import ShopifyExtractor
from vga.stores.extractors.shopify import DEFAULT_GENDER_FIELDS, GENDER_FIELDS

MEN, WOMEN, UNISEX = Gender.MEN, Gender.WOMEN, Gender.UNISEX
LETTER = {"M": MEN, "W": WOMEN, "U": UNISEX, ".": None}
CURLY = chr(0x2019)  # the curly apostrophe some stores type (Giordano writes Men + this + s)


def extract_genders(body: str, **options: object) -> list[Gender | None]:
    strategy = StrategyConfig(name="shopify", options=dict(options))
    records = ShopifyExtractor().extract(body, shopify_store(), strategy)
    return [record["gender"] for record in records]


def gender_of(**fields: Any) -> Gender | None:
    """The gender read from one product with these ``type`` / ``tags`` (and nothing else set)."""
    [gender] = extract_genders(suggest_body(shopify_product(1, **fields)))
    return gender


# --------------------------------------------------------------------------------------------
# The six stores' real responses: every product, and the counts per store
# --------------------------------------------------------------------------------------------

# One letter per product, in the order the response lists them:
#   M men, W women, U unisex, "." unknown (the store's type and tags say nothing).
SAVED_RESPONSES = {
    ("sacoor-brothers-uae", "suggest-black-blazer.json"): "MMWWMWMMMM",
    ("sacoor-brothers-uae", "suggest-men-shirt.json"): "MMMMMMMMMM",
    ("nautica-uae", "suggest-jacket.json"): "MMMMMMMMMM",
    ("nautica-uae", "suggest-men-shirt.json"): "MMMMMMMMMM",
    ("nautica-uae", "suggest-trousers.json"): "MMMMMMWMWW",
    ("nautica-uae", "suggest-women-dress.json"): "WWWWWWWWWW",
    ("maison-dvie", "suggest-blazer.json"): "WWWWWWWWWW",
    ("maison-dvie", "suggest-shirt.json"): "WWWMWWWMWM",
    ("maison-dvie", "suggest-trousers.json"): "WWWWWWWWWW",
    ("giordano-uae", "suggest-jacket.json"): "..........",
    ("oh-polly", "suggest-blazer.json"): "W.........",
    ("oh-polly", "suggest-heels.json"): "..........",
    ("oh-polly", "suggest-jacket.json"): "..........",
    ("club-l-london", "suggest-blazer.json"): "W..WWWW.WW",
    ("club-l-london", "suggest-heels.json"): "WWWWW.W...",
    ("club-l-london", "suggest-jacket.json"): "WW..W..W..",
}

# (men, women, unisex, unknown) over all of a store's saved responses.
STORE_COUNTS = {
    "sacoor-brothers-uae": (17, 3, 0, 0),
    "nautica-uae": (27, 13, 0, 0),
    "maison-dvie": (3, 27, 0, 0),
    "giordano-uae": (0, 0, 0, 10),
    "oh-polly": (0, 1, 0, 29),
    "club-l-london": (0, 17, 0, 13),
}
"""Where the rule is silent, the titles are: Giordano's ten are all "Men's ..." in the title, and
Oh Polly and Club L London are women-only brands whose titles say nothing about gender. The ranker
falls back to the title for a ``None`` gender, and these two stores' files set ``genders: [women]``
(or are single-brand) for the rest."""


saved = gender_fixture_text


def test_every_saved_response_is_in_the_table() -> None:
    on_disk = {(path.parent.name, path.name) for path in GENDER_FIXTURES.glob("*/*.json")}

    assert on_disk == set(SAVED_RESPONSES)
    assert {store for store, _ in SAVED_RESPONSES} == set(STORE_COUNTS)


@pytest.mark.parametrize(("store_id", "name"), list(SAVED_RESPONSES))
def test_each_product_in_a_saved_response_gets_the_expected_gender(
    store_id: str, name: str
) -> None:
    body = saved(store_id, name)
    titles = [p["title"] for p in json.loads(body)["resources"]["results"]["products"]]

    genders = extract_genders(body)

    expected = SAVED_RESPONSES[(store_id, name)]
    assert len(genders) == len(titles) == len(expected) == 10
    got = "".join(next(k for k, v in LETTER.items() if v is g) for g in genders)
    assert got == expected, list(zip(titles, got, expected, strict=True))


@pytest.mark.parametrize("store_id", list(STORE_COUNTS))
def test_counts_per_store_over_the_saved_responses(store_id: str) -> None:
    counted: Counter[Gender | None] = Counter()
    for (store, name), _ in SAVED_RESPONSES.items():
        if store == store_id:
            counted.update(extract_genders(saved(store, name)))

    men, women, unisex, unknown = STORE_COUNTS[store_id]
    assert (counted[MEN], counted[WOMEN], counted[UNISEX], counted[None]) == (
        men,
        women,
        unisex,
        unknown,
    )


# --- Sacoor: the type is reliable, the tags are not -----------------------------------------


def test_sacoor_women_are_women_although_the_store_tags_them_formalwear_men() -> None:
    body = saved("sacoor-brothers-uae", "suggest-black-blazer.json")
    products = json.loads(body)["resources"]["results"]["products"]
    women = [p for p in products if "/ Woman /" in p["type"]]
    assert len(women) == 3
    assert all("Formalwear Men" in p["tags"] for p in women)  # the trap, in the real data

    genders = extract_genders(body)

    assert [g for p, g in zip(products, genders, strict=True) if "/ Woman /" in p["type"]] == [
        WOMEN,
        WOMEN,
        WOMEN,
    ]
    assert genders.count(MEN) == 7


def test_reading_only_the_tags_would_call_those_women_men() -> None:
    body = saved("sacoor-brothers-uae", "suggest-black-blazer.json")

    assert extract_genders(body, gender_fields=["tags"]).count(MEN) == 10
    assert extract_genders(body, gender_fields=["type"]) == extract_genders(body)


# --- The genders reach the validated Product -------------------------------------------------


def test_the_validated_products_carry_the_gender() -> None:
    name = "suggest-black-blazer.json"
    products = gender_products("sacoor-brothers-uae", name)

    # Sacoor lists a velvet tuxedo blazer and a "pied poule" blazer twice; validation keeps the
    # first of each, so 8 of the 10 products survive, and each keeps its own gender.
    assert len(products) == 8
    assert Counter(p.gender for p in products) == {MEN: 5, WOMEN: 3}
    raw = json.loads(saved("sacoor-brothers-uae", name))["resources"]["results"]["products"]
    women_titles = {p["title"] for p in raw if "/ Woman /" in p["type"]}
    assert len(women_titles) == 3
    for product in products:
        assert product.gender is (WOMEN if product.title in women_titles else MEN)


def test_with_gender_fields_empty_no_product_gets_a_gender() -> None:
    products = gender_products("sacoor-brothers-uae", "suggest-black-blazer.json", gender_fields=[])

    assert len(products) == 8
    assert {p.gender for p in products} == {None}


# --------------------------------------------------------------------------------------------
# The rule, case by case
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("type_", "tags", "expected"),
    [
        # type: "Season / Gender / Category" (Sacoor)
        pytest.param("Winter 2025 / Man / Blazer", ["Blazers"], MEN, id="type man"),
        pytest.param("Summer 2026 / Woman / Suit Blazer", ["Blazers"], WOMEN, id="type woman"),
        pytest.param("Never Out of Stock / Man / Shirt Classic", [], MEN, id="type man, no tags"),
        # type holds the word at the start or the end (Maison D'Vie)
        pytest.param("Women blazers, Jacket", ["Women"], WOMEN, id="type women blazers"),
        pytest.param("Men shirts", ["Men"], MEN, id="type men shirts"),
        # tags: a word inside a longer tag, a hyphenated tag, either case (Nautica, Oh Polly)
        pytest.param("Jackets", ["Jackets for men", "Winter"], MEN, id="tag 'Jackets for men'"),
        pytest.param("Trousers", ["Mens", "mens-new", "Mens-trousers"], MEN, id="tag mens"),
        pytest.param("Shirts", ["men", "Men Shirts", "mens topwear"], MEN, id="tag men"),
        pytest.param("Coats", ["womens-clothing-sale-all"], WOMEN, id="hyphenated womens"),
        pytest.param("Shirts", ["Women", "women-new"], WOMEN, id="tag women"),
        pytest.param("Shirts", ["Polo for Women"], WOMEN, id="tag 'Polo for Women'"),
        pytest.param("SHOES", ["Fabric Type: PU LADIES SHOES"], WOMEN, id="LADIES in capitals"),
        pytest.param("Tops", ["Search: ladies day"], WOMEN, id="ladies"),
        pytest.param("Tops", ["Web Collection: Women's day edit"], WOMEN, id="straight women's"),
        pytest.param("Tops", [f"Women{CURLY}s day edit"], WOMEN, id="curly women's"),
        pytest.param("Tops", ["Men's New In"], MEN, id="straight men's"),
        pytest.param("Tops", [f"Men{CURLY}s New In"], MEN, id="curly men's"),
        pytest.param("Tops", [f"MEN{CURLY}S"], MEN, id="capitals and curly"),
        pytest.param("Dresses", ["Woman"], WOMEN, id="tag woman"),
        pytest.param("Tops", ["Man"], MEN, id="tag man"),
        # one word for the whole department (Signature Studio tags its men's kurta sets Menswear)
        pytest.param("Clothing", ["Buy Dresses", "Menswear"], MEN, id="tag Menswear"),
        pytest.param("Clothing", ["MENSWEAR"], MEN, id="tag MENSWEAR in capitals"),
        pytest.param("Clothing", ["Womenswear", "Sale"], WOMEN, id="tag Womenswear"),
        pytest.param("Menswear", [], MEN, id="type Menswear"),
        # unisex
        pytest.param("Hoodies", ["Unisex"], UNISEX, id="tag unisex"),
        pytest.param("Unisex Hoodies", [], UNISEX, id="type unisex"),
        pytest.param("Hoodies", ["Mens", "Unisex"], UNISEX, id="unisex beside mens"),
        pytest.param("Hoodies", ["Men", "Women", "Unisex"], UNISEX, id="unisex beside both"),
        # type is read first and decides when it names a gender
        pytest.param("Winter 2025 / Woman / Suit", ["Formalwear Men"], WOMEN, id="type wins"),
        pytest.param("Winter 2025 / Man / Blazer", ["Women"], MEN, id="type wins, other way"),
        # tags decide when type is silent
        pytest.param("Jackets", ["Women"], WOMEN, id="type silent, tags decide"),
    ],
)
def test_the_type_and_tags_name_the_gender(type_: str, tags: list[str], expected: Gender) -> None:
    assert gender_of(type=type_, tags=tags) is expected


@pytest.mark.parametrize(
    ("type_", "tags"),
    [
        pytest.param("Coats & Jackets", ["tag"], id="the default test product"),
        pytest.param("Jackets", [], id="no tags"),
        pytest.param("", [], id="nothing at all"),
        pytest.param(None, None, id="fields are null"),
        pytest.param(7, {"a": "Men"}, id="fields of an odd type"),
        pytest.param("Jackets", [5, None, ["Men"]], id="tags that are not text"),
        # a brand, a colour or another word that merely contains or resembles a cue
        pytest.param("Jackets", ["Colour: Amen Green", "Mint", "Menthol"], id="amen, menthol"),
        pytest.param("Jackets", ["Mango", "Roman", "Human Made", "Manchester"], id="man inside"),
        pytest.param("Jackets", ["Madmen", "Mentor", "Mental Health Week"], id="men inside"),
        pytest.param(
            "Jackets", ["Formalwear", "Swimwear", "Sportswear"], id="other wear words are not cues"
        ),
        pytest.param(
            "Dresses", ["city-girl-871", "Collection: COOL GIRL", "Birthday Girl"], id="girl"
        ),
        pytest.param("Dresses", ["Mother of The Bride", "Lady Luck"], id="mother, lady"),
        pytest.param("Fabrics", ["Fabric: man-made fibres", "MAN MADE"], id="man-made"),
        pytest.param("Fabrics", ["Man  -  Made"], id="man - made"),
    ],
)
def test_fields_that_do_not_name_a_gender_give_none(type_: object, tags: object) -> None:
    assert gender_of(type=type_, tags=tags) is None


def test_the_word_women_never_yields_men() -> None:
    spellings = ["women", "Women", "WOMEN", "women's", f"Women{CURLY}s", "womens", "womens-new"]
    for spelling in spellings:
        assert gender_of(type="Tops", tags=[spelling]) is WOMEN, spelling
        assert gender_of(type=spelling, tags=[]) is WOMEN, spelling


def test_a_cue_inside_a_man_made_phrase_does_not_count_but_a_real_one_beside_it_does() -> None:
    assert gender_of(type="Tops", tags=["man-made", "Mens"]) is MEN


@pytest.mark.parametrize(
    ("type_", "tags"),
    [
        pytest.param("Tops", ["Mens", "Women"], id="two tags disagree"),
        pytest.param("Tops", ["Men & Women"], id="one tag names both"),
        pytest.param("Tops", ["Womenswear", "Menswear"], id="two wear tags disagree"),
        pytest.param("Men / Women", [], id="type names both"),
        # the deciding field contradicts itself, so the other field is not used to break the tie
        pytest.param("Men / Women", ["Men"], id="type names both, tags say men"),
    ],
)
def test_a_field_that_names_both_men_and_women_gives_none(type_: str, tags: list[str]) -> None:
    assert gender_of(type=type_, tags=tags) is None


def test_tags_may_be_one_comma_separated_string() -> None:
    assert gender_of(type="Tops", tags="Jackets, Mens, mens-new") is MEN
    assert gender_of(type="Tops", tags="Jackets, Mens, Women") is None


def test_a_title_cue_is_not_read_by_the_extractor_but_is_left_to_the_ranker() -> None:
    """Title-only cue: type and tags are silent, so the product has no gender here; the ranker
    reads "Men's" from the title itself (see tests/rank_text/test_filters_gender.py)."""
    product = shopify_product(1, title="Men's Regular Fit Hoodie Jacket", type="Jackets", tags=[])

    [record] = ShopifyExtractor().extract(
        suggest_body(product), shopify_store(), StrategyConfig(name="shopify")
    )

    assert record["gender"] is None
    assert record["title"] == "Men's Regular Fit Hoodie Jacket"


def test_the_title_is_not_read_for_the_gender() -> None:
    contradicting = shopify_product(1, title="Women's Blazer", type="Man", tags=["Mens"])

    [gender] = extract_genders(suggest_body(contradicting))

    assert gender is MEN


# --------------------------------------------------------------------------------------------
# The gender_fields option
# --------------------------------------------------------------------------------------------

CONFLICTING_PRODUCT = shopify_product(1, type="Winter 2025 / Woman / Suit", tags=["Formalwear Men"])


def test_the_default_reads_type_then_tags() -> None:
    assert DEFAULT_GENDER_FIELDS == ("type", "tags") == GENDER_FIELDS
    body = suggest_body(CONFLICTING_PRODUCT)

    assert extract_genders(body) == extract_genders(body, gender_fields=["type", "tags"])
    assert extract_genders(body) == [WOMEN]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param([], None, id="off"),
        pytest.param(["type"], WOMEN, id="type only"),
        pytest.param(["tags"], MEN, id="tags only"),
        pytest.param(["tags", "type"], MEN, id="tags first"),
        pytest.param(["type", "tags"], WOMEN, id="type first"),
    ],
)
def test_gender_fields_picks_the_fields_and_their_order(
    fields: list[str], expected: Gender | None
) -> None:
    assert extract_genders(suggest_body(CONFLICTING_PRODUCT), gender_fields=fields) == [expected]


@pytest.mark.parametrize("fields", [[], ["type"], ["tags"], ["type", "tags"], ["tags", "type"]])
def test_valid_gender_fields_pass_validation(fields: list[str]) -> None:
    ShopifyExtractor().validate(StrategyConfig(name="shopify", options={"gender_fields": fields}))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param("type", "must be a list of field names", id="a bare string"),
        pytest.param("type, tags", "must be a list of field names", id="a joined string"),
        pytest.param(None, "must be a list of field names", id="null"),
        pytest.param(True, "must be a list of field names", id="a boolean"),
        pytest.param({"type": True}, "must be a list of field names", id="a mapping"),
        pytest.param([1], "must be a list of field names", id="a number in the list"),
        pytest.param(["title"], r"unknown field\(s\) \['title'\]", id="title is not a field"),
        pytest.param(["Type"], r"unknown field\(s\) \['Type'\]", id="names are lower case"),
        pytest.param(["type", "vendor"], r"unknown field\(s\) \['vendor'\]", id="vendor"),
        pytest.param(["type", "type"], "more than once", id="a repeated field"),
    ],
)
def test_invalid_gender_fields_are_rejected_naming_the_option(value: object, message: str) -> None:
    strategy = StrategyConfig(name="shopify", options={"gender_fields": value})

    with pytest.raises(ValueError, match=f"options.gender_fields.*{message}"):
        ShopifyExtractor().validate(strategy)


def test_a_misspelled_option_name_is_still_rejected() -> None:
    strategy = StrategyConfig(name="shopify", options={"gender_field": ["type"]})

    with pytest.raises(ValueError, match="gender_field"):
        ShopifyExtractor().validate(strategy)
