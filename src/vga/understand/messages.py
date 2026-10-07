"""Plain-language messages for the shopper when there is nothing to search for (plan A16).

Every message says what to do next and names the four categories the demo covers, so a shopper who
asked for a handbag learns the limit instead of getting a wrong result or a silent failure.
"""

from vga.errors import InvalidInputError, LlmError
from vga.understand.schema import Verdict

COVERED = "tops, outerwear, bottoms and shoes"

_MESSAGES: dict[Verdict, str] = {
    Verdict.NO_GARMENT: (
        "We couldn't find any clothing or shoes to search for. "
        f"Please try a clear photo of an item from {COVERED}, "
        "or describe what you want, for example 'black leather jacket for men'."
    ),
    Verdict.OUT_OF_SCOPE: (
        f"We can only search for {COVERED} for now. "
        "Please describe an item from one of those groups, "
        "for example 'white sneakers' or 'wide-leg jeans'."
    ),
    Verdict.NOT_A_REQUEST: (
        "We couldn't tell what you'd like to find. "
        f"Please describe an item from {COVERED}, "
        "for example 'navy chinos for men', or upload a clear photo of it."
    ),
}

PHOTO_ONLY_FAILURE_MESSAGE = (
    "We couldn't read your photo right now. "
    "Please try again in a moment, or describe the item in words instead."
)
"""A photo-only request when the model is unavailable: there is nothing to fall back on."""


def nothing_to_shop_for(verdict: Verdict) -> InvalidInputError:
    """The invalid-input error a shopper sees when the request holds nothing to search for."""
    return InvalidInputError(_MESSAGES[verdict], detail=f"nothing to shop for: {verdict.value}")


def photo_only_failure(reason: str) -> LlmError:
    """The error for a photo-only request the model path could not handle."""
    return LlmError(PHOTO_ONLY_FAILURE_MESSAGE, detail=reason)
