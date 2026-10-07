"""Plan 14.1.4, price words and the kill switch (BRD Rule 7 and "safe by default").

*Price words.* "Cheap", "budget", "under 400 AED" and their Arabic forms are filters, never search
terms: a store search for "cheap black jacket" returns whatever the store calls cheap, not what the
shopper wants. The model is asked to leave them out, and the code removes them again because a
model cannot be trusted with it. These tests run the REAL ``OpenAIUnderstander`` against a fake
OpenAI that does what a careless model does (keeps the price word, or translates رخيص to "cheap"),
or that is down altogether (the fallback searches the shopper's own words), and then read every
URL that left for a store.

*Kill switch.* A store is used only when its file says ``enabled: true`` (and it is in the
configured country and selected in the settings). Any other store gets no request, not even for
its robots.txt.
"""

import re
from collections.abc import AsyncIterator, Callable
from urllib.parse import quote, unquote_plus

import pytest

from tests.factories import make_item_intent, make_search_request, make_settings
from tests.fakes import FakeClock
from tests.guards.scraping.support import GuardPipelines, GuardWorld, understanding
from tests.pipeline.builders import rerun
from tests.pipeline.world import store_for
from tests.understand.fake_openai import FakeOpenAI, answer, http_error
from tests.understand.readings import make_reading, make_reading_budget, make_reading_item
from vga.models import (
    Category,
    ChipEdits,
    ItemEdit,
    RunOverrides,
    StoreConfig,
    StoreStatus,
)
from vga.pipeline import messages
from vga.settings import Settings
from vga.understand import OpenAIUnderstander
from vga.understand.budget import CallBudget

MODEL = "gpt-5-mini-2025-08-07"

ENGLISH_PRICE_WORDS = frozenset(
    [
        "cheap",
        "cheaper",
        "cheapest",
        "budget",
        "affordable",
        "inexpensive",
        "economical",
        "bargain",
        "discount",
        "discounted",
        "sale",
        "deal",
        "deals",
        "clearance",
        "expensive",
        "pricey",
        "luxury",
        "premium",
        "price",
        "prices",
        "priced",
        "under",
        "below",
        "aed",
        "dirham",
        "dirhams",
        "400",
    ]
)
ARABIC_PRICE_WORDS = (
    "رخيص",
    "ارخص",
    "أرخص",
    "ميزاني",
    "تخفيض",
    "خصم",
    "عروض",
    "غالي",
    "فاخر",
    "سعر",
)
"""Written out here, apart from the product's own list, so the guard does not agree with a gap in
it by construction. Arabic words take prefixes ("وارخص"), so they are looked for inside tokens."""

WORD = re.compile(r"[^\W\d_]+|\d+")


def price_words_in(url: str) -> list[str]:
    """The price words found in a request URL, whatever its encoding."""
    tokens = [token.lower() for token in WORD.findall(unquote_plus(url))]
    found = [token for token in tokens if token in ENGLISH_PRICE_WORDS]
    found += [word for word in ARABIC_PRICE_WORDS if any(word in token for token in tokens)]
    return found


def store_urls(world: GuardWorld) -> list[str]:
    """Every URL that was sent to a store, robots.txt included."""
    return [str(request.url) for request in world.every_request()]


def search_urls(world: GuardWorld) -> list[str]:
    return [url for url in store_urls(world) if "/search/suggest.json" in url]


# --------------------------------------------------------------------------------------------
# A real understander against a fake OpenAI
# --------------------------------------------------------------------------------------------


@pytest.fixture
def openai_settings(tmp_path) -> Settings:
    return make_settings(openai_model=MODEL, log_dir=str(tmp_path / "logs"))


@pytest.fixture
async def model(
    clock: FakeClock, openai_settings: Settings
) -> AsyncIterator[Callable[..., OpenAIUnderstander]]:
    """``model(*steps)``: the real ``OpenAIUnderstander`` talking to a scripted fake OpenAI."""
    fakes: list[FakeOpenAI] = []

    def make(*steps) -> OpenAIUnderstander:
        fake = FakeOpenAI(*steps)
        fakes.append(fake)
        return OpenAIUnderstander(
            openai_settings, fake.client(), clock=clock, budget=CallBudget(), jitter=lambda: 0.5
        )

    yield make
    for fake in fakes:
        await fake.aclose()


