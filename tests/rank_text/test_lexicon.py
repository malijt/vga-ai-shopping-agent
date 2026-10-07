"""Colour lexicon (plan 7.1.1), tokens and gender cues."""

import pytest

from vga.models import Gender
from vga.rank import colour_affinity, find_colours, normalise_colour
from vga.rank.lexicon import (
    CATEGORY_WORDS,
    COLOUR_NAMES,
    OUT_OF_SCOPE_WORDS,
    Colour,
    canon,
    split_colours,
    title_gender,
    tokenize,
)

CURLY_QUOTE = chr(0x2019)
EN_DASH = chr(0x2013)


def test_there_are_at_least_30_colours() -> None:
    assert len(COLOUR_NAMES) >= 30


@pytest.mark.parametrize("name", sorted(COLOUR_NAMES))
def test_every_colour_name_normalises_to_itself(name: str) -> None:
    found = normalise_colour(name)

    assert found is not None
    assert found.name == name


@pytest.mark.parametrize(
    ("text", "name", "shade"),
    [
        pytest.param("dark brown", "brown", "dark", id="dark modifier"),
        pytest.param("light blue", "blue", "light", id="light modifier"),
        pytest.param("deep green", "green", "dark", id="deep is dark"),
        pytest.param("pale pink", "pink", "light", id="pale is light"),
        pytest.param("pastel yellow", "yellow", "light", id="pastel is light"),
        pytest.param("Navy", "navy", "dark", id="navy is dark blue"),
        pytest.param("navy blue", "navy", "dark", id="two-word synonym"),
        pytest.param("BLACK", "black", None, id="upper case"),
        pytest.param("  black  ", "black", None, id="padding"),
        pytest.param("gray", "grey", None, id="spelling variant"),
        pytest.param("maroon", "burgundy", "dark", id="synonym"),
        pytest.param("hot pink", "fuchsia", None, id="two-word synonym beats pink"),
        pytest.param("Fuchsia Pink", "fuchsia", None, id="longest phrase wins"),
        pytest.param("off-white", "off-white", "light", id="hyphenated name"),
        pytest.param("Off White", "off-white", "light", id="the same without the hyphen"),
        pytest.param("chocolate", "brown", "dark", id="a dark brown by name"),
        pytest.param("sky blue", "blue", "light", id="a light blue by name"),
        pytest.param("Soft Lilac", "lilac", "light", id="an unknown word before it is ignored"),
        pytest.param("PERSPEX WITH BLACK", "black", None, id="colour inside a phrase"),
    ],
)
def test_normalise_colour(text: str, name: str, shade: str | None) -> None:
    found = normalise_colour(text)

    assert found is not None
    assert (found.name, found.shade) == (name, shade)


def test_dark_brown_is_brown_and_dark() -> None:
    """The acceptance criterion of 7.1.1."""
    assert normalise_colour("dark brown") == Colour(name="brown", family="brown", shade="dark")


@pytest.mark.parametrize("text", [None, "", "   ", "banana", "dark", "light jacket", "12345"])
def test_text_without_a_colour_gives_none(text: str | None) -> None:
    assert normalise_colour(text) is None
    assert find_colours(text) == []


def test_find_colours_returns_every_colour_in_order() -> None:
    names = [c.name for c in find_colours("Black Charcoal Pinstripe")]

    assert names == ["black", "charcoal"]


def test_a_shade_word_that_does_not_precede_a_colour_is_left_in_the_rest() -> None:
    colours, rest = split_colours(tokenize("light oversized jacket in black"))

    assert [c.name for c in colours] == ["black"]
    assert rest == ["light", "oversized", "jacket", "in"]


def test_the_basic_colour_families_are_covered() -> None:
    families = {c.family for name in COLOUR_NAMES for c in find_colours(name)}

    assert {"black", "white", "grey", "beige", "brown", "red", "pink", "blue", "green"} <= families


