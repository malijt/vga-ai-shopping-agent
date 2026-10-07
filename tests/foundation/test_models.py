"""Behaviour of the shared contracts in vga.models (plan features 1.2.1 to 1.2.3)."""

from typing import Any

import pytest
from pydantic import ValidationError

from tests.factories import (
    make_budget,
    make_garment_group,
    make_item_intent,
    make_product,
    make_products,
    make_scored_product,
    make_scores,
    make_search_request,
    make_search_response,
    make_store_config,
    make_store_report,
    make_store_result,
    make_tier_result,
    make_understand_result,
)
from vga.models import (
    MAX_TEXT_CHARS,
    Category,
    ChipEdits,
    Flag,
    GarmentGroup,
    Gender,
    GenderSource,
    ItemEdit,
    MixPreset,
    Product,
    QueryImage,
    RunOverrides,
    SearchRequest,
    StoreConfig,
    StoreResult,
    StoreStatus,
    Tier,
    TierMix,
    TierResult,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def round_trip(model: Any) -> Any:
    return type(model).model_validate_json(model.model_dump_json())


class TestSearchRequest:
    def test_text_request_round_trips_through_json(self) -> None:
        request = make_search_request(text="red dress")

        assert round_trip(request) == request

    def test_text_is_stripped(self) -> None:
        assert SearchRequest(text="  red dress \n").text == "red dress"

    def test_whitespace_only_text_with_no_image_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="needs text, a photo, or both"):
            SearchRequest(text="   \n\t ")

    def test_whitespace_only_text_with_an_image_is_accepted_and_becomes_none(self) -> None:
        request = SearchRequest(text="   ", image=PNG_BYTES)

        assert request.text is None
        assert request.has_image

    def test_request_with_neither_text_nor_image_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="needs text, a photo, or both"):
            SearchRequest()

    def test_text_of_exactly_the_limit_is_accepted(self) -> None:
        assert len(SearchRequest(text="a" * MAX_TEXT_CHARS).text or "") == MAX_TEXT_CHARS

    def test_text_one_character_over_the_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most 2000 characters"):
            SearchRequest(text="a" * (MAX_TEXT_CHARS + 1))

    def test_limit_is_counted_after_stripping(self) -> None:
        padded = " " * 50 + "a" * MAX_TEXT_CHARS + " " * 50

        assert len(SearchRequest(text=padded).text or "") == MAX_TEXT_CHARS

    def test_arabic_text_is_kept_intact(self) -> None:
        assert SearchRequest(text="جاكيت أسود").text == "جاكيت أسود"

    def test_photo_never_appears_in_repr_or_json(self) -> None:
        request = SearchRequest(text="x", image=PNG_BYTES)

        assert "PNG" not in repr(request)
        assert "image" not in request.model_dump()
        assert "image" not in request.model_dump_json()

    def test_request_id_is_generated_and_unique(self) -> None:
        ids = {SearchRequest(text="x").request_id for _ in range(20)}

        assert len(ids) == 20

    @pytest.mark.parametrize("bad", ["", "has space", "x" * 65, "semi;colon", "new\nline"])
    def test_unsafe_request_ids_are_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(text="x", request_id=bad)

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest.model_validate({"text": "x", "colour": "red"})


