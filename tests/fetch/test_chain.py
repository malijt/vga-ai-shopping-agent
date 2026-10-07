"""Strategy interface, registry and chain (plan 6.4.1)."""

from typing import Any

import pytest

from tests.factories import make_store_config
from tests.fetch.conftest import HOST, shopify_product, shopify_store, suggest_body
from vga.models import StoreConfig, StrategyConfig
from vga.stores.extractors import (
    ExtractionChain,
    ExtractionError,
    Extractor,
    ExtractorRegistry,
    ShopifyExtractor,
    default_registry,
)
from vga.stores.normalise import RawRecord

BASE = f"https://{HOST}/search?q=x"


class StubExtractor:
    """A strategy that returns canned records, or raises."""

    def __init__(
        self, name: str, records: list[RawRecord] | None = None, error: Exception | None = None
    ) -> None:
        self.name = name
        self._records = records or []
        self._error = error
        self.calls = 0

    def validate(self, strategy: StrategyConfig) -> None:
        if strategy.options.get("bad"):
            msg = "options.bad is not allowed"
            raise ValueError(msg)

    def extract(self, body: str, store: StoreConfig, strategy: StrategyConfig) -> list[RawRecord]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._records


def good_record(index: int = 1) -> dict[str, Any]:
    return {
        "title": f"Blazer {index}",
        "price": f"{100 + index}.00",
        "image_url": f"https://cdn.demo-store.example/{index}.jpg",
        "product_url": f"/products/{index}",
    }


def store_with(*names: str) -> StoreConfig:
    return make_store_config(
        extraction={"strategies": [{"name": name} for name in names]},
    )


def chain_of(*extractors: Extractor) -> ExtractionChain:
    return ExtractionChain(ExtractorRegistry(list(extractors)))


def test_the_first_strategy_that_yields_products_wins_and_is_named() -> None:
    first = StubExtractor("first", [good_record(1)])
    second = StubExtractor("second", [good_record(2)])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.strategy == "first"
    assert [p.title for p in outcome.products] == ["Blazer 1"]
    assert second.calls == 0  # the chain stops at the first success


def test_an_empty_first_strategy_hands_over_to_the_second() -> None:
    first = StubExtractor("first", [])
    second = StubExtractor("second", [good_record(2)])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert (first.calls, second.calls) == (1, 1)
    assert outcome.strategy == "second"
    assert [p.title for p in outcome.products] == ["Blazer 2"]


def test_a_strategy_whose_records_are_all_invalid_hands_over_to_the_next() -> None:
    first = StubExtractor("first", [{"title": "No price", "price": None}])
    second = StubExtractor("second", [good_record(2)])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.strategy == "second"
    assert outcome.dropped == {}  # the winner's own drops only


def test_a_strategy_that_cannot_read_the_body_hands_over_and_the_error_is_kept() -> None:
    first = StubExtractor("first", error=ExtractionError("not JSON"))
    second = StubExtractor("second", [good_record(2)])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.strategy == "second"
    assert outcome.errors == ["first: not JSON"]
    assert outcome.ran_cleanly == 1


def test_a_crashing_strategy_does_not_break_the_search() -> None:
    first = StubExtractor("first", error=RuntimeError("bug"))
    second = StubExtractor("second", [good_record(2)])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.strategy == "second"
    assert outcome.errors == ["first: crashed: RuntimeError"]


def test_an_unknown_strategy_name_is_skipped_and_reported() -> None:
    known = StubExtractor("known", [good_record(1)])

    outcome = chain_of(known).run("", store_with("store_json", "known"), BASE)

    assert outcome.strategy == "known"
    assert outcome.errors == ["store_json: unknown extraction strategy"]


def test_when_no_strategy_yields_anything_the_outcome_says_why() -> None:
    first = StubExtractor("first", error=ExtractionError("not JSON"))
    second = StubExtractor("second", [])

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.strategy is None
    assert outcome.products == []
    assert outcome.examined == 0
    assert outcome.ran_cleanly == 1
    assert outcome.errors == ["first: not JSON"]


def test_drops_from_every_strategy_are_summed_when_none_wins() -> None:
    bad = [{"title": "x", "price": None}]
    first = StubExtractor("first", bad)
    second = StubExtractor("second", bad + bad)

    outcome = chain_of(first, second).run("", store_with("first", "second"), BASE)

    assert outcome.products == []
    assert outcome.dropped == {"missing_price": 3}
    assert outcome.examined == 3


def test_the_strategy_receives_its_own_settings() -> None:
    seen: list[StrategyConfig] = []

    class Spy(StubExtractor):
        def extract(
            self, body: str, store: StoreConfig, strategy: StrategyConfig
        ) -> list[RawRecord]:
            seen.append(strategy)
            return [good_record(1)]

    store = make_store_config(
        extraction={"strategies": [{"name": "spy", "options": {"depth": 3}}]},
    )

    chain_of(Spy("spy")).run("", store, BASE)

    assert seen[0].options == {"depth": 3}


# --------------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------------


def test_the_default_registry_holds_only_the_strategies_that_are_built() -> None:
    registry = default_registry()

    assert registry.names == ["shopify"]
    assert isinstance(registry.get("shopify"), ShopifyExtractor)
    assert registry.get("css") is None
    assert registry.get("store_json") is None


def test_a_new_strategy_is_added_by_registering_a_class() -> None:
    registry = default_registry()

    registry.register(StubExtractor("custom"))

    assert registry.names == ["custom", "shopify"]


def test_registering_a_name_twice_is_an_error() -> None:
    registry = default_registry()

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ShopifyExtractor())


def test_shopify_satisfies_the_extractor_protocol() -> None:
    assert isinstance(ShopifyExtractor(), Extractor)


def test_check_rejects_an_unknown_name_and_lists_the_known_ones() -> None:
    with pytest.raises(ValueError, match=r"unknown extraction strategy 'css'.*\['shopify'\]"):
        default_registry().check(StrategyConfig(name="css"))


def test_check_passes_the_strategys_own_validation_through() -> None:
    registry = ExtractorRegistry([StubExtractor("custom")])

    with pytest.raises(ValueError, match=r"options\.bad"):
        registry.check(StrategyConfig(name="custom", options={"bad": True}))


def test_the_chain_works_with_the_real_shopify_strategy_in_second_place() -> None:
    store = shopify_store(
        extraction={"strategies": [{"name": "css"}, {"name": "shopify"}]},
    )

    outcome = ExtractionChain(default_registry()).run(
        suggest_body(shopify_product(1)), store, "https://ohpolly.ae/search/suggest.json"
    )

    assert outcome.strategy == "shopify"
    assert outcome.errors == ["css: unknown extraction strategy"]
