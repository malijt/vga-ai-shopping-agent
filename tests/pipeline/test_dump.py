"""Plan 13.2.4: with ``VGA_DEBUG_DUMP=1`` each request writes its ranked candidates to a JSON-lines
file in the log directory: one line per candidate, and no image data of any kind."""

import base64
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from tests.factories import make_search_request, make_settings
from tests.fakes import FakeImageRanker
from tests.fetch.conftest import shopify_product, suggest_body
from tests.pipeline.builders import OUTFIT, outfit_understander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.disk import exists, files_under
from tests.pipeline.world import CDN_PREFIX, StoreWorld, store_for
from vga.models import SearchResponse, Tier
from vga.pipeline.dump import dump_path
from vga.settings import Settings

ALLOWED_KEYS = {
    "request_id",
    "item_index",
    "category",
    "rank",
    "url",
    "store",
    "strategy",
    "title",
    "price",
    "currency",
    "base_price",
    "scores",
    "flags",
    "shown",
    "price_range",
    "price_range_min",
    "price_range_max",
}


@pytest.fixture
def dumping(tmp_path: Path) -> Settings:
    return make_settings(debug_dump=True, log_dir=str(tmp_path / "logs"))


def read_lines(settings: Settings, response: SearchResponse) -> list[dict[str, Any]]:
    path = dump_path(settings.log_dir, response.request_id)
    assert path.is_file()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_the_dump_has_one_line_per_ranked_candidate(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)

    lines = read_lines(dumping, response)
    # 16 blazers were found, 12 are shown (6 per store at most); all 16 were ranked
    assert len(lines) == 16
    assert sum(1 for line in lines if line["shown"]) == response.result_count == 12
    assert [line["rank"] for line in lines] == list(range(1, 17))
    assert {line["request_id"] for line in lines} == {response.request_id}


async def test_each_line_holds_the_url_store_scores_price_range_and_strategy(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)

    lines = read_lines(dumping, response)
    for line in lines:
        assert set(line) == ALLOWED_KEYS
        assert line["url"].startswith("https://")
        assert line["store"] in {"Alpha", "Beta"}
        assert line["strategy"] == "shopify"
        assert set(line["scores"]) == {"text", "image", "price", "total"}
        assert line["currency"] == "AED"
        assert line["base_price"] is None  # a dirham price is its own figure in dirhams
    shown_in = {s.product.product_url: s.tier for s in response.products}
    for line in lines:
        if line["shown"]:
            assert line["price_range"] == shown_in[line["url"]].value
            assert line["price_range_min"] <= line["price"] <= line["price_range_max"]
        else:
            assert line["url"] not in shown_in
            assert line["price_range"] is None
            assert line["price_range_min"] is None


DINAR_RATE = 11.92
"""Dirhams to the dinar, as in ``config/settings.yaml`` (ADR 0006)."""


def dinar_blazers(*prices: float) -> str:
    """A Shopify suggest answer of black blazers priced in dinars, written with three decimals as
    a Kuwaiti store writes them (``"30.000"``)."""
    products = [
        shopify_product(
            number,
            title=f"Black Oversized Blazer K{number}",
            price=f"{price:.3f}",
            price_min=f"{price:.3f}",
            price_max=f"{price:.3f}",
            handle=f"blazer-kuwait-{number}",
            id=3000 + number,
            image=f"{CDN_PREFIX}s/files/1/0001/blazer-kuwait-{number}.jpg?v=1",
            url=f"/products/blazer-kuwait-{number}?_pos={number}",
            type="Coats & Jackets",
        )
        for number, price in enumerate(prices, start=1)
    ]
    return suggest_body(*products)


@pytest.fixture
def two_currencies(world: StoreWorld) -> list:
    """A dirham store and a dinar store whose blazers cost 10 to 80 KWD, which is 119 to 954 AED:
    the same price ranges as the dirham store's, so both are shown together."""
    stores = [
        store_for("alpha"),
        store_for("kuwait", currency="KWD", country="KW"),
    ]
    world.add(stores[0])
    world.add(stores[1], bodies={"blazer": dinar_blazers(10, 15, 20, 25, 30, 40, 60, 80)})
    return stores


def two_currency_settings(tmp_path: Path, **overrides: Any) -> Settings:
    fields: dict[str, Any] = {
        "debug_dump": True,
        "log_dir": str(tmp_path / "logs"),
        "extra_store_countries": ["KW"],
        "fx_rates": {"KWD": DINAR_RATE},
    }
    return make_settings(**{**fields, **overrides})


async def test_a_candidate_in_another_currency_carries_the_figure_the_ranges_used(
    make_pipeline: PipelineMaker, two_currencies: list, tmp_path: Path
) -> None:
    settings = two_currency_settings(tmp_path)
    pipeline = make_pipeline(engine_settings=settings)

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    lines = read_lines(settings, response)
    dinar = [line for line in lines if line["currency"] == "KWD"]
    assert dinar
    assert all(set(line) == ALLOWED_KEYS for line in lines)
    for line in dinar:
        assert line["base_price"] == pytest.approx(line["price"] * DINAR_RATE, abs=0.01)
    assert all(line["base_price"] is None for line in lines if line["currency"] == "AED")


