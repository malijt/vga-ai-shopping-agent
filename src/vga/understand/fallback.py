"""The fallback intent when the model path fails (plan 5.3.1).

A text request becomes one item whose keywords are the shopper's own words, cleaned: no URLs, no
control characters, no price words. It is a degraded answer and says so in ``warnings``, and its
``model`` and ``prompt_version`` are the marker ``FALLBACK_MARKER`` so no log or test can mistake it
for the model's reading.

There is no model to say which of the five categories the words mean, and ``ItemIntent`` needs one.
The fallback reads it from a short garment word list (``lexicon.garment_category``). When the text
names no garment from the five categories there is nothing to search for, and the shopper is told
what to type instead; a guessed category would send them to wrong results.
"""

import re

from vga.models import ItemIntent, UnderstandResult, Usage
from vga.understand.input_type import derive_input_type
from vga.understand.lexicon import garment_category
from vga.understand.messages import nothing_to_shop_for
from vga.understand.schema import Verdict
from vga.understand.text import clean_keyword, neutralise_user_text, remove_urls

FALLBACK_MARKER = "fallback"
"""Value of ``UnderstandResult.model`` and ``.prompt_version`` for a fallback result."""

FALLBACK_WARNING = (
    "We could not fully analyse your request, so we searched with your words as typed. "
    "A price limit you gave was not applied."
)
FALLBACK_WARNING_WITH_PHOTO = (
    "We could not fully analyse your request, so we searched with your words as typed. "
    "Your photo and any price limit you gave were not used."
)

_SENTENCES = re.compile(r"[\n.!?;:؟؛]+")
"""Sentence breaks, including the Arabic question mark and semicolon."""


def fallback_result(text: str, *, has_image: bool, usage: Usage) -> UnderstandResult:
    """The degraded ``UnderstandResult`` for ``text``.

    Raises the invalid-input ``VgaError`` when the text names no garment from the five categories.
    """
    item = _item_from_words(text)
    if item is None:
        raise nothing_to_shop_for(Verdict.NOT_A_REQUEST)
    return UnderstandResult(
        input_type=derive_input_type(has_image=has_image, has_text=True, item_count=1),
        items=[item],
        prompt_version=FALLBACK_MARKER,
        model=FALLBACK_MARKER,
        usage=usage,
        warnings=[FALLBACK_WARNING_WITH_PHOTO if has_image else FALLBACK_WARNING],
    )


def _item_from_words(text: str) -> ItemIntent | None:
    """The first sentence that names a garment, as one keyword. The rest of the text is not
    searched, which keeps a sentence of injected instructions out of the store query."""
    # Links go first: splitting at the dots and colons of a URL would leave fragments of it behind.
    for sentence in _SENTENCES.split(neutralise_user_text(remove_urls(text))):
        keyword = clean_keyword(sentence, allow_gender=True)
        category = garment_category(keyword) if keyword else None
        if category is not None:
            return ItemIntent(category=category, search_keywords=[keyword])
    return None
