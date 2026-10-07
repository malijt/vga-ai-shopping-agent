"""The "Who is this for?" question, answered the way a shopper would (BRD Rule 8, plan A3).

A gender the model only guessed is shown, not applied, until the shopper confirms it. The page asks
the shopper after the first search whenever some garment's gender was not stated in the request,
and the answer is a second search: the earlier understanding is reused, the answer is written onto
every garment whose gender was not stated, and the stores are asked again for those garments. No
photo is sent and no model is called.

A headless run has nobody to ask, so a women's outfit photo would also return men's shoes. Each
query may therefore record the shopper's answer (``shopper_gender`` in the query file), and this
module gives it exactly as the page does:

- the question is asked only when at least one garment's gender is not explicit;
- the answer goes to every garment whose gender is not explicit, and to no other;
- a gender the request stated stands, even if it differs from the recorded answer (the difference
  is reported);
- the harness never applies a guess on its own: a query with no recorded answer is not re-searched.

Everything here is plain data in, plain data out. The runner makes the second search.
"""

from dataclasses import dataclass

from pydantic import Field

from vga.models import (
    Category,
    ChipEdits,
    Gender,
    GenderSource,
    ItemEdit,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    StepTiming,
    UnderstandResult,
    VgaModel,
)


class GarmentGender(VgaModel):
    """One garment and a gender: the model's guess (for a garment that was asked about) or the
    gender the request stated (for one that was not)."""

    index: int = Field(ge=0)
    category: Category
    gender: Gender | None


class GenderAnswer(VgaModel):
    """What happened to the question for one query that has a recorded answer."""

    answer: Gender
    """The shopper's recorded answer."""
    asked: bool
    """True when the question was asked (and so a second search ran). False when the request
    already stated the gender of every garment: the answer was not needed and is ignored."""
    garments: list[GarmentGender] = Field(default_factory=list)
    """The garments the answer was given for, with the model's guess (``None``: no guess)."""
    typed_differently: list[GarmentGender] = Field(default_factory=list)
    """Garments whose request stated a gender other than the answer. The stated one stands."""
    first_timings: list[StepTiming] = Field(default_factory=list)
    """The step timings of the first search, kept because the response that is scored belongs to
    the second search. Empty when the question was not asked."""
    wall_ms: float | None = Field(default=None, ge=0)
    """The second search, measured around ``Pipeline.run``. ``None`` when it did not run."""
    duration_ms: float | None = Field(default=None, ge=0)
    """The second search's time as reported beside the first: the slower of the pipeline's own
    figure and the wall time, or the recorded live figure on a replay."""


@dataclass(frozen=True)
class Question:
    """What the page would do after a first search, given the shopper's recorded answer."""

    answer: Gender
    edits: ChipEdits | None
    """The chip edits that answer the question; ``None`` when the page would not ask."""
    asked_about: tuple[GarmentGender, ...]
    typed_differently: tuple[GarmentGender, ...]


def read_question(understood: UnderstandResult, answer: Gender) -> Question:
    """Whether the page would ask, and what the answer changes, for this understanding."""
    asked: list[GarmentGender] = []
    differently: list[GarmentGender] = []
    edits: list[ItemEdit] = []
    for index, item in enumerate(understood.items):
        garment = GarmentGender(index=index, category=item.category, gender=item.gender)
        if item.gender_source is GenderSource.EXPLICIT:
            if item.gender is not answer:
                differently.append(garment)
            continue
        asked.append(garment)
        edits.append(ItemEdit(index=index, gender=answer))
    return Question(
        answer=answer,
        edits=ChipEdits(items=edits) if edits else None,
        asked_about=tuple(asked),
        typed_differently=tuple(differently),
    )


def rerun_request(first: SearchResponse) -> SearchRequest:
    """The request the page sends after the question: no text, no photo, only the earlier id."""
    return SearchRequest(rerun_of=first.request_id)


def rerun_overrides(first: SearchResponse, edits: ChipEdits) -> RunOverrides:
    """Reuse the first search's understanding and image embedding, and apply the answer."""
    return RunOverrides(
        understood=first.understood,
        query_embedding=first.query_embedding,
        chips=edits,
    )


def describe_asked(garments: list[GarmentGender]) -> str:
    """``tops (guessed men), shoes (no guess)`` for a note or a table cell."""
    return ", ".join(
        f"{garment.category.value} (guessed {garment.gender.value})"
        if garment.gender is not None
        else f"{garment.category.value} (no guess)"
        for garment in garments
    )


def describe_stated(garments: list[GarmentGender]) -> str:
    """``tops (stated men)`` for a garment whose request already said who it is for."""
    return ", ".join(
        f"{garment.category.value} (stated {garment.gender.value if garment.gender else '?'})"
        for garment in garments
    )