async def test_a_shown_candidates_figure_is_the_one_the_result_carries(
    make_pipeline: PipelineMaker, two_currencies: list, tmp_path: Path
) -> None:
    settings = two_currency_settings(tmp_path)
    pipeline = make_pipeline(engine_settings=settings)

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    carried = {s.product.product_url: s.base_price for s in response.products}
    shown_dinar = [
        line
        for line in read_lines(settings, response)
        if line["shown"] and line["currency"] == "KWD"
    ]
    assert shown_dinar
    for line in shown_dinar:
        assert line["base_price"] == carried[line["url"]]
        # the range's span is in dirhams, so the figure sits inside it
        assert line["price_range_min"] <= line["base_price"] <= line["price_range_max"]


async def test_a_currency_with_no_rate_has_no_figure_and_is_not_shown(
    make_pipeline: PipelineMaker, two_currencies: list, tmp_path: Path
) -> None:
    settings = two_currency_settings(tmp_path, fx_rates={})
    pipeline = make_pipeline(engine_settings=settings)

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    dinar = [line for line in read_lines(settings, response) if line["currency"] == "KWD"]
    assert dinar
    assert all(line["base_price"] is None and line["shown"] is False for line in dinar)


async def test_lines_are_in_ranking_order(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings
) -> None:
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)

    totals = [line["scores"]["total"] for line in read_lines(dumping, response)]
    assert totals == sorted(totals, reverse=True)


async def test_the_image_score_is_in_the_dump_but_no_image_data_is(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(image_ranker=FakeImageRanker(default=0.6, embedding=[0.123456, 0.5]))

    response = await pipeline.run(make_search_request(image=photo, text="black blazer"), dumping)

    path = dump_path(dumping.log_dir, response.request_id)
    raw = path.read_bytes()
    lines = read_lines(dumping, response)
    assert all(line["scores"]["image"] == 0.6 for line in lines)
    assert photo not in raw
    assert base64.b64encode(photo)[:40] not in raw
    assert b"0.123456" not in raw  # not even the embedding
    for forbidden in (b"embedding", b"image_url", b"data:image"):
        assert forbidden not in raw
    assert b"cdn.shopify.com" not in raw  # thumbnail addresses are not dumped either


async def test_an_outfit_dump_covers_every_garment(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander(OUTFIT[:2]))

    response = await pipeline.run(make_search_request(image=photo, text=None), dumping)

    lines = read_lines(dumping, response)
    assert {line["item_index"] for line in lines} == {0, 1}
    assert {line["category"] for line in lines} == {"outerwear", "tops"}
    # ranks restart for each garment
    assert next(line["rank"] for line in lines if line["item_index"] == 1) == 1
    shown = {Tier(line["price_range"]) for line in lines if line["shown"]}
    assert shown <= set(Tier)


async def test_nothing_is_written_unless_the_setting_is_on(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, tmp_path: Path
) -> None:
    assert settings.debug_dump is False
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), settings)

    assert not exists(settings.log_dir)
    assert not exists(dump_path(settings.log_dir, response.request_id))
    assert [path for path in files_under(tmp_path) if path.suffix == ".jsonl"] == []


async def test_each_request_has_its_own_file(
    make_pipeline: PipelineMaker, two_stores: list, dumping: Settings
) -> None:
    pipeline = make_pipeline()

    first = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)
    second = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)

    assert dump_path(dumping.log_dir, first.request_id).is_file()
    assert dump_path(dumping.log_dir, second.request_id).is_file()
    assert dump_path(dumping.log_dir, first.request_id) != dump_path(
        dumping.log_dir, second.request_id
    )


async def test_a_dump_that_cannot_be_written_never_fails_the_request(
    make_pipeline: PipelineMaker,
    two_stores: list,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="vga")
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the log folder should be")
    broken = make_settings(debug_dump=True, log_dir=str(blocker))
    pipeline = make_pipeline()
    request = make_search_request(text="black oversized blazer")

    response = await pipeline.run(request, broken)

    assert response.result_count > 0
    assert any(
        record.levelno == logging.WARNING
        and "dump could not be written" in record.getMessage()
        and getattr(record, "request_id", None) == request.request_id
        for record in caplog.records
    )


async def test_a_search_that_found_nothing_still_writes_an_empty_dump(
    make_pipeline: PipelineMaker, world: StoreWorld, dumping: Settings
) -> None:
    from tests.pipeline.world import store_for

    world.add(store_for("alpha"), bodies={})
    pipeline = make_pipeline()

    response = await pipeline.run(make_search_request(text="black oversized blazer"), dumping)

    assert read_lines(dumping, response) == []
