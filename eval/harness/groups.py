"""Small helpers over a ``SearchResponse`` that several checks share.

The "top 10" lives here, once (plan assumption A15): the 10 best results of a garment group by
overall match score across all four price ranges, never ordered by price. Every part of the
harness that needs a top 10 (the labelling sheet, good@10, the link check) calls ``top_results``,
so they cannot disagree about which products they mean.
"""

from collections import Counter

from vga.models import GarmentGroup, ScoredProduct, SearchResponse

TOP_N = 10
"""How many results per garment group a person labels (rubric.md, "How to label the top 10")."""


def group_names(response: SearchResponse) -> list[str]:
    """One short, unique label per garment group, in group order.

    The category when it is unique (``tops``), otherwise the category with the garment's position
    (``tops-1``, ``tops-2``). The labelling sheet and the report use these names, so they must be
    unique within one response.
    """
    counts = Counter(group.category for group in response.groups)
    return [
        group.category.value
        if counts[group.category] == 1
        else f"{group.category.value}-{group.item_index + 1}"
        for group in response.groups
    ]


def displayed_results(group: GarmentGroup) -> list[ScoredProduct]:
    """Every result of a group in the order the shopper sees them: price range by price range."""
    return [scored for tier in group.tiers for scored in tier.results]


def top_results(group: GarmentGroup, n: int = TOP_N) -> list[ScoredProduct]:
    """The ``n`` best results by ``scores.total`` across all price ranges of the group.

    Ties keep the displayed order (cheapest price range first, best match first inside it), so
    the ranking is deterministic. Fewer than ``n`` results are returned as they are: the missing
    places count as "not good" later, they are not invented here.
    """
    return sorted(displayed_results(group), key=lambda scored: -scored.scores.total)[:n]


def distinct_stores(response: SearchResponse) -> list[str]:
    """Display names of the stores that have at least one result, sorted."""
    return sorted({scored.product.store for scored in response.products})
