"""The store search engine (plan 6.5.3 and 6.5.4): isolation, cooldown, cache, robots, variants."""

import asyncio
import logging

import httpx
import pytest
import respx

from tests.factories import make_item_intent, make_settings, make_store_config
from tests.fakes import FakeClock
from tests.fetch.conftest import (
    ALLOW_ALL_ROBOTS,
    OHPOLLY_BLAZER_URL,
    OHPOLLY_ROBOTS_URL,
    club_l_store,
    fixture_text,
    json_response,
    shopify_product,
    shopify_store,
    suggest_body,
    text_response,
)
from vga.interfaces import StoreSearcher
from vga.log import request_context
from vga.models import ItemIntent, StoreConfig, StoreStatus
from vga.settings import Settings
from vga.stores.engine import StoreSearchEngine
from vga.stores.registry import StoreRegistry

SUGGEST = "https://ohpolly.ae/search/suggest.json"
CLUBL_ROBOTS_URL = "https://www.clubllondon.ae/robots.txt"
CLUBL_SUGGEST = "https://www.clubllondon.ae/search/suggest.json"


def item(*keywords: str) -> ItemIntent:
    return make_item_intent(search_keywords=list(keywords) or ["black blazer"])


@pytest.fixture
def engine(settings: Settings, clock: FakeClock, router: respx.MockRouter) -> StoreSearchEngine:
    return StoreSearchEngine(settings, clock=clock)


def mock_oh_polly(
    router: respx.MockRouter,
    body: str | None = None,
    *,
    robots: str = ALLOW_ALL_ROBOTS,
) -> tuple[respx.Route, respx.Route]:
    """Robots and search routes for the Oh Polly store."""
    robots_route = router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(robots))
    search_route = router.get(url__startswith=SUGGEST).mock(
        return_value=json_response(body or fixture_text("ohpolly-suggest-black-blazer.json"))
    )
    return robots_route, search_route


def queries(route: respx.Route) -> list[str]:
    return [call.request.url.params["q"] for call in route.calls]


def test_the_engine_is_a_store_searcher(engine: StoreSearchEngine) -> None:
    assert isinstance(engine, StoreSearcher)


# --------------------------------------------------------------------------------------------
# The happy path, on the saved Oh Polly response
# --------------------------------------------------------------------------------------------