def jacket_reading(*keywords: str, budget: bool = False):
    return make_reading(
        items=[
            make_reading_item(
                category=Category.OUTERWEAR,
                colour="black",
                style="jacket",
                search_keywords=list(keywords),
            )
        ],
        budget=make_reading_budget(max_price=400.0, currency="AED") if budget else None,
    )


@pytest.fixture
def stores(world: GuardWorld) -> list[StoreConfig]:
    """Two ordinary stores that answer a search for a jacket."""
    opened = [store_for("alpha"), store_for("beta")]
    for store in opened:
        world.add(store)
    return opened


# --------------------------------------------------------------------------------------------
# Price words never reach a store URL
# --------------------------------------------------------------------------------------------


async def test_cheap_black_jacket_reaches_the_stores_without_the_word_cheap(
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
    model: Callable[..., OpenAIUnderstander],
) -> None:
    careless = answer(jacket_reading("cheap black jacket", "cheapest jacket", "jacket"))
    pipeline = build(understander=model(careless))

    await pipeline.run(make_search_request(text="cheap black jacket"), openai_settings)

    sent = search_urls(world)
    assert sent
    assert all("jacket" in unquote_plus(url) for url in sent)  # a real search, not an empty one
    assert [(url, price_words_in(url)) for url in store_urls(world) if price_words_in(url)] == []


async def test_a_price_phrase_and_a_budget_stay_out_of_the_store_urls(
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
    model: Callable[..., OpenAIUnderstander],
) -> None:
    careless = answer(
        jacket_reading("black jacket under 400 AED", "affordable jacket 400 dirhams", budget=True)
    )
    pipeline = build(understander=model(careless))

    response = await pipeline.run(
        make_search_request(text="black jacket under 400 AED, nothing expensive"), openai_settings
    )

    assert response.understood.budget is not None  # the budget is kept, as a filter
    assert response.understood.budget.max_price == 400
    assert search_urls(world)
    assert [url for url in store_urls(world) if price_words_in(url)] == []


async def test_an_arabic_request_for_a_cheap_jacket_reaches_the_stores_without_a_price_word(
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
    model: Callable[..., OpenAIUnderstander],
) -> None:
    # The model translates رخيص ("cheap") into the English "cheap" and keeps it in the keyword.
    careless = answer(jacket_reading("cheap black jacket", "inexpensive black jacket", "jacket"))
    pipeline = build(understander=model(careless))

    await pipeline.run(make_search_request(text="جاكيت أسود رخيص"), openai_settings)

    assert search_urls(world)
    assert [url for url in store_urls(world) if price_words_in(url)] == []


async def test_an_arabic_price_word_the_model_leaves_in_a_keyword_does_not_reach_the_stores(
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
    model: Callable[..., OpenAIUnderstander],
) -> None:
    careless = answer(jacket_reading("جاكيت أسود رخيص", "أرخص جاكيت", "black jacket"))
    pipeline = build(understander=model(careless))

    await pipeline.run(make_search_request(text="جاكيت أسود رخيص"), openai_settings)

    assert search_urls(world)
    assert [url for url in store_urls(world) if price_words_in(url)] == []


@pytest.mark.parametrize(
    "text",
    [
        "cheap black jacket under 400 AED",
        "affordable black jacket, budget 400 dirhams",
        "جاكيت أسود رخيص بأقل من 400 درهم",
    ],
    ids=["english", "english_with_budget", "arabic_with_budget"],
)
async def test_when_the_model_is_down_the_shoppers_own_words_are_searched_without_price_words(
    text: str,
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
    model: Callable[..., OpenAIUnderstander],
) -> None:
    pipeline = build(understander=model(http_error(500), http_error(500)))

    response = await pipeline.run(make_search_request(text=text), openai_settings)

    assert response.understood.model == "fallback"
    assert search_urls(world)  # the search went on, with the words as typed minus the price
    assert [url for url in store_urls(world) if price_words_in(url)] == []