@pytest.mark.parametrize(
    ("wanted", "found", "expected"),
    [
        pytest.param("black", "black", 1.0, id="same colour"),
        pytest.param("brown", "dark brown", 1.0, id="asked for no shade"),
        pytest.param("dark brown", "brown", 0.85, id="asked for a shade the product omits"),
        pytest.param("dark brown", "chocolate", 1.0, id="same shade by another name"),
        pytest.param("light blue", "navy", 0.3, id="same family, opposite shade"),
        pytest.param("light blue", "dark blue", 0.5, id="same name, opposite shade"),
        pytest.param("grey", "charcoal", 0.5, id="same family"),
        pytest.param("black", "white", 0.0, id="different colour"),
        pytest.param("black", "charcoal", 0.0, id="black is not grey"),
    ],
)
def test_colour_affinity(wanted: str, found: str, expected: float) -> None:
    a, b = normalise_colour(wanted), normalise_colour(found)
    assert a is not None
    assert b is not None

    assert colour_affinity(a, b) == pytest.approx(expected)


# --------------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        pytest.param("Men's T-Shirt", ["mens", "tshirt"], id="apostrophe and t-shirt"),
        pytest.param(f"Women{CURLY_QUOTE}s Jeans", ["womens", "jeans"], id="curly apostrophe"),
        pytest.param("Dolce & Gabbana", ["dolce", "and", "gabbana"], id="ampersand"),
        pytest.param("Co-ord Set", ["coord", "set"], id="co-ord"),
        pytest.param("Two-Piece Suit", ["twopiece", "suit"], id="two-piece"),
        pytest.param("Slip-On Sneakers", ["slip", "on", "sneakers"], id="hyphen splits"),
        pytest.param("Blazer w/ Belt", ["blazer", "w", "belt"], id="slash"),
        pytest.param(f"Jacket {EN_DASH} Black", ["jacket", "black"], id="dash"),
        pytest.param("", [], id="empty"),
    ],
)
def test_tokenize(text: str, tokens: list[str]) -> None:
    assert tokenize(text) == tokens


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("blazers", "blazer"),
        ("dresses", "dress"),
        ("trainers", "sneakers"),
        ("jumper", "sweater"),
        ("tee", "tshirt"),
        ("trousers", "pants"),
        ("jeans", "jean"),
    ],
)
def test_canon_folds_plurals_and_synonyms(a: str, b: str) -> None:
    assert canon(a) == canon(b)


def test_category_word_lists_do_not_overlap() -> None:
    seen: dict[str, str] = {}
    for category, words in CATEGORY_WORDS.items():
        for word in words:
            assert word not in seen, f"{word!r} is in {category} and {seen[word]}"
            assert word not in OUT_OF_SCOPE_WORDS, f"{word!r} is also out of scope"
            seen[word] = str(category)


# --------------------------------------------------------------------------------------------
# Gender cues
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        pytest.param("Men's Wool Blazer", Gender.MEN, id="men's"),
        pytest.param("Mens Wool Blazer", Gender.MEN, id="mens"),
        pytest.param("Black Blazer for Men", Gender.MEN, id="for men"),
        pytest.param("Black Blazer, Menswear", Gender.MEN, id="menswear"),
        pytest.param("Women's Wool Blazer", Gender.WOMEN, id="women's"),
        pytest.param("Velvet blazer with black color for women", Gender.WOMEN, id="for women"),
        pytest.param("Ladies Blazer", Gender.WOMEN, id="ladies"),
        pytest.param("Unisex Hoodie", Gender.UNISEX, id="unisex"),
        pytest.param("Men's & Women's Hoodie", None, id="both is unclear"),
        pytest.param("Oversized Blazer", None, id="no cue"),
        pytest.param("Man-made Leather Jacket", None, id="'man' alone is not a cue"),
        pytest.param("Boyfriend Blazer", None, id="'boyfriend' is not a cue"),
        pytest.param("Menthol Green Jacket", None, id="'men' inside a word is not a cue"),
        pytest.param("Womenswear Blazer", Gender.WOMEN, id="womenswear is not read as men"),
    ],
)
def test_title_gender_only_reads_clear_cues(title: str, expected: Gender | None) -> None:
    assert title_gender(title) == expected
