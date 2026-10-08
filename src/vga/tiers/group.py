"""One ``GarmentGroup`` per detected garment (plan 9.3.2).

The pipeline calls ``build_group`` once per garment with that garment's scored products. The same
rules as ``shape`` apply to each garment on its own: its own borders (a shoe search and a blazer
search get different price ranges), its own store cap (``max_per_store`` counts products inside
that garment's list), and its own total.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from vga.models import (
    Budget,
    Category,
    GarmentGroup,
    InputType,
    ScoredProduct,
    StoreConfig,
)
from vga.settings import Settings
from vga.tiers.shaper import shape


@dataclass(frozen=True, slots=True)
class GroupResult:
    """A built group and the warnings the caller should add to ``SearchResponse.warnings``."""

    group: GarmentGroup
    warnings: list[str] = field(default_factory=list)


def results_total(settings: Settings, input_type: InputType) -> int:
    """How many results one garment's list holds: ``outfit_results_per_garment`` for an outfit
    photo (plan assumption A2), ``results`` for every other kind of request."""
    if input_type is InputType.OUTFIT_PHOTO:
        return settings.outfit_results_per_garment
    return settings.results


def build_group(
    products: Sequence[ScoredProduct],
    settings: Settings,
    budget: Budget | None,
    stores: Sequence[StoreConfig],
    *,
    item_index: int,
    category: Category,
    total: int,
) -> GroupResult:
    """Shape one garment's scored products into a ``GarmentGroup`` of four price ranges.

    ``item_index`` is the garment's index in ``SearchResponse.understood.items``. ``total`` is the
    number of results wanted for this garment (see ``results_total``). Everything else is as in
    ``shape``. An empty ``products`` gives a group of four empty ranges, never an error.
    """
    shaped = shape(products, settings, budget, stores, total=total)
    group = GarmentGroup(item_index=item_index, category=category, tiers=shaped.tiers)
    return GroupResult(group=group, warnings=shaped.warnings)
