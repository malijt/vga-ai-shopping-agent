"""Small helpers for reading the page the way a shopper (or a screen reader) would.

A node's text is what the shopper can read: element text, widget labels and button labels.
"""

import re
from collections.abc import Iterator
from typing import Any

from streamlit.testing.v1 import AppTest

from tests.ui.browser import shown_number, shown_option, shown_text

SEARCH_BUTTON = "search_button"
TEXT_BOX = "query_text"
PHOTO = "photo_upload"

EXAMPLE_TEXT = "black oversized blazer for men under 400 AED"

# Element types that Streamlit reads as markdown. ``text`` is not one of them.
_MARKDOWN_TYPES = {
    "markdown",
    "caption",
    "title",
    "header",
    "subheader",
    "info",
    "error",
    "warning",
    "success",
}


def nodes(at: AppTest) -> Iterator[Any]:
    """Every element on the page, main area first, then the sidebar."""
    yield from at.main
    yield from at.sidebar


def link_buttons(at: AppTest) -> list[Any]:
    """The "View product" link buttons (AppTest has no typed accessor for them)."""
    return [node for node in nodes(at) if getattr(node, "type", None) == "link_button"]


def markdown_bodies(at: AppTest) -> list[str]:
    """The text of everything that Streamlit reads as markdown: markdown, captions, headings,
    alerts, plus button and widget labels, expander labels and link-button labels."""
    bodies: list[str] = []
    for node in nodes(at):
        kind = getattr(node, "type", "")
        if kind in _MARKDOWN_TYPES:
            bodies.append(str(node.value))
        elif kind == "link_button":
            bodies.append(str(node.proto.label))
        elif hasattr(node, "label") and isinstance(node.label, str):
            bodies.append(node.label)
    return bodies


def plain_texts(at: AppTest) -> list[str]:
    """The text of every ``st.text`` element: the only place untrusted strings may appear."""
    return [str(node.value) for node in nodes(at) if getattr(node, "type", "") == "text"]


def visible_strings(at: AppTest) -> list[str]:
    return markdown_bodies(at) + plain_texts(at)


def search(at: AppTest, text: str = EXAMPLE_TEXT) -> AppTest:
    """Type a description and press "Search stores"."""
    at.text_input(key=TEXT_BOX).set_value(text).run()
    at.button(key=SEARCH_BUTTON).click().run()
    return at


def photo_key(at: AppTest) -> str:
    """The photo uploader's current widget key: it changes each time a finished search lets go of
    the photo (``app.state.photo_key``)."""
    generation = at.session_state.get("photo_generation", 0)
    return PHOTO if generation == 0 else f"{PHOTO}_{generation}"


# --- The chips ----------------------------------------------------------------------------------
# The chip widgets are found by what they are (item and field), not by the exact key, so the tests
# say what the shopper sees and do not depend on how the page names the widgets.


def _chip(widgets: Any, suffix: str) -> Any:
    matches = [w for w in widgets if re.fullmatch(rf"chip_(g\d+_)?{suffix}", w.key or "")]
    assert len(matches) == 1, f"expected one chip '{suffix}', found {[w.key for w in matches]}"
    return matches[0]


def chip_category(at: AppTest, index: int = 0) -> Any:
    return _chip(at.selectbox, f"{index}_category")


def chip_colour(at: AppTest, index: int = 0) -> Any:
    return _chip(at.text_input, f"{index}_colour")


def chip_gender(at: AppTest, index: int = 0) -> Any:
    return _chip(at.selectbox, f"{index}_gender")


def chip_budget(at: AppTest) -> Any:
    return _chip(at.number_input, "budget")


def chip_count(at: AppTest) -> int:
    return len([w for w in at.selectbox if re.fullmatch(r"chip_(g\d+_)?\d+_category", w.key or "")])


def chips_shown(at: AppTest) -> list[tuple[str | None, str, str | None]]:
    """What each item's chips show now, in words: (category, colour, gender) per item, in order,
    for example ``("Dresses and ethnic wear", "red", "Not set")``. With a browser tab
    (``tests/ui/browser.py``) it is what the browser holds, which is what the shopper reads."""
    return [
        (
            shown_option(at, chip_category(at, i)),
            shown_text(at, chip_colour(at, i)),
            shown_option(at, chip_gender(at, i)),
        )
        for i in range(chip_count(at))
    ]


def budget_shown(at: AppTest) -> float | None:
    """What the budget chip shows: the number, or ``None`` when the box is empty."""
    return shown_number(at, chip_budget(at))


def gender_notes(at: AppTest) -> list[str | None]:
    """The line under each item's chips that says where its gender stands, in item order
    (``None`` for an item whose box says nothing: no gender was found, not even a guess)."""
    boxes = {getattr(node, "key", None): node for node in at.get("container")}
    notes: list[str | None] = []
    for index in range(chip_count(at)):
        lines = [
            m.value for m in boxes[f"chips_item_{index}"].markdown if m.value.startswith("Gender:")
        ]
        notes.append(lines[0] if lines else None)
    return notes


def holds_bytes(value: object, needle: bytes, _seen: set[int] | None = None) -> bool:
    """Whether ``needle`` (a photo) is anywhere inside ``value``: as bytes, inside an uploaded
    file, or in any attribute, item or field, however deep. Pydantic fields that are excluded from
    dumps are looked at too, because they are still in memory."""
    seen = _seen if _seen is not None else set()
    if id(value) in seen or isinstance(value, str | int | float | bool | type(None)):
        return False
    seen.add(id(value))
    if isinstance(value, bytes | bytearray | memoryview):
        return needle in bytes(value)
    getvalue = getattr(value, "getvalue", None)
    if callable(getvalue):
        try:
            return holds_bytes(getvalue(), needle, seen)
        except (OSError, ValueError):
            return False
    if isinstance(value, dict):
        return any(holds_bytes(item, needle, seen) for item in [*value.keys(), *value.values()])
    if isinstance(value, list | tuple | set | frozenset):
        return any(holds_bytes(item, needle, seen) for item in value)
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return any(holds_bytes(item, needle, seen) for item in attributes.values())
    return False


def session_holds_bytes(at: AppTest, needle: bytes) -> bool:
    """Whether anything the page remembers between runs holds the photo."""
    return any(holds_bytes(at.session_state[key], needle) for key in at.session_state)
