"""Text and attribute score: how well a product title fits what the shopper asked for (plan 7.2.2).

A weighted overlap, not a model: pure and deterministic. Five parts, each 0 to 1:

- overlap: the share of the request's product words found in the title. Words naming a garment
  ("blazer") weigh 3, other words ("oversized") weigh 1. The request has up to three keyword
  variants that are alternative phrasings, so the best-matching variant counts.
- category: 1 when the title names the requested category, 0 when it names none or another.
- colour: how well a colour on the product (its colour field or its title) fits the requested
  colour, using the colour lexicon. A product that states no colour gets a small credit (titles
  often leave it out); one with a different colour gets none.
- style and material: the share of the requested style or material words found in the title.

A part that does not apply (no colour requested, no material requested) is left out and the
others are renormalised, so a request without a colour does not penalise any product. A title
matching every part of the request scores 1.
"""

from dataclasses import dataclass

from vga.models import Category, ItemIntent, Product
from vga.rank.category import resolve_category
from vga.rank.lexicon import (
    GENDER_WORDS,
    HEAD_WORDS,
    STOPWORDS,
    Colour,
    canon,
    colour_affinity,
    find_colours,
    split_colours,
    tokenize,
)

WEIGHT_OVERLAP = 0.40
WEIGHT_CATEGORY = 0.20
WEIGHT_COLOUR = 0.25
WEIGHT_STYLE = 0.10
WEIGHT_MATERIAL = 0.05
"""Share of each part in the text score. Only the parts that apply are counted."""

HEAD_TERM_WEIGHT = 3.0
"""Weight of a garment noun in the overlap; any other word weighs 1."""

UNKNOWN_COLOUR_CREDIT = 0.3
"""Colour part for a product that states no colour at all."""

CLOSE_COLOUR = 0.5
"""A colour affinity at or above this counts as a colour match worth mentioning."""


@dataclass(frozen=True)
class TextMatch:
    """The text score with the facts behind it, so the reason sentence can use only what is true."""

    score: float
    overlap: float | None
    """Weighted share of the request's words found in the title; ``None`` if it has none."""
    colour: Colour | None
    """A colour on the product that fits the requested colour (affinity at least 0.5), else
    ``None``. Taken from the product's own colour field or title, never from the request."""
    colour_fit: float | None
    """How well ``colour`` fits the requested colour (0.5 to 1); ``None`` when ``colour`` is."""
    category_matches: bool


def _terms(text: str | None) -> list[str]:
    """Product words in ``text``: no colours, price words, gender words or numbers, in order,
    without repeats."""
    if not text:
        return []
    _, rest = split_colours(tokenize(text))
    words = [
        canon(token)
        for token in rest
        if token not in STOPWORDS and token not in GENDER_WORDS and not token.isdigit()
    ]
    return list(dict.fromkeys(words))


def _weight(term: str) -> float:
    return HEAD_TERM_WEIGHT if term in HEAD_WORDS else 1.0


def _coverage(terms: list[str], present: set[str]) -> float:
    total = sum(_weight(term) for term in terms)
    return sum(_weight(term) for term in terms if term in present) / total


def _overlap(item: ItemIntent, present: set[str]) -> float | None:
    variants = [terms for terms in (_terms(text) for text in item.search_keywords) if terms]
    if not variants:
        return None
    return max(_coverage(terms, present) for terms in variants)


def _share(text: str | None, present: set[str]) -> float | None:
    terms = _terms(text)
    if not terms:
        return None
    return sum(1 for term in terms if term in present) / len(terms)


def _wanted_colours(item: ItemIntent) -> list[Colour]:
    # The model fills ``colour``; with the raw-text fallback it is empty and the colour is only in
    # the keywords.
    return find_colours(item.colour) or find_colours(item.search_keywords[0])


def _colour_part(item: ItemIntent, product: Product) -> tuple[float | None, Colour | None, float]:
    """The colour part of the score, the colour found on the product that matches the request
    (``None`` if none does), and that match's affinity (0 if none)."""
    wanted = _wanted_colours(item)
    if not wanted:
        return None, None, 0.0
    found = find_colours(product.colour) + find_colours(product.title)
    if not found:
        return UNKNOWN_COLOUR_CREDIT, None, 0.0
    best_affinity = 0.0
    best: Colour | None = None
    for candidate in found:
        for want in wanted:
            affinity = colour_affinity(want, candidate)
            if affinity > best_affinity:
                best_affinity, best = affinity, candidate
    if best_affinity < CLOSE_COLOUR:
        return best_affinity, None, 0.0
    return best_affinity, best, best_affinity


def match_text(item: ItemIntent, product: Product) -> TextMatch:
    """Score ``product`` against ``item`` and keep the facts behind the score."""
    present = {canon(token) for token in tokenize(product.title)}
    overlap = _overlap(item, present)
    kind = resolve_category(product.title, product.category)
    category_matches = isinstance(kind, Category) and kind is item.category
    colour_value, colour, colour_fit = _colour_part(item, product)

    parts: list[tuple[float, float | None]] = [
        (WEIGHT_OVERLAP, overlap),
        (WEIGHT_CATEGORY, 1.0 if category_matches else 0.0),
        (WEIGHT_COLOUR, colour_value),
        (WEIGHT_STYLE, _share(item.style, present)),
        (WEIGHT_MATERIAL, _share(item.material, present)),
    ]
    applicable = [(weight, value) for weight, value in parts if value is not None]
    total_weight = sum(weight for weight, _ in applicable)
    score = sum(weight * value for weight, value in applicable) / total_weight
    return TextMatch(
        score=min(1.0, max(0.0, score)),
        overlap=overlap,
        colour=colour,
        colour_fit=colour_fit if colour is not None else None,
        category_matches=category_matches,
    )


def text_score(item: ItemIntent, product: Product) -> float:
    """Just the 0-1 text score; see ``match_text`` for the facts behind it."""
    return match_text(item, product).score
