"""Which of the five categories a product belongs to, read from its title (plan 7.1.2).

Real store search pads its results with off-category items: a search for "black blazer" returned
9 dresses and 1 blazer at one store (docs/store-qualification/SUMMARY.md). So the ranker decides the
category itself, from the words of the title, and does not trust the store's order or labels.

The rule is "the last garment noun wins", which is how English titles work: in "Blazer Mini Dress"
the dress is the garment and "blazer" describes it, while in "Dress Shirt" the shirt is. Details
that follow "with", "in", "for" and similar words are ignored ("Heeled Boots With Feather Trims").

The fifth category, dresses, holds dresses, gowns, kaftans, abayas, jalabiyas, kurtas and similar
one-piece or ethnic garments. A shirt dress is a dress (never a shirt), so a request for shirts
drops it. Jumpsuits, swimwear, nightwear and accessories (bags, scarves, sheilas, hijabs) belong to
no category and are dropped for every request.

A title gets no category (``None``) when it names no garment noun we know, when it is a set or a
combined listing ("Shirt and Trousers Set"), or when it only uses words that are ambiguous in
retail ("cardigan", "vest", "suit"). ``None`` means "keep it, but give no category bonus": better
to show an odd product than to hide a good one. A set named after a dress-category garment is the
exception: "2 Piece - Embroidered Gown" and "Kurta Set" are dresses.
"""

import re
from typing import Final, Literal

from vga.models import Category
from vga.rank.lexicon import (
    CATEGORY_BY_WORD,
    COORDINATORS,
    CUT_WORDS,
    ETHNIC_SET_STARTERS,
    OUT_OF_SCOPE_OVERRIDES,
    OUT_OF_SCOPE_WORDS,
    SET_WORDS_ANYWHERE,
    SET_WORDS_TRAILING,
    tokenize,
)

OutOfScope = Literal["out_of_scope"]
OUT_OF_SCOPE: Final[OutOfScope] = "out_of_scope"
"""Result of ``classify_title`` for a garment or accessory outside the five categories."""

TitleKind = Category | OutOfScope | None

_BREADCRUMB_SEPARATORS = re.compile("[>/|" + chr(0x203A) + chr(0xBB) + "]")


def _head(tokens: list[str]) -> list[str]:
    """The tokens up to the first word that starts a detail ("with", "in", "for", ...)."""
    for index, token in enumerate(tokens):
        if index > 0 and token in CUT_WORDS:
            return tokens[:index]
    return tokens


def classify_title(title: str) -> TitleKind:
    """A ``Category``, ``OUT_OF_SCOPE`` for a jumpsuit, bag, sheila and the like, or ``None``."""
    tokens = _head(tokenize(title))
    if OUT_OF_SCOPE_OVERRIDES.intersection(tokens):
        return OUT_OF_SCOPE

    matches: list[tuple[int, Category | OutOfScope]] = []
    for index, token in enumerate(tokens):
        category = CATEGORY_BY_WORD.get(token)
        if category is not None:
            matches.append((index, category))
        elif token in OUT_OF_SCOPE_WORDS:
            matches.append((index, OUT_OF_SCOPE))
    if not matches:
        return None

    last_index, last_kind = matches[-1]
    if last_kind is not OUT_OF_SCOPE and last_kind is not Category.DRESSES:
        # A set names several garments, so it has no single category. A set named after a dress,
        # gown or kurta ("2 Piece - Embroidered Gown", "Kurta Set") is one outfit in the dresses
        # category, so that case is exempt.
        if SET_WORDS_ANYWHERE.intersection(tokens):
            return None
        if SET_WORDS_TRAILING.intersection(tokens[last_index + 1 :]):
            return None
        # "Kurta Trouser": a kurta sold with trousers is a set, not a pair of trousers.
        if ETHNIC_SET_STARTERS.intersection(tokens[:last_index]):
            return None
    # "Shirt and Trousers": two different garments joined by "and" is a combined listing.
    for index, kind in reversed(matches[:-1]):
        if kind != last_kind:
            if COORDINATORS.intersection(tokens[index + 1 : last_index]):
                return None
            break
    return last_kind


def infer_category(title: str, breadcrumb: str | None = None) -> Category | None:
    """The category a product title (or, failing that, a breadcrumb) names, else ``None``.

    ``None`` covers titles that name no garment, ambiguous titles and sets, and also items outside
    the five categories (use ``classify_title`` to tell those apart). ``breadcrumb`` is a path
    such as ``"Women > Clothing > Coats & Jackets"``; the most specific part is tried first.
    """
    kind = classify_title(title)
    if kind is None and breadcrumb:
        for part in reversed(_BREADCRUMB_SEPARATORS.split(breadcrumb)):
            kind = classify_title(part)
            if kind is not None:
                break
    return kind if isinstance(kind, Category) else None


def resolve_category(title: str, hint: Category | None) -> TitleKind:
    """The category of a product: its title decides, the store's own label (``hint``) is used only
    when the title says nothing. The title wins because store labels are loose: Oh Polly files a
    "Blazer Mini Dress" under "Coats & Jackets"."""
    kind = classify_title(title)
    return kind if kind is not None else hint
