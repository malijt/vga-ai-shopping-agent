"""Hard filters (plan 7.2.1, PRD R7): what is dropped before any scoring.

A product is dropped when
- the store says it is out of stock (``in_stock is False``; ``None`` means unknown and is kept),
- its title names a garment outside the five categories (jumpsuit, bag, belt, sheila, ...),
- its category is known and differs from the one requested (a dress is dropped for a request for
  shirts, and a shirt for a request for dresses),
- the request names a gender explicitly (men or women) and its title marks a children's product
  ("Boys Crew Neck T-shirt", kids, baby, toddler, infant, junior), or
- the request names a gender explicitly and the product is clearly for the other one.

"Clearly for the other one" is what the store's own data says (``Product.gender``, read from its
``type`` and ``tags``) and, only when that is unknown (``None``), what the title says. A unisex
product, and one whose gender nobody states, is kept for either request.

A product is never dropped for being over budget (assumption A4) and never for a category that
cannot be inferred (it is kept without a category bonus). Gender that the model only inferred
(assumption A3, BRD Rule 8) is never used here.
"""

from dataclasses import dataclass
from enum import StrEnum

from vga.models import Category, Gender, GenderSource, ItemIntent, Product
from vga.rank.category import OUT_OF_SCOPE, resolve_category
from vga.rank.lexicon import is_childrens_title, title_gender


class DropReason(StrEnum):
    """Why a product was dropped, for logs and the candidate dump."""

    OUT_OF_STOCK = "out_of_stock"
    OUT_OF_SCOPE = "out_of_scope_garment"
    WRONG_CATEGORY = "wrong_category"
    GENDER_MISMATCH = "gender_mismatch"
    CHILDRENS_ITEM = "childrens_item"


@dataclass(frozen=True)
class FilterResult:
    """The outcome for one product: kept or dropped (with the reason), and its category."""

    keep: bool
    reason: DropReason | None
    category: Category | None
    """The product's category when it is known and kept, else ``None``."""


def _drop(reason: DropReason) -> FilterResult:
    return FilterResult(keep=False, reason=reason, category=None)


def _stated_gender(product: Product) -> Gender | None:
    """Who the product is for: the store's own data when it says, else a clear cue in the title."""
    return product.gender if product.gender is not None else title_gender(product.title)


def apply_hard_filters(item: ItemIntent, product: Product) -> FilterResult:
    """Decide whether ``product`` may be shown for ``item``."""
    if product.in_stock is False:
        return _drop(DropReason.OUT_OF_STOCK)

    kind = resolve_category(product.title, product.category)
    if kind == OUT_OF_SCOPE:
        return _drop(DropReason.OUT_OF_SCOPE)
    category = kind if isinstance(kind, Category) else None
    if category is not None and category is not item.category:
        return _drop(DropReason.WRONG_CATEGORY)

    if item.gender in (Gender.MEN, Gender.WOMEN) and item.gender_source is GenderSource.EXPLICIT:
        if is_childrens_title(product.title):
            return _drop(DropReason.CHILDRENS_ITEM)
        stated = _stated_gender(product)
        if stated in (Gender.MEN, Gender.WOMEN) and stated is not item.gender:
            return _drop(DropReason.GENDER_MISMATCH)

    return FilterResult(keep=True, reason=None, category=category)
