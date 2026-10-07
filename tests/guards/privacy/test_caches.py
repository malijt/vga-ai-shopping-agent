"""What the app remembers between requests, and what it does not.

Assumption A8 of the plan: after the first request the app keeps the photo's *embedding* (a list of
numbers) so that a change to the chips can search again without the photo, and nothing else of the
photo. The thumbnails of products are fetched, compared and dropped: there is no thumbnail cache.
"""

import pytest

from tests.guards.privacy.audit import Audited
from tests.guards.privacy.reachable import photos_held, reachable
from tests.guards.privacy.scenarios import BOTH, CHIP_EDIT, OUTFIT, PRODUCT_PHOTO, cases
from tests.guards.privacy.traces import is_an_image


def cached_runs(audited: Audited) -> list:
    return list(audited.rig.pipeline._cache._runs.values())


@pytest.mark.parametrize("audited", cases([CHIP_EDIT], [BOTH]), indirect=True)
async def test_the_rerun_cache_keeps_the_embedding_of_the_photo_as_numbers(
    audited: Audited,
) -> None:
    first, again = audited.responses

    assert len(cached_runs(audited)) == 2  # the first request and the chip edit
    assert first.query_embedding
    for run in cached_runs(audited):
        assert isinstance(run.query_embedding, tuple)
        assert all(isinstance(number, float) for number in run.query_embedding)
        assert list(run.query_embedding) == first.query_embedding
    assert again.query_embedding == first.query_embedding


@pytest.mark.parametrize("audited", cases([CHIP_EDIT], [BOTH]), indirect=True)
async def test_the_rerun_cache_holds_no_bytes_and_no_picture_at_all(audited: Audited) -> None:
    cache = audited.rig.pipeline._cache

    assert [obj for obj in reachable([cache]) if isinstance(obj, bytes | bytearray)] == []
    assert photos_held([cache], audited.traces) == []


@pytest.mark.parametrize("audited", cases([CHIP_EDIT], [BOTH]), indirect=True)
async def test_a_chip_edit_searches_again_without_the_photo_and_without_asking_openai(
    audited: Audited,
) -> None:
    first, again = audited.responses

    assert len(audited.rig.fake_openai.requests) == 1  # only the first request asked the model
    assert len(audited.sent_images) == 1
    assert (first.usage.llm_calls, again.usage.llm_calls) == (1, 0)
    assert again.query_embedding == first.query_embedding  # the ranker used the stored numbers


@pytest.mark.parametrize("audited", cases([PRODUCT_PHOTO, OUTFIT], [BOTH]), indirect=True)
async def test_product_thumbnails_are_fetched_and_dropped_not_cached(audited: Audited) -> None:
    rig = audited.rig
    assert rig.world.thumbnails, "no thumbnail was fetched: the test is not testing anything"

    holders = [rig.engine, rig.ranker]
    images = [obj for obj in reachable(holders) if isinstance(obj, bytes) and is_an_image(obj)]
    assert images == []
    in_the_caches = reachable([rig.engine.cache._entries, rig.engine.robots._cache])
    assert [obj for obj in in_the_caches if isinstance(obj, bytes | bytearray)] == []


@pytest.mark.parametrize("audited", cases([PRODUCT_PHOTO], [BOTH]), indirect=True)
async def test_no_store_cache_holds_the_photo(audited: Audited) -> None:
    rig = audited.rig

    assert len(rig.engine.cache) > 0, "the store cache is empty: the test is not testing anything"
    caches = [rig.engine.cache._entries, rig.engine.robots._cache]
    assert photos_held(caches, audited.traces) == []
