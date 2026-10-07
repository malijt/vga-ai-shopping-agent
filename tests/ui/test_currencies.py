"""A second currency on the page (ADR 0006): a product priced in dinars keeps its own price and
shows an approximate dirham figure beside it, and a page of dirham products looks as it always did.

The figures are the pipeline's: the page reads ``ScoredProduct.base_price`` and the base currency
from the settings, and converts and compares nothing itself.
"""

import re

from streamlit.testing.v1 import AppTest

from tests.factories import (
    make_garment_group,
    make_product,
    make_scored_product,
    make_search_response,
    make_understand_result,
)
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import markdown_bodies, plain_texts, search
from vga.models import Flag, GarmentGroup, ScoredProduct, SearchResponse, Tier, TierResult

DINAR_TITLE = "Embellished Maxi Dress in Black"
DINAR_PRICE_LINE = "245.000 KWD (about 2,920 AED)"
"""What the card of the dinar product reads: 245 KWD at 11.92 AED is 2,920.40 AED, shown to the
nearest 10 dirhams from 100 up (``vga.money.approximate_amount``)."""

# Everything a price line may hold: a number, a currency code and, for another currency, the
# approximate figure. No markup, no store-supplied text.
PRICE_LINE = re.compile(r"^\d[\d,.]* [A-Z]{3}( \(about \d[\d,]* [A-Z]{3}\))?$")


def dinar_scored(**overrides: object) -> ScoredProduct:
    """The dinar dress as the price-range shaper delivers it: 245.000 KWD, 2,920.40 AED."""
    product = make_product(
        7, title=DINAR_TITLE, price=245.0, currency="KWD", store="Hamsa", colour="black"
    )
    fields: dict[str, object] = {"base_price": 2920.4, "tier": Tier.LUXURY}
    return make_scored_product(product, **{**fields, **overrides})


def mixed_currency_response() -> SearchResponse:
    """One garment whose Luxury range holds a dirham product and the dinar dress, its span in
    dirhams as the contract needs (2,400 to 2,921)."""
    dirham = make_scored_product(
        make_product(8, title="Silk Evening Gown", price=2400.0), tier=Tier.LUXURY
    )
    luxury = TierResult(
        name=Tier.LUXURY,
        price_min=2400.0,
        price_max=2921.0,
        currency="AED",
        target_count=2,
        count=2,
        results=[dirham, dinar_scored()],
    )
    plain = make_garment_group()
    group = GarmentGroup(item_index=0, category=plain.category, tiers=[*plain.tiers[:3], luxury])
    return make_search_response(groups=[group])


def card_page(scored: ScoredProduct, base_currency: str = "AED") -> AppTest:
    """One result card on its own, drawn the way the price range section draws it."""

    def script(card, base) -> None:  # runs on its own, so it imports what it uses
        from app.components.result_card import render_result_card as draw

        draw(card, key="card", base_currency=base)

    return AppTest.from_function(script, args=(scored, base_currency)).run()


def bold_lines(at: AppTest) -> list[str]:
    """The price lines (a card's one bold line), without the markers. The page has other bold
    text ("Who is this for?", "Item 2"), but only a price names a currency code."""
    return [
        markdown.value.strip("*")
        for markdown in at.markdown
        if markdown.value.startswith("**")
        and markdown.value.endswith("**")
        and re.search(r"[A-Z]{3}", markdown.value)
    ]


class TestTheCardOfAProductInAnotherCurrency:
    def test_it_shows_the_stores_own_price_and_the_approximate_dirham_figure(self) -> None:
        at = card_page(dinar_scored())

        assert not at.exception
        assert DINAR_PRICE_LINE in bold_lines(at)

    def test_a_dirham_product_shows_the_plain_form_it_always_had(self) -> None:
        at = card_page(make_scored_product(make_product(1, price=535.0)))

        assert bold_lines(at) == ["535 AED"]

    def test_a_dirham_price_with_cents_and_thousands_reads_as_before(self) -> None:
        cents = card_page(make_scored_product(make_product(1, price=89.5)))
        thousands = card_page(make_scored_product(make_product(1, price=1499.0)))

        assert bold_lines(cents) == ["89.50 AED"]
        assert bold_lines(thousands) == ["1,499 AED"]

    def test_a_product_with_no_dirham_figure_shows_only_its_own_price(self) -> None:
        # A currency with no rate has no base figure; the card says what it knows and no more.
        at = card_page(dinar_scored(base_price=None))

        assert bold_lines(at) == ["245.000 KWD"]

    def test_the_base_currency_comes_from_the_caller_not_from_the_code(self) -> None:
        at = card_page(dinar_scored(base_price=3000.0), base_currency="SAR")

        assert bold_lines(at) == ["245.000 KWD (about 3,000 SAR)"]

    def test_the_price_line_holds_only_numbers_and_currency_codes(self) -> None:
        for scored in (dinar_scored(), make_scored_product(make_product(1, price=89.5))):
            at = card_page(scored)

            assert all(PRICE_LINE.match(line) for line in bold_lines(at))

    def test_a_flag_is_the_pipelines_word_and_the_page_adds_none_of_its_own(self) -> None:
        # 245 is below any budget in the raw number, 2,920 AED above it. The card says what the
        # pipeline decided (it measured the AED figure) and nothing else.
        flagged = card_page(dinar_scored(flags=[Flag.OVER_BUDGET]))
        unflagged = card_page(dinar_scored())

        assert any("Over your budget" in text.value for text in flagged.text)
        assert not any("Over your budget" in text.value for text in unflagged.text)


class TestThePageWithTwoCurrencies:
    def test_the_dinar_card_and_the_dirham_card_sit_side_by_side(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(mixed_currency_response())
        at.run()

        search(at)

        assert not at.exception
        lines = bold_lines(at)
        assert DINAR_PRICE_LINE in lines
        assert "2,400 AED" in lines
        assert DINAR_TITLE in plain_texts(at)

    def test_every_price_line_on_the_page_is_plain_numbers_and_codes(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(mixed_currency_response())
        at.run()

        search(at)

        assert all(PRICE_LINE.match(line) for line in bold_lines(at))

    def test_the_range_header_stays_in_dirhams(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        install_pipeline(mixed_currency_response())
        at.run()

        search(at)

        headers = [subheader.value for subheader in at.subheader]
        assert headers[-1] == "Luxury · 2,400-2,921 AED · 2 results"

    def test_the_card_is_the_one_the_pipeline_flagged_over_budget(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        dirham = make_scored_product(make_product(8, price=2400.0), tier=Tier.LUXURY)
        flagged = dinar_scored(flags=[Flag.OVER_BUDGET])
        luxury = TierResult(
            name=Tier.LUXURY,
            price_min=2400.0,
            price_max=2921.0,
            currency="AED",
            target_count=2,
            count=2,
            results=[dirham, flagged],
        )
        plain = make_garment_group()
        group = GarmentGroup(
            item_index=0, category=plain.category, tiers=[*plain.tiers[:3], luxury]
        )
        install_pipeline(
            make_search_response(
                groups=[group], understood=make_understand_result(budget={"max_price": 400})
            )
        )
        at.run()

        search(at)

        shown = [text.value for text in at.text if "Over your budget" in text.value]
        assert len(shown) == 1
        assert "Store: Hamsa" in shown[0]


def test_a_page_of_dirham_products_has_no_approximate_figure(
    at: AppTest, install_pipeline: InstallPipeline
) -> None:
    install_pipeline(make_search_response())
    at.run()

    search(at)

    assert not any("about" in line for line in bold_lines(at))
    assert not any("about" in body for body in markdown_bodies(at) if "AED" in body)
