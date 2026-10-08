"""Turn the model's answer into the public contract, or say exactly what is wrong with it (5.2.3).

The model's answer is untrusted output: it was produced from a stranger's text and photo. Native
structured outputs make it well-formed JSON, but "well-formed" is not "safe": a model that obeyed
an injected instruction would still return valid JSON. So every field is checked again here, in
code, against the same rules the contract uses, and free text is cleaned (no URLs, markup or
control characters, bounded length; keywords also lose price and gender words).

Two outcomes besides success:

- ``NothingToShopFor``: the model said there is nothing to search for. Not an error.
- ``OutputValidationError``: the answer breaks a rule. ``problems`` names each field and the rule,
  never the offending value, because the list is sent back to the model for one corrective retry
  and must not be a way to echo attacker text.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

from pydantic import ValidationError

from vga.errors import LlmError
from vga.log import get_logger
from vga.models import (
    MAX_ITEMS,
    Budget,
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemIntent,
    Language,
)
from vga.understand.input_type import derive_input_type
from vga.understand.keywords import dedupe_keywords, with_stated_gender
from vga.understand.lexicon import (
    asks_for_a_higher_price,
    asks_for_a_lower_price,
    edit_words,
    is_typed,
    mentioned_genders,
    names_a_number_in_words,
    typed_word_forms,
)
from vga.understand.prompt import echoes_instructions
from vga.understand.schema import UnderstandReading, Verdict
from vga.understand.text import KEYWORD_MAX_CHARS, clean_keyword, clean_phrase, numbers_in

log = get_logger(__name__)

MAX_COLOUR_CHARS = 60
MAX_STYLE_CHARS = 120
MAX_MATERIAL_CHARS = 60
MAX_EDIT_CHARS = 60
MAX_EDITS = 10
"""Same limits as ``ItemIntent`` and ``UnderstandResult``."""

UNMATCHED_BUDGET_WARNING = (
    "We ignored a price limit that did not match the numbers in your request. "
    "Add it again if you want one."
)

_LANGUAGES = ("en", "ar", "mixed", "other")
_CATEGORY_NAMES = ", ".join(category.value for category in Category)


class NothingToShopFor(Exception):
    """The model found nothing to search for. ``verdict`` says why."""

    def __init__(self, verdict: Verdict) -> None:
        super().__init__(verdict.value)
        self.verdict = verdict


class OutputValidationError(LlmError):
    """The model's answer broke a rule (a schema failure is one too). ``problems`` are value-free,
    one line per field. A typed ``VgaError`` as the plan asks (5.1.2): the shopper only ever sees
    the plain ``LlmError`` message, and ``detail`` carries the problems for the log."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(detail="; ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class ValidatedReading:
    """The parts of ``UnderstandResult`` that come from the model, checked."""

    input_type: InputType
    items: list[ItemIntent]
    budget: Budget | None
    edits: list[str]
    language: Language
    warnings: list[str] = field(default_factory=list)
    """Plain notes for the shopper about something the validator set aside."""


def validate_reading(
    reading: UnderstandReading, *, text: str | None, has_image: bool
) -> ValidatedReading:
    """Check and clean ``reading`` for a request with the given ``text`` and photo.

    ``text`` is the shopper's cleaned text (``None`` for a photo-only request). Raises
    ``NothingToShopFor`` or ``OutputValidationError``.
    """
    verdict = _verdict(reading.verdict)
    if verdict is None:
        raise OutputValidationError(
            ["verdict: must be one of ok, no_garment, out_of_scope, not_a_request"]
        )
    if verdict is not Verdict.OK:
        raise NothingToShopFor(verdict)

    problems: list[str] = []
    raw_items = list(reading.items)
    if not raw_items:
        problems.append("items: must hold at least one item when verdict is ok")
    if len(raw_items) > MAX_ITEMS:
        problems.append(f"items: at most {MAX_ITEMS} items are allowed")

    items = [
        item
        for index, raw in enumerate(raw_items[:MAX_ITEMS])
        if (item := _validate_item(index, raw, text, problems)) is not None
    ]
    warnings: list[str] = []
    budget = _validate_budget(reading.budget, text, problems, warnings)
    edits = _validate_edits(reading.edits, text, problems)
    language = _validate_language(reading.language, text, problems)

    if problems:
        raise OutputValidationError(problems)
    input_type = _derive_input_type(reading.input_type, text, has_image, len(items))
    return ValidatedReading(input_type, items, budget, edits, language, warnings)


