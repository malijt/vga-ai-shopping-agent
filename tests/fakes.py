"""Shared fakes for the three boundaries (store HTTP, OpenAI, image model) and for time.

Every phase imports its fakes from here and never re-implements them (plan 1.2.7). Each fake
honours the same contract as the real thing, and passes the same suite in
``tests/foundation/contracts.py``. This module has no pytest import, so the acceptance harness can
use ``FakePipeline`` at runtime (``python -m eval.harness --mock``).
"""

import asyncio
import heapq
import itertools
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import httpx

from tests.factories import (
    load_sample_response,
    make_item_intent,
    make_product,
    make_understand_result,
)
from vga.errors import VgaError
from vga.models import (
    InputType,
    ItemIntent,
    Product,
    QueryImage,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    Step,
    StoreConfig,
    StoreResult,
    StoreStatus,
    UnderstandResult,
)
from vga.settings import Settings

# --------------------------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------------------------


class FakeClock:
    """A ``Clock`` whose time only moves when told to, so no test ever really waits.

    - ``monotonic()`` returns virtual seconds.
    - ``sleep(s)`` suspends the caller until virtual time reaches ``now + s``. Time advances by
      itself, to the earliest pending wake-up, once every other task has had a chance to run.
      Concurrent sleeps therefore overlap, as in real life: ``gather(sleep(1), sleep(2))`` takes
      2 virtual seconds, not 3.
    - ``advance(s)`` moves time forward at once (for example to expire a cache entry).
    - ``sleeps`` lists every requested duration in call order, so a test can assert on backoff
      delays.
    """

    SETTLE_HOPS = 5
    """Event-loop iterations to wait before advancing time, so tasks that are still doing
    zero-time work (mocked HTTP, parsing) finish first."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self._tick_scheduled = False
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        heapq.heappush(self._sleepers, (self._now + seconds, next(self._order), future))
        self._schedule_tick(loop)
        await future

    def advance(self, seconds: float) -> None:
        """Move time forward by ``seconds`` now and wake every sleeper whose time has come."""
        self._now += seconds
        self._wake_due()

    def _schedule_tick(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self._tick_scheduled:
            self._tick_scheduled = True
            loop.call_soon(self._settle, self.SETTLE_HOPS)

    def _settle(self, hops: int) -> None:
        if hops > 0:
            asyncio.get_running_loop().call_soon(self._settle, hops - 1)
            return
        self._tick_scheduled = False
        self._drop_cancelled()
        if not self._sleepers:
            return
        self._now = max(self._now, self._sleepers[0][0])
        self._wake_due()
        self._drop_cancelled()
        if self._sleepers:
            self._schedule_tick(asyncio.get_running_loop())

    def _drop_cancelled(self) -> None:
        while self._sleepers and self._sleepers[0][2].done():
            heapq.heappop(self._sleepers)

    def _wake_due(self) -> None:
        while self._sleepers and self._sleepers[0][0] <= self._now:
            _, _, future = heapq.heappop(self._sleepers)
            if not future.done():
                future.set_result(None)


# --------------------------------------------------------------------------------------------
# OpenAI boundary
# --------------------------------------------------------------------------------------------

ResultFactory = Callable[[SearchRequest], UnderstandResult]


def default_understand_result(req: SearchRequest) -> UnderstandResult:
    """A plausible single-item result for any request: keywords come from the text if present."""
    if req.has_image and req.text:
        input_type = InputType.PHOTO_TEXT
    elif req.has_image:
        input_type = InputType.PRODUCT_PHOTO
    else:
        input_type = InputType.TEXT
    keywords = [" ".join(req.text.split()[:6])[:80]] if req.text else ["black oversized blazer"]
    return make_understand_result(
        input_type=input_type, items=[make_item_intent(search_keywords=keywords)]
    )


class FakeUnderstander:
    """Stands in for the OpenAI call. Returns a fixed result, a result computed from the request,
    or raises a chosen error. Records every request in ``calls``."""

    def __init__(
        self,
        result: UnderstandResult | ResultFactory | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.calls: list[SearchRequest] = []

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        self.calls.append(req)
        if self._error is not None:
            raise self._error
        if self._result is None:
            return default_understand_result(req)
        if callable(self._result):
            return self._result(req)
        return self._result


# --------------------------------------------------------------------------------------------
# Image model boundary
# --------------------------------------------------------------------------------------------


class FakeImageRanker:
    """Stands in for the FashionSigLIP model: no weights, no images decoded.

    Scores come from ``scores`` (keyed by ``Product.key``) and fall back to ``default``. With no
    query photo every score is ``None``, as the real rankers do. When given a photo it stores a
    fixed ``embedding`` on the query, so tests can check that a re-run without the photo works.
    ``error`` makes ``score`` raise, to test the factory's fallback (a real ranker never raises).
    """

    def __init__(
        self,
        scores: Mapping[str, float | None] | None = None,
        *,
        default: float | None = 0.5,
        embedding: Sequence[float] = (0.1, 0.2, 0.3),
        error: Exception | None = None,
    ) -> None:
        self._scores = dict(scores or {})
        self._default = default
        self._embedding = list(embedding)
        self._error = error
        self.calls: list[list[str]] = []
        """Product keys passed to each ``score`` call."""

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        keys = [product.key for product in products]
        self.calls.append(keys)
        if self._error is not None:
            raise self._error
        if query is None or (query.image is None and query.embedding is None):
            return dict.fromkeys(keys)
        if query.embedding is None:
            query.embedding = list(self._embedding)
        return {key: self._scores.get(key, self._default) for key in keys}


# --------------------------------------------------------------------------------------------
# Store boundary
# --------------------------------------------------------------------------------------------


class FakeStoreSearcher:
    """Stands in for the whole fetch engine when a test only needs its output.

    Returns the canned ``StoreResult`` for a store id if one was given, otherwise ``product_count``
    generated products whose links sit on that store's first allowed host. To test the real engine,
    fake the HTTP layer instead (``StoreHttpFixtures``).
    """

    def __init__(
        self, results: Mapping[str, StoreResult] | None = None, *, product_count: int = 3
    ) -> None:
        self._results = dict(results or {})
        self._product_count = product_count
        self.calls: list[tuple[ItemIntent, list[str]]] = []

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        self.calls.append((item, [store.id for store in stores]))
        return [self._results.get(store.id) or self._generate(store) for store in stores]

    def _generate(self, store: StoreConfig) -> StoreResult:
        host = store.allowed_hosts[0]
        products = [
            make_product(
                index,
                store=store.display_name,
                currency=store.currency,
                image_url=f"https://{host}/img/{store.id}-{index}.jpg",
                product_url=f"https://{host}/p/{store.id}-{index}",
            )
            for index in range(1, self._product_count + 1)
        ]
        if not products:
            return StoreResult(store_id=store.id, status=StoreStatus.EMPTY, duration_ms=1.0)
        return StoreResult(
            store_id=store.id,
            status=StoreStatus.OK,
            products=products,
            duration_ms=1.0,
            strategy="fake",
        )


@dataclass(frozen=True)
class RecordedResponse:
    """A store HTTP response saved from a real run (trimmed), replayed offline."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def to_httpx(self) -> httpx.Response:
        return httpx.Response(self.status, headers=self.headers, content=self.body)


