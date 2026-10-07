"""The requests the audit runs: what a shopper might do, including what goes wrong.

Each ``Scenario`` is one whole request, from the photo the shopper uploads to the answer (or the
error) the pipeline gives back. ``Switches`` are the two debug settings that write more to disk
(``VGA_LOG_PROMPTS`` and ``VGA_DEBUG_DUMP``). A ``Case`` is a scenario under one setting of both.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pytest

from tests.guards.privacy.photos import PrivatePhoto, disguised_as_a_jpeg, truncated
from tests.guards.privacy.rig import Leak, blazer_reading, outfit_reading
from tests.understand.fake_openai import Step, answer, cut_off, http_error, refusal
from vga.errors import InvalidInputError, LlmError, VgaError
from vga.models import InputType
from vga.pipeline.errors import RequestTimeoutError

SHOPPER_WORDS = "zebra-wedding-7731"
"""Words the shopper types. Unlike the photo they are meant to reach OpenAI; the audit uses them to
show what ``VGA_LOG_PROMPTS`` writes."""
SHOPPER_TEXT = f"the same blazer but darker, for the {SHOPPER_WORDS}"
NOT_A_PHOTO_TEXT = "PRIVATE notes in a text file that was renamed to .jpg"


@dataclass(frozen=True)
class Switches:
    """The two debug settings. Both are off unless someone turns them on."""

    log_prompts: bool
    debug_dump: bool

    def __str__(self) -> str:
        prompts = "on" if self.log_prompts else "off"
        dump = "on" if self.debug_dump else "off"
        return f"prompts {prompts}, dump {dump}"


OFF = Switches(log_prompts=False, debug_dump=False)
PROMPTS = Switches(log_prompts=True, debug_dump=False)
DUMP = Switches(log_prompts=False, debug_dump=True)
BOTH = Switches(log_prompts=True, debug_dump=True)
EVERY_COMBINATION = (OFF, PROMPTS, DUMP, BOTH)


def _upload(photo: PrivatePhoto) -> bytes:
    return photo.data


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: Callable[[], list[Step]]
    """OpenAI's scripted answers, in order. Built fresh for each run."""
    text: str | None = None
    photo_format: str = "JPEG"
    upload: Callable[[PrivatePhoto], bytes] = _upload
    """The bytes the shopper uploads: the photo as it is, unless the scenario breaks it."""
    expect: type[VgaError] | None = None
    """The error the request must end with. ``None`` means it must produce an answer."""
    rerun: bool = False
    """After the first answer, the shopper changes the price mix (a chip edit): no photo is sent."""
    store_status: Mapping[str, int] = field(default_factory=dict)
    slow_model: bool = False
    slow_thumbnails: bool = False
    broken_weights: bool = False
    leak: Leak | None = None
    """A deliberate privacy bug, for the canary tests only (``test_canaries.py``)."""

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Case:
    scenario: Scenario
    switches: Switches

    def __str__(self) -> str:
        return f"{self.scenario} / {self.switches}"


# --------------------------------------------------------------------------------------------
# A request that works
# --------------------------------------------------------------------------------------------

PRODUCT_PHOTO = Scenario("one garment", lambda: [answer(blazer_reading())])
PHOTO_AND_TEXT = Scenario(
    "photo and text",
    lambda: [answer(blazer_reading(InputType.PHOTO_TEXT))],
    text=SHOPPER_TEXT,
)
OUTFIT = Scenario("outfit", lambda: [answer(outfit_reading())])
PNG_PHOTO = Scenario("PNG photo", lambda: [answer(blazer_reading())], photo_format="PNG")
WEBP_PHOTO = Scenario("WebP photo", lambda: [answer(blazer_reading())], photo_format="WEBP")

# --------------------------------------------------------------------------------------------
# A request that works, with something going wrong on the way
# --------------------------------------------------------------------------------------------