# --------------------------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------------------------


def _validate_item(
    index: int, raw: Any, text: str | None, problems: list[str]
) -> ItemIntent | None:
    where = f"items[{index}]"
    before = len(problems)

    category = _enum(Category, raw.category)
    if category is None:
        problems.append(f"{where}.category: must be one of {_CATEGORY_NAMES}")
    colour = _phrase(raw.colour, MAX_COLOUR_CHARS, f"{where}.colour", problems)
    style = _phrase(raw.style, MAX_STYLE_CHARS, f"{where}.style", problems)
    material = _phrase(raw.material, MAX_MATERIAL_CHARS, f"{where}.material", problems)
    gender, source = _gender(raw, text, where, problems)
    keywords = _keywords(raw.search_keywords, where, problems)

    if len(problems) > before or category is None:
        return None
    return ItemIntent(
        category=category,
        colour=colour,
        style=style,
        material=material,
        gender=gender,
        gender_source=source,
        search_keywords=with_stated_gender(keywords, gender, source),
    )


def _gender(
    raw: Any, text: str | None, where: str, problems: list[str]
) -> tuple[Gender | None, GenderSource]:
    """Read gender and its source, and refuse to let "explicit" stand unless the shopper's own
    words say so (BRD Rule 8): a guess from the photo must stay a guess."""
    gender = None if raw.gender is None else _enum(Gender, raw.gender)
    source = _enum(GenderSource, raw.gender_source)
    if raw.gender is not None and gender is None:
        problems.append(f"{where}.gender: must be men, women, unisex or null")
    if source is None:
        problems.append(f"{where}.gender_source: must be explicit, inferred or none")
        return None, GenderSource.NONE
    if gender is None:
        return None, GenderSource.NONE
    if source is GenderSource.NONE:
        return gender, GenderSource.INFERRED  # a gender with no source is a guess
    if source is GenderSource.EXPLICIT and (text is None or gender not in mentioned_genders(text)):
        return gender, GenderSource.INFERRED
    return gender, source


def _keywords(value: Any, where: str, problems: list[str]) -> list[str]:
    field = f"{where}.search_keywords"
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        problems.append(f"{field}: must be a list of strings")
        return []
    cleaned = dedupe_keywords(clean_keyword(entry, allow_gender=False) for entry in value)
    if any(echoes_instructions(keyword) for keyword in cleaned):
        problems.append(f"{field}: must describe the garment, not repeat the instructions")
        return []
    if not cleaned:
        problems.append(
            f"{field}: needs at least one keyword that names the garment, without prices, "
            "links or gender words"
        )
    return [keyword[:KEYWORD_MAX_CHARS] for keyword in cleaned]


# --------------------------------------------------------------------------------------------
# Budget, edits, language, input type
# --------------------------------------------------------------------------------------------


def _validate_budget(
    raw: Any, text: str | None, problems: list[str], warnings: list[str]
) -> Budget | None:
    """The budget, only when the shopper's own typed words state one.

    A price printed in the photo is data, not a limit, so a budget needs a number in the typed text:
    a digit (Western or Arabic-Indic) or a number word such as "four hundred" or "مئتين". With no
    typed text, or none of those in it, whatever the model reported is dropped unseen: nothing the
    shopper wrote is being ignored, so there is nothing to explain and nothing to ask the model to
    redo. When the text holds digits and no number word, one of the digits must be the model's
    amount. With a number word in it the amount cannot be checked (the words are not added up), and
    a digit beside it ("size 38 under four hundred") is no reason to drop the budget.
    """
    if raw is None or text is None:
        return None  # a photo cannot state a budget; a price printed in it is data, not a limit
    written = numbers_in(text)
    in_words = names_a_number_in_words(text)
    if not written and not in_words:
        return None  # the shopper typed no number, so a price from elsewhere is not their limit
    currency = raw.currency.strip().upper() if isinstance(raw.currency, str) else None
    max_price = raw.max_price
    if (
        isinstance(max_price, bool)
        or not isinstance(max_price, int | float)
        or not math.isfinite(max_price)
    ):
        problems.append("budget.max_price: must be a positive number")
        return None
    try:
        fields: dict[str, Any] = {"max_price": float(max_price)}
        if currency:
            fields["currency"] = currency
        budget = Budget.model_validate(fields)
    except ValidationError:
        problems.append("budget: max_price must be above 0 and currency a 3-letter code or null")
        return None
    if not in_words and not any(abs(number - budget.max_price) < 0.005 for number in written):
        # The model reported a price the shopper never wrote (for example one read from a sign in
        # the photo). A wrong limit hides good results; no limit hides nothing.
        warnings.append(UNMATCHED_BUDGET_WARNING)
        return None
    return budget


