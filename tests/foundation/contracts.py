"""Reusable contract suites: one per interface in ``vga.interfaces``.

A fake and its real implementation must behave the same, or tests built on the fake prove
nothing (Liskov). Each suite below states that shared behaviour once. To run it against an
implementation, subclass the suite in that implementation's own test folder and override the
fixtures::

    from tests.foundation.contracts import ImageRankerContract

    class TestSiglipRanker(ImageRankerContract):
        @pytest.fixture
        def ranker(self):
            return build_real_ranker_with_fake_weights()

Suites hold only the invariants every implementation shares. Behaviour specific to one
implementation (prompts, ranking quality, parsing) belongs in that implementation's own tests.
"""

import asyncio
from collections import Counter
from urllib.parse import urlsplit

import pytest

from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_products,
    make_search_request,
    make_settings,
    make_store_config,
)
from vga.interfaces import Clock, ImageRanker, Pipeline, StoreSearcher, Understander
from vga.models import (
    MAX_ITEMS,
    MAX_KEYWORDS,
    Product,
    QueryImage,
    SearchRequest,
    SearchResponse,
    Step,
    StoreConfig,
    StoreStatus,
    UnderstandResult,
)
from vga.settings import Settings

STEP_ORDER = list(Step)


class ClockContract:
    """``Clock``: time that never goes backwards and a sleep that really passes time."""

    @pytest.fixture
    def clock(self) -> Clock:
        raise NotImplementedError

    def test_satisfies_the_protocol(self, clock: Clock) -> None:
        assert isinstance(clock, Clock)

    def test_monotonic_never_goes_backwards(self, clock: Clock) -> None:
        readings = [clock.monotonic() for _ in range(5)]
        assert readings == sorted(readings)

    async def test_sleep_passes_at_least_the_requested_time(self, clock: Clock) -> None:
        before = clock.monotonic()
        await clock.sleep(0.02)
        assert clock.monotonic() - before >= 0.02 - 0.002

    @pytest.mark.parametrize("seconds", [0, -1])
    async def test_sleep_of_zero_or_less_returns_promptly(
        self, clock: Clock, seconds: float
    ) -> None:
        before = clock.monotonic()
        await asyncio.wait_for(clock.sleep(seconds), timeout=1)
        assert clock.monotonic() - before < 0.5


class UnderstanderContract:
    """``Understander``: turns a request into a valid ``UnderstandResult``."""

    @pytest.fixture
    def understander(self) -> Understander:
        raise NotImplementedError

    @pytest.fixture
    def search_request(self) -> SearchRequest:
        return make_search_request(text="black oversized blazer for men under 400 AED")

    def test_satisfies_the_protocol(self, understander: Understander) -> None:
        assert isinstance(understander, Understander)

    async def test_returns_a_valid_result(
        self, understander: Understander, search_request: SearchRequest
    ) -> None:
        result = await understander.understand(search_request)

        assert isinstance(result, UnderstandResult)
        assert 1 <= len(result.items) <= MAX_ITEMS
        for item in result.items:
            assert 1 <= len(item.search_keywords) <= MAX_KEYWORDS
        assert result.prompt_version
        assert result.model

    async def test_result_survives_a_json_round_trip(
        self, understander: Understander, search_request: SearchRequest
    ) -> None:
        result = await understander.understand(search_request)

        assert UnderstandResult.model_validate_json(result.model_dump_json()) == result

    async def test_does_not_change_the_request(
        self, understander: Understander, search_request: SearchRequest
    ) -> None:
        snapshot = search_request.model_copy()

        await understander.understand(search_request)

        assert search_request == snapshot

    async def test_accepts_a_photo_request(self, understander: Understander) -> None:
        photo_request = make_search_request(image=make_image_bytes(), text=None)

        result = await understander.understand(photo_request)

        assert isinstance(result, UnderstandResult)


