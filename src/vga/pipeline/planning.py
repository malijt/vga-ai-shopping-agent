"""The decisions made before any store is asked: which items, which stores, which budget, which mix.

All of it is pure (no clock, no I/O), so each rule is tested on its own.
"""

import re
from collections.abc import Sequence

from vga.models import (
    Budget,
    ItemIntent,
    MixPreset,
    RunOverrides,
    StoreConfig,
    UnderstandResult,
)
from vga.settings import Settings
from vga.understand import effective_gender

MAX_OUTFIT_KEYWORDS = 2
"""An outfit searches several garments, one search each, so each gets at most this many keyword
variants (plan 13.1.3). That keeps the number of store requests inside the politeness budget."""

_CHEAPER = re.compile(r"\b(?:cheaper|less expensive|more affordable)\b", re.IGNORECASE)


def items_to_search(understood: UnderstandResult) -> list[ItemIntent]:
    """The items to search for, in order. With more than one garment each keeps at most
    ``MAX_OUTFIT_KEYWORDS`` keyword variants."""
    items = list(understood.items)
    if len(items) <= 1:
        return items
    return [
        item.model_copy(update={"search_keywords": item.search_keywords[:MAX_OUTFIT_KEYWORDS]})
        for item in items
    ]


def stores_for_item(
    active: Sequence[StoreConfig], item: ItemIntent
) -> tuple[list[StoreConfig], list[StoreConfig]]:
    """Split the active stores into those to search for ``item`` and those left out.

    A store is left out when it does not sell the item's category (a dresses-only boutique is not
    asked for shoes) or does not sell for its gender. Only a stated or confirmed gender counts
    (BRD Rule 8): a guessed one excludes nothing.
    """
    gender = effective_gender(item)

    def sells(store: StoreConfig) -> bool:
        return store.sells_category(item.category) and store.sells_for_gender(gender)

    searched = [store for store in active if sells(store)]
    skipped = [store for store in active if not sells(store)]
    return searched, skipped


def resolve_budget(understood: UnderstandResult, overrides: RunOverrides | None) -> Budget | None:
    """The budget this run ranks with: the chips, then the sidebar, then what was understood.

    ``understood`` already holds the chip edits (the pipeline applies them first), including a
    budget the shopper typed in the chips or removed; a removed budget stays removed even if the
    sidebar still holds one.
    """
    if overrides is not None:
        chips = overrides.chips
        if chips is not None:
            if chips.budget is not None:
                return chips.budget
            if chips.clear_budget:
                return None
        sidebar = overrides.settings
        if sidebar is not None and sidebar.budget is not None:
            return sidebar.budget
    return understood.budget


def wants_cheaper(understood: UnderstandResult) -> bool:
    """Whether the text asked for something cheaper ("similar but dark brown and cheaper")."""
    return any(_CHEAPER.search(edit) for edit in understood.edits)


def settings_for_run(
    settings: Settings,
    overrides: RunOverrides | None,
    understood: UnderstandResult,
    budget: Budget | None,
) -> tuple[Settings, bool]:
    """The settings to rank and shape with, and whether the value-first mix was chosen for the
    shopper (plan assumption A7).

    The sidebar's mix wins when the shopper picked one. "Cheaper" with no budget has no price to
    aim at, so, unless the shopper picked a mix, it switches this request to the value-first mix.
    A sidebar mix equal to the configured default counts as not picked: the sidebar always sends
    its current choice, and it starts on the default.
    """
    sidebar = overrides.settings if overrides is not None else None
    run_settings = settings.with_overrides(sidebar)
    picked = sidebar is not None and sidebar.tier_mix not in (None, settings.tier_mix)
    if budget is None and wants_cheaper(understood) and not picked:
        value_first = MixPreset.VALUE_FIRST.mix
        if run_settings.tier_mix != value_first:
            return run_settings.model_copy(update={"tier_mix": value_first}), True
    return run_settings, False
