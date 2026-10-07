"""Builders for the model's private answer (``UnderstandReading``), for the Understand tests.

Built with ``model_construct`` on purpose: it skips pydantic's checks, so a test can hand the
validator the kind of garbage a model that obeyed an attack would return (a category that is not
one of the five, a link in a keyword) and prove that ``validation.py`` still holds.
"""

from typing import Any

from vga.models import Category, GenderSource, InputType
from vga.understand.schema import ReadingBudget, ReadingItem, UnderstandReading, Verdict


def make_reading_item(**overrides: Any) -> ReadingItem:
    """A black oversized blazer, no gender known."""
    fields: dict[str, Any] = {
        "category": Category.OUTERWEAR,
        "colour": "black",
        "style": "oversized blazer",
        "material": None,
        "gender": None,
        "gender_source": GenderSource.NONE,
        "search_keywords": ["black oversized blazer", "oversized blazer"],
    }
    return ReadingItem.model_construct(**{**fields, **overrides})


def make_reading_budget(**overrides: Any) -> ReadingBudget:
    return ReadingBudget.model_construct(**{"max_price": 400.0, "currency": "AED", **overrides})


def make_reading(**overrides: Any) -> UnderstandReading:
    """A valid ``ok`` answer with one item. Pass ``items=[...]`` etc. to change it."""
    fields: dict[str, Any] = {
        "verdict": Verdict.OK,
        "input_type": InputType.TEXT,
        "language": "en",
        "items": [make_reading_item()],
        "budget": None,
        "edits": [],
    }
    return UnderstandReading.model_construct(**{**fields, **overrides})


def make_declined_reading(verdict: Verdict = Verdict.NOT_A_REQUEST) -> UnderstandReading:
    """The answer of a model that found nothing to shop for."""
    return make_reading(verdict=verdict, items=[], budget=None, edits=[])