async def test_a_search_returns_validated_products_and_names_the_strategy(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    robots_route, search_route = mock_oh_polly(router)

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert result.from_cache is False
    assert len(result.products) == 4
    assert {p.store for p in result.products} == {"Oh Polly"}
    assert result.dropped == {}
    assert (robots_route.call_count, search_route.call_count) == (1, 1)


async def test_the_search_url_is_the_one_the_qualification_saw_working(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router)

    await engine.search(item("black blazer"), [shopify_store()])

    assert str(search_route.calls.last.request.url) == OHPOLLY_BLAZER_URL


async def test_robots_txt_is_asked_for_before_the_search_page(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)

    await engine.search(item("black blazer"), [shopify_store()])

    assert [call.request.url.path for call in router.calls] == [
        "/robots.txt",
        "/search/suggest.json",
    ]


async def test_the_duration_is_measured_on_the_injected_clock(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await clock.sleep(2.5)
        return json_response(fixture_text("ohpolly-suggest-black-blazer.json"))

    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(side_effect=slow)

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    # the search waits 1 s for its rate-limit slot after robots.txt, then the answer takes 2.5 s
    assert result.duration_ms == pytest.approx(3500)


# --------------------------------------------------------------------------------------------
# Shape of the result list
# --------------------------------------------------------------------------------------------


async def test_no_stores_give_no_results_and_no_requests(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    assert await engine.search(item(), []) == []
    assert router.calls.call_count == 0


async def test_one_result_per_store_in_input_order(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)
    router.get(CLUBL_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=CLUBL_SUGGEST).mock(
        return_value=json_response(fixture_text("clubl-suggest-black-blazer.json"))
    )

    results = await engine.search(item(), [club_l_store(), shopify_store()])

    assert [r.store_id for r in results] == ["club-l-london", "oh-polly"]
    assert {p.store for p in results[0].products} == {"Club L London"}


async def test_stores_are_searched_in_parallel(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await clock.sleep(3)
        return json_response(suggest_body(shopify_product(1)))

    for robots_url, suggest in ((OHPOLLY_ROBOTS_URL, SUGGEST), (CLUBL_ROBOTS_URL, CLUBL_SUGGEST)):
        router.get(robots_url).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
        router.get(url__startswith=suggest).mock(side_effect=slow)
    started = clock.monotonic()

    results = await engine.search(item(), [shopify_store(), club_l_store()])

    assert [r.status for r in results] == [StoreStatus.OK, StoreStatus.OK]
    # robots.txt, a 1 s rate-limit slot, then 3 s of waiting: the stores overlap (sequential: 8 s)
    assert clock.monotonic() - started == pytest.approx(4, abs=0.01)


# --------------------------------------------------------------------------------------------
# Failure isolation
# --------------------------------------------------------------------------------------------


async def test_one_store_raises_one_times_out_one_succeeds_and_all_three_come_back(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    engine = StoreSearchEngine(settings, clock=clock)
    broken = shopify_store(
        id="broken",
        name="Broken",
        search_url_template="https://www.broken.example/s?q={query}",
        allowed_hosts=["www.broken.example", "cdn.shopify.com"],
    )
    slow = shopify_store(
        id="slow",
        name="Slow",
        search_url_template="https://www.slow.example/s?q={query}",
        allowed_hosts=["www.slow.example", "cdn.shopify.com"],
    )
    good = shopify_store()
    router.get("https://www.broken.example/robots.txt").mock(side_effect=RuntimeError("bug"))
    router.get("https://www.slow.example/robots.txt").mock(return_value=text_response(""))

    async def hang(request: httpx.Request) -> httpx.Response:
        await clock.sleep(1000)
        return httpx.Response(200)

    router.get(url__startswith="https://www.slow.example/s").mock(side_effect=hang)
    mock_oh_polly(router)
    started = clock.monotonic()

    results = await engine.search(item(), [broken, slow, good])

    assert [r.store_id for r in results] == ["broken", "slow", "oh-polly"]
    assert [r.status for r in results] == [
        StoreStatus.ERROR,
        StoreStatus.TIMEOUT,
        StoreStatus.OK,
    ]
    assert "RuntimeError" in (results[0].detail or "")
    assert results[2].duration_ms < 2000  # the good store was not held up by the slow one
    # the slow store gave up at its own timeout, not at the end of the world
    assert clock.monotonic() - started == pytest.approx(settings.timeout_s, abs=1.1)


async def test_a_bug_in_one_stores_extractor_does_not_touch_another_store(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)
    router.get(CLUBL_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=CLUBL_SUGGEST).mock(return_value=json_response("not json at all"))

    results = await engine.search(item(), [club_l_store(), shopify_store()])

    assert [r.status for r in results] == [StoreStatus.ERROR, StoreStatus.OK]
    assert "could read the response" in (results[0].detail or "")


async def test_an_unexpected_exception_becomes_an_error_result_and_is_logged(
    engine: StoreSearchEngine, router: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(side_effect=ZeroDivisionError("oops"))

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert result.detail == "unexpected ZeroDivisionError"
    assert any(r.getMessage() == "store search crashed" for r in caplog.records)


async def test_cancelling_a_search_is_not_swallowed(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        return httpx.Response(200)

    router.get(OHPOLLY_ROBOTS_URL).mock(side_effect=hang)
    task = asyncio.create_task(engine.search(item(), [shopify_store()]))
    for _ in range(5):
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_store_that_is_down_is_reported_not_retried(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    route = router.get(url__startswith=SUGGEST).mock(return_value=httpx.Response(503))

    [result] = await engine.search(item("black blazer", "blazer"), [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert "503" in (result.detail or "")
    assert route.call_count == 1  # no retry, and the second variant is not tried either


async def test_a_connection_failure_is_an_error_result(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(side_effect=httpx.ConnectError("refused"))

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ERROR


async def test_a_slow_response_is_a_timeout_result_after_one_attempt(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    attempts: list[str] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.params["q"])
        await clock.sleep(1000)
        return httpx.Response(200)

    router.get(url__startswith=SUGGEST).mock(side_effect=hang)

    [result] = await engine.search(item("black blazer", "blazer"), [shopify_store()])

    assert result.status is StoreStatus.TIMEOUT
    assert result.products == []
    assert attempts == ["black blazer"]  # no retry, and the second variant is not tried


async def test_a_store_timeout_keeps_the_products_found_before_it(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    """A rate limit slower than the store's budget: variant one lands, variant two would not."""
    engine = StoreSearchEngine(settings, clock=clock)
    store = shopify_store(rps=0.1, timeout_s=6)  # one request every 10 s; budget 6 s x 3 = 18 s
    mock_oh_polly(router, suggest_body(shopify_product(1)))

    [result] = await engine.search(item("black blazer", "oversized blazer"), [store])

    assert result.status is StoreStatus.OK
    assert [p.title for p in result.products] == ["Blazer 1"]
    assert "did not finish all its searches in time" in (result.detail or "")


# --------------------------------------------------------------------------------------------
# Which stores are searched
# --------------------------------------------------------------------------------------------


async def test_a_disabled_store_gets_no_request(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)

    [result] = await engine.search(item(), [shopify_store(enabled=False)])

    assert result.status is StoreStatus.ERROR
    assert "not enabled" in (result.detail or "")
    assert router.calls.call_count == 0


async def test_a_store_without_enabled_true_gets_no_request(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    data = shopify_store().model_dump(mode="json")
    del data["enabled"]  # a store file that never says enabled: true
    default_store = StoreConfig.model_validate(data)
    assert default_store.enabled is False

    [result] = await engine.search(item(), [default_store])

    assert result.status is StoreStatus.ERROR
    assert router.calls.call_count == 0


async def test_a_store_in_another_country_gets_no_request(
    router: respx.MockRouter, clock: FakeClock
) -> None:
    engine = StoreSearchEngine(make_settings(country="SA"), clock=clock)
    mock_oh_polly(router)

    [result] = await engine.search(item(), [shopify_store(country="AE")])

    assert result.status is StoreStatus.ERROR
    assert "AE" in (result.detail or "")
    assert router.calls.call_count == 0


async def test_a_store_in_a_listed_extra_country_is_searched(
    router: respx.MockRouter, clock: FakeClock
) -> None:
    engine = StoreSearchEngine(
        make_settings(country="AE", extra_store_countries=["KW"]), clock=clock
    )
    mock_oh_polly(router)

    [result] = await engine.search(item(), [shopify_store(country="KW")])

    assert result.status is StoreStatus.OK
    assert router.calls.call_count > 0


async def test_a_store_in_a_country_that_is_not_listed_still_gets_no_request(
    router: respx.MockRouter, clock: FakeClock
) -> None:
    engine = StoreSearchEngine(
        make_settings(country="AE", extra_store_countries=["KW"]), clock=clock
    )
    mock_oh_polly(router)

    [result] = await engine.search(item(), [shopify_store(country="SA")])

    assert result.status is StoreStatus.ERROR
    assert "SA" in (result.detail or "")
    assert router.calls.call_count == 0


async def test_a_store_whose_strategies_are_not_built_gets_no_request(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    store = make_store_config()  # the shared default asks for store_json, which is not built

    [result] = await engine.search(item(), [store])

    assert result.status is StoreStatus.ERROR
    assert "store_json" in (result.detail or "")
    assert router.calls.call_count == 0


async def test_a_skipped_store_does_not_disturb_the_others(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)

    results = await engine.search(
        item(), [shopify_store(id="off", name="Off", enabled=False), shopify_store()]
    )

    assert [r.status for r in results] == [StoreStatus.ERROR, StoreStatus.OK]


# --------------------------------------------------------------------------------------------
# Keyword variants
# --------------------------------------------------------------------------------------------


async def test_every_variant_is_searched_and_the_products_merged(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(
        side_effect=[
            json_response(suggest_body(shopify_product(1), shopify_product(2))),
            json_response(suggest_body(shopify_product(2), shopify_product(3))),
            json_response(suggest_body(shopify_product(4))),
        ]
    )

    [result] = await engine.search(item("a one", "b two", "c three"), [shopify_store()])

    assert queries(search_route) == ["a one", "b two", "c three"]
    assert [p.title for p in result.products] == ["Blazer 1", "Blazer 2", "Blazer 3", "Blazer 4"]


async def test_variants_overlapping_each_other_are_deduplicated(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router, suggest_body(shopify_product(1), shopify_product(2)))

    [result] = await engine.search(item("a one", "b two"), [shopify_store()])

    assert [p.title for p in result.products] == ["Blazer 1", "Blazer 2"]


async def test_max_variants_limits_the_requests_to_a_store(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router)

    await engine.search(item("a one", "b two", "c three"), [shopify_store(max_variants=1)])
    assert queries(search_route) == ["a one"]


async def test_max_variants_two_of_three(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router)

    await engine.search(item("a one", "b two", "c three"), [shopify_store(max_variants=2)])

    assert queries(search_route) == ["a one", "b two"]


async def test_variants_that_differ_only_in_case_or_spacing_are_searched_once(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router)

    await engine.search(
        item("black blazer", "Black  Blazer", "oversized blazer"), [shopify_store()]
    )

    assert queries(search_route) == ["black blazer", "oversized blazer"]


async def test_the_variant_requests_to_one_store_are_spaced_by_its_rate(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock
) -> None:
    mock_oh_polly(router)
    started = clock.monotonic()

    await engine.search(item("a one", "b two", "c three"), [shopify_store()])

    # robots.txt, then three searches, on one host at 1 request per second
    assert clock.monotonic() - started == pytest.approx(3.0, abs=0.01)


async def test_a_failing_variant_stops_the_rest(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(
        side_effect=[httpx.ConnectError("down"), json_response(suggest_body(shopify_product(1)))]
    )

    [result] = await engine.search(item("a one", "b two"), [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert search_route.call_count == 1


async def test_an_empty_variant_does_not_stop_the_next_one(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(
        side_effect=[
            json_response(suggest_body()),
            json_response(suggest_body(shopify_product(1))),
        ]
    )

    [result] = await engine.search(item("a one", "b two"), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert len(result.products) == 1


# --------------------------------------------------------------------------------------------
# What the extraction found
# --------------------------------------------------------------------------------------------


async def test_no_products_is_an_empty_result(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router, suggest_body())

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.EMPTY
    assert result.products == []
    assert result.strategy is None


async def test_records_that_are_all_dropped_make_an_error_with_the_reasons(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(
        router, suggest_body(shopify_product(1, price="free"), shopify_product(2, title=""))
    )

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert result.dropped == {"unknown_price_format": 1, "missing_title": 1}
    assert "all 2 records were dropped" in (result.detail or "")


async def test_dropped_records_are_counted_on_an_ok_result(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(
        router,
        suggest_body(
            shopify_product(1),
            shopify_product(2, price="free"),
            shopify_product(3, url="https://evil.example/p/3"),
        ),
    )

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert [p.title for p in result.products] == ["Blazer 1"]
    assert result.dropped == {"unknown_price_format": 1, "product_url_not_allowed": 1}


async def test_one_title_under_many_handles_is_collapsed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    repeats = [
        shopify_product(
            n, title="Linen Shirt", price="89.00", handle=f"linen-{n}", url=f"/products/linen-{n}"
        )
        for n in range(1, 8)
    ]
    mock_oh_polly(router, suggest_body(*repeats, shopify_product(9)))

    [result] = await engine.search(item(), [shopify_store()])

    assert [p.title for p in result.products] == ["Linen Shirt", "Blazer 9"]
    assert result.dropped == {"duplicate_title_price": 6}


async def test_a_non_200_search_answer_is_an_error(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(return_value=httpx.Response(404))

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert "404" in (result.detail or "")


async def test_an_empty_keyword_is_an_error_and_no_request_is_made(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)
    blank = ItemIntent.model_construct(
        **{**make_item_intent().model_dump(), "search_keywords": ["  "]}
    )

    [result] = await engine.search(blank, [shopify_store()])

    assert result.status is StoreStatus.ERROR
    assert "empty" in (result.detail or "")
    assert router.calls.call_count == 0


# --------------------------------------------------------------------------------------------
# 6.1.4 Block detection and cooldown, end to end
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [403, 429])
async def test_a_blocked_search_makes_exactly_one_search_request(
    engine: StoreSearchEngine, router: respx.MockRouter, status: int
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(return_value=httpx.Response(status))

    [result] = await engine.search(item("a one", "b two", "c three"), [shopify_store()])

    assert result.status is StoreStatus.BLOCKED
    assert search_route.call_count == 1  # and the other two variants were not tried


async def test_the_next_query_within_the_cooldown_makes_zero_requests_and_reports_cooldown(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock, settings: Settings
) -> None:
    robots_route = router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(return_value=httpx.Response(403))
    await engine.search(item("black blazer"), [shopify_store()])
    requests_before = router.calls.call_count

    clock.advance(settings.store_cooldown_s - 5)
    [again] = await engine.search(item("a different query"), [shopify_store()])

    assert again.status is StoreStatus.COOLDOWN
    assert router.calls.call_count == requests_before
    assert (robots_route.call_count, search_route.call_count) == (1, 1)

    clock.advance(10)
    search_route.mock(return_value=json_response(suggest_body(shopify_product(1))))
    [later] = await engine.search(item("a different query"), [shopify_store()])
    assert later.status is StoreStatus.OK


async def test_a_blocked_robots_request_blocks_the_store(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    robots_route = router.get(OHPOLLY_ROBOTS_URL).mock(return_value=httpx.Response(403))
    search_route = router.get(url__startswith=SUGGEST)

    [first] = await engine.search(item("a one"), [shopify_store()])
    [second] = await engine.search(item("b two"), [shopify_store()])

    assert (first.status, second.status) == (StoreStatus.BLOCKED, StoreStatus.COOLDOWN)
    assert robots_route.call_count == 1
    assert search_route.call_count == 0


async def test_a_challenge_page_in_place_of_the_search_answer_blocks_the_store(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(
        return_value=text_response(
            "<html><title>Just a moment...</title></html>", content_type="text/html"
        )
    )

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.BLOCKED
    assert "challenge" in (result.detail or "")


async def test_a_blocked_store_does_not_stop_another_store_being_searched(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=httpx.Response(403))
    router.get(CLUBL_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=CLUBL_SUGGEST).mock(
        return_value=json_response(fixture_text("clubl-suggest-shoes.json"))
    )

    results = await engine.search(item("shoes"), [shopify_store(), club_l_store()])

    assert [r.status for r in results] == [StoreStatus.BLOCKED, StoreStatus.OK]


async def test_concurrent_items_hitting_a_blocked_store_cause_one_block_not_four(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    """An outfit photo searches up to four garments at once; a block must still cost one request."""
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(return_value=httpx.Response(403))

    outcomes = await asyncio.gather(
        *(engine.search(item(f"query {n}"), [shopify_store()]) for n in range(4))
    )

    assert search_route.call_count == 1
    statuses = sorted(result.status.value for [result] in outcomes)
    assert statuses == ["blocked", "cooldown", "cooldown", "cooldown"]


# --------------------------------------------------------------------------------------------
# 6.2.1 robots.txt end to end
# --------------------------------------------------------------------------------------------


async def test_a_robots_denied_search_url_is_never_fetched(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    robots = "User-agent: *\nDisallow: /search\n"
    _, search_route = mock_oh_polly(router, robots=robots)

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert result.products == []
    assert search_route.call_count == 0


async def test_noons_wildcard_rule_stops_a_noon_style_search(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    noon = shopify_store(
        id="noon",
        name="Noon",
        search_url_template="https://www.noon.com/uae-en/search/?q={query}",
        allowed_hosts=["www.noon.com"],
    )
    router.get("https://www.noon.com/robots.txt").mock(
        return_value=text_response(fixture_text("robots.noon.txt"))
    )
    search_route = router.get(url__startswith="https://www.noon.com/uae-en/")

    [result] = await engine.search(item(), [noon])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert search_route.call_count == 0


async def test_namshis_malformed_rule_stops_a_namshi_style_search(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    namshi = shopify_store(
        id="namshi",
        name="Namshi",
        search_url_template="https://www.namshi.com/uae-en/search?q={query}",
        allowed_hosts=["www.namshi.com"],
    )
    router.get("https://www.namshi.com/robots.txt").mock(
        return_value=text_response(fixture_text("robots.namshi.txt"))
    )
    search_route = router.get(url__startswith="https://www.namshi.com/uae-en/")

    [result] = await engine.search(item(), [namshi])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert search_route.call_count == 0


@pytest.mark.parametrize("status", [500, 503])
async def test_an_unreachable_robots_file_means_the_store_is_not_searched(
    engine: StoreSearchEngine, router: respx.MockRouter, status: int
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=httpx.Response(status))
    search_route = router.get(url__startswith=SUGGEST)

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert search_route.call_count == 0


async def test_no_robots_file_means_the_store_is_searched(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=httpx.Response(404))
    router.get(url__startswith=SUGGEST).mock(
        return_value=json_response(suggest_body(shopify_product(1)))
    )

    [result] = await engine.search(item(), [shopify_store()])

    assert result.status is StoreStatus.OK


async def test_robots_txt_is_fetched_once_for_many_searches(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    robots_route, _ = mock_oh_polly(router, suggest_body(shopify_product(1)))

    for query in ("a one", "b two", "c three"):
        await engine.search(item(query), [shopify_store()])

    assert robots_route.call_count == 1


# --------------------------------------------------------------------------------------------
# robots.txt for a redirect target (BRD Rule 2): the page we are sent to is asked about too
# --------------------------------------------------------------------------------------------

WWW_ROBOTS_URL = "https://www.ohpolly.ae/robots.txt"
WWW_SUGGEST = "https://www.ohpolly.ae/search/suggest.json"


def mock_apex_redirecting_to_www(
    router: respx.MockRouter, *, www_robots: httpx.Response
) -> tuple[respx.Route, respx.Route, respx.Route]:
    """Oh Polly's apex host sends every search to ``www.``. Returns the apex search route, the
    ``www.`` robots.txt route and the ``www.`` search route."""
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))

    def to_www(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": str(request.url).replace("//ohpolly.ae", "//www.ohpolly.ae")}
        )

    apex = router.get(url__startswith=SUGGEST).mock(side_effect=to_www)
    www_robots_route = router.get(WWW_ROBOTS_URL).mock(return_value=www_robots)
    www_search = router.get(url__startswith=WWW_SUGGEST).mock(
        return_value=json_response(suggest_body(shopify_product(1)))
    )
    return apex, www_robots_route, www_search


async def test_a_redirect_to_another_host_is_followed_only_after_that_hosts_robots_txt_allows_it(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_apex_redirecting_to_www(router, www_robots=text_response(ALLOW_ALL_ROBOTS))

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert [(call.request.url.host, call.request.url.path) for call in router.calls] == [
        ("ohpolly.ae", "/robots.txt"),
        ("ohpolly.ae", "/search/suggest.json"),
        ("www.ohpolly.ae", "/robots.txt"),
        ("www.ohpolly.ae", "/search/suggest.json"),
    ]


async def test_a_redirect_to_a_host_whose_robots_txt_disallows_the_search_is_not_followed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    apex, www_robots, www_search = mock_apex_redirecting_to_www(
        router, www_robots=text_response("User-agent: *\nDisallow: /search\n")
    )

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert result.products == []
    assert (apex.call_count, www_robots.call_count, www_search.call_count) == (1, 1, 0)


@pytest.mark.parametrize("status", [500, 503])
async def test_a_redirect_to_a_host_whose_robots_txt_cannot_be_read_is_not_followed(
    engine: StoreSearchEngine, router: respx.MockRouter, status: int
) -> None:
    _, _, www_search = mock_apex_redirecting_to_www(router, www_robots=httpx.Response(status))

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert www_search.call_count == 0


async def test_a_redirect_to_a_host_with_no_robots_txt_is_followed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, _, www_search = mock_apex_redirecting_to_www(router, www_robots=httpx.Response(404))

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert www_search.call_count == 1


async def test_a_block_while_reading_the_redirect_hosts_robots_txt_puts_the_store_in_cooldown(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    apex, www_robots, www_search = mock_apex_redirecting_to_www(
        router, www_robots=httpx.Response(403)
    )

    [first] = await engine.search(item("a one"), [shopify_store()])
    [second] = await engine.search(item("b two"), [shopify_store()])

    assert (first.status, second.status) == (StoreStatus.BLOCKED, StoreStatus.COOLDOWN)
    assert (apex.call_count, www_robots.call_count, www_search.call_count) == (1, 1, 0)


async def test_the_redirect_hosts_robots_txt_is_fetched_once_for_all_the_variants(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    apex, www_robots, www_search = mock_apex_redirecting_to_www(
        router, www_robots=text_response(ALLOW_ALL_ROBOTS)
    )

    [result] = await engine.search(item("black blazer", "oversized blazer"), [shopify_store()])

    assert result.status is StoreStatus.OK
    assert (apex.call_count, www_robots.call_count, www_search.call_count) == (2, 1, 2)


async def test_a_redirect_to_a_path_the_same_hosts_robots_txt_disallows_is_not_followed(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(
        return_value=text_response("User-agent: *\nDisallow: /collections\n")
    )
    router.get(url__startswith=SUGGEST).mock(
        return_value=httpx.Response(302, headers={"location": "/collections/all"})
    )
    landing = router.get("https://ohpolly.ae/collections/all").mock(
        return_value=json_response(suggest_body(shopify_product(1)))
    )

    [result] = await engine.search(item("black blazer"), [shopify_store()])

    assert result.status is StoreStatus.ROBOTS_DENIED
    assert landing.call_count == 0


# --------------------------------------------------------------------------------------------
# 6.5.3 Result cache
# --------------------------------------------------------------------------------------------


async def test_a_second_identical_search_makes_zero_requests_and_sets_from_cache(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)
    [first] = await engine.search(item("black blazer"), [shopify_store()])
    requests = router.calls.call_count

    [second] = await engine.search(item("black blazer"), [shopify_store()])

    assert router.calls.call_count == requests
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.products == first.products
    assert second.status is StoreStatus.OK
    assert second.strategy == "shopify"


async def test_the_cache_expires_after_the_ttl_on_the_fake_clock(
    engine: StoreSearchEngine, router: respx.MockRouter, clock: FakeClock, settings: Settings
) -> None:
    _, search_route = mock_oh_polly(router)
    await engine.search(item("black blazer"), [shopify_store()])

    clock.advance(settings.store_cache_ttl_s - 1)
    [still_cached] = await engine.search(item("black blazer"), [shopify_store()])
    assert still_cached.from_cache is True
    assert search_route.call_count == 1

    clock.advance(2)
    [refreshed] = await engine.search(item("black blazer"), [shopify_store()])
    assert refreshed.from_cache is False
    assert search_route.call_count == 2


async def test_only_the_variants_not_seen_before_are_requested(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router, suggest_body(shopify_product(1)))
    await engine.search(item("a one", "b two"), [shopify_store()])

    [result] = await engine.search(item("a one", "c three"), [shopify_store()])

    assert queries(search_route) == ["a one", "b two", "c three"]
    assert result.from_cache is False  # one variant was fresh, so the result is not wholly cached


async def test_the_cache_is_per_store(engine: StoreSearchEngine, router: respx.MockRouter) -> None:
    mock_oh_polly(router)
    club_robots = router.get(CLUBL_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    club_search = router.get(url__startswith=CLUBL_SUGGEST).mock(
        return_value=json_response(fixture_text("clubl-suggest-black-blazer.json"))
    )
    await engine.search(item("black blazer"), [shopify_store()])

    [club] = await engine.search(item("black blazer"), [club_l_store()])

    assert club.from_cache is False
    assert (club_robots.call_count, club_search.call_count) == (1, 1)


async def test_an_empty_result_is_cached_too(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    _, search_route = mock_oh_polly(router, suggest_body())
    await engine.search(item("xyzzy"), [shopify_store()])

    [second] = await engine.search(item("xyzzy"), [shopify_store()])

    assert second.status is StoreStatus.EMPTY
    assert second.from_cache is True
    assert search_route.call_count == 1


async def test_a_failure_is_not_cached(engine: StoreSearchEngine, router: respx.MockRouter) -> None:
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    search_route = router.get(url__startswith=SUGGEST).mock(
        side_effect=[httpx.ConnectError("down"), json_response(suggest_body(shopify_product(1)))]
    )
    [first] = await engine.search(item("black blazer"), [shopify_store()])

    [second] = await engine.search(item("black blazer"), [shopify_store()])

    assert (first.status, second.status) == (StoreStatus.ERROR, StoreStatus.OK)
    assert search_route.call_count == 2


async def test_a_zero_ttl_turns_caching_off(router: respx.MockRouter, clock: FakeClock) -> None:
    engine = StoreSearchEngine(make_settings(store_cache_ttl_s=0), clock=clock)
    _, search_route = mock_oh_polly(router)

    await engine.search(item("black blazer"), [shopify_store()])
    await engine.search(item("black blazer"), [shopify_store()])

    assert search_route.call_count == 2


async def test_a_cache_hit_is_logged(
    engine: StoreSearchEngine, router: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    mock_oh_polly(router)
    await engine.search(item("black blazer"), [shopify_store()])
    caplog.clear()
    caplog.set_level(logging.INFO)

    await engine.search(item("black blazer"), [shopify_store()])

    assert any(r.getMessage() == "cache hit; no request made" for r in caplog.records)


# --------------------------------------------------------------------------------------------
# Logging: nothing fails silently, and every line carries the request id
# --------------------------------------------------------------------------------------------


async def test_skips_blocks_and_drops_are_logged_with_the_request_id(
    engine: StoreSearchEngine, router: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    router.get(OHPOLLY_ROBOTS_URL).mock(return_value=text_response(ALLOW_ALL_ROBOTS))
    router.get(url__startswith=SUGGEST).mock(
        return_value=json_response(
            suggest_body(shopify_product(1), shopify_product(2, price="free"))
        )
    )
    router.get(CLUBL_ROBOTS_URL).mock(return_value=httpx.Response(403))

    with request_context("req-123"):
        await engine.search(
            item("black blazer"),
            [shopify_store(), club_l_store(), shopify_store(id="off", name="Off", enabled=False)],
        )
        await engine.search(item("another"), [club_l_store()])

    messages = {r.getMessage() for r in caplog.records}
    assert "record dropped" in messages
    assert "store blocked the request; no retry, cooldown started" in messages
    assert "store skipped; no request made" in messages
    assert "store in cooldown; no request made" in messages
    store_lines = [r for r in caplog.records if r.name.startswith("vga.")]
    assert store_lines
    assert {getattr(r, "request_id", None) for r in store_lines} == {"req-123"}


async def test_a_robots_denial_is_logged(
    engine: StoreSearchEngine, router: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    mock_oh_polly(router, robots="User-agent: *\nDisallow: /search\n")

    await engine.search(item(), [shopify_store()])

    assert any(r.getMessage() == "robots.txt disallows the URL; skipped" for r in caplog.records)


# --------------------------------------------------------------------------------------------
# Registry and lifetime
# --------------------------------------------------------------------------------------------


async def test_stores_passed_to_search_are_remembered_by_the_registry(
    engine: StoreSearchEngine, router: respx.MockRouter
) -> None:
    mock_oh_polly(router)

    await engine.search(item(), [shopify_store()])

    assert engine.registry.by_display_name("Oh Polly") is not None


async def test_the_engine_can_be_built_from_a_registry_and_closed(
    settings: Settings, clock: FakeClock, router: respx.MockRouter
) -> None:
    registry = StoreRegistry([shopify_store()])
    engine = StoreSearchEngine(settings, registry, clock=clock)
    mock_oh_polly(router)

    results = await engine.search(item(), registry.active(settings))
    await engine.aclose()

    assert [r.status for r in results] == [StoreStatus.OK]


def test_two_separate_event_loops_can_use_one_engine(
    settings: Settings, router: respx.MockRouter, clock: FakeClock
) -> None:
    """A UI that calls ``asyncio.run`` per request keeps one engine for the whole process."""
    mock_oh_polly(router, suggest_body(shopify_product(1)))
    engine = StoreSearchEngine(settings, clock=clock)

    first = asyncio.run(engine.search(item("a one"), [shopify_store()]))
    second = asyncio.run(engine.search(item("b two"), [shopify_store()]))

    assert [first[0].status, second[0].status] == [StoreStatus.OK, StoreStatus.OK]
