"""Results (plan 10.2.2 to 10.2.4): price-range sections, result cards and garment groups."""

import re

import pytest
from streamlit.testing.v1 import AppTest

from app.components.price_range import facts_line
from app.components.result_card import TITLE_MAX_CHARS
from app.copy import FLAG_TEXT, PLACEHOLDER_NO_IMAGE
from tests.factories import (
    load_sample_response,
    make_garment_group,
    make_product,
    make_scored_product,
    make_search_response,
    make_tier_result,
)
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import link_buttons, plain_texts, search
from vga.models import Category, Flag, SearchResponse, Tier

SAMPLE = load_sample_response()
HEADER_FORMAT = re.compile(
    r"^(Budget|Mid-range|Premium|Luxury) · (no results|[\d,.]+(-[\d,.]+)? [A-Z]{3} · \d+ results?)$"
)


def range_headers(at: AppTest) -> list[str]:
    return [subheader.value for subheader in at.subheader]


class TestPriceRangeSections:
    def test_the_sample_renders_four_headers_per_garment_in_the_prd_format(
        self, results_at: AppTest
    ) -> None:
        assert range_headers(results_at) == [
            "Budget · 129-169 AED · 3 results",
            "Mid-range · 219-289 AED · 3 results",
            "Premium · 349-640 AED · 3 results",
            "Luxury · 890-2,400 AED · 3 results",
            "Budget · 89-129 AED · 3 results",
            "Mid-range · 179-249 AED · 3 results",
            "Premium · 399-475 AED · 2 results",
            "Luxury · 1,150 AED · 1 result",
        ]

    def test_every_header_matches_the_prd_label_format(self, results_at: AppTest) -> None:
        assert all(HEADER_FORMAT.match(header) for header in range_headers(results_at))

    def test_the_header_is_the_contracts_own_label(self, results_at: AppTest) -> None:
        expected = [tier.display_label for group in SAMPLE.groups for tier in group.tiers]

        assert range_headers(results_at) == expected

    def test_the_four_ranges_come_in_order_cheapest_to_most_expensive(
        self, results_at: AppTest
    ) -> None:
        names = [header.split(" · ")[0] for header in range_headers(results_at)]

        assert names == ["Budget", "Mid-range", "Premium", "Luxury"] * 2

    def test_an_empty_range_still_gets_its_header_and_says_so(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        group = make_garment_group()
        tiers = [
            make_tier_result(Tier.BUDGET, [], target_count=2, flags=[Flag.FEW_OPTIONS]),
            *group.tiers[1:],
        ]
        response = make_search_response(groups=[group.model_copy(update={"tiers": tiers})])
        install_pipeline(response)
        at.run()

        search(at)

        assert range_headers(at)[0] == "Budget · no results"
        texts = plain_texts(at)
        assert "No products in this price range." in texts
        assert "Showing 0 of 2. Few options in this range." in texts


class TestFlagsAreText:
    def test_a_range_that_could_not_be_filled_says_so_in_words(self, results_at: AppTest) -> None:
        texts = plain_texts(results_at)

        assert "Showing 2 of 3. Few options in this range." in texts
        assert "Showing 1 of 3. Few options in this range." in texts
        assert "Showing 3 of 3." in texts

    def test_an_over_budget_product_says_so_in_words(self, results_at: AppTest) -> None:
        shown = [text for text in plain_texts(results_at) if "Over your budget" in text]

        over_budget = [s for s in SAMPLE.products if Flag.OVER_BUDGET in s.flags]
        assert over_budget
        assert len(shown) == len(over_budget)

    def test_every_flag_has_wording_so_none_can_be_shown_blank(self) -> None:
        assert set(FLAG_TEXT) == set(Flag)
        assert all(FLAG_TEXT.values())

    def test_a_relative_range_flag_explains_what_luxury_means(self) -> None:
        tier = make_tier_result(Tier.LUXURY, flags=[Flag.RELATIVE_RANGE])

        assert "most expensive found" in facts_line(tier)


class TestResultCards:
    def test_each_link_goes_to_the_products_own_url_in_display_order(
        self, results_at: AppTest
    ) -> None:
        urls = [button.proto.url for button in link_buttons(results_at)]

        assert urls == [scored.product.product_url for scored in SAMPLE.products]

    def test_each_link_says_which_store_it_opens(self, results_at: AppTest) -> None:
        labels = [button.proto.label for button in link_buttons(results_at)]

        assert labels == [f"View product on {scored.product.store}" for scored in SAMPLE.products]

    def test_each_card_shows_title_store_price_currency_colour_and_reason(
        self, results_at: AppTest
    ) -> None:
        first = SAMPLE.groups[0].tiers[0].results[0]
        texts = plain_texts(results_at)

        assert first.product.title in texts
        assert any(f"Store: {first.product.store}" in text for text in texts)
        assert any(f"Colour: {first.product.colour}" in text for text in texts)
        assert first.reason in texts
        assert "129 AED" in [markdown.value.strip("*") for markdown in results_at.markdown]

    def test_each_card_has_a_picture_with_the_products_image_address(
        self, results_at: AppTest
    ) -> None:
        shown = [url for image in results_at.image for url in image.value]

        assert shown == [scored.product.image_url for scored in SAMPLE.products]

    def test_a_missing_colour_is_said_not_left_blank(self, results_at: AppTest) -> None:
        assert any("Colour: not listed" in text for text in plain_texts(results_at))

    def test_a_very_long_title_is_cut_to_a_readable_length_with_an_ellipsis(
        self, results_at: AppTest
    ) -> None:
        long_title = max((s.product.title for s in SAMPLE.products), key=len)
        assert len(long_title) > TITLE_MAX_CHARS

        shown = [text for text in plain_texts(results_at) if text.startswith(long_title[:30])]

        assert shown
        assert all(len(text) <= TITLE_MAX_CHARS and text.endswith("…") for text in shown)

    def test_a_missing_image_address_shows_a_placeholder_instead_of_a_picture(self) -> None:
        def script(scored) -> None:
            from app.components.result_card import render_result_card

            render_result_card(scored, key="card")

        # `model_copy` skips validation: the contract refuses an empty address, but the page must
        # still cope if one ever got through.
        product = make_product(1).model_copy(update={"image_url": ""})
        scored = make_scored_product(product)

        at = AppTest.from_function(script, args=(scored,)).run()

        assert not at.exception
        assert not at.image
        assert PLACEHOLDER_NO_IMAGE in [text.value for text in at.text]

    def test_a_product_link_that_is_not_https_is_not_offered(self) -> None:
        def script(scored) -> None:
            from app.components.result_card import render_result_card

            render_result_card(scored, key="card")

        product = make_product(1).model_copy(update={"product_url": "javascript:alert(1)"})
        scored = make_scored_product(product)

        at = AppTest.from_function(script, args=(scored,)).run()

        assert not at.get("link_button")
        assert "The store link is not available." in [text.value for text in at.text]


class TestGarmentGroups:
    def test_an_outfit_response_shows_one_group_per_garment(self, results_at: AppTest) -> None:
        groups = [h.value for h in results_at.header if h.value.startswith("Item ")]

        assert groups == ["Item 1: Outerwear", "Item 2: Shoes"]
        assert len(SAMPLE.groups) == 2

    def test_a_single_garment_response_shows_one_results_heading_and_no_item_headings(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(make_search_response())
        at.run()

        search(at)

        headers = [h.value for h in at.header]
        assert "Results" in headers
        assert not [h for h in headers if h.startswith("Item ")]
        assert len(range_headers(at)) == 4

    def test_four_garments_show_four_groups(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        categories = [Category.TOPS, Category.OUTERWEAR, Category.BOTTOMS, Category.SHOES]
        groups = [
            make_garment_group(category, item_index=index, per_tier=1)
            for index, category in enumerate(categories)
        ]
        install_pipeline(make_search_response(groups=groups))
        at.run()

        search(at)

        headings = [h.value for h in at.header if h.value.startswith("Item ")]
        assert headings == [
            "Item 1: Tops",
            "Item 2: Outerwear",
            "Item 3: Bottoms",
            "Item 4: Shoes",
        ]
        assert len(range_headers(at)) == 16
        assert len({button.key for button in link_buttons(at)}) == 16  # unique keys, no clash


class TestWholeResponse:
    @pytest.mark.parametrize("response", [SAMPLE, make_search_response()], ids=["outfit", "single"])
    def test_every_product_of_the_response_is_on_the_page_once(
        self, at: AppTest, install_pipeline: InstallPipeline, response: SearchResponse
    ) -> None:
        install_pipeline(response)
        at.run()

        search(at)

        assert len(link_buttons(at)) == response.result_count
        assert not at.exception

    def test_the_search_request_carries_the_typed_text(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        search(at, "wide-leg blue jeans for women")

        assert pipeline.calls[-1].req.text == "wide-leg blue jeans for women"
        assert pipeline.calls[-1].req.image is None
