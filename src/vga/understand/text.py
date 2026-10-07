# ruff: noqa: RUF001  (the typographic apostrophe is meant: shoppers type it)
"""Cleaning of text that came from outside: the shopper's words and the model's answer.

Everything here is a pure function. The same helpers clean the shopper's text before it is shown to
the model, every free-text field of the model's answer after (plan 5.2.3), and the raw words the
fallback searches with (plan 5.3.1), so one definition of "safe text" applies everywhere.
"""

import re
import unicodedata

from vga.understand.lexicon import (
    meaningful_tokens,
    strip_gender_words,
    strip_price_words,
    trim_connectors,
)

KEYWORD_MAX_CHARS = 80
"""Same cap as ``ItemIntent.search_keywords`` items."""

_URL = re.compile(
    r"(?:\b(?:https?|ftp|file|data|javascript):\S*"
    r"|\bwww\.\S+"
    r"|\b[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,4}\.(?:com|net|org|io|ae|sa|co|me|shop|store|info|xyz|app|dev"
    r"|example|ru|cn|tk|link|site|online|ly|to)\b(?:/\S*)?)",
    re.IGNORECASE,
)

_MARKUP_TAG = re.compile(r"</?[a-z][^<>]{0,100}>", re.IGNORECASE)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_NUMBER_IN_TEXT = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)(\s?k\b)?", re.IGNORECASE
)

_USER_TEXT_TAG = re.compile(r"<\s*/?\s*user_text\b[^>]*>?", re.IGNORECASE)
_SPACES = re.compile(r"\s+")


def strip_control_characters(text: str, *, keep_newlines: bool = False) -> str:
    """Remove control and invisible formatting characters (zero-width, bidi overrides, ...).

    Controls become spaces so words do not fuse; format characters are dropped. Hidden characters
    are a known way to smuggle instructions past a human reader.
    """
    out: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch == "\n" and keep_newlines:
            out.append(ch)
        elif category in {"Cc", "Zl", "Zp"}:
            out.append(" ")
        elif category == "Cf":
            continue
        else:
            out.append(ch)
    return "".join(out)


def remove_urls(text: str) -> str:
    """Remove links and bare domains, so no answer can carry a place to send the shopper."""
    return _URL.sub(" ", text)


def collapse_spaces(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def has_letters_or_digits(text: str) -> bool:
    """False for "!!! ### ;;;": nothing a shopper could mean."""
    return any(ch.isalnum() for ch in text)


def neutralise_user_text(text: str) -> str:
    """Prepare the shopper's text for the prompt: no control characters and no way to close the
    ``<user_text>`` block it will sit in. Newlines stay (they are part of how people type)."""
    text = strip_control_characters(text, keep_newlines=True)
    text = _USER_TEXT_TAG.sub(" ", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_phrase(text: str, max_chars: int) -> str:
    """A short, plain phrase from untrusted text: letters, digits, spaces, hyphens, apostrophes.

    No URLs, no control characters, no markup or punctuation that could mean something to a store
    search or a renderer; at most ``max_chars`` long, cut at a word boundary.
    """
    text = _MARKUP_TAG.sub(" ", remove_urls(strip_control_characters(text)))
    kept = [ch if (unicodedata.category(ch)[0] in "LNM" or ch in " -'’") else " " for ch in text]
    phrase = collapse_spaces("".join(kept)).strip("-'’ ")
    if len(phrase) > max_chars:
        cut = phrase[:max_chars]
        phrase = (cut.rsplit(" ", 1)[0] if " " in cut else cut).strip("-'’ ")
    return phrase


def clean_keyword(text: str, *, allow_gender: bool) -> str:
    """One search keyword: cleaned, with price words removed (BRD Rule 7), with gender words
    removed unless the shopper stated a gender (Rule 8), or ``""`` when nothing meaningful is left.

    Price words go first, on the raw text, because their patterns need symbols such as ``$``.
    """
    text = strip_price_words(remove_urls(strip_control_characters(text)))
    if not allow_gender:
        text = strip_gender_words(text)
    phrase = trim_connectors(clean_phrase(text, KEYWORD_MAX_CHARS))
    return phrase if meaningful_tokens(phrase) else ""


def numbers_in(text: str) -> list[float]:
    """The numbers written in ``text``: Arabic-Indic digits are read, ``1,200`` is 1200, ``3k`` is
    3000. Used to check that a budget the model reports is a number the shopper really wrote."""
    found: list[float] = []
    for raw, thousands in _NUMBER_IN_TEXT.findall(text.translate(_DIGITS)):
        grouped = re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw)
        value = float(raw.replace(",", "") if grouped else raw.replace(",", "."))
        found.append(value * 1000 if thousands else value)
    return found
