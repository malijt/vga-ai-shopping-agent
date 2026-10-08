"""The note about the approximate figure (ADR 0006).

The budget box says "Budget in AED", and a dinar card shows "about 2,920 AED". One plain sentence,
once on the page, says that the approximate figure is the one price ranges and the budget go by. It
is not repeated on every card, and a page of dirham products does not have it.
"""

from streamlit.testing.v1 import AppTest

from app.copy import approximate_price_note
from tests.factories import (
    make_garment_group,
    make_product,
    make_scored_product,
    make_search_response,
    make_understand_result,
)
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import chip_budget, plain_texts, search
from tests.ui.test_currencies import bold_lines, dinar_scored, mixed_currency_response
from vga.models import GarmentGroup, SearchResponse, Tier, TierResult

NOTE = (
    "A price in another currency also shows an approximate AED figure, and price ranges "
    "and your budget go by that figure."
)


def two_dinar_response() -> SearchResponse:
    """Three cards in the Luxury range, two of them in dinars."""
    dirham = make_scored_product(make_product(8, price=2400.0), tier=Tier.LUXURY)
    second = make_scored_product(
        make_product(10, price=250.0, currency="KWD", store="Hamsa"),
        base_price=2980.0,
        tier=Tier.LUXURY,
    )
    luxury = TierResult(
        name=Tier.LUXURY,
        price_min=2400.0,
        price_max=2980.0,
        currency="AED",
        target_count=3,
        count=3,
        results=[dirham, dinar_scored(), second],
    )
    plain = make_garment_group()
    group = GarmentGroup(item_index=0, category=plain.category, tiers=[*plain.tiers[:3], luxury])
    return make_search_response(groups=[group])


def test_the_note_is_one_plain_sentence_naming_the_base_currency() -> None:
    assert approximate_price_note("AED") == NOTE
    assert "approximate SAR figure" in approximate_price_note("SAR")


def test_it_appears_once_however_many_cards_show_an_approximate_figure(
    at: AppTest, install_pipeline: InstallPipeline
) -> None:
    install_pipeline(two_dinar_response())
    at.run()

    search(at)

    assert len([line for line in bold_lines(at) if "about" in line]) == 2
    assert plain_texts(at).count(NOTE) == 1


def test_it_sits_above_the_first_price_range(
    at: AppTest, install_pipeline: InstallPipeline
) -> None:
    install_pipeline(mixed_currency_response())
    at.run()

    search(at)

    shown = [
        str(node.value) for node in at.main if getattr(node, "type", "") in {"text", "subheader"}
    ]
    first_range = next(text for text in shown if text.startswith("Budget · "))
    assert shown.index(NOTE) < shown.index(first_range)


def test_it_is_not_on_a_page_of_dirham_products(
    at: AppTest, install_pipeline: InstallPipeline
) -> None:
    install_pipeline(make_search_response())
    at.run()

    search(at)

    assert not any("approximate" in text for text in plain_texts(at))


def test_it_is_not_in_a_markdown_element(at: AppTest, install_pipeline: InstallPipeline) -> None:
    install_pipeline(mixed_currency_response())
    at.run()

    search(at)

    assert not any("approximate" in markdown.value for markdown in at.markdown)


def test_the_budget_box_still_names_the_currency_the_budget_is_in(
    at: AppTest, install_pipeline: InstallPipeline
) -> None:
    install_pipeline(
        make_search_response(understood=make_understand_result(budget={"max_price": 400}))
    )
    at.run()

    search(at)

    assert chip_budget(at).label == "Budget in AED (optional)"