class TestItemIntentAndUnderstandResult:
    def test_round_trip(self) -> None:
        result = make_understand_result(budget=make_budget())

        assert round_trip(result) == result

    @pytest.mark.parametrize("category", ["accessories", "bag", "Shirts", ""])
    def test_category_outside_the_four_is_rejected(self, category: str) -> None:
        with pytest.raises(ValidationError):
            make_item_intent(category=category)

    @pytest.mark.parametrize("category", ["tops", "outerwear", "bottoms", "shoes"])
    def test_the_four_categories_are_accepted(self, category: str) -> None:
        assert make_item_intent(category=category).category == Category(category)

    @pytest.mark.parametrize("count", [0, 4])
    def test_keywords_must_be_one_to_three(self, count: int) -> None:
        with pytest.raises(ValidationError):
            make_item_intent(search_keywords=[f"word {i}" for i in range(count)])

    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_one_to_three_keywords_are_accepted(self, count: int) -> None:
        item = make_item_intent(search_keywords=[f"word {i}" for i in range(count)])

        assert len(item.search_keywords) == count

    def test_a_blank_keyword_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_item_intent(search_keywords=["black blazer", "   "])

    def test_blank_attributes_become_none(self) -> None:
        item = make_item_intent(colour="  ", style="", material=" ")

        assert (item.colour, item.style, item.material) == (None, None, None)

    def test_gender_needs_a_source(self) -> None:
        with pytest.raises(ValidationError, match="gender_source"):
            make_item_intent(gender=Gender.MEN, gender_source=GenderSource.NONE)

    def test_a_source_needs_a_gender(self) -> None:
        with pytest.raises(ValidationError, match="gender_source"):
            make_item_intent(gender=None, gender_source=GenderSource.INFERRED)

    def test_inferred_gender_is_representable(self) -> None:
        item = make_item_intent(gender=Gender.WOMEN, gender_source=GenderSource.INFERRED)

        assert item.gender_source is GenderSource.INFERRED

    def test_at_most_four_items(self) -> None:
        with pytest.raises(ValidationError):
            make_understand_result(items=[make_item_intent() for _ in range(5)])

    def test_at_least_one_item(self) -> None:
        with pytest.raises(ValidationError):
            make_understand_result(items=[])

    def test_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_budget(max_price=0)

    def test_budget_currency_is_normalised(self) -> None:
        assert make_budget(currency="aed").currency == "AED"

    def test_input_type_must_be_known(self) -> None:
        with pytest.raises(ValidationError):
            make_understand_result(input_type="video")

    def test_language_must_be_known(self) -> None:
        with pytest.raises(ValidationError):
            make_understand_result(language="klingon")


class TestChipEditsAndOverrides:
    def test_round_trip(self) -> None:
        edits = ChipEdits(
            items=[
                ItemEdit(index=0, category=Category.TOPS, colour="dark brown", gender=Gender.MEN)
            ],
            budget=make_budget(),
        )

        assert round_trip(edits) == edits

    def test_item_index_must_not_repeat(self) -> None:
        with pytest.raises(ValidationError, match="repeat"):
            ChipEdits(items=[ItemEdit(index=0), ItemEdit(index=0)])

    def test_item_index_must_be_a_possible_item(self) -> None:
        with pytest.raises(ValidationError):
            ItemEdit(index=4)

    def test_budget_and_clear_budget_are_exclusive(self) -> None:
        with pytest.raises(ValidationError, match="not both"):
            ChipEdits(budget=make_budget(), clear_budget=True)

    def test_empty_colour_means_clear_it(self) -> None:
        assert ItemEdit(index=0, colour="  ").colour == ""

    def test_run_overrides_keep_the_embedding_out_of_json_and_repr(self) -> None:
        overrides = RunOverrides(query_embedding=[0.123456, 0.2])

        assert "query_embedding" not in overrides.model_dump_json()
        assert "0.123456" not in repr(overrides)

    def test_query_image_hides_photo_and_embedding_in_repr(self) -> None:
        query = QueryImage(image=PNG_BYTES, embedding=[0.987654])

        assert "PNG" not in repr(query)
        assert "0.987654" not in repr(query)


