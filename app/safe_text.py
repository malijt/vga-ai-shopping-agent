"""Helpers for showing text that came from a store or from the shopper.

Rule (CLAUDE.md, Non-Negotiables): such text is shown as plain text. It is never given to a
function that reads markdown or HTML, and never rendered with ``unsafe_allow_html``. The page
therefore shows it with ``st.text`` (Streamlit documents it as "without Markdown or HTML
parsing"). The helpers here tidy the text for that (control characters, bidirectional overrides,
runaway length) without changing what it says.

One exception is unavoidable: a link button's label always reads markdown, and the plan wants the
label "View product on {store}". ``label_fragment`` makes the store name safe for that one place by
keeping only letters, digits, spaces, hyphens and apostrophes. Nothing that could start markdown,
a link, an image or an emoji shortcode survives, so the label cannot be interpreted as anything but
plain words. The full name is still shown by ``st.text`` next to the button.
"""

import re

DEFAULT_MAX_CHARS = 140
LABEL_MAX_CHARS = 40
ELLIPSIS = "…"

# Control characters, and the Unicode bidirectional overrides and isolates that can make text
# read in a misleading order (U+202A-202E, U+2066-2069). Left-to-right and right-to-left marks and
# the zero-width joiners that Arabic and emoji text use legitimately are kept.
_UNSAFE_CHARS = re.compile("[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
# Everything except word characters (letters and digits in any script), whitespace, a hyphen and
# an apostrophe. The underscore is a "word" character to the regex but is markdown emphasis.
_NOT_LABEL_SAFE = re.compile(r"[^\w\s'\-]")


def clamp(text: str, max_chars: int) -> str:
    """Cut ``text`` to at most ``max_chars`` characters, ending with an ellipsis when it is cut."""
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - len(ELLIPSIS))].rstrip() + ELLIPSIS


def plain_text(text: str | None, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Tidy untrusted text for ``st.text``: drop control and bidi-override characters, collapse
    whitespace runs to single spaces, and cut very long text. It never adds or rewrites markup:
    ``<b>x</b>`` stays ``<b>x</b>`` because ``st.text`` shows it literally."""
    if not text:
        return ""
    cleaned = _UNSAFE_CHARS.sub("", text)
    return clamp(" ".join(cleaned.split()), max_chars)


def label_fragment(text: str | None, max_chars: int = LABEL_MAX_CHARS) -> str:
    """Reduce untrusted text to words that are safe inside a markdown-reading label."""
    if not text:
        return ""
    cleaned = _NOT_LABEL_SAFE.sub("", text.replace("_", " "))
    return clamp(" ".join(cleaned.split()), max_chars)
