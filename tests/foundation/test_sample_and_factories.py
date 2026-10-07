"""The bundled sample response and the test builders (plan feature 1.2.6)."""

import json
from collections import Counter

import pytest

from tests.factories import (
    FIXTURES_DIR,
    SAMPLE_RESPONSE_PATH,
    load_sample_response,
    make_budget,
    make_chip_edits,
    make_garment_group,
    make_image_bytes,
    make_item_intent,
    make_product,
    make_products,
    make_scored_product,
    make_scores,
    make_search_request,
    make_search_response,
    make_settings,
    make_store_config,
    make_store_report,
    make_store_result,
    make_tier_result,
    make_understand_result,
)
from vga.models import (
    Category,
    Flag,
    InputType,
    SearchResponse,
    StoreStatus,
    Tier,
)


@pytest.fixture(scope="module")
def sample() -> SearchResponse:
    return load_sample_response()


class TestSampleResponse:
    def test_file_loads_into_a_search_response(self, sample: SearchResponse) -> None:
        assert isinstance(sample, SearchResponse)
        assert SAMPLE_RESPONSE_PATH.parent == FIXTURES_DIR

    def test_it_is_an_outfit_photo_with_two_garments_and_four_ranges_each(
        self, sample: SearchResponse
    ) -> None:
        assert sample.understood.input_type is InputType.OUTFIT_PHOTO
        assert [g.category for g in sample.groups] == [Category.OUTERWEAR, Category.SHOES]
        for group in sample.groups:
            assert [t.name for t in group.tiers] == list(Tier)

    def test_one_range_is_thin(self, sample: SearchResponse) -> None:
        thin = [
            (group.category, tier.name)
            for group in sample.groups
            for tier in group.tiers
            if tier.count < tier.target_count
        ]

        assert thin
        for group in sample.groups:
            for tier in group.tiers:
                if tier.count < tier.target_count:
                    assert Flag.FEW_OPTIONS in tier.flags

    def test_one_store_was_skipped_with_a_reason(self, sample: SearchResponse) -> None:
        (skipped,) = sample.stores_skipped

        assert skipped.status is StoreStatus.BLOCKED
        assert skipped.reason
        assert all(report.status is StoreStatus.OK for report in sample.stores_used)

    def test_it_holds_a_very_long_title(self, sample: SearchResponse) -> None:
        assert max(len(s.product.title) for s in sample.products) > 250

    def test_it_holds_a_product_with_no_colour(self, sample: SearchResponse) -> None:
        assert any(s.product.colour is None for s in sample.products)

    def test_it_holds_over_budget_items_flagged_and_priced_above_the_budget(
        self, sample: SearchResponse
    ) -> None:
        assert sample.understood.budget is not None
        ceiling = sample.understood.budget.max_price
        over = [s for s in sample.products if Flag.OVER_BUDGET in s.flags]

        assert over
        assert all(s.product.price > ceiling for s in over)
        assert all(s.product.price <= ceiling for s in sample.products if s not in over)

    def test_over_budget_items_sit_only_in_the_upper_ranges(self, sample: SearchResponse) -> None:
        for group in sample.groups:
            for tier in group.tiers:
                if tier.name in (Tier.BUDGET, Tier.MID_RANGE):
                    assert all(Flag.OVER_BUDGET not in s.flags for s in tier.results)

    def test_gender_is_inferred_so_the_unconfirmed_state_can_be_shown(
        self, sample: SearchResponse
    ) -> None:
        assert {item.gender_source.value for item in sample.understood.items} == {"inferred"}

    def test_no_store_exceeds_six_results_and_every_link_is_https(
        self, sample: SearchResponse
    ) -> None:
        per_store = Counter(s.product.store for s in sample.products)

        assert max(per_store.values()) <= 6
        assert all(s.product.product_url.startswith("https://") for s in sample.products)

    def test_store_report_counts_match_the_products_shown(self, sample: SearchResponse) -> None:
        shown = Counter(s.product.store for s in sample.products)
        names = {"souq-atelier": "Souq Atelier", "gulf-threads": "Gulf Threads"}
        names |= {"marina-mode": "Marina Mode", "oasis-luxe": "Oasis Luxe"}

        for report in sample.stores_used:
            assert report.product_count == shown[names[report.store_id]]

    def test_is_stable_json_with_no_photo_or_embedding(self) -> None:
        raw = json.loads(SAMPLE_RESPONSE_PATH.read_text(encoding="utf-8"))

        assert "query_embedding" not in raw
        assert "image" not in raw

    def test_json_round_trip_is_lossless(self, sample: SearchResponse) -> None:
        assert SearchResponse.model_validate_json(sample.model_dump_json()) == sample


class TestFactories:
    def test_every_default_builder_returns_a_valid_object(self) -> None:
        builders = [
            make_budget,
            make_chip_edits,
            make_garment_group,
            make_item_intent,
            make_product,
            make_scored_product,
            make_scores,
            make_search_request,
            make_search_response,
            make_settings,
            make_store_config,
            make_store_report,
            make_store_result,
            make_tier_result,
            make_understand_result,
        ]

        for build in builders:
            assert build() is not None

    def test_overrides_replace_defaults(self) -> None:
        assert make_product(title="Custom", price=10).price == 10
        assert make_item_intent(colour="red").colour == "red"

    def test_invalid_overrides_still_fail(self) -> None:
        with pytest.raises(ValueError, match="price"):
            make_product(price=-1)

    def test_products_are_distinct_and_priced_in_order(self) -> None:
        products = make_products(5)

        assert len({p.key for p in products}) == 5
        assert [p.price for p in products] == sorted(p.price for p in products)

    def test_demo_store_hosts_are_on_the_reserved_example_domain(self) -> None:
        config = make_store_config()

        assert all(host.endswith(".example") for host in config.allowed_hosts)

    def test_group_has_four_ranges_of_rising_price(self) -> None:
        group = make_garment_group(per_tier=3)

        spans = [(t.price_min, t.price_max) for t in group.tiers]
        assert all(low is not None and high is not None for low, high in spans)
        assert spans == sorted(spans)

    def test_store_result_for_a_failed_store_has_no_products(self) -> None:
        assert make_store_result(StoreStatus.TIMEOUT).products == []

    def test_image_bytes_are_real_images_in_the_requested_format(self) -> None:
        assert make_image_bytes("PNG").startswith(b"\x89PNG")
        assert make_image_bytes("JPEG")[:2] == b"\xff\xd8"
        assert make_image_bytes("WEBP")[:4] == b"RIFF"

    def test_settings_builder_reads_no_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VGA_IMAGE_RANKER", "siglip")

        assert make_settings().image_ranker == "off"
