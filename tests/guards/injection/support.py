"""Shared setup and checks for the Module 14.3 injection tests (plan 14.3.1 and 14.3.2).

Every test here runs the REAL ``SearchPipeline`` with the REAL ``OpenAIUnderstander`` and the REAL
``StoreSearchEngine``. Only the boundaries are faked: OpenAI (``FakeOpenAI``, at HTTP level), the
stores (``StoreWorld``, answered by ``respx``), the image model, and the clock.

What this file adds on top of the shared fakes:

- ``Shop``: the fake stores plus a **tripwire**. ``respx`` raises on a request nobody mocked and
  does not record it, so an attempt to reach an attacker's host would vanish from
  ``router.calls``. The tripwire is a catch-all route added after the real ones; whatever lands in
  it is a request the code should never have made, and it is kept in ``Shop.strays``.
- ``Rig``: a pipeline, its fake OpenAI and its shop, with ``search`` that returns an ``Outcome``
  (a response or a plain ``VgaError``). Any other exception escapes, which fails the test: that is
  the "never a stack trace" check.
- The checks every test makes. The URL, host and link checks are written without the product's own
  helpers (``check_url``, ``is_allowed``), so a bug in those cannot hide itself: plain-word
  queries, requests that stay on a store's hosts, links in the response. ``test_oracles.py`` shows
  each of them failing on bad input.
"""

import json
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import respx
import yaml

from tests.pipeline.world import DEFAULT_PRICES, StoreWorld, generated_body
from tests.understand.eval_cases import EDGE_CASES_PATH, EdgeCase, load_image
from tests.understand.fake_openai import FakeOpenAI
from vga.errors import VgaError
from vga.models import (
    RunOverrides,
    SearchRequest,
    SearchResponse,
    StoreConfig,
)
from vga.pipeline import SearchPipeline
from vga.settings import Settings

MODEL = "gpt-5-mini-2025-08-07"

SEARCH_PATH = "/search/suggest.json"
SEARCH_PARAMETERS = frozenset({"q", "resources[type]", "resources[limit]"})
"""The only query parameters a store search carries: the template's own, with the keywords in
``q``. Anything else in the URL would be content that came from somewhere it should not."""

PRICE_WORDS = frozenset(
    {
        "cheap", "cheaper", "cheapest", "budget", "affordable", "inexpensive", "discount",
        "discounted", "sale", "price", "prices", "priced", "expensive", "under", "below", "aed",
        "dirham", "dirhams", "dhs", "sar", "usd",
    }
)  # fmt: skip
"""Price words that must never reach a store search (BRD Rule 7). Written out here on purpose,
instead of imported from the code under test."""

INJECTION_CASE_PREFIXES = ("e01_", "e02_", "e03_", "e04_", "e05_", "e06_", "e07_")
"""The Phase 4 cases this module covers, found by id prefix so a later rename of the rest of the
id does not break the lookup."""


# --------------------------------------------------------------------------------------------
# The edge cases (read-only)
# --------------------------------------------------------------------------------------------


def injection_cases() -> dict[str, EdgeCase]:
    """``e01`` to ``e07`` from ``eval/data/edge_cases.yaml``, keyed by the short id ("e01").

    Only these entries are read, so a case added to the file later cannot break these tests.
    """
    raw = yaml.safe_load(EDGE_CASES_PATH.read_text(encoding="utf-8"))
    found: dict[str, EdgeCase] = {}
    for entry in raw["cases"]:
        prefix = next((p for p in INJECTION_CASE_PREFIXES if entry["id"].startswith(p)), None)
        if prefix is None:
            continue
        found[prefix.rstrip("_")] = EdgeCase(
            id=entry["id"],
            type=entry["type"],
            text=entry.get("text"),
            image=entry.get("image"),
            expected=entry["expected"],
            why=entry["why"],
        )
    assert len(found) == len(INJECTION_CASE_PREFIXES), "an injection case is missing from the file"
    return found


def request_for(case: EdgeCase) -> SearchRequest:
    """The request a shopper would send for ``case``: its text and its photo, as the file says."""
    return SearchRequest(text=case.text, image=load_image(case))


# --------------------------------------------------------------------------------------------
# The shop: fake stores with a tripwire
# --------------------------------------------------------------------------------------------


@dataclass
class Shop:
    """The fake stores of one test and every request that was made to them."""

    world: StoreWorld
    stores: list[StoreConfig]
    strays: list[httpx.Request]
    """Requests that matched no route of the fake stores. There must never be one."""

    @property
    def requests(self) -> list[httpx.Request]:
        """Every request the code made, in order (strays included)."""
        return [call.request for call in self.world.router.calls]

    @property
    def search_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path == SEARCH_PATH]

    @property
    def queries(self) -> list[str]:
        """The decoded ``q`` of every store search, in order."""
        return [request.url.params.get("q", "") for request in self.search_requests]

    @property
    def allowed_hosts(self) -> set[str]:
        return {host for store in self.stores for host in store.allowed_hosts}

    def store_named(self, display_name: str) -> StoreConfig | None:
        return next((s for s in self.stores if s.display_name == display_name), None)


