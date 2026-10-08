"""Stores on a hosted platform, for the tests of the platform queue and the platform cooldown.

``shopify("one")`` is a Shopify storefront at ``https://one.example``; ``store_on("store_json",
"plain")`` is a store of the same kind of address on no known platform. ``FakeShops`` answers for
every ``*.example`` shop and the shared image host, notes when each request arrived, and can be told
to answer one shop differently (``refuse``, ``answer``).
"""

from collections.abc import Callable
from typing import Any

import httpx
import respx

from tests.factories import make_store_config
from tests.fakes import FakeClock
from tests.fetch.conftest import ALLOW_ALL_ROBOTS, text_response
from vga.fetch import PoliteClient
from vga.models import ExtractionConfig, StoreConfig, StrategyConfig

Answer = Callable[[httpx.Request], httpx.Response]


def store_on(strategy: str, key: str, **overrides: Any) -> StoreConfig:
    """A store ``key`` at ``https://<key>.example`` that reads its answers with ``strategy``."""
    fields: dict[str, Any] = {
        "id": key,
        "name": key.title(),
        "search_url_template": f"https://{key}.example/search?q={{query}}",
        "allowed_hosts": [f"{key}.example", "cdn.shopify.com"],
        "extraction": ExtractionConfig(strategies=[StrategyConfig(name=strategy)]),
    }
    return make_store_config(**{**fields, **overrides})


def shopify(key: str, **overrides: Any) -> StoreConfig:
    return store_on("shopify", key, **overrides)


class FakeShops:
    """Every ``*.example`` shop and the image CDN answer anything with 200, and note when each
    request arrived (seconds after the shops were set up, on the fake clock)."""

    def __init__(self, router: respx.MockRouter, clock: FakeClock) -> None:
        self._clock = clock
        self._start = clock.monotonic()
        self._answers: dict[str, Answer] = {}
        self.arrivals: list[tuple[str, float]] = []
        router.get(url__regex=r"https://([a-z0-9-]+\.example|cdn\.shopify\.com)/.*").mock(
            side_effect=self._answer
        )

    def answer(self, host: str, answer: Answer) -> None:
        """Answer every request to ``host`` (a name such as ``one.example``) with ``answer``."""
        self._answers[host] = answer

    def refuse(self, key: str, status: int, **headers: str) -> None:
        """Answer every request to the shop ``key`` with an empty ``status`` response."""
        self.answer(
            f"{key}.example", lambda _request: httpx.Response(status, text="no", headers=headers)
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.arrivals.append((str(request.url), self._clock.monotonic() - self._start))
        answer = self._answers.get(request.url.host)
        return answer(request) if answer is not None else text_response(ALLOW_ALL_ROBOTS)

    def times(self, only: str = "") -> list[float]:
        return sorted(time for url, time in self.arrivals if only in url)


async def get(client: PoliteClient, store: StoreConfig, path: str = "/p") -> None:
    """Request ``path`` of ``store``'s own site."""
    await client.fetch(f"https://{store.id}.example{path}", store, client.page_policy(store))