class TestTierMix:
    def test_mix_that_sums_to_100_is_accepted(self) -> None:
        mix = TierMix(budget=40, mid_range=30, premium=20, luxury=10)

        assert mix.as_tuple() == (40, 30, 20, 10)
        assert mix.share(Tier.PREMIUM) == 20

    @pytest.mark.parametrize("values", [(25, 25, 25, 24), (30, 30, 30, 30), (0, 0, 0, 0)])
    def test_mix_that_does_not_sum_to_100_names_the_total(self, values: tuple[int, ...]) -> None:
        with pytest.raises(ValidationError, match=f"sum to 100, got {sum(values)}"):
            TierMix(budget=values[0], mid_range=values[1], premium=values[2], luxury=values[3])

    def test_negative_share_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TierMix(budget=-10, mid_range=50, premium=30, luxury=30)

    @pytest.mark.parametrize(
        ("preset", "expected"),
        [
            (MixPreset.EVEN, (25, 25, 25, 25)),
            (MixPreset.VALUE_FIRST, (40, 30, 20, 10)),
            (MixPreset.LUXURY_FIRST, (10, 20, 30, 40)),
        ],
    )
    def test_presets_match_the_prd(self, preset: MixPreset, expected: tuple[int, ...]) -> None:
        assert preset.mix.as_tuple() == expected


class TestStoreConfig:
    def test_enabled_defaults_to_false(self) -> None:
        config = StoreConfig.model_validate(
            {
                **make_store_config().model_dump(exclude={"enabled"}),
            }
        )

        assert config.enabled is False

    def test_enabled_must_be_set_explicitly(self) -> None:
        assert make_store_config(enabled=True).enabled is True

    def test_round_trip(self) -> None:
        config = make_store_config()

        assert round_trip(config) == config

    @pytest.mark.parametrize(
        "template",
        [
            "http://www.demo-store.example/search?q={query}",
            "ftp://www.demo-store.example/search?q={query}",
            "//www.demo-store.example/search?q={query}",
            "www.demo-store.example/search?q={query}",
        ],
    )
    def test_non_https_template_is_rejected(self, template: str) -> None:
        with pytest.raises(ValidationError, match="https"):
            make_store_config(search_url_template=template)

    def test_template_without_query_placeholder_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"\{query\}"):
            make_store_config(search_url_template="https://www.demo-store.example/search")

    def test_template_with_another_placeholder_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="only use"):
            make_store_config(
                search_url_template="https://www.demo-store.example/{lang}/search?q={query}"
            )

    def test_template_host_must_be_allowed(self) -> None:
        with pytest.raises(ValidationError, match="allowed_hosts"):
            make_store_config(
                search_url_template="https://www.other.example/search?q={query}",
            )

    def test_query_placeholder_in_the_host_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not the host"):
            make_store_config(
                search_url_template="https://{query}.demo-store.example/",
                allowed_hosts=["demo-store.example"],
            )

    def test_template_with_credentials_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="credentials"):
            make_store_config(
                search_url_template="https://user:pass@www.demo-store.example/s?q={query}"
            )

    def test_allowed_hosts_is_required_and_not_empty(self) -> None:
        with pytest.raises(ValidationError):
            make_store_config(allowed_hosts=[])
        data = make_store_config().model_dump()
        del data["allowed_hosts"]
        with pytest.raises(ValidationError):
            StoreConfig.model_validate(data)

    @pytest.mark.parametrize(
        "host",
        ["http://x.example", "x.example/path", "x.example:8080", "*.example.com", "127.0.0.1",
         "localhost", "10.0.0.5", "exa mple.com", ""],
    )  # fmt: skip
    def test_allowed_hosts_must_be_plain_host_names(self, host: str) -> None:
        with pytest.raises(ValidationError, match="plain host name"):
            make_store_config(allowed_hosts=["www.demo-store.example", host])

    def test_allowed_hosts_are_lowercased_and_deduplicated(self) -> None:
        config = make_store_config(
            allowed_hosts=["WWW.Demo-Store.example", "www.demo-store.example", "cdn.x.example"]
        )

        assert config.allowed_hosts == ["www.demo-store.example", "cdn.x.example"]

    def test_unknown_field_is_rejected_so_typos_fail_loudly(self) -> None:
        with pytest.raises(ValidationError):
            make_store_config(enabeld=True)

    def test_extraction_needs_at_least_one_strategy(self) -> None:
        with pytest.raises(ValidationError):
            make_store_config(extraction={"strategies": []})

    def test_strategy_may_only_map_product_fields(self) -> None:
        with pytest.raises(ValidationError, match="unknown product field"):
            make_store_config(
                extraction={"strategies": [{"name": "store_json", "fields": {"store": "x"}}]}
            )

    def test_display_name_defaults_to_the_id(self) -> None:
        assert make_store_config(name=None).display_name == "demo-store"
        assert make_store_config(name="Demo Store").display_name == "Demo Store"

    def test_country_and_currency_are_normalised_to_upper_case(self) -> None:
        config = make_store_config(country="ae", currency="aed")

        assert (config.country, config.currency) == ("AE", "AED")

    def test_rps_and_timeout_are_optional_overrides(self) -> None:
        config = make_store_config()

        assert config.rps is None
        assert config.timeout_s is None

    def test_rps_must_be_polite(self) -> None:
        with pytest.raises(ValidationError):
            make_store_config(rps=50)

    def test_response_cap_and_variant_limit_default_to_the_settings(self) -> None:
        config = make_store_config()

        assert config.max_response_bytes is None
        assert config.max_variants is None

    @pytest.mark.parametrize("value", [1, 500_000, 8_000_000])
    def test_response_cap_accepts_positive_values(self, value: int) -> None:
        assert make_store_config(max_response_bytes=value).max_response_bytes == value

    @pytest.mark.parametrize("value", [0, -1, 1.5])
    def test_response_cap_must_be_a_positive_whole_number(self, value: float) -> None:
        with pytest.raises(ValidationError, match="max_response_bytes"):
            make_store_config(max_response_bytes=value)

    @pytest.mark.parametrize("value", [1, 2, 3])
    def test_variant_limit_accepts_one_to_three(self, value: int) -> None:
        assert make_store_config(max_variants=value).max_variants == value

    @pytest.mark.parametrize("value", [0, 4, -1, 2.5])
    def test_variant_limit_outside_one_to_three_is_rejected(self, value: float) -> None:
        with pytest.raises(ValidationError, match="max_variants"):
            make_store_config(max_variants=value)

    def test_response_cap_and_variant_limit_survive_a_round_trip(self) -> None:
        config = make_store_config(max_response_bytes=750_000, max_variants=2)

        assert round_trip(config) == config