def open_shop(
    world: StoreWorld,
    router: respx.MockRouter,
    stores: Sequence[StoreConfig],
    *,
    bodies: Mapping[str, Mapping[str, str]] | None = None,
) -> Shop:
    """Serve ``stores`` (with ``bodies[store id]`` as their answers, if given) and add the
    tripwire. The tripwire is added last, so it only ever sees requests nothing else answers."""
    for store in stores:
        world.add(store, bodies=(bodies or {}).get(store.id))
    strays: list[httpx.Request] = []

    def tripwire(request: httpx.Request) -> httpx.Response:
        strays.append(request)
        return httpx.Response(404, text="nobody expected this request")

    router.route().mock(side_effect=tripwire)
    return Shop(world, list(stores), strays)


def answers_every_query(store: StoreConfig) -> dict[str, str]:
    """A store that sells every kind of garment and shows its jackets for any query it does not
    recognise (an Arabic one, or a stray word), so that every search that happens has results."""
    bodies = {
        kind: generated_body(kind, store.id, prices) for kind, prices in DEFAULT_PRICES.items()
    }
    bodies[""] = bodies["blazer"]
    return bodies


# --------------------------------------------------------------------------------------------
# The rig: the real pipeline around a fake OpenAI
# --------------------------------------------------------------------------------------------


@dataclass
class Outcome:
    """What the shopper gets: a response or a plain error, never both."""

    response: SearchResponse | None = None
    error: VgaError | None = None


@dataclass
class Rig:
    pipeline: SearchPipeline
    fake: FakeOpenAI
    shop: Shop
    settings: Settings

    async def search(
        self, request: SearchRequest, overrides: RunOverrides | None = None
    ) -> Outcome:
        """Run ``request``. A ``VgaError`` is the "friendly error" the UI shows; any other
        exception is a stack trace the shopper would see, and is left to fail the test."""
        try:
            return Outcome(response=await self.pipeline.run(request, self.settings, overrides))
        except VgaError as error:
            return Outcome(error=error)

    @property
    def openai_text(self) -> str:
        """Everything sent to OpenAI so far, as one string (every message of every call)."""
        return json.dumps([recorded.body for recorded in self.fake.requests], ensure_ascii=False)


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------


def is_plain_words(text: str) -> bool:
    """Letters, digits and marks of any script, spaces, hyphens and apostrophes: nothing that
    could be a link, markup, an escape sequence or a control character."""
    return bool(text.strip()) and all(
        unicodedata.category(ch)[0] in "LNM" or ch in " -'’"  # noqa: RUF001 (the curly one is meant)
        for ch in text
    )


def assert_hosts_allowed(
    requests: Sequence[httpx.Request],
    strays: Sequence[httpx.Request],
    allowed_hosts: Collection[str],
) -> None:
    """Every request went to https, the default port, no credentials, and a host in
    ``allowed_hosts``; none of them reached the tripwire."""
    assert [str(r.url) for r in strays] == [], "a request nobody expected was made"
    for request in requests:
        url = request.url
        assert url.scheme == "https", str(url)
        assert url.port is None, str(url)
        assert not url.userinfo, str(url)
        assert url.host in allowed_hosts, f"{url.host} is not on any store's allowed_hosts"


def assert_requests_stay_on_the_stores_hosts(shop: Shop) -> None:
    assert_hosts_allowed(shop.requests, shop.strays, shop.allowed_hosts)


def assert_plain_keyword_queries(
    requests: Sequence[httpx.Request], forbidden: Sequence[str] = ()
) -> None:
    """Each store search is the store's own template with plain words in ``q``: no extra
    parameter, no link, markup or control character in the words, no price word, none of
    ``forbidden`` (matched without regard to case), and no longer than a keyword may be."""
    for request in requests:
        if request.url.path != SEARCH_PATH:
            continue
        params = request.url.params
        assert set(params.keys()) == SEARCH_PARAMETERS, str(request.url)
        assert params["resources[type]"] == "product", str(request.url)
        query = params["q"]
        assert is_plain_words(query), f"query is not plain words: {query!r}"
        assert len(query) <= 100, f"query is too long: {len(query)} characters"
        folded = query.casefold()
        words = set(re.findall(r"[^\W_]+", folded))
        assert not words & PRICE_WORDS, f"price word in the query: {query!r}"
        for bad in forbidden:
            assert bad.casefold() not in folded, f"{bad!r} reached a store: {query!r}"


def assert_links_on_the_stores_hosts(
    response: SearchResponse, stores: Sequence[StoreConfig]
) -> None:
    """Every product link and image link in the response is https, has no credentials or port,
    and sits on a host of the store the product is labelled with (a name from the store's
    configuration)."""
    by_name = {store.display_name: store for store in stores}
    for scored in response.products:
        store = by_name.get(scored.product.store)
        assert store is not None, f"unknown store label {scored.product.store!r}"
        for url in (scored.product.product_url, scored.product.image_url):
            parts = urlsplit(url)
            assert parts.scheme == "https", url
            assert parts.hostname in store.allowed_hosts, url
            assert parts.username is None, url
            assert parts.password is None, url
            assert parts.port is None, url


FRIENDLY_LEAKS = re.compile(
    r"traceback|exception|stack|openai|\bhttps?\b|json|schema|validation|pydantic|\.py\b",
    re.IGNORECASE,
)


def assert_friendly(error: VgaError, forbidden: Sequence[str] = ()) -> None:
    """The message is plain language that says what to do next, and says nothing of internals,
    the log-only detail, or the attacker's words."""
    message = error.user_message
    assert len(message) >= 40, message
    assert not FRIENDLY_LEAKS.search(message), message
    assert not error.detail or error.detail not in message
    for bad in forbidden:
        assert bad.casefold() not in message.casefold()
    assert "Traceback" not in repr(error)
