"""Turn the model's answer into the public contract, or say exactly what is wrong with it (5.2.3).

The model's answer is untrusted output: it was produced from a stranger's text and photo. Native
structured outputs make it well-formed JSON, but "well-formed" is not "safe": a model that obeyed
an injected instruction would still return valid JSON. So every field is checked again here, in
code, against the same rules the contract uses, and free text is cleaned (no URLs, no control
characters, no price words, bounded length).

Two outcomes besides success:

- ``NothingToShopFor``: the model said there is nothing to search for. Not an error.
- ``OutputValidationError``: the answer breaks a rule. ``problems`` names each field and the rule,
  never the offending value, because the list is sent back to the model for one corrective retry
  and must not be a way to echo attacker text.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from pydantic import ValidationError

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
from vga.understand.keywords import dedupe_keywords, with_stated_gender
from vga.understand.lexicon import mentioned_genders
from vga.understand.schema import UnderstandReading, Verdict
from vga.understand.text import KEYWORD_MAX_CHARS, clean_keyword, clean_phrase

MAX_COLOUR_CHARS = 60
MAX_STYLE_CHARS = 120
MAX_MATERIAL_CHARS = 60
MAX_EDIT_CHARS = 60
MAX_EDITS = 10
"""Same limits as ``ItemIntent`` and ``UnderstandResult``."""

_LANGUAGES = ("en", "ar", "mixed", "other")
_CATEGORY_NAMES = ", ".join(category.value for category in Category)


class NothingToShopFor(Exception):
    """The model found nothing to search for. ``verdict`` says why."""

    def __init__(self, verdict: Verdict) -> None:
        super().__init__(verdict.value)
        self.verdict = verdict


class OutputValidationError(Exception):
    """The model's answer broke a rule. ``problems`` are value-free, one line per field."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class ValidatedReading:
    """The parts of ``UnderstandResult`` that come from the model, checked."""

    input_type: InputType
    items: list[ItemIntent]
    budget: Budget | None
    edits: list[str]
    language: Language


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
    budget = _validate_budget(reading.budget, text, problems)
    edits = _validate_edits(reading.edits, problems)
    language = _validate_language(reading.language, text, problems)
    input_type = _reconcile_input_type(reading.input_type, text, has_image, len(items))

    if problems:
        raise OutputValidationError(problems)
    return ValidatedReading(input_type, items, budget, edits, language)


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
    if not cleaned:
        problems.append(
            f"{field}: needs at least one keyword that names the garment, without prices, "
            "links or gender words"
        )
    return [keyword[:KEYWORD_MAX_CHARS] for keyword in cleaned]


# --------------------------------------------------------------------------------------------
# Budget, edits, language, input type
# --------------------------------------------------------------------------------------------


def _validate_budget(raw: Any, text: str | None, problems: list[str]) -> Budget | None:
    if raw is None or text is None:
        return None  # a photo cannot state a budget; a price printed in it is data, not a limit
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
        return Budget.model_validate(fields)
    except ValidationError:
        problems.append("budget: max_price must be above 0 and currency a 3-letter code or null")
        return None


def _validate_edits(raw: Any, problems: list[str]) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        problems.append("edits: must be a list of strings")
        return []
    cleaned = dedupe_keywords(
        (clean_phrase(entry, MAX_EDIT_CHARS) for entry in raw), limit=MAX_EDITS
    )
    return cleaned


def _validate_language(raw: Any, text: str | None, problems: list[str]) -> Language:
    if text is None:
        return "en"
    if raw not in _LANGUAGES:
        problems.append("language: must be one of en, ar, mixed, other")
        return "en"
    return cast(Language, raw)


def _reconcile_input_type(
    claimed: Any, text: str | None, has_image: bool, item_count: int
) -> InputType:
    """What was sent is known to the code, so the model only decides product vs outfit."""
    if not has_image:
        return InputType.TEXT
    if text is not None:
        return InputType.PHOTO_TEXT
    outfit = _enum(InputType, claimed) is InputType.OUTFIT_PHOTO or item_count > 1
    return InputType.OUTFIT_PHOTO if outfit else InputType.PRODUCT_PHOTO


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
    return clean_phrase(value, max_chars) or None
