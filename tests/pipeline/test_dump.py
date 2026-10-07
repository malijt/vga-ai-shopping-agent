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
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.disk import exists, files_under
from tests.pipeline.test_outfit import OUTFIT, outfit_understander
from tests.pipeline.world import StoreWorld
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
    shown_in = {s.product.product_url: s.tier for s in response.products}
    for line in lines:
        if line["shown"]:
            assert line["price_range"] == shown_in[line["url"]].value
            assert line["price_range_min"] <= line["price"] <= line["price_range_max"]
        else:
            assert line["url"] not in shown_in
            assert line["price_range"] is None
            assert line["price_range_min"] is None


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
