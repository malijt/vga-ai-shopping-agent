"""Search keywords: the one place that decides which words go to a store (plan 5.3.3, 5.3.4).

Rules, each a project rule rather than a taste:
- No price words (BRD Rule 7) and no URLs: ``text.clean_keyword`` removes them.
- No gender word unless the shopper stated the gender (BRD Rule 8). A gender the model only
  inferred is shown as a chip but kept out of the keywords until the shopper confirms it.
- A stated gender is added to the first, most specific variant only. The other variants stay
  without it, so a store whose titles never say "men" still returns something.
"""

import re
from collections.abc import Iterable

from vga.models import MAX_KEYWORDS, Gender, GenderSource, ItemIntent
from vga.understand.lexicon import CATEGORY_NOUN, GENDER_KEYWORD
from vga.understand.text import KEYWORD_MAX_CHARS, clean_keyword

_WORDS = re.compile(r"\S+")


def dedupe_keywords(candidates: Iterable[str], *, limit: int = MAX_KEYWORDS) -> list[str]:
    """Keep the first ``limit`` distinct (case-insensitive) non-empty keywords, in order."""
    seen: set[str] = set()
    kept: list[str] = []
    for candidate in candidates:
        key = candidate.casefold()
        if candidate and key not in seen:
            seen.add(key)
            kept.append(candidate)
        if len(kept) == limit:
            break
    return kept


def applied_gender_word(gender: Gender | None, source: GenderSource) -> str | None:
    """The word a stated gender adds to a keyword, or ``None`` (inferred, unknown or unisex)."""
    if gender is None or source is not GenderSource.EXPLICIT:
        return None
    return GENDER_KEYWORD.get(gender)


def with_stated_gender(
    keywords: list[str], gender: Gender | None, source: GenderSource
) -> list[str]:
    """Add the stated gender to the first keyword. Other keywords are returned unchanged."""
    word = applied_gender_word(gender, source)
    if word is None or not keywords:
        return keywords
    first = f"{keywords[0]} {word}"
    if len(first) > KEYWORD_MAX_CHARS:
        return keywords
    return [first, *keywords[1:]]


def rebuild_keywords(item: ItemIntent) -> list[str]:
    """Search keywords made from the item's fields alone: no model, no network.

    Used after a chip edit (plan 5.3.3): changing the colour from black to brown must change the
    words sent to the stores, without another OpenAI call. Up to three variants, most specific
    first: colour + material + style, colour + style, style. ``style`` is the garment phrase the
    model gave ("oversized blazer"); when there is none, a plain noun for the category is used.
    """
    noun = item.style or CATEGORY_NOUN[item.category]
    drafts: list[list[str | None]] = [
        [item.colour, item.material, noun],
        [item.colour, noun],
        [noun],
    ]
    variants = dedupe_keywords(_one_phrase(parts) for parts in drafts)
    return with_stated_gender(variants, item.gender, item.gender_source) or [
        CATEGORY_NOUN[item.category]
    ]


def _one_phrase(parts: list[str | None]) -> str:
    """Join the parts, drop a repeated word ("black" in both colour and style), clean the result."""
    seen: set[str] = set()
    words: list[str] = []
    for part in parts:
        for word in _WORDS.findall(part or ""):
            if word.casefold() not in seen:
                seen.add(word.casefold())
                words.append(word)
    return clean_keyword(" ".join(words), allow_gender=False)
