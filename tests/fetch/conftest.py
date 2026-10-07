"""Fixtures shared by the Phase 6 tests. Nothing here touches the network: HTTP is answered by
``respx`` and time by the shared ``FakeClock``."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from tests.factories import make_settings, make_store_config
from tests.fakes import FakeClock
from vga.fetch.client import PoliteClient
from vga.fetch.robots import RobotsChecker
from vga.models import ExtractionConfig, StoreConfig, StrategyConfig
from vga.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"

HOST = "www.demo-store.example"
CDN = "cdn.demo-store.example"
SEARCH_URL = f"https://{HOST}/search?q=black%20blazer"
ROBOTS_URL = f"https://{HOST}/robots.txt"

ALLOW_ALL_ROBOTS = "User-agent: *\nDisallow:\n"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def store() -> StoreConfig:
    return make_store_config()


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    """Answers every httpx request in the test. A request nobody mocked raises, so a test cannot
    reach the network by accident."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


@pytest.fixture
def client(settings: Settings, clock: FakeClock, router: respx.MockRouter) -> PoliteClient:
    return PoliteClient(settings, clock=clock)


@pytest.fixture
def robots(client: PoliteClient) -> RobotsChecker:
    return RobotsChecker(client)


def text_response(
    body: str, *, status: int = 200, content_type: str = "text/plain"
) -> httpx.Response:
    return httpx.Response(
        status, content=body.encode("utf-8"), headers={"content-type": content_type}
    )


# --------------------------------------------------------------------------------------------
# Shopify stores and responses
# --------------------------------------------------------------------------------------------

SUGGEST_PATH = "/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10"
OHPOLLY_ROBOTS_URL = "https://ohpolly.ae/robots.txt"
OHPOLLY_BLAZER_URL = (
    "https://ohpolly.ae/search/suggest.json?q=black%20blazer"
    "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
)


def shopify_store(**overrides: Any) -> StoreConfig:
    """Oh Polly as the store file will describe it: Shopify suggest endpoint, AED, CDN images."""
    fields: dict[str, Any] = {
        "id": "oh-polly",
        "name": "Oh Polly",
        "country": "AE",
        "currency": "AED",
        "search_url_template": "https://ohpolly.ae" + SUGGEST_PATH,
        "allowed_hosts": ["ohpolly.ae", "www.ohpolly.ae", "cdn.shopify.com"],
        "extraction": ExtractionConfig(strategies=[StrategyConfig(name="shopify")]),
        "tier_hint": "mid_range",
        "enabled": True,
    }
    return make_store_config(**{**fields, **overrides})


def club_l_store(**overrides: Any) -> StoreConfig:
    fields: dict[str, Any] = {
        "id": "club-l-london",
        "name": "Club L London",
        "search_url_template": "https://www.clubllondon.ae" + SUGGEST_PATH,
        "allowed_hosts": ["www.clubllondon.ae", "clubllondon.ae", "cdn.shopify.com"],
        "tier_hint": "premium",
    }
    return shopify_store(**{**fields, **overrides})


def shopify_product(index: int = 1, **overrides: Any) -> dict[str, Any]:
    """One product in the shape of a real ``/search/suggest.json`` response."""
    product: dict[str, Any] = {
        "available": True,
        "body": "<p>store supplied html</p>",
        "compare_at_price_max": "0.00",
        "compare_at_price_min": "0.00",
        "handle": f"blazer-{index}",
        "id": 1000 + index,
        "image": f"https://cdn.shopify.com/s/files/1/0001/0002/files/blazer-{index}.jpg?v=1",
        "price": f"{100 + index}.00",
        "price_max": f"{100 + index}.00",
        "price_min": f"{100 + index}.00",
        "tags": ["tag"],
        "title": f"Blazer {index}",
        "type": "Coats & Jackets",
        "url": f"/products/blazer-{index}?_pos={index}&_psq=blazer&_psid=abc123&_ss=e",
        "variants": [],
        "vendor": "Demo Brand",
    }
    return {**product, **overrides}


def suggest_body(*products: dict[str, Any]) -> str:
    return json.dumps({"resources": {"results": {"products": list(products)}}})


def json_response(body: str) -> httpx.Response:
    return text_response(body, content_type="application/json; charset=utf-8")