def _validate_edits(raw: Any, text: str | None, problems: list[str]) -> list[str]:
    """The edits the shopper's own typed words ask for.

    An edit changes the search ("cheaper" switches the price mix), so like a budget it needs the
    shopper behind it: a sign in the photo that says "cheaper" must not be able to ask. With no
    typed text there are no edits; otherwise each edit is kept only when ``_is_asked_for``.
    """
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        problems.append("edits: must be a list of strings")
        return []
    if text is None:
        return []  # only the shopper's words can ask for a change; a sign in a photo cannot
    cleaned = dedupe_keywords(
        (clean_phrase(entry, MAX_EDIT_CHARS) for entry in raw), limit=MAX_EDITS
    )
    if any(echoes_instructions(edit) for edit in cleaned):
        problems.append("edits: must name the changes asked for, not repeat the instructions")
        return []
    typed = typed_word_forms(text)
    return [edit for edit in cleaned if _is_asked_for(edit, text, typed)]


def _is_asked_for(edit: str, text: str, typed: frozenset[str]) -> bool:
    """Whether the typed ``text`` asks for ``edit``. Conservative: every part of the edit must be
    backed by the text, and an edit that cannot be checked is not kept.

    - a number in the edit ("under 250 AED") must be a number the shopper typed;
    - "cheaper" and its kin need a word asking for a lower price, and "pricier" and its kin a
      word asking for a higher one (a price limit is a budget, not this wish);
    - a gender needs that gender named in the text, in either language;
    - every other word (a colour, a fabric, a cut) must be a word the shopper typed, or, for an
      English colour or fabric, its Arabic spelling.
    """
    numbers = numbers_in(edit)
    if not set(numbers) <= set(numbers_in(text)):
        return False
    lower, higher = asks_for_a_lower_price(edit), asks_for_a_higher_price(edit)
    if (lower and not asks_for_a_lower_price(text)) or (
        higher and not asks_for_a_higher_price(text)
    ):
        return False
    genders = mentioned_genders(edit)
    if not genders <= mentioned_genders(text):
        return False
    words = edit_words(edit)
    if not all(is_typed(word, typed) for word in words):
        return False
    return bool(numbers or lower or higher or genders or words)  # an empty change is no change


def _validate_language(raw: Any, text: str | None, problems: list[str]) -> Language:
    if text is None:
        return "en"
    if raw not in _LANGUAGES:
        problems.append("language: must be one of en, ar, mixed, other")
        return "en"
    return cast(Language, raw)


def _derive_input_type(
    claimed: Any, text: str | None, has_image: bool, item_count: int
) -> InputType:
    """The kind of request, from what was sent and how many garments were found, never from the
    model's ``claimed`` label (``derive_input_type`` holds the rule and the reason).

    A label that disagrees is not an error: the answer is not rejected and the model is not asked
    again. It is noted at debug level (the request id is stamped by the logger) so a flipping model
    can be seen in the logs. Only a known label is logged by value; anything else is the model's
    free output and is not copied into the log.
    """
    derived = derive_input_type(
        has_image=has_image, has_text=text is not None, item_count=item_count
    )
    label = _enum(InputType, claimed)
    if label is not derived:
        log.debug(
            "model input type overridden",
            extra={
                "model_input_type": label.value if label is not None else "unrecognised",
                "input_type": derived.value,
                "item_count": item_count,
                "has_image": has_image,
                "has_text": text is not None,
            },
        )
    return derived


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def _verdict(value: Any) -> Verdict | None:
    return _enum(Verdict, value)


def _enum[E: StrEnum](kind: type[E], value: Any) -> E | None:
    try:
        return kind(value)
    except ValueError:
        return None


def _phrase(value: Any, max_chars: int, field: str, problems: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        problems.append(f"{field}: must be text or null")
        return None
    phrase = clean_phrase(value, max_chars)
    if echoes_instructions(phrase):
        problems.append(f"{field}: must describe the garment, not repeat the instructions")
        return None
    return phrase or None
