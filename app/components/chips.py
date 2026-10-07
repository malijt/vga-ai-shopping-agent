"""Chips: what the AI detected, shown so the shopper can fix it (plan 10.2.1, PRD R3).

Per detected item the shopper can change the category, the colour and the gender; the budget is
one value for the whole request (``ChipEdits`` has one budget). Two rules matter here:

- A gender the AI only guessed is shown as "not confirmed" and stays unset until the shopper
  chooses one (BRD Rule 8, assumption A3). Choosing it is the confirmation.
- "Apply changes and search again" sends only what changed (``ChipEdits``); everything left alone
  keeps the detected value. "Reset to detected" puts every chip back to what the current results
  were built from.

The widgets hold their own values under keys that start with ``chip_``. ``state.store_response``
clears those keys when a new response arrives, so the chips always start from the newest detection.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import streamlit as st

from app import state
from app.copy import (
    BUTTON_APPLY_CHIPS,
    BUTTON_RESET_CHIPS,
    CATEGORY_LABELS,
    GENDER_LABELS,
    GENDER_NOT_SET,
)
from vga.models import (
    DEFAULT_CURRENCY,
    Budget,
    Category,
    ChipEdits,
    Gender,
    GenderSource,
    ItemEdit,
    ItemIntent,
    UnderstandResult,
)

APPLY_KEY = "chips_apply"
RESET_KEY = "chips_reset"
BUDGET_KEY = "chip_budget"
MAX_COLOUR_CHARS = 60  # same limit as ItemIntent.colour
BUDGET_MAX = 1_000_000.0
GENDER_UNSET = "unset"
"""The gender box's value for "Not set". A plain string, not ``None``, because a select box uses
``None`` for "nothing chosen"."""


def category_key(index: int) -> str:
    return f"chip_{index}_category"


def colour_key(index: int) -> str:
    return f"chip_{index}_colour"


def gender_key(index: int) -> str:
    return f"chip_{index}_gender"


@dataclass(frozen=True)
class ItemValues:
    """What the chips of one item hold right now. ``gender`` is ``None`` for "Not set"."""

    category: Category
    colour: str
    gender: Gender | None


def applied_gender(item: ItemIntent) -> Gender | None:
    """The gender the search uses for this item: only one that was stated or confirmed."""
    return item.gender if item.gender_source is GenderSource.EXPLICIT else None


def detected_values(item: ItemIntent) -> ItemValues:
    return ItemValues(category=item.category, colour=item.colour or "", gender=applied_gender(item))


def build_chip_edits(
    understood: UnderstandResult, items: Sequence[ItemValues], budget: float | None
) -> ChipEdits:
    """Compare the chips with the detection and return only the differences.

    Nothing changed gives an empty ``ChipEdits``. An emptied colour box is sent as ``""`` (which
    clears the colour), and an emptied budget box as ``clear_budget``. A gender the AI only guessed
    counts as unset, so choosing it, even the same one, is sent as the shopper's confirmation.
    """
    item_edits: list[ItemEdit] = []
    for index, (detected, now) in enumerate(zip(understood.items, items, strict=True)):
        changes: dict[str, object] = {}
        if now.category != detected.category:
            changes["category"] = now.category
        colour = now.colour.strip()
        if colour != (detected.colour or ""):
            changes["colour"] = colour
        if now.gender is not None and now.gender != applied_gender(detected):
            changes["gender"] = now.gender
        if changes:
            item_edits.append(ItemEdit.model_validate({"index": index, **changes}))

    detected_budget = understood.budget
    detected_price = detected_budget.max_price if detected_budget else None
    if budget == detected_price:
        return ChipEdits(items=item_edits)
    if budget is None:
        return ChipEdits(items=item_edits, clear_budget=True)
    currency = detected_budget.currency if detected_budget else DEFAULT_CURRENCY
    return ChipEdits(items=item_edits, budget=Budget(max_price=budget, currency=currency))


def _gender_from_option(option: str) -> Gender | None:
    return None if option == GENDER_UNSET else Gender(option)


def _gender_option_label(option: str) -> str:
    return GENDER_NOT_SET if option == GENDER_UNSET else GENDER_LABELS[Gender(option)]


def chip_edits_from_state(understood: UnderstandResult) -> ChipEdits:
    """``ChipEdits`` for the values currently in the chip widgets."""
    values: list[ItemValues] = []
    for index, item in enumerate(understood.items):
        detected = detected_values(item)
        gender_option = st.session_state.get(
            gender_key(index), detected.gender.value if detected.gender else GENDER_UNSET
        )
        values.append(
            ItemValues(
                category=st.session_state.get(category_key(index), detected.category),
                colour=st.session_state.get(colour_key(index), detected.colour) or "",
                gender=_gender_from_option(gender_option),
            )
        )
    detected_price = understood.budget.max_price if understood.budget else None
    return build_chip_edits(understood, values, st.session_state.get(BUDGET_KEY, detected_price))


def _apply_changes() -> None:
    """``on_click`` of "Apply changes and search again"."""
    response = state.get_response()
    if response is not None:
        state.request_search(chip_edits_from_state(response.understood))


def _label(noun: str, index: int, *, multiple: bool) -> str:
    """ "Category" for one item, "Item 2 category" when there are several (labels stay unique)."""
    return f"Item {index + 1} {noun}" if multiple else noun.capitalize()


def _render_item(index: int, item: ItemIntent, *, multiple: bool, disabled: bool) -> None:
    detected = detected_values(item)
    categories = list(Category)
    if detected.gender is None:
        gender_options = [GENDER_UNSET, *(gender.value for gender in Gender)]
        detected_gender_option = GENDER_UNSET
    else:
        # A stated gender can be changed but not unset (a chip edit cannot clear it).
        gender_options = [gender.value for gender in Gender]
        detected_gender_option = detected.gender.value

    with st.container(border=True, key=f"chips_item_{index}"):
        if multiple:
            st.markdown(f"**Item {index + 1}**")
        category_column, colour_column, gender_column = st.columns(3)
        with category_column:
            st.selectbox(
                _label("category", index, multiple=multiple),
                options=categories,
                index=categories.index(detected.category),
                format_func=lambda option: CATEGORY_LABELS[option],
                key=category_key(index),
                disabled=disabled,
            )
        with colour_column:
            st.text_input(
                _label("colour", index, multiple=multiple),
                value=detected.colour,
                max_chars=MAX_COLOUR_CHARS,
                placeholder="Not detected",
                key=colour_key(index),
                disabled=disabled,
            )
        with gender_column:
            chosen = st.selectbox(
                _label("gender", index, multiple=multiple),
                options=gender_options,
                index=gender_options.index(detected_gender_option),
                format_func=_gender_option_label,
                key=gender_key(index),
                disabled=disabled,
            )
        _render_gender_status(item, _gender_from_option(chosen))


def _render_gender_status(item: ItemIntent, chosen: Gender | None) -> None:
    """Say in words whether the gender is being used (never by colour alone)."""
    if item.gender_source is GenderSource.EXPLICIT:
        st.markdown("Gender: taken from your request.")
    elif item.gender is not None and chosen is None:
        guess = GENDER_LABELS[item.gender]
        st.markdown(
            f"Gender: not confirmed. The AI guessed {guess}. "
            "It is not used in the search until you choose a gender."
        )
    elif chosen is not None:
        st.markdown("Gender: confirmed by you.")


def _render_budget(budget: Budget | None, *, disabled: bool) -> None:
    currency = budget.currency if budget else DEFAULT_CURRENCY
    # The detected budget is put in the box through its state, and the widget's own default stays
    # empty. Streamlit answers a cleared number box with the widget's default, so a box created
    # with a default of 400 could never say "no budget".
    if BUDGET_KEY not in st.session_state:
        st.session_state[BUDGET_KEY] = budget.max_price if budget else None
    st.number_input(
        f"Budget in {currency} (optional)",
        min_value=1.0,
        max_value=BUDGET_MAX,
        value=None,
        step=10.0,
        format="%g",
        placeholder="No budget",
        key=BUDGET_KEY,
        disabled=disabled,
    )


def render_chips(understood: UnderstandResult, *, disabled: bool, can_search: bool) -> None:
    """Draw the chips for the current detection.

    ``disabled`` is true while a search runs. ``can_search`` is false when the input panel has
    nothing to search with (a new request needs the photo or text again, assumption A8).
    """
    st.header("Detected by AI", anchor=False)
    st.markdown("Check what the AI understood. Change anything that is wrong, then search again.")
    multiple = len(understood.items) > 1
    for index, item in enumerate(understood.items):
        _render_item(index, item, multiple=multiple, disabled=disabled)
    _render_budget(understood.budget, disabled=disabled)

    with st.container(horizontal=True):
        st.button(
            BUTTON_APPLY_CHIPS,
            key=APPLY_KEY,
            on_click=_apply_changes,
            disabled=disabled or not can_search,
        )
        st.button(
            BUTTON_RESET_CHIPS,
            key=RESET_KEY,
            on_click=state.clear_chip_state,
            disabled=disabled,
        )
    if not can_search:
        st.markdown("To search again, keep your photo or description in the boxes above.")