class TestProduct:
    REQUIRED = ["title", "price", "currency", "image_url", "product_url", "store"]

    def test_round_trip(self) -> None:
        product = make_product()

        assert round_trip(product) == product

    @pytest.mark.parametrize("missing", REQUIRED)
    def test_each_of_the_six_required_fields_is_required(self, missing: str) -> None:
        data = make_product().model_dump()
        del data[missing]

        with pytest.raises(ValidationError, match=missing):
            Product.model_validate(data)

    @pytest.mark.parametrize("field", ["title", "store", "image_url", "product_url", "currency"])
    def test_required_text_fields_must_not_be_blank(self, field: str) -> None:
        with pytest.raises(ValidationError):
            make_product(**{field: "   "})

    @pytest.mark.parametrize("price", [0, -1, -0.01, float("nan"), float("inf")])
    def test_price_must_be_positive_and_finite(self, price: float) -> None:
        with pytest.raises(ValidationError):
            make_product(price=price)

    @pytest.mark.parametrize(
        "url",
        [
            "http://www.demo-store.example/p/1",
            "javascript:alert(1)",
            "data:text/html;base64,PGgxPmhpPC9oMT4=",
            "ftp://x.example/a",
            "https://",
            "https:///path",
            "https://user:pw@www.demo-store.example/p/1",
            "https://www.demo-store.example/p/1 2",
            "https://www.demo-store.example/p/1\n",
            "/relative/path",
        ],
    )
    @pytest.mark.parametrize("field", ["product_url", "image_url"])
    def test_urls_must_be_absolute_https_without_credentials_or_whitespace(
        self, field: str, url: str
    ) -> None:
        # A trailing newline is stripped by the model, so only the inner-space cases still fail.
        if url.endswith("\n"):
            assert make_product(**{field: url}).model_dump()[field] == url.strip()
            return
        with pytest.raises(ValidationError):
            make_product(**{field: url})

    def test_very_long_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            make_product(product_url="https://www.demo-store.example/" + "a" * 2100)

    def test_optional_fields_default_to_none(self) -> None:
        product = Product(
            title="Plain Tee",
            price=59,
            currency="AED",
            image_url="https://cdn.demo-store.example/a.jpg",
            product_url="https://www.demo-store.example/p/a",
            store="Demo Store",
        )

        assert (product.colour, product.in_stock, product.category) == (None, None, None)

    def test_very_long_title_is_accepted(self) -> None:
        assert len(make_product(title="Blazer " * 100).title) > 600

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_product(brand="Acme")

    def test_key_is_the_product_url(self) -> None:
        product = make_product()

        assert product.key == product.product_url


