"""The real engine passes the same ``StoreSearcher`` contract suite as the fake (Liskov).

The suite's default stores ask for the ``store_json`` strategy, which is not built, so the stores
fixture is replaced with two Shopify stores on the suite's hosts. Their HTTP is served from
``StoreHttpFixtures`` (the shared recorded-response fake), and nothing touches the network.
"""

import pytest

from tests.factories import make_item_intent, make_settings, make_store_config
from tests.fakes import FakeClock, RecordedResponse, StoreHttpFixtures
from tests.fetch.conftest import shopify_product, suggest_body
from tests.foundation.contracts import StoreSearcherContract
from vga.interfaces import StoreSearcher
from vga.models import StoreConfig, StoreStatus
from vga.stores.engine import StoreSearchEngine

HOST_A = "www.store-a.example"
HOST_B = "www.store-b.example"


def shopify_on(host: str, store_id: str, name: str) -> StoreConfig:
    return make_store_config(
        id=store_id,
        name=name,
        search_url_template=f"https://{host}/search/suggest.json?q={{query}}",
        allowed_hosts=[host, "cdn.shopify.com"],
        extraction={"strategies": [{"name": "shopify"}]},
    )


def recorded(url: str, content_type: str, body: str) -> RecordedResponse:
    return RecordedResponse(url, 200, {"content-type": content_type}, body.encode("utf-8"))


def build_http() -> StoreHttpFixtures:
    """Store A answers with three products, store B with none."""
    products = [
        shopify_product(n, handle=f"a-{n}", url=f"/products/a-{n}?_pos={n}", title=f"A blazer {n}")
        for n in range(1, 4)
    ]
    http = StoreHttpFixtures()
    for host, body in ((HOST_A, suggest_body(*products)), (HOST_B, suggest_body())):
        http.add(
            f"https://{host}/robots.txt",
            recorded(f"https://{host}/robots.txt", "text/plain", "User-agent: *\nDisallow:\n"),
        )
        http.add(
            f"https://{host}/search/suggest.json",
            recorded(f"https://{host}/search/suggest.json", "application/json", body),
        )
    return http


class TestStoreSearchEngineContract(StoreSearcherContract):
    @pytest.fixture
    def http(self) -> StoreHttpFixtures:
        return build_http()

    @pytest.fixture
    def stores(self) -> list[StoreConfig]:
        return [shopify_on(HOST_A, "store-a", "Store A"), shopify_on(HOST_B, "store-b", "Store B")]

    @pytest.fixture
    def searcher(self, http: StoreHttpFixtures) -> StoreSearcher:
        return StoreSearchEngine(make_settings(), clock=FakeClock(), transport=http.transport())

    async def test_the_suite_exercised_real_products_and_an_empty_store(
        self, searcher: StoreSearcher, stores: list[StoreConfig], http: StoreHttpFixtures
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        assert [r.status for r in results] == [StoreStatus.OK, StoreStatus.EMPTY]
        assert len(results[0].products) == 3
        assert all(p.store == "Store A" for p in results[0].products)
        http.assert_no_unexpected_requests()
        assert {request.url.host for request in http.requests} == {HOST_A, HOST_B}


class TestStoreSearchEngineContractWithUnbuiltStrategies(StoreSearcherContract):
    """The suite's own default stores ask for ``store_json``, which is not built. The engine must
    still honour the contract: one result per store, no products, and no request made."""

    @pytest.fixture
    def http(self) -> StoreHttpFixtures:
        return StoreHttpFixtures()

    @pytest.fixture
    def searcher(self, http: StoreHttpFixtures) -> StoreSearcher:
        return StoreSearchEngine(make_settings(), clock=FakeClock(), transport=http.transport())

    async def test_every_store_is_reported_as_an_error_without_a_request(
        self, searcher: StoreSearcher, stores: list[StoreConfig], http: StoreHttpFixtures
    ) -> None:
        results = await searcher.search(make_item_intent(), stores)

        assert [r.status for r in results] == [StoreStatus.ERROR] * len(stores)
        assert http.request_count() == 0
