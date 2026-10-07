"""What the model returns: a small private schema, kept apart from the public contract (plan 5.1.2).

``UnderstandResult`` (``vga.models``) is what the rest of the app reads. It has fields the model
must not write (``prompt_version``, ``model``, ``usage``, ``warnings``) and it cannot say "there is
nothing to shop for" because it needs at least one item. This schema is narrower on one side and
wider on the other: it is exactly what the model is asked for, plus a ``verdict`` so it can decline.
``vga.understand.validation`` turns it into the contract and rejects anything that does not fit.

Every field is required (an optional value is ``null``), which is what OpenAI's strict structured
outputs ask for. There are no length or pattern limits in the schema on purpose: the limits live in
``validation.py``, where a breach produces a named, value-free error for the corrective retry.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from vga.models import Category, Gender, GenderSource, InputType, Language


class Verdict(StrEnum):
    """Can this request be searched? Anything but ``ok`` means no search happens (plan A16)."""

    OK = "ok"
    NO_GARMENT = "no_garment"
    OUT_OF_SCOPE = "out_of_scope"
    NOT_A_REQUEST = "not_a_request"


class ReadingItem(BaseModel):
    """One garment the shopper wants."""

    model_config = ConfigDict(extra="forbid")

    category: Category = Field(description="Exactly one of the five categories.")
    colour: str | None = Field(description="Plain English colour such as 'dark brown', or null.")
    style: str = Field(
        description="The garment type with its cut or key feature, in English: 'oversized blazer'."
    )
    material: str | None = Field(description="Only if stated or clearly visible, else null.")
    gender: Gender | None = Field(description="men, women, unisex, or null when unknown.")
    gender_source: GenderSource = Field(
        description="explicit only if the shopper's text states the gender; inferred if guessed; "
        "none when gender is null."
    )
    search_keywords: list[str] = Field(
        description="2 or 3 English search phrases, most specific first. No gender or price words."
    )


class ReadingBudget(BaseModel):
    """A maximum price the shopper stated in words."""

    model_config = ConfigDict(extra="forbid")

    max_price: float = Field(description="The upper limit as a number.")
    currency: str | None = Field(description="Three-letter code if stated (AED, SAR), else null.")


class UnderstandReading(BaseModel):
    """The model's whole answer."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict = Field(
        description="ok if at least one garment in scope can be searched; otherwise the reason "
        "there is nothing to shop for. Then items is empty."
    )
    input_type: InputType = Field(description="What the shopper sent.")
    language: Language = Field(description="Language of the shopper's text: en, ar, mixed, other.")
    items: list[ReadingItem] = Field(description="One per distinct garment, at most 4.")
    budget: ReadingBudget | None = Field(description="Only a maximum price stated in the text.")
    edits: list[str] = Field(
        description="Changes the text asks for on top of a photo, such as 'dark brown', 'cheaper'."
    )
