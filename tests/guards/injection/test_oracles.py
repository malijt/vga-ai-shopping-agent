"""The checks the injection tests rely on, shown to FAIL on bad input.

A guard test that can never fail proves nothing. The product code cannot be broken here to see the
tests go red, so each shared check is fed data a broken pipeline would produce, and must reject it.
"""

import httpx
import pytest

from tests.factories import make_product, make_search_response, make_store_config, make_tier_result
from tests.guards.injection.support import (
    PRICE_WORDS,
    assert_friendly,
    assert_hosts_allowed,
    assert_links_on_the_stores_hosts,
    assert_plain_keyword_queries,
    injection_cases,
    is_plain_words,
)
from vga.errors import InvalidInputError
from vga.models import Category, GarmentGroup, SearchResponse, Tier

STORE = make_store_config()
SEARCH = "https://www.demo-store.example/search/suggest.json"
TEMPLATE = "resources%5Btype%5D=product&resources%5Blimit%5D=10"


def get(url: str) -> httpx.Request:
    return httpx.Request("GET", url)


def search_for(query: str, extra: str = "") -> httpx.Request:
    return get(f"{SEARCH}?q={query}&{TEMPLATE}{extra}")


def response_with(**product_fields: str) -> SearchResponse:
    """A response whose products have the given link fields (everything else is valid)."""
    tiers = [
        make_tier_result(tier, [make_product(index, **product_fields)])
        for index, tier in enumerate(Tier, start=1)
    ]
    group = GarmentGroup(item_index=0, category=Category.OUTERWEAR, tiers=tiers)
    return make_search_response(groups=[group])


# --------------------------------------------------------------------------------------------
# Plain words
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["black leather jacket", "جاكيت جلد أسود", "o'neil style", "t-shirt"]
)
def test_plain_words_are_accepted(text: str) -> None:
    assert is_plain_words(text)


@pytest.mark.parametrize(
    "text",
    [
        "http://evil.example",
        "evil.example",
        "<b>jacket</b>",
        "jacket[31m",
        "jacket\x00",
        "jacket\u202e",
        "jacket\u200b",
        "![x](y)",
        "jacket;drop",
        "",
        "   ",
    ],
)
def test_links_markup_and_hidden_characters_are_not_plain_words(text: str) -> None:
    assert not is_plain_words(text)


# --------------------------------------------------------------------------------------------
# Store searches
# --------------------------------------------------------------------------------------------


def test_a_clean_store_search_passes_the_query_check() -> None:
    assert_plain_keyword_queries([search_for("black%20jacket")])


@pytest.mark.parametrize(
    ("request_", "forbidden"),
    [
        (search_for("black%20jacket", "&redirect=https%3A%2F%2Fevil.example"), ()),
        (search_for("black%20jacket%20http%3A%2F%2Fevil.example"), ()),
        (search_for("%3Cscript%3Ealert"), ()),
        (search_for("black%20jacket%00"), ()),
        (search_for("cheap%20black%20jacket"), ()),
        (search_for("black%20jacket%20under%20400%20AED"), ()),
        (search_for("black%20jacket%20pwned"), ("PWNED",)),
        (search_for("jacket%20" * 30), ()),
    ],
    ids=[
        "extra-parameter",
        "link",
        "markup",
        "control-character",
        "price-word",
        "price-phrase",
        "forbidden-word",
        "overlong",
    ],
)
def test_a_store_search_with_something_injected_fails_the_query_check(
    request_: httpx.Request, forbidden: tuple[str, ...]
) -> None:
    with pytest.raises(AssertionError):
        assert_plain_keyword_queries([request_], forbidden)


def test_the_price_words_the_query_check_forbids_include_the_common_ones() -> None:
    assert {"cheap", "budget", "aed", "under", "sale"} <= PRICE_WORDS


# --------------------------------------------------------------------------------------------
# Hosts
# --------------------------------------------------------------------------------------------

ALLOWED = set(STORE.allowed_hosts)


def test_requests_to_allowed_hosts_pass_the_host_check() -> None:
    assert_hosts_allowed([get(f"https://{host}/x") for host in ALLOWED], [], ALLOWED)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.demo-store.example/x",
        "https://evil.example/x",
        "https://www.demo-store.example.evil.example/x",
        "https://www.demo-store.example:8443/x",
        "https://www.demo-store.example@evil.example/x",
        "https://169.254.169.254/latest",
    ],
    ids=["http", "other-host", "look-alike", "port", "credentials", "private-address"],
)
def test_a_request_somewhere_else_fails_the_host_check(url: str) -> None:
    with pytest.raises(AssertionError):
        assert_hosts_allowed([get(url)], [], ALLOWED)


def test_a_request_that_reached_the_tripwire_fails_the_host_check() -> None:
    stray = get("https://evil.example/x")

    with pytest.raises(AssertionError):
        assert_hosts_allowed([], [stray], ALLOWED)


# --------------------------------------------------------------------------------------------
# Links in a response
# --------------------------------------------------------------------------------------------


def test_a_response_with_links_on_the_stores_hosts_passes_the_link_check() -> None:
    assert_links_on_the_stores_hosts(response_with(), [STORE])


@pytest.mark.parametrize(
    "fields",
    [
        {"product_url": "https://evil.example/p/1"},
        {"image_url": "https://evil.example/i.jpg"},
        {"product_url": "https://www.demo-store.example:8443/p/1"},
        {"product_url": "https://www.demo-store.example.evil.example/p/1"},
        {"product_url": "https://169.254.169.254/p/1"},
        {"store": "Somebody Else"},
    ],
    ids=[
        "product-off-host",
        "image-off-host",
        "product-port",
        "product-look-alike",
        "product-private-address",
        "store-label-not-from-config",
    ],
)
def test_a_response_with_a_link_somewhere_else_fails_the_link_check(fields: dict[str, str]) -> None:
    with pytest.raises(AssertionError):
        assert_links_on_the_stores_hosts(response_with(**fields), [STORE])


# --------------------------------------------------------------------------------------------
# Friendly errors
# --------------------------------------------------------------------------------------------

GOOD = "We couldn't find any clothing or shoes to search for. Please describe an item instead."


def test_a_plain_message_passes_the_friendly_check() -> None:
    assert_friendly(InvalidInputError(GOOD, detail="nothing to shop for: no_garment"))


@pytest.mark.parametrize(
    ("message", "detail"),
    [
        ("Short.", None),
        ("Traceback (most recent call last): File x.py line 3 in run the request again", None),
        ("The OpenAI call failed with a validation error. Please try again in a moment.", None),
        ("We could not open https://evil.example for you, please describe the item instead.", None),
        (GOOD, GOOD),
    ],
    ids=["too-short", "traceback", "internals", "link", "detail-shown"],
)
def test_a_message_with_internals_fails_the_friendly_check(
    message: str, detail: str | None
) -> None:
    with pytest.raises(AssertionError):
        assert_friendly(InvalidInputError(message, detail=detail))


# --------------------------------------------------------------------------------------------
# The edge-case file
# --------------------------------------------------------------------------------------------


def test_the_seven_injection_cases_are_found_in_the_edge_case_file() -> None:
    cases = injection_cases()

    assert sorted(cases) == [f"e0{n}" for n in range(1, 8)]
    assert {case.expected for case in cases.values()} <= {"valid_schema", "friendly_error"}
