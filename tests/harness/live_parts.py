"""Fake "live" boundaries for the record, replay and CLI tests.

``LiveParts`` stands in for the real OpenAI call, the real fetch engine and the real image model.
Its searcher really talks to a fake network (``StoreHttpFixtures``), so a test can prove that a
replay made no network call and no model call by checking the counters afterwards.
"""

from collections.abc import Sequence

import httpx
from eval.harness.links import LinkResult
from eval.harness.wiring import Boundaries, Wiring

from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_store_config,
    make_understand_result,
)
from tests.fakes import (
    FakeImageRanker,
    FakeStoreSearcher,
    FakeUnderstander,
    RecordedResponse,
    StoreHttpFixtures,
)
from tests.harness.helpers import ToyPipeline
from vga.models import (
    Category,
    InputType,
    ItemIntent,
    SearchRequest,
    StoreConfig,
    StoreResult,
    UnderstandResult,
)
from vga.settings import Settings

PHOTO = make_image_bytes("JPEG", (64, 64), (10, 120, 200))
OUTFIT_TEXT = "an outfit: top and shoes"


def make_stores() -> list[StoreConfig]:
    return [
        make_store_config(
            id=name,
            name=name.title(),
            search_url_template=f"https://www.{name}.example/search?q={{query}}",
            allowed_hosts=[f"www.{name}.example", f"cdn.{name}.example"],
        )
        for name in ("alpha", "beta")
    ]


def understand_for(req: SearchRequest) -> UnderstandResult:
    """Two garments for the outfit query, one item otherwise."""
    if req.text == OUTFIT_TEXT:
        items = [
            make_item_intent(category=Category.TOPS, search_keywords=["white shirt"]),
            make_item_intent(category=Category.SHOES, search_keywords=["white sneakers"]),
        ]
        return make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items)
    kind = InputType.PRODUCT_PHOTO if req.text is None else InputType.TEXT
    return make_understand_result(input_type=kind)


class NetworkedSearcher:
    """Like the real fetch engine: it really issues a request per store, through a fake network."""

    def __init__(self, fixtures: StoreHttpFixtures, inner: FakeStoreSearcher) -> None:
        self._fixtures = fixtures
        self.inner = inner

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        async with httpx.AsyncClient(transport=self._fixtures.transport()) as client:
            for store in stores:
                await client.get(f"https://www.{store.id}.example/search?q=x")
        return await self.inner.search(item, stores)


class LiveParts:
    """The fake 'live' boundaries and everything that proves what they were asked."""

    def __init__(self) -> None:
        self.fixtures = StoreHttpFixtures()
        for store in make_stores():
            host = f"www.{store.id}.example"
            self.fixtures.add(
                f"https://{host}/", RecordedResponse(f"https://{host}/", 200, {}, b"{}")
            )
        self.understander = FakeUnderstander(understand_for)
        self.searcher = NetworkedSearcher(self.fixtures, FakeStoreSearcher(product_count=4))
        self.ranker = FakeImageRanker({}, default=0.8)

    def boundaries(self) -> Boundaries:
        return Boundaries(self.understander, self.searcher, self.ranker)

    def calls(self) -> tuple[int, int, int, int]:
        return (
            self.fixtures.request_count(),
            len(self.understander.calls),
            len(self.searcher.inner.calls),
            len(self.ranker.calls),
        )


def fake_wiring(settings: Settings) -> Wiring:
    """A ``(Settings) -> Wiring`` built from the fakes, named on the command line in tests as
    ``--wiring tests.harness.live_parts:fake_wiring``."""
    stores = make_stores()
    live = LiveParts()
    return Wiring(
        pipeline_factory=lambda u, s, r: ToyPipeline(u, s, r, stores),
        stores=stores,
        link_fetch=ok_link_fetch,
        build_boundaries=live.boundaries,
    )


async def ok_link_fetch(url: str) -> LinkResult:
    """Every product link opens its own page, titled like the fake products."""
    return LinkResult(
        url=url, final_url=url, status=200, title="Oversized Wool Blazer", elapsed_s=0.2
    )
