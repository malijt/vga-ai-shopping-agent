"""Untrusted text (plan 10.2.3, CLAUDE.md "Rendering"): anything that came from a store or from
the shopper is shown as plain text. A title with HTML or markdown in it appears exactly as typed,
and no function that reads markdown or HTML ever receives it.
"""

import pytest
from app.components.result_card import REASON_MAX_CHARS, STORE_MAX_CHARS, TITLE_MAX_CHARS
from streamlit.testing.v1 import AppTest

from tests.factories import (
    make_garment_group,
    make_product,
    make_scored_product,
    make_search_response,
    make_store_report,
    make_tier_result,
)
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import link_buttons, markdown_bodies, plain_texts, search
from vga.models import Flag, GarmentGroup, StoreStatus, Tier

HOSTILE_TITLE = (
    "<script>alert(1)</script> <b>bold</b> **md** _it_ [x](https://evil.example) "
    "![p](https://evil.example/p.png) :smile:"
)
HOSTILE_STORE = "<b>Evil</b> *Store* [x](https://evil.example) :smile:"
HOSTILE_COLOUR = "**red** <i>x</i>"
HOSTILE_REASON = "Matches **your** colour <u>and</u> [more](https://evil.example) www.evil.example"
HOSTILE_WARNING = "<img src=x onerror=alert(1)> **Evil Store** was skipped"
HOSTILE_STORE_ID = "evil-store"
HOSTILE_SKIP_REASON = "Skipped because [click here](https://evil.example) **now**"

# The strings must be short enough to be shown whole (longer ones are cut, tested elsewhere).
assert len(HOSTILE_TITLE) < TITLE_MAX_CHARS
assert len(HOSTILE_STORE) < STORE_MAX_CHARS
assert len(HOSTILE_REASON) < REASON_MAX_CHARS

# Distinctive pieces of the strings above. None may appear in anything that reads markdown. The
# link-button label is the one exception (it must hold the store name), tested on its own below.
FRAGMENTS = ("evil", "alert(", "smile", "<script", "onerror", "[x]", "**md**", "**your**", "<b>")


def hostile_response():
    product = make_product(
        1, title=HOSTILE_TITLE, store=HOSTILE_STORE, colour=HOSTILE_COLOUR, price=100.0
    )
    scored = make_scored_product(product, reason=HOSTILE_REASON, flags=[Flag.OVER_BUDGET])
    budget = make_tier_result(Tier.BUDGET, [product]).model_copy(update={"results": [scored]})
    filler = make_garment_group()
    group = GarmentGroup(item_index=0, category=filler.category, tiers=[budget, *filler.tiers[1:]])
    return make_search_response(
        groups=[group],
        warnings=[HOSTILE_WARNING],
        stores_used=[],
        stores_skipped=[
            make_store_report(
                StoreStatus.BLOCKED, store_id=HOSTILE_STORE_ID, reason=HOSTILE_SKIP_REASON
            )
        ],
    )


@pytest.fixture
def hostile_at(at: AppTest, install_pipeline: InstallPipeline) -> AppTest:
    install_pipeline(hostile_response())
    at.run()
    return search(at)


class TestStoreTextShowsAsTyped:
    def test_the_page_renders_without_error(self, hostile_at: AppTest) -> None:
        assert not hostile_at.exception

    def test_a_title_with_html_and_markdown_appears_as_literal_text(
        self, hostile_at: AppTest
    ) -> None:
        assert HOSTILE_TITLE in plain_texts(hostile_at)

    def test_the_store_name_colour_and_reason_appear_as_literal_text(
        self, hostile_at: AppTest
    ) -> None:
        texts = "\n".join(plain_texts(hostile_at))

        assert f"Store: {HOSTILE_STORE}" in texts
        assert f"Colour: {HOSTILE_COLOUR}" in texts
        assert HOSTILE_REASON in plain_texts(hostile_at)

    def test_warnings_and_skipped_store_reasons_appear_as_literal_text(
        self, hostile_at: AppTest
    ) -> None:
        texts = "\n".join(plain_texts(hostile_at))

        assert f"- {HOSTILE_WARNING}" in texts
        assert f"{HOSTILE_STORE_ID}: {HOSTILE_SKIP_REASON}" in texts

    def test_the_skipped_store_expander_label_holds_no_store_text(
        self, hostile_at: AppTest
    ) -> None:
        labels = [expander.label for expander in hostile_at.expander]

        assert "Skipped stores (1)" in labels


class TestNothingUntrustedReachesAMarkdownReader:
    def test_no_hostile_text_is_in_any_markdown_element_heading_or_label(
        self, hostile_at: AppTest
    ) -> None:
        readers = [
            body
            for body in markdown_bodies(hostile_at)
            if not body.startswith("View product on ")  # the sanitised link label, tested below
        ]

        assert readers
        for body in readers:
            for fragment in FRAGMENTS:
                assert fragment not in body.lower(), f"{fragment!r} reached {body!r}"

    def test_no_markdown_element_allows_html(self, hostile_at: AppTest) -> None:
        elements = [*hostile_at.markdown, *hostile_at.caption]

        assert elements
        assert not any(element.allow_html for element in elements)

    def test_the_link_label_holds_only_plain_words_from_the_store_name(
        self, hostile_at: AppTest
    ) -> None:
        label = link_buttons(hostile_at)[0].proto.label

        assert label.startswith("View product on ")
        assert set(label.removeprefix("View product on ")) <= set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '-…"
        )

    def test_the_link_goes_to_the_products_url_and_nowhere_else(self, hostile_at: AppTest) -> None:
        links = link_buttons(hostile_at)

        assert [button.proto.url for button in links[:1]] == [
            hostile_response().groups[0].tiers[0].results[0].product.product_url
        ]
        assert not any("evil.example/p.png" in str(button.proto.url) for button in links)

    def test_the_picture_alt_text_is_the_plain_title_and_the_address_is_the_products(
        self, hostile_at: AppTest
    ) -> None:
        product = hostile_response().groups[0].tiers[0].results[0].product

        first = hostile_at.image[0]

        assert first.value == [product.image_url]
        assert first.proto.imgs[0].alt == HOSTILE_TITLE


class TestContentExtremes:
    def test_text_with_control_and_direction_override_characters_is_cleaned(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        title = "Blazer\u202eevil\u2066 \x00 text\nwith\tbreaks"
        product = make_product(1, title=title)
        budget = make_tier_result(Tier.BUDGET, [product])
        filler = make_garment_group()
        group = GarmentGroup(
            item_index=0, category=filler.category, tiers=[budget, *filler.tiers[1:]]
        )
        install_pipeline(make_search_response(groups=[group]))
        at.run()

        search(at)

        assert "Blazerevil text with breaks" in plain_texts(at)

    def test_arabic_titles_and_store_names_survive_unchanged(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        product = make_product(1, title="جاكيت جلد أسود للرجال", store="متجر الأزياء")
        budget = make_tier_result(Tier.BUDGET, [product])
        filler = make_garment_group()
        group = GarmentGroup(
            item_index=0, category=filler.category, tiers=[budget, *filler.tiers[1:]]
        )
        install_pipeline(make_search_response(groups=[group]))
        at.run()

        search(at)

        assert "جاكيت جلد أسود للرجال" in plain_texts(at)
        assert link_buttons(at)[0].proto.label == "View product on متجر الأزياء"