class StoreSearcherContract:
    """``StoreSearcher``: one ``StoreResult`` per store, products that belong to that store."""

    @pytest.fixture
    def searcher(self) -> StoreSearcher:
        raise NotImplementedError

    @pytest.fixture
    def stores(self) -> list[StoreConfig]:
        return [
            make_store_config(
                id="store-a",
                name="Store A",
                search_url_template="https://www.store-a.example/search?q={query}",
                allowed_hosts=["www.store-a.example", "cdn.store-a.example"],
            ),
            make_store_config(
                id="store-b",
                name="Store B",
                search_url_template="https://www.store-b.example/s/{query}",
                allowed_hosts=["www.store-b.example", "cdn.store-b.example"],
            ),
        ]

    def test_satisfies_the_protocol(self, searcher: StoreSearcher) -> None:
        assert isinstance(searcher, StoreSearcher)

    async def test_returns_one_result_per_store_in_order(
        self, searcher: StoreSearcher, stores: list[StoreConfig]
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        assert [result.store_id for result in results] == [store.id for store in stores]

    async def test_no_stores_gives_no_results(self, searcher: StoreSearcher) -> None:
        assert await searcher.search(make_item_intent(), []) == []

    async def test_products_carry_their_stores_name_and_stay_on_allowed_hosts(
        self, searcher: StoreSearcher, stores: list[StoreConfig]
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        for store, result in zip(stores, results, strict=True):
            for product in result.products:
                assert product.store == store.display_name
                assert _host(product.product_url) in store.allowed_hosts
                assert _host(product.image_url) in store.allowed_hosts

    async def test_only_ok_results_carry_products(
        self, searcher: StoreSearcher, stores: list[StoreConfig]
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        for result in results:
            assert bool(result.products) == (result.status is StoreStatus.OK)

    async def test_product_links_are_unique_within_a_store(
        self, searcher: StoreSearcher, stores: list[StoreConfig]
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        for result in results:
            urls = [product.product_url for product in result.products]
            assert len(urls) == len(set(urls))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class ImageRankerContract:
    """``ImageRanker``: a 0-1 score or ``None`` for every product, deterministic, never raising."""

    @pytest.fixture
    def ranker(self) -> ImageRanker:
        raise NotImplementedError

    @pytest.fixture
    def products(self) -> list[Product]:
        return make_products(4)

    @pytest.fixture
    def query(self) -> QueryImage:
        return QueryImage(image=make_image_bytes())

    def test_satisfies_the_protocol(self, ranker: ImageRanker) -> None:
        assert isinstance(ranker, ImageRanker)

    async def test_without_a_photo_every_score_is_none(
        self, ranker: ImageRanker, products: list[Product]
    ) -> None:
        scores = await ranker.score(None, products)

        assert scores == dict.fromkeys(p.key for p in products)

    async def test_no_products_gives_an_empty_mapping(
        self, ranker: ImageRanker, query: QueryImage
    ) -> None:
        assert await ranker.score(query, []) == {}

    async def test_every_product_gets_an_entry_between_zero_and_one(
        self, ranker: ImageRanker, products: list[Product], query: QueryImage
    ) -> None:
        scores = await ranker.score(query, products)

        assert set(scores) == {p.key for p in products}
        for value in scores.values():
            assert value is None or 0.0 <= value <= 1.0

    async def test_scoring_twice_gives_the_same_result(
        self, ranker: ImageRanker, products: list[Product]
    ) -> None:
        first = await ranker.score(QueryImage(image=make_image_bytes()), products)
        second = await ranker.score(QueryImage(image=make_image_bytes()), products)

        assert first == second

    async def test_a_stored_embedding_scores_the_same_as_the_photo(
        self, ranker: ImageRanker, products: list[Product], query: QueryImage
    ) -> None:
        with_photo = await ranker.score(query, products)
        if query.embedding is None:
            pytest.skip("this ranker does not produce a query embedding")

        without_photo = await ranker.score(
            QueryImage(image=None, embedding=query.embedding), products
        )

        assert without_photo == with_photo


class PipelineContract:
    """``Pipeline``: a well-formed ``SearchResponse`` for the request, and honest progress."""

    @pytest.fixture
    def pipeline(self) -> Pipeline:
        raise NotImplementedError

    @pytest.fixture
    def search_request(self) -> SearchRequest:
        return make_search_request()

    @pytest.fixture
    def settings(self) -> Settings:
        return make_settings()

    def test_satisfies_the_protocol(self, pipeline: Pipeline) -> None:
        assert isinstance(pipeline, Pipeline)

    async def test_response_belongs_to_the_request(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        response = await pipeline.run(search_request, settings)

        assert isinstance(response, SearchResponse)
        assert response.request_id == search_request.request_id

    async def test_every_group_has_the_four_price_ranges_in_order(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        response = await pipeline.run(search_request, settings)

        for group in response.groups:
            assert [tier.name.value for tier in group.tiers] == [
                "budget",
                "mid_range",
                "premium",
                "luxury",
            ]

    async def test_no_store_exceeds_the_per_store_cap(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        response = await pipeline.run(search_request, settings)

        per_store = Counter(scored.product.store for scored in response.products)
        assert all(count <= settings.max_per_store for count in per_store.values())

    async def test_every_link_is_https(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        response = await pipeline.run(search_request, settings)

        assert all(s.product.product_url.startswith("https://") for s in response.products)

    async def test_progress_steps_are_known_and_in_order(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        seen: list[Step] = []

        await pipeline.run(search_request, settings, on_step=seen.append)

        assert seen, "on_step was never called"
        positions = [STEP_ORDER.index(step) for step in seen]
        assert positions == sorted(positions)

    async def test_runs_without_a_progress_callback(
        self, pipeline: Pipeline, search_request: SearchRequest, settings: Settings
    ) -> None:
        response = await pipeline.run(search_request, settings, on_step=None)

        assert isinstance(response, SearchResponse)
