"""The question "Who is this for?", above the results (BRD Rule 8, plan assumption A3).

A gender the AI only guessed is shown and never applied until the shopper says so. The chip and its
note were easy to miss, and a women's outfit photo then also brought men's shoes. So when a search
has finished and some garment's gender was guessed or not found, the page asks, with three buttons:

- Women or Men: the same search again with that gender on every garment that is not explicit. It
  goes through the chip re-search (``state.request_search`` with ``ChipEdits``): no photo is sent
  and OpenAI is not called, and a store that does not sell for that gender is left out, as for any
  confirmed gender. The question then has nothing left to ask and goes away.
- Show both: closes the question. Nothing is applied and nothing is searched again; the results
  stay as they are (``state.dismiss_gender_question``).

"Women" and "Men" are the main actions of the question and are filled with the theme's accent
colour (`type="primary"`); "Show both" is the quiet way out and stays plain.

The answer goes with whatever the chips already hold. A colour typed in a chip and not yet applied
is not lost by answering, and the answer wins over a different gender chosen in the chip.

The question is asked once per search: a garment whose gender the shopper stated is never asked
about, "Show both" is remembered until a new search, and a page with no results does not ask.
"""

import streamlit as st

from app import state
from app.components.chips import chip_edits_from_state
from app.copy import (
    BUTTON_SHOW_BOTH,
    GENDER_GUESS_DIFFERS,
    GENDER_LABELS,
    GENDER_NOT_STATED,
    GENDER_QUESTION,
    gender_guess_note,
)
from vga.models import ChipEdits, Gender, GenderSource, ItemEdit, SearchResponse, UnderstandResult

WOMEN_KEY = "gender_women"
MEN_KEY = "gender_men"
BOTH_KEY = "gender_both"
CONTAINER_KEY = "gender_question"


def undecided_items(understood: UnderstandResult) -> list[int]:
    """The garments whose gender the shopper has not stated: guessed by the AI, or not found."""
    return [
        index
        for index, item in enumerate(understood.items)
        if item.gender_source is not GenderSource.EXPLICIT
    ]


def should_ask(response: SearchResponse) -> bool:
    """Ask when there are results to refine, some garment's gender is not explicit, and the
    shopper has not already closed the question for this search."""
    return (
        response.result_count > 0
        and bool(undecided_items(response.understood))
        and not state.gender_question_dismissed()
    )


def edits_with_gender(
    understood: UnderstandResult, pending: ChipEdits, gender: Gender
) -> ChipEdits:
    """``pending`` (the chips' own edits) with ``gender`` set on every garment not yet explicit.

    A garment the shopper stated keeps its gender. Edits to other fields, the budget and a removed
    budget are carried over unchanged; a gender already chosen in a chip for an undecided garment
    is replaced by the answer.
    """
    undecided = set(undecided_items(understood))
    by_index = {edit.index: edit for edit in pending.items}
    for index in undecided:
        by_index[index] = by_index.get(index, ItemEdit(index=index)).model_copy(
            update={"gender": gender}
        )
    return ChipEdits(
        items=[by_index[index] for index in sorted(by_index)],
        budget=pending.budget,
        clear_budget=pending.clear_budget,
    )


def guess_note(understood: UnderstandResult) -> str:
    """Say in words what the AI guessed, or that the request did not say."""
    items = [understood.items[index] for index in undecided_items(understood)]
    guesses = {item.gender for item in items if item.gender is not None}
    if not guesses:
        return GENDER_NOT_STATED
    if len(guesses) > 1:
        return GENDER_GUESS_DIFFERS
    (guess,) = guesses
    return gender_guess_note(guess, understood.input_type)


def _answer(gender: Gender) -> None:
    """``on_click`` of Women and Men: search again with that gender."""
    response = state.get_response()
    if response is not None:
        pending = chip_edits_from_state(response.understood)
        state.request_search(edits_with_gender(response.understood, pending, gender))


def render_gender_question(response: SearchResponse, *, disabled: bool) -> None:
    """Draw the question above the results, when it is to be asked. ``disabled`` is true while a
    search runs."""
    if not should_ask(response):
        return
    with st.container(border=True, key=CONTAINER_KEY):
        st.markdown(f"**{GENDER_QUESTION}**")
        st.text(guess_note(response.understood))
        with st.container(horizontal=True):
            for gender, key in ((Gender.WOMEN, WOMEN_KEY), (Gender.MEN, MEN_KEY)):
                st.button(
                    GENDER_LABELS[gender],
                    key=key,
                    type="primary",
                    on_click=_answer,
                    args=(gender,),
                    disabled=disabled,
                )
            st.button(
                BUTTON_SHOW_BOTH,
                key=BOTH_KEY,
                on_click=state.dismiss_gender_question,
                disabled=disabled,
            )