class TestStoreResult:
    def test_round_trip(self) -> None:
        result = make_store_result()

        assert round_trip(result) == result

    @pytest.mark.parametrize(
        "status",
        [s for s in StoreStatus if s is not StoreStatus.OK],
    )
    def test_failed_or_empty_status_must_not_carry_products(self, status: StoreStatus) -> None:
        with pytest.raises(ValidationError, match="must not carry products"):
            StoreResult(store_id="x", status=status, products=make_products(1))

    def test_ok_status_needs_products(self) -> None:
        with pytest.raises(ValidationError, match="at least one product"):
            StoreResult(store_id="x", status=StoreStatus.OK)

    def test_unknown_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StoreResult(store_id="x", status="exploded")  # type: ignore[arg-type]

    def test_negative_duration_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_store_result(duration_ms=-1)


class TestResultModels:
    def test_scores_must_lie_between_zero_and_one(self) -> None:
        with pytest.raises(ValidationError):
            make_scores(total=1.01)
        with pytest.raises(ValidationError):
            make_scores(text=-0.1)

    def test_image_score_may_be_missing(self) -> None:
        assert make_scores(image=None).image is None

    def test_scored_product_round_trip(self) -> None:
        scored = make_scored_product(flags=[Flag.OVER_BUDGET], tier=Tier.PREMIUM)

        assert round_trip(scored) == scored

    def test_tier_result_always_carries_span_count_target_and_flags(self) -> None:
        tier = make_tier_result(
            Tier.MID_RANGE, make_products(3), target_count=4, flags=[Flag.FEW_OPTIONS]
        )
        dumped = tier.model_dump(mode="json")

        assert dumped["price_min"] == 125.0
        assert dumped["price_max"] == 175.0
        assert (dumped["count"], dumped["target_count"]) == (3, 4)
        assert dumped["flags"] == ["few_options"]
        assert dumped["currency"] == "AED"

    def test_tier_result_count_must_match_results(self) -> None:
        data = make_tier_result().model_dump()
        data["count"] = 5

        with pytest.raises(ValidationError, match="count"):
            TierResult.model_validate(data)

    def test_tier_result_span_must_cover_every_price(self) -> None:
        data = make_tier_result().model_dump()
        data["price_max"] = data["price_min"]

        with pytest.raises(ValidationError, match="outside the span"):
            TierResult.model_validate(data)

    def test_tier_result_with_results_needs_a_span(self) -> None:
        data = make_tier_result().model_dump()
        data["price_min"] = None

        with pytest.raises(ValidationError, match="needs price_min"):
            TierResult.model_validate(data)

    def test_empty_tier_has_no_span(self) -> None:
        tier = TierResult(name=Tier.LUXURY, target_count=3, count=0, flags=[Flag.FEW_OPTIONS])

        assert tier.price_min is None

    def test_empty_tier_must_not_claim_a_span(self) -> None:
        with pytest.raises(ValidationError, match="empty range"):
            TierResult(name=Tier.LUXURY, price_min=10, price_max=20, target_count=3, count=0)

    @pytest.mark.parametrize(
        ("tier", "prices", "expected"),
        [
            (Tier.BUDGET, [45, 80, 139], "Budget · 45-139 AED · 3 results"),
            (Tier.MID_RANGE, [140, 299], "Mid-range · 140-299 AED · 2 results"),
            (Tier.LUXURY, [700, 2400], "Luxury · 700-2,400 AED · 2 results"),
            (Tier.PREMIUM, [349.5, 520], "Premium · 349.50-520 AED · 2 results"),
            (Tier.BUDGET, [99], "Budget · 99 AED · 1 result"),
        ],
    )
    def test_display_label_follows_the_prd_format(
        self, tier: Tier, prices: list[float], expected: str
    ) -> None:
        products = [make_product(i, price=p) for i, p in enumerate(prices, start=1)]

        assert make_tier_result(tier, products).display_label == expected

    def test_display_label_for_an_empty_range(self) -> None:
        tier = TierResult(name=Tier.LUXURY, target_count=3, count=0)

        assert tier.display_label == "Luxury · no results"

    def test_tier_labels_use_shopper_words(self) -> None:
        assert [t.label for t in Tier] == ["Budget", "Mid-range", "Premium", "Luxury"]

    def test_group_needs_exactly_the_four_tiers_in_order(self) -> None:
        group = make_garment_group()
        shuffled = [group.tiers[1], group.tiers[0], *group.tiers[2:]]

        with pytest.raises(ValidationError, match="exactly budget"):
            GarmentGroup(item_index=0, category=Category.TOPS, tiers=shuffled)
        with pytest.raises(ValidationError, match="exactly budget"):
            GarmentGroup(item_index=0, category=Category.TOPS, tiers=group.tiers[:3])

    def test_group_counts_its_results(self) -> None:
        assert make_garment_group(per_tier=2).result_count == 8