async def test_a_price_word_typed_into_a_colour_chip_does_not_reach_the_stores(
    world: GuardWorld,
    stores: list[StoreConfig],
    build: GuardPipelines,
    openai_settings: Settings,
) -> None:
    pipeline = build(understander=understanding(make_item_intent(search_keywords=["black jacket"])))
    first = await pipeline.run(make_search_request(text="black jacket"), openai_settings)
    request, overrides = rerun(first)
    overrides = RunOverrides(
        chips=ChipEdits(items=[ItemEdit(index=0, colour="cheap dark brown")]),
        understood=overrides.understood,
        query_embedding=overrides.query_embedding,
    )

    await pipeline.run(request, openai_settings, overrides)

    sent = [unquote_plus(url) for url in search_urls(world)]
    assert any("brown" in url for url in sent)  # the edit was searched ...
    assert [url for url in store_urls(world) if price_words_in(url)] == []  # ... minus the price


def test_the_price_word_check_itself_catches_a_leak() -> None:
    # A guard on the guard: if the scan found nothing in anything, the tests above would prove
    # nothing.
    leaky = "https://alpha.example/search/suggest.json?q=cheap%20black%20jacket"
    arabic = "https://alpha.example/search/suggest.json?q=" + quote("جاكيت رخيص")
    clean = "https://alpha.example/search/suggest.json?q=black%20jacket&resources%5Blimit%5D=10"

    assert price_words_in(leaky) == ["cheap"]
    assert price_words_in(arabic) == ["رخيص"]
    assert price_words_in("https://alpha.example/search/suggest.json?q=under%20400%20AED") == [
        "under",
        "400",
        "aed",
    ]
    assert price_words_in(clean) == []


# --------------------------------------------------------------------------------------------
# The kill switch
# --------------------------------------------------------------------------------------------


async def test_a_store_that_is_not_enabled_gets_no_request_at_all(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("gamma", enabled=False))
    pipeline = build(understander=understanding(make_item_intent()))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("gamma.example") == 0  # not even its robots.txt
    assert world.stray == []
    assert {report.store_id for report in response.stores_used} == {"alpha"}
    assert response.stores_skipped == []  # it is not "skipped for a reason": it is off


async def test_a_store_file_that_does_not_say_enabled_is_off(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    silent = StoreConfig.model_validate(store_for("gamma").model_dump(exclude={"enabled"}))
    world.add(silent)
    assert silent.enabled is False  # the safe default of the contract
    pipeline = build(understander=understanding(make_item_intent()))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("gamma.example") == 0
    assert world.stray == []


async def test_when_no_store_is_enabled_nothing_is_requested_and_the_shopper_is_told(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha", enabled=False))
    world.add(store_for("beta", enabled=False))
    pipeline = build(understander=understanding(make_item_intent()))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.all_requests() == 0
    assert world.stray == []
    assert messages.NO_STORES_CONFIGURED in response.warnings
    assert response.result_count == 0


async def test_the_engine_itself_refuses_a_disabled_store_it_is_handed_directly(
    world: GuardWorld, build: GuardPipelines
) -> None:
    store = store_for("gamma", enabled=False)
    world.add(store)
    build(understander=understanding(make_item_intent()))

    [result] = await build.engine.search(make_item_intent(), [store])

    assert result.status is StoreStatus.ERROR
    assert result.detail == "the store is not enabled"
    assert world.all_requests() == 0


async def test_a_store_in_another_country_gets_no_request(
    world: GuardWorld, build: GuardPipelines, settings: Settings
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("gamma", country="SA", currency="SAR"))
    pipeline = build(understander=understanding(make_item_intent()))

    await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert world.requests_to("gamma.example") == 0
    assert world.stray == []


async def test_a_store_the_settings_do_not_select_gets_no_request(
    world: GuardWorld, build: GuardPipelines, tmp_path
) -> None:
    world.add(store_for("alpha"))
    world.add(store_for("beta"))
    only_alpha = make_settings(stores=["alpha"], log_dir=str(tmp_path / "logs"))
    pipeline = build(understander=understanding(make_item_intent()))

    response = await pipeline.run(make_search_request(text="black oversized blazer"), only_alpha)

    assert world.requests_to("beta.example") == 0
    assert {report.store_id for report in response.stores_used} == {"alpha"}
