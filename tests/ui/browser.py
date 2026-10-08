"""A browser tab for ``AppTest``: a widget keeps the value it holds while its id stays the same.

``AppTest`` has no browser. It reads every widget's value from the page's own session state and
sends that back on the next run, so a widget whose key the page deleted, or whose default the page
changed, simply shows the new default. A real browser does not. Streamlit gives a keyed widget an
id made from its key alone (for the text box, the select box and the number box, plus one or two
settings that never change here), so the id does not change when the page redraws the widget
with another default. The browser keeps the value it holds for that id, and ignores the new
default unless the page also sets the widget's value (then the element carries ``set_value``,
which Streamlit does for a value set through ``st.session_state`` and for a select box value that
no longer matches any of its options). That is how the chips of one search kept the colours of an
earlier one while the page's own state said something else.

``BrowserMemory`` puts that one behaviour back, so a test can see what a shopper sees:

- After every run it remembers what the browser holds for each widget that keeps a value. A widget
  new on the page starts from its default, a widget the page set takes the value the page sent,
  and any other widget keeps what it held (the new default is ignored). A widget that left the
  page is forgotten.
- Before every run it sends what the browser holds, not what the page's own state says, except for
  a widget the test has just changed with ``set_value``: that is the shopper typing.
- ``shown_text``, ``shown_number`` and ``shown_option`` read what the browser shows in a widget.
  ``widget.value`` reads the page's own state, which is not what the shopper sees.

Buttons are not touched: a click lasts for one run, in the browser too.
"""

from collections.abc import Iterator
from typing import Any

from streamlit.proto.WidgetStates_pb2 import WidgetState, WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import (
    ElementTree,
    InitialValue,
    NumberInput,
    Selectbox,
    TextInput,
    Widget,
)


def _keeps_a_value(node: Any) -> bool:
    """A widget whose value the browser holds from run to run (one with a ``set_value`` flag)."""
    return isinstance(node, Widget) and hasattr(node.proto, "set_value")


def _stateful_widgets(tree: ElementTree) -> Iterator[Widget]:
    for node in tree:
        if isinstance(node, Widget) and _keeps_a_value(node):
            yield node


def _as_sent_by_the_page(node: Widget) -> WidgetState:
    """The state the page's element carries for a widget whose value the page set."""
    state = WidgetState()
    state.id = node.id
    proto = node.proto
    if isinstance(node, TextInput):
        state.string_value = proto.value
    elif isinstance(node, NumberInput):
        if proto.HasField("value"):
            state.double_value = proto.value
    elif isinstance(node, Selectbox):
        if proto.raw_value:
            state.string_value = proto.raw_value
    else:
        return node._widget_state
    return state


class BrowserMemory:
    """Makes ``at`` hold widget values the way a browser does. Use ``browser_memory(at)``."""

    def __init__(self, at: AppTest) -> None:
        self._at = at
        self._held: dict[str, WidgetState] = {}
        self._original_run = at._run
        at._run = self._run  # type: ignore[method-assign]
        at._browser = self  # type: ignore[attr-defined]

    def holding(self, widget_id: str) -> WidgetState | None:
        return self._held.get(widget_id)

    def _to_send(self, widget_state: WidgetStates | None) -> WidgetStates | None:
        if widget_state is None:
            return None
        widgets = list(_stateful_widgets(self._at._tree))
        keeps_a_value = {node.id for node in widgets}
        touched = {
            node.id
            for node in widgets
            if not isinstance(getattr(node, "_value", InitialValue()), InitialValue)
        }
        sent = WidgetStates()
        for state in widget_state.widgets:
            if state.id in keeps_a_value and (state.id in touched or state.id not in self._held):
                self._held[state.id] = state  # the shopper just typed, or nothing is held yet
            sent.widgets.append(self._held[state.id] if state.id in keeps_a_value else state)
        return sent

    def _remember(self) -> None:
        now: dict[str, WidgetState] = {}
        for node in _stateful_widgets(self._at._tree):
            if node.id in self._held and not node.proto.set_value:
                now[node.id] = self._held[node.id]  # the browser ignores the new default
            elif node.proto.set_value:
                now[node.id] = _as_sent_by_the_page(node)
            else:
                now[node.id] = node._widget_state  # new on the page: its default
        self._held = now

    def _run(self, widget_state: WidgetStates | None = None, timeout: float | None = None) -> Any:
        result = self._original_run(self._to_send(widget_state), timeout=timeout)
        self._remember()
        return result


def browser_memory(at: AppTest) -> AppTest:
    """``at``, now holding widget values like a browser tab. Returns ``at`` for chaining."""
    BrowserMemory(at)
    return at


def _held(at: AppTest, node: Widget) -> WidgetState | None:
    browser: BrowserMemory | None = getattr(at, "_browser", None)
    return browser.holding(node.id) if browser is not None else None


def shown_text(at: AppTest, box: TextInput) -> str:
    """What a text box shows. Without a browser tab (``browser_memory``) it is the box's value."""
    held = _held(at, box)
    return held.string_value if held is not None else str(box.value or "")


def shown_number(at: AppTest, box: NumberInput) -> float | None:
    """What a number box shows: ``None`` when it is empty."""
    held = _held(at, box)
    if held is None:
        return None if box.value is None else float(box.value)
    return held.double_value if held.WhichOneof("value") == "double_value" else None


def shown_option(at: AppTest, box: Selectbox[Any]) -> str | None:
    """The label a select box shows (what the shopper reads), or ``None`` when nothing is chosen."""
    held = _held(at, box)
    if held is not None:
        return held.string_value if held.WhichOneof("value") == "string_value" else None
    index = box.index
    return None if index is None else box.options[index]
