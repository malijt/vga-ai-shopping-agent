"""The two-photo scenario of the stale-chips bug, shared by the tests that replay it.

A shopper searches with a photo of black abayas (two garments, a budget of 400 AED, nobody said
who it is for), then with a photo of red, blue, black and white kaftans (four garments, no
budget). The fake model tells the photos apart by their bytes. Run over the real pipeline with
``install_live`` and the ``live`` fixture, every store request, OpenAI call and image-model call
is counted (``costs``).
"""

from streamlit.testing.v1 import AppTest

from app.copy import CATEGORY_LABELS, GENDER_LABELS, GENDER_NOT_SET, GENDER_QUESTION
from tests.factories import make_image_bytes, make_item_intent, make_understand_result
from tests.ui.helpers import SEARCH_BUTTON, markdown_bodies, photo_key
from tests.ui.live import LiveSearch
from vga.models import (
    Category,
    Gender,
    InputType,
    ItemIntent,
    SearchRequest,
    SearchResponse,
    UnderstandResult,
)

# The keys of the buttons the page draws.
WOMEN, MEN, BOTH = "gender_women", "gender_men", "gender_both"
APPLY, RESET = "chips_apply", "chips_reset"

# What a chip box shows, in words.
DRESSES = CATEGORY_LABELS[Category.DRESSES]
NOT_SET = GENDER_NOT_SET
WOMEN_LABEL = GENDER_LABELS[Gender.WOMEN]
MEN_LABEL = GENDER_LABELS[Gender.MEN]

ABAYA_PHOTO = make_image_bytes("JPEG", (64, 64), (5, 5, 5))
KAFTAN_PHOTO = make_image_bytes("JPEG", (64, 64), (200, 30, 30))


def dress(colour: str, style: str, **overrides: object) -> ItemIntent:
    return make_item_intent(
        category=Category.DRESSES,
        colour=colour,
        style=style,
        search_keywords=[f"{colour} {style}"],
        **overrides,
    )


BLACK_ABAYAS = make_understand_result(
    input_type=InputType.OUTFIT_PHOTO,
    items=[dress("black", "abaya"), dress("black", "abaya")],
    budget={"max_price": 400, "currency": "AED"},
)
KAFTANS = make_understand_result(
    input_type=InputType.OUTFIT_PHOTO,
    items=[dress(colour, "kaftan") for colour in ("red", "blue", "black", "white")],
)


def what_the_model_sees(req: SearchRequest) -> UnderstandResult:
    """The fake model: the photo decides what it finds (a typed request finds the kaftans)."""
    return BLACK_ABAYAS if req.image == ABAYA_PHOTO else KAFTANS


def search_with_photo(at: AppTest, photo: bytes) -> AppTest:
    """Choose ``photo`` and press "Search stores"."""
    at.file_uploader(key=photo_key(at)).set_value(("look.jpg", photo, "image/jpeg")).run()
    at.button(key=SEARCH_BUTTON).click().run()
    assert not at.exception
    return at


def answer(at: AppTest, key: str) -> AppTest:
    """Press one of the buttons of "Who is this for?" (``WOMEN``, ``MEN`` or ``BOTH``)."""
    at.button(key=key).click().run()
    assert not at.exception
    return at


def response_of(at: AppTest) -> SearchResponse:
    response = at.session_state["response"]
    assert isinstance(response, SearchResponse)
    return response


def asks_who_it_is_for(at: AppTest) -> bool:
    return GENDER_QUESTION in " ".join(markdown_bodies(at))


def costs(live: LiveSearch) -> tuple[int, int, int, int]:
    """Store requests, store searches, OpenAI calls and image-model calls so far."""
    return (
        live.store_requests,
        len(live.store_searches),
        live.openai_calls,
        len(live.image_model_calls),
    )