RETRIED = Scenario(
    "model answer cut off, asked again",
    lambda: [cut_off(), answer(blazer_reading(InputType.PHOTO_TEXT))],
    text=SHOPPER_TEXT,
)
ONE_STORE_BLOCKS = Scenario(
    "one store blocks us",
    lambda: [answer(blazer_reading())],
    store_status={"beta": 403},
)
CHIP_EDIT = Scenario("chip edit after a photo", lambda: [answer(blazer_reading())], rerun=True)
MODEL_DOWN_WITH_TEXT = Scenario(
    "model down, falls back to the typed words",
    lambda: [http_error(500), http_error(500)],
    text=SHOPPER_TEXT,
)
BROKEN_WEIGHTS = Scenario(
    "image model crashes", lambda: [answer(blazer_reading())], broken_weights=True
)
THUMBNAILS_TOO_SLOW = Scenario(
    "deadline passes while comparing",
    lambda: [answer(blazer_reading())],
    slow_thumbnails=True,
)

# --------------------------------------------------------------------------------------------
# A request that fails
# --------------------------------------------------------------------------------------------

NOT_AN_IMAGE = Scenario(
    "a text file as a photo",
    lambda: [],
    upload=lambda photo: NOT_A_PHOTO_TEXT.encode() + photo.marker,
    expect=InvalidInputError,
)
DISGUISED = Scenario(
    "junk with a JPEG header",
    lambda: [],
    upload=disguised_as_a_jpeg,
    expect=InvalidInputError,
)
TRUNCATED = Scenario(
    "a photo cut in half",
    lambda: [],
    upload=truncated,
    expect=InvalidInputError,
)
MODEL_DOWN = Scenario(
    "model down, photo only",
    lambda: [http_error(500), http_error(500)],
    expect=LlmError,
)
WRONG_KEY = Scenario("OpenAI refuses the key", lambda: [http_error(401)], expect=LlmError)
MODEL_REFUSES = Scenario("model refuses", lambda: [refusal()], expect=LlmError)
MODEL_TOO_SLOW = Scenario(
    "deadline passes while waiting for the model",
    lambda: [answer(blazer_reading())],
    slow_model=True,
    expect=RequestTimeoutError,
)

WORKING = (PRODUCT_PHOTO, PHOTO_AND_TEXT, OUTFIT, PNG_PHOTO, WEBP_PHOTO)
WORKING_WITH_TROUBLE = (
    RETRIED,
    ONE_STORE_BLOCKS,
    CHIP_EDIT,
    MODEL_DOWN_WITH_TEXT,
    BROKEN_WEIGHTS,
    THUMBNAILS_TOO_SLOW,
)
FAILING = (NOT_AN_IMAGE, DISGUISED, TRUNCATED, MODEL_DOWN, WRONG_KEY, MODEL_REFUSES, MODEL_TOO_SLOW)
EVERY_SCENARIO = (*WORKING, *WORKING_WITH_TROUBLE, *FAILING)

CORE = (PRODUCT_PHOTO, PHOTO_AND_TEXT, OUTFIT)
"""The three kinds of request the PRD names. They run under every combination of the switches."""


def cases(scenarios: tuple[Scenario, ...], switches: tuple[Switches, ...]) -> list:
    """``pytest.param`` for each scenario under each setting of the switches."""
    return [
        pytest.param(Case(scenario, setting), id=str(Case(scenario, setting)))
        for scenario in scenarios
        for setting in switches
    ]


def every_case() -> list:
    """The core requests under all four settings, every other scenario with both switches on (the
    setting that writes the most, so the one most likely to show a leak)."""
    return cases(CORE, EVERY_COMBINATION) + cases(
        tuple(s for s in EVERY_SCENARIO if s not in CORE), (BOTH,)
    )


def every_scenario_once() -> list:
    """Every scenario once, with both switches on."""
    return cases(EVERY_SCENARIO, (BOTH,))