_CONTENT_TYPES = {
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
}


def load_recorded_response(
    body_path: Path | str,
    *,
    url: str | None = None,
    status: int | None = None,
    headers: Mapping[str, str] | None = None,
) -> RecordedResponse:
    """Load a recorded response from its body file (``.html``, ``.json``, ...).

    An optional sidecar ``<body file>.meta.json`` may hold ``{"url", "status", "headers"}``;
    arguments given here win over the sidecar. Without either, status is 200 and the content type
    follows the file extension.
    """
    path = Path(body_path)
    meta: dict[str, Any] = {}
    sidecar = path.with_name(path.name + ".meta.json")
    if sidecar.is_file():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    merged_headers: dict[str, str] = {}
    content_type = _CONTENT_TYPES.get(path.suffix.lower())
    if content_type:
        merged_headers["content-type"] = content_type
    merged_headers.update({k.lower(): v for k, v in (meta.get("headers") or {}).items()})
    merged_headers.update({k.lower(): v for k, v in (headers or {}).items()})
    return RecordedResponse(
        url=url or meta.get("url") or f"https://recorded.example/{path.name}",
        status=status or int(meta.get("status", 200)),
        headers=merged_headers,
        body=path.read_bytes(),
    )


class UnexpectedRequestError(AssertionError):
    """A test's code requested a URL that has no recorded response."""