class TestSearchResponse:
    def test_serialises_to_json_and_back(self) -> None:
        response = make_search_response()

        assert round_trip(response) == response

    def test_json_contains_the_documented_top_level_fields(self) -> None:
        dumped = make_search_response().model_dump(mode="json")

        assert {
            "understood",
            "groups",
            "stores_used",
            "stores_skipped",
            "timings",
            "usage",
            "warnings",
            "request_id",
        } <= set(dumped)

    def test_query_embedding_is_excluded_from_json_and_repr(self) -> None:
        response = make_search_response(query_embedding=[0.424242, 0.1])

        assert "query_embedding" not in response.model_dump_json()
        assert "0.424242" not in repr(response)
        assert response.query_embedding == [0.424242, 0.1]

    def test_skipped_store_needs_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="needs a reason"):
            make_search_response(
                stores_skipped=[make_store_report(StoreStatus.TIMEOUT, reason=None)]
            )

    def test_an_ok_store_cannot_be_listed_as_skipped(self) -> None:
        with pytest.raises(ValidationError, match="must not hold status 'ok'"):
            make_search_response(stores_skipped=[make_store_report(StoreStatus.OK, reason="x")])

    def test_only_ok_stores_are_listed_as_used(self) -> None:
        with pytest.raises(ValidationError, match="only hold status 'ok'"):
            make_search_response(stores_used=[make_store_report(StoreStatus.BLOCKED)])

    def test_may_have_no_groups_when_every_store_failed(self) -> None:
        response = make_search_response(groups=[], stores_used=[])

        assert response.result_count == 0
        assert response.products == []

    def test_result_count_adds_up_all_groups(self) -> None:
        response = make_search_response(
            groups=[make_garment_group(per_tier=1), make_garment_group(per_tier=2, item_index=1)]
        )

        assert response.result_count == 4 + 8
        assert len(response.products) == 12

    def test_store_report_is_built_from_a_result(self) -> None:
        result = make_store_result(dropped={"missing_price": 2})

        report = type(make_store_report()).from_result(result)

        assert report.product_count == 3
        assert report.dropped == {"missing_price": 2}
        assert report.store_id == result.store_id
