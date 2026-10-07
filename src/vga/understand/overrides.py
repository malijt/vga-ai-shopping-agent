"""Chip edits applied to an understanding, with no model call (plan 5.3.3, 5.3.4).

The shopper sees the understanding as editable chips (PRD R3). When they change one and search
again, the pipeline calls ``apply_overrides`` and re-runs the search: no second OpenAI call, no
photo needed. Both functions are pure; they return new objects and never touch the input.
"""

from typing import Any

from vga.errors import InvalidInputError
from vga.models import (
    ChipEdits,
    Gender,
    GenderSource,
    ItemEdit,
    ItemIntent,
    UnderstandResult,
)
from vga.understand.keywords import rebuild_keywords
from vga.understand.text import clean_phrase

MAX_COLOUR_CHARS = 60


def effective_gender(item: ItemIntent) -> Gender | None:
    """The gender the search may use: only one the shopper stated or confirmed (BRD Rule 8).

    An ``inferred`` gender is shown as an unconfirmed chip and is not applied, to filtering or to
    keywords, until the shopper confirms it; this is the single place that says so. Downstream
    code that filters or ranks by gender should call this rather than read ``item.gender``.
    """
    return item.gender if item.gender_source is GenderSource.EXPLICIT else None


def apply_overrides(result: UnderstandResult, edits: ChipEdits) -> UnderstandResult:
    """``result`` with the shopper's chip edits applied.

    An edited item gets fresh keywords from ``rebuild_keywords``; an item with no real change keeps
    the model's keywords. A gender chosen in the chips counts as confirmed and becomes explicit.
    Changing an item's category drops its style phrase, because "bomber jacket" no longer describes
    a top. Raises ``InvalidInputError`` for an edit that points at an item that does not exist.
    """
    items = list(result.items)
    for edit in edits.items:
        if edit.index >= len(items):
            raise InvalidInputError(
                detail=f"chip edit for item {edit.index} but only {len(items)} items were found"
            )
        items[edit.index] = _edit_item(items[edit.index], edit)

    budget = result.budget
    if edits.clear_budget:
        budget = None
    elif edits.budget is not None:
        budget = edits.budget
    return result.model_copy(update={"items": items, "budget": budget})


def _edit_item(item: ItemIntent, edit: ItemEdit) -> ItemIntent:
    changes: dict[str, Any] = {}
    if edit.category is not None and edit.category != item.category:
        changes["category"] = edit.category
        changes["style"] = None
    if edit.colour is not None:
        changes["colour"] = clean_phrase(edit.colour, MAX_COLOUR_CHARS) or None
    if edit.gender is not None:
        changes["gender"] = edit.gender
        changes["gender_source"] = GenderSource.EXPLICIT

    edited = item.model_copy(update=changes)
    if edited == item:
        return item
    return ItemIntent.model_validate(
        {**edited.model_dump(), "search_keywords": rebuild_keywords(edited)}
    )