@dataclass
class StoreHttpFixtures:
    """Serves recorded responses through ``httpx.MockTransport``, and counts requests.

    ::

        fixtures = StoreHttpFixtures()
        fixtures.add_file("https://www.demo-store.example/search", "tests/stores/demo/search.json")
        async with httpx.AsyncClient(transport=fixtures.transport()) as client:
            ...
        assert fixtures.request_count() == 1

    A request is answered by the recorded response with the longest matching URL prefix. A
    request with no match is remembered in ``unexpected`` and raises ``UnexpectedRequestError``;
    call ``assert_no_unexpected_requests`` at the end of a test, because the code under test may
    swallow the exception.
    """

    routes: list[tuple[str, RecordedResponse]] = field(default_factory=list)
    requests: list[httpx.Request] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)

    def add(self, url_prefix: str, recorded: RecordedResponse) -> Self:
        self.routes.append((url_prefix, recorded))
        return self

    def add_file(self, url_prefix: str, body_path: Path | str, **kwargs: Any) -> Self:
        return self.add(url_prefix, load_recorded_response(body_path, **kwargs))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        matches = [(prefix, rec) for prefix, rec in self.routes if url.startswith(prefix)]
        if not matches:
            self.unexpected.append(url)
            msg = f"no recorded response for {url}"
            raise UnexpectedRequestError(msg)
        _, recorded = max(matches, key=lambda match: len(match[0]))
        return recorded.to_httpx()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def request_count(self, host: str | None = None) -> int:
        """Requests seen so far, optionally only those to ``host``."""
        if host is None:
            return len(self.requests)
        return sum(1 for request in self.requests if request.url.host == host)

    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]

    def assert_no_unexpected_requests(self) -> None:
        if self.unexpected:
            msg = f"unexpected requests: {self.unexpected}"
            raise UnexpectedRequestError(msg)


# --------------------------------------------------------------------------------------------
# Pipeline boundary
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineCall:
    req: SearchRequest
    settings: Settings
    overrides: RunOverrides | None


class FakePipeline:
    """Returns a canned ``SearchResponse`` (default: the bundled sample) for any request.

    Calls ``on_step`` for each of ``steps`` first, like the real pipeline. Used by the UI tests
    and by the acceptance harness in ``--mock`` mode. Pass ``error`` to raise instead, to test
    error handling.
    """

    def __init__(
        self,
        response: SearchResponse | None = None,
        *,
        error: VgaError | None = None,
        steps: Sequence[Step] = tuple(Step),
    ) -> None:
        self._response = response
        self._error = error
        self._steps = tuple(steps)
        self.calls: list[PipelineCall] = []

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> SearchResponse:
        self.calls.append(PipelineCall(req, settings, overrides))
        if on_step is not None:
            for step in self._steps:
                on_step(step)
        if self._error is not None:
            raise self._error
        base = self._response or load_sample_response()
        return base.model_copy(update={"request_id": req.request_id})
