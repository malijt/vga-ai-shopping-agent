"""Fixtures shared by the Phase 6 tests. Nothing here touches the network: HTTP is answered by
``respx`` and time by the shared ``FakeClock``."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from tests.factories import make_settings, make_store_config
from tests.fakes import FakeClock
from vga.fetch.client import PoliteClient
from vga.fetch.robots import RobotsChecker
from vga.models import StoreConfig
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
