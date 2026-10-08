"""Plan 13.1.3: an outfit photo is one search per garment, sharing the engine's rate limiter."""

from itertools import pairwise

from tests.factories import make_search_request, make_understand_result
from tests.fakes import FakeImageRanker, FakeUnderstander
from tests.pipeline.builders import OUTFIT, outfit_understander
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld, store_for
from vga.models import Category, Tier
from vga.settings import Settings


async def test_four_garments_give_four_groups_in_the_order_they_were_detected(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert [group.item_index for group in response.groups] == [0, 1, 2, 3]
    assert [group.category for group in response.groups] == [
        Category.OUTERWEAR,
        Category.TOPS,
        Category.BOTTOMS,
        Category.SHOES,
    ]
    assert all(group.result_count > 0 for group in response.groups)
    for group in response.groups:
        assert [tier.name for tier in group.tiers] == list(Tier)


async def test_each_garment_has_its_own_price_ranges_and_twelve_results_at_most(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    for group in response.groups:
        # Plan assumption A2: 12 results per garment for an outfit photo.
        assert sum(tier.target_count for tier in group.tiers) == 12
        assert group.result_count <= 12
    shoe_prices = {s.product.price for s in response.groups[3].tiers[0].results}
    top_prices = {s.product.price for s in response.groups[1].tiers[0].results}
    assert shoe_prices != top_prices  # borders come from each garment's own candidates


async def test_each_garment_is_searched_with_its_first_keyword_variant_and_no_other(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    for store_id in ("alpha", "beta"):
        # The garments are searched side by side, one search each, in item order.
        assert world.queries(store_id) == [
            "black blazer",
            "white shirt",
            "blue jeans",
            "white sneakers",
        ]


async def test_an_outfit_photos_garments_never_get_a_second_variant_however_little_a_store_has(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    settings: Settings,
    photo: bytes,
) -> None:
    # Two products a garment: a store that thin would be sent a second variant by any other search.
    thin = dict.fromkeys(("blazer", "shirt", "jeans", "shoes"), (120, 180))
    for key in ("alpha", "beta"):
        world.add(store_for(key), prices=thin)
    pipeline = make_pipeline(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    for store_id in ("alpha", "beta"):
        assert len(world.queries(store_id)) == len(OUTFIT)


async def test_the_number_of_search_requests_is_one_per_garment_and_store(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    garments, stores = 4, 2
    assert world.search_requests() == garments * stores
    # Politeness: one robots.txt per store, and nothing else is requested from a store.
    assert world.requests_to("alpha.example") == garments + 1
    assert world.requests_to("beta.example") == garments + 1


async def test_the_searches_start_in_item_order_and_then_store_order(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    await pipeline.run(make_search_request(image=photo, text=None), settings)

    # Each store is searched on its own, so one slow store never holds the others back.
    assert make_pipeline.spy is not None
    started = [(call.category, call.store_ids) for call in make_pipeline.spy.calls]
    assert started == [
        (category, (store,))
        for category in (Category.OUTERWEAR, Category.TOPS, Category.BOTTOMS, Category.SHOES)
        for store in ("alpha", "beta")
    ]


async def test_every_garment_shares_one_rate_limiter_per_store(
    make_pipeline: PipelineMaker,
    world: StoreWorld,
    two_stores: list,
    settings: Settings,
    photo: bytes,
) -> None:
    pipeline = make_pipeline(understander=outfit_understander())

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    # Four searches to one store, started together, still arrive one second apart (BRD Rule 2).
    for store_id in ("alpha", "beta"):
        times = world.arrival_times(store_id)
        assert len(times) == 4
        gaps = [later - earlier for earlier, later in pairwise(times)]
        assert all(gap >= 1.0 - 1e-9 for gap in gaps)
    # ... and so the whole outfit takes about 4 seconds, well inside the 30 s deadline.
    assert 4_000 <= response.duration_ms < 30_000
    assert not any("longer than" in warning for warning in response.warnings)


async def test_an_outfit_photo_is_not_handed_to_the_image_ranker(
    make_pipeline: PipelineMaker, two_stores: list, settings: Settings, photo: bytes
) -> None:
    # Comparing the photo with each garment's thumbnails is left out for an outfit photo: see
    # test_outfit_images.py for why, and for the thumbnail and warning side of it.
    ranker = FakeImageRanker()
    pipeline = make_pipeline(understander=outfit_understander(), image_ranker=ranker)

    response = await pipeline.run(make_search_request(image=photo, text=None), settings)

    assert ranker.calls == []
    assert all(scored.scores.image is None for scored in response.products)
    assert response.query_embedding is None


async def test_a_text_request_that_names_two_garments_is_one_search_per_garment_and_store(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, settings: Settings
) -> None:
    items = OUTFIT[:2]
    pipeline = make_pipeline(understander=FakeUnderstander(make_understand_result(items=items)))

    response = await pipeline.run(
        make_search_request(text="black blazer and a white shirt"), settings
    )

    assert len(response.groups) == 2
    assert world.search_requests() == 2 * 2 * 1


async def test_a_text_request_for_two_garments_may_still_send_a_thin_store_a_second_variant(
    make_pipeline: PipelineMaker, world: StoreWorld, settings: Settings
) -> None:
    thin = dict.fromkeys(("blazer", "shirt", "jeans", "shoes"), (120, 180))
    world.add(store_for("alpha"), prices=thin)
    items = OUTFIT[:2]
    pipeline = make_pipeline(understander=FakeUnderstander(make_understand_result(items=items)))

    await pipeline.run(make_search_request(text="black blazer and a white shirt"), settings)

    # The outfit-photo cap does not apply to words; the engine's own rule does: two, never three.
    assert sorted(world.queries("alpha")) == sorted(
        ["black blazer", "oversized blazer", "white shirt", "cotton shirt"]
    )
