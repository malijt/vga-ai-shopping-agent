"""Which products get an image score (plan 8.2.2).

Fetching and embedding a thumbnail costs time, so only the best candidates by text score are
scored: 30-50 of them, at most 10 from any one store (assumption A5).
"""

from collections.abc import Sequence

from vga.models import Product

DEFAULT_CANDIDATE_LIMIT = 40
"""How many products to score by default: inside the plan's 30-50, and well inside the 3 s
budget (40 thumbnails took 0.6-1.2 s in the spike)."""

MAX_CANDIDATE_LIMIT = 50
"""The most the ranker will ever score in one call, whatever it is given."""

MAX_PER_STORE = 10
"""The most thumbnails taken from one store (plan 8.2.1)."""


def select_candidates(
    products: Sequence[Product],
    *,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    per_store: int = MAX_PER_STORE,
) -> list[Product]:
    """The products to image-score, taken from ``products`` ordered best first.

    Walks the list in order and keeps a product unless its store already has ``per_store`` of them
    in the selection, or the selection already has ``limit`` products. A product seen twice (same
    ``Product.key``) counts once. The result keeps the input order, so the same input always gives
    the same selection.
    """
    if limit < 0:
        msg = f"limit must not be negative, got {limit}"
        raise ValueError(msg)
    if per_store < 1:
        msg = f"per_store must be at least 1, got {per_store}"
        raise ValueError(msg)
    selected: list[Product] = []
    seen: set[str] = set()
    taken_per_store: dict[str, int] = {}
    for product in products:
        if len(selected) >= limit:
            break
        if product.key in seen or taken_per_store.get(product.store, 0) >= per_store:
            continue
        seen.add(product.key)
        taken_per_store[product.store] = taken_per_store.get(product.store, 0) + 1
        selected.append(product)
    return selected
