"""The two public steps: ``prefilter_and_score`` and ``apply_image_scores``."""

import json
import random
from pathlib import Path

import pytest

from tests.factories import (
    make_budget,
    make_item_intent,
    make_product,
    make_scored_product,
    make_scores,
    make_settings,
)
from vga.models import Category, Flag, Gender, GenderSource, Product, ScoredProduct
from vga.rank import apply_image_scores, combine_scores, prefilter_and_score

SETTINGS = make_settings()
ITEM = make_item_intent()  # outerwear, black, "oversized blazer"
SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "store-qualification" / "samples"


def product(title: str, index: int = 1, **overrides: object) -> Product:
    return make_product(index, title=title, **{"category": None, "colour": None, **overrides})


def titles(scored: list[ScoredProduct]) -> list[str]:
    return [entry.product.title for entry in scored]


# --------------------------------------------------------------------------------------------
# Step 1: prefilter_and_score
# --------------------------------------------------------------------------------------------


def test_scores_have_text_and_price_and_no_image_and_a_total_from_the_available_parts() -> None:
    [scored] = prefilter_and_score(
        ITEM, [product("Black Oversized Blazer")], make_budget(), SETTINGS
    )

    assert scored.scores.image is None
    assert scored.scores.text == pytest.approx(1.0)
    assert scored.scores.price == 1.0
    assert scored.scores.total == pytest.approx(
        combine_scores(scored.scores.text, None, scored.scores.price, SETTINGS.ranking_weights)
    )


def test_products_come_back_best_first() -> None:
    products = [
        product("Black Shirt", 1),
        product("Black Oversized Blazer", 2),
        product("Black Blazer", 3),
        product("Black Jacket", 4),
    ]

    scored = prefilter_and_score(ITEM, products, None, SETTINGS)

    assert titles(scored) == ["Black Oversized Blazer", "Black Blazer", "Black Jacket"]


def test_the_wrong_category_and_out_of_scope_and_out_of_stock_are_dropped() -> None:
    products = [
        product("Black Oversized Blazer", 1),
        product("Black Cotton Shirt", 2),
        product("Black Blazer Mini Dress", 3),
        product("Black Leather Tote Bag", 4),
        product("Black Blazer Sold Out", 5, in_stock=False),
    ]

    scored = prefilter_and_score(ITEM, products, None, SETTINGS)

    assert titles(scored) == ["Black Oversized Blazer"]


def test_unknown_stock_and_unknown_category_are_kept() -> None:
    products = [
        product("Black Oversized Blazer", 1, in_stock=None),
        product("Black Oversized", 2),
    ]

    scored = prefilter_and_score(ITEM, products, None, SETTINGS)

    assert set(titles(scored)) == {"Black Oversized Blazer", "Black Oversized"}
    by_title = {entry.product.title: entry for entry in scored}
    assert by_title["Black Oversized Blazer"].scores.text > by_title["Black Oversized"].scores.text


def test_over_budget_products_are_kept_and_flagged_not_dropped() -> None:
    products = [
        product("Black Oversized Blazer", 1, price=300.0),
        product("Black Blazer", 2, price=900.0),
    ]

    scored = prefilter_and_score(ITEM, products, make_budget(max_price=400), SETTINGS)

    by_title = {entry.product.title: entry for entry in scored}
    assert by_title["Black Oversized Blazer"].flags == []
    assert by_title["Black Blazer"].flags == [Flag.OVER_BUDGET]
    assert by_title["Black Blazer"].scores.price < by_title["Black Oversized Blazer"].scores.price


def test_without_a_budget_nothing_is_flagged_and_price_is_neutral() -> None:
    settings = make_settings(neutral_price_score=0.4)

    scored = prefilter_and_score(ITEM, [product("Black Blazer", price=9999.0)], None, settings)

    assert scored[0].flags == []
    assert scored[0].scores.price == 0.4


def test_the_inferred_category_is_written_onto_the_product() -> None:
    products = [product("Black Oversized Blazer", 1), product("Black Oversized", 2)]

    scored = prefilter_and_score(ITEM, products, None, SETTINGS)

    by_title = {entry.product.title: entry.product for entry in scored}
    assert by_title["Black Oversized Blazer"].category is Category.OUTERWEAR
    assert by_title["Black Oversized"].category is None


def test_the_input_products_are_not_modified() -> None:
    original = product("Black Oversized Blazer")

    prefilter_and_score(ITEM, [original], None, SETTINGS)

    assert original.category is None


def test_a_missing_budget_and_an_empty_list_are_fine() -> None:
    assert prefilter_and_score(ITEM, [], None, SETTINGS) == []
    assert prefilter_and_score(ITEM, [], make_budget(), SETTINGS) == []


def test_explicit_gender_drops_the_other_gender_but_an_inferred_one_does_not() -> None:
    products = [product("Women's Black Blazer", 1), product("Men's Black Blazer", 2)]
    explicit = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)
    inferred = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.INFERRED)

    assert titles(prefilter_and_score(explicit, products, None, SETTINGS)) == ["Men's Black Blazer"]
    assert len(prefilter_and_score(inferred, products, None, SETTINGS)) == 2


def test_the_order_does_not_depend_on_the_input_order() -> None:
    products = [product("Black Blazer", i) for i in range(1, 9)]  # equal scores, different URLs
    expected = [entry.product.key for entry in prefilter_and_score(ITEM, products, None, SETTINGS)]

    for seed in range(5):
        shuffled = random.Random(seed).sample(products, len(products))
        got = [entry.product.key for entry in prefilter_and_score(ITEM, shuffled, None, SETTINGS)]

        assert got == expected


def test_every_result_carries_a_reason() -> None:
    scored = prefilter_and_score(ITEM, [product("Black Oversized Blazer")], make_budget(), SETTINGS)

    assert scored[0].reason.endswith("Sold by Demo Store.")


# --------------------------------------------------------------------------------------------
# The real "black blazer" searches (docs/store-qualification/samples)
# --------------------------------------------------------------------------------------------


def _sample_products(path: str) -> list[Product]:
    sample = json.loads((SAMPLES / path).read_text(encoding="utf-8"))
    raw = sample["resources"]["results"]["products"]
    return [
        make_product(
            index,
            title=entry["title"],
            price=float(entry["price"]),
            category=None,
            colour=None,
            in_stock=entry["available"],
        )
        for index, entry in enumerate(raw, start=1)
    ]


def test_club_l_black_blazer_search_keeps_only_the_blazer() -> None:
    """3 of its 4 results are dresses; the Shopify `type` says DRESS or JACKETS & BLAZERS."""
    scored = prefilter_and_score(
        ITEM, _sample_products("club-l-london/suggest-black-blazer.json"), None, SETTINGS
    )

    assert titles(scored) == ["Vergia | Black Lace Tailored-Blazer"]


def test_oh_polly_black_blazer_search_drops_the_blazer_mini_dress_and_ranks_the_rest() -> None:
    """Oh Polly files the mini dress under "Coats & Jackets"; none of its blazers is black."""
    products = _sample_products("oh-polly/suggest-black-blazer.json")

    scored = prefilter_and_score(ITEM, products, make_budget(max_price=300), SETTINGS)

    assert len(scored) == 3
    assert all("Dress" not in entry.product.title for entry in scored)
    assert scored[0].scores.total >= scored[-1].scores.total


def test_black_heels_lead_the_club_l_shoe_search_for_black_heels() -> None:
    shoes = make_item_intent(
        category=Category.SHOES, colour="black", style=None, search_keywords=["black heels"]
    )

    scored = prefilter_and_score(
        shoes, _sample_products("club-l-london/suggest-shoes.json"), None, SETTINGS
    )

    # All four are shoes. The two black heels come first; a black boot and pink heels are each
    # right on one count (colour or "heels") and follow.
    assert len(scored) == 4
    assert all(entry.product.category is Category.SHOES for entry in scored)
    leaders = {entry.product.title.split(" | ")[0] for entry in scored[:2]}
    assert leaders == {"Covergirl", "Doll Drama"}


# --------------------------------------------------------------------------------------------
# Step 2: apply_image_scores
# --------------------------------------------------------------------------------------------


def _scored(*specs: tuple[str, float, float]) -> list[ScoredProduct]:
    """ScoredProducts with the given (title, text, price) and no image score."""
    return [
        make_scored_product(
            product(title, index),
            scores=make_scores(
                text=text,
                price=price,
                total=combine_scores(text, None, price, SETTINGS.ranking_weights),
            ),
            reason="A reason.",
        )
        for index, (title, text, price) in enumerate(specs, start=1)
    ]


def test_an_empty_mapping_gives_text_and_price_only() -> None:
    scored = _scored(("A", 0.8, 0.5), ("B", 0.6, 1.0))

    result = apply_image_scores(scored, {}, SETTINGS)

    assert all(entry.scores.image is None for entry in result)
    assert {entry.product.title: entry.scores.total for entry in result} == pytest.approx(
        {
            "A": combine_scores(0.8, None, 0.5, SETTINGS.ranking_weights),
            "B": combine_scores(0.6, None, 1.0, SETTINGS.ranking_weights),
        }
    )


def test_image_scores_are_added_the_totals_recomputed_and_the_order_follows() -> None:
    scored = _scored(("Text leader", 0.9, 0.5), ("Image leader", 0.7, 0.5))
    keys = {entry.product.title: entry.product.key for entry in scored}

    before = apply_image_scores(scored, {}, SETTINGS)
    after = apply_image_scores(
        scored, {keys["Text leader"]: 0.0, keys["Image leader"]: 1.0}, SETTINGS
    )

    assert titles(before) == ["Text leader", "Image leader"]
    assert titles(after) == ["Image leader", "Text leader"]
    leader = after[0]
    assert leader.scores.image == 1.0
    assert leader.scores.total == pytest.approx(
        combine_scores(0.7, 1.0, 0.5, SETTINGS.ranking_weights)
    )


def test_a_missing_or_none_image_score_renormalises_that_product() -> None:
    scored = _scored(("Scored", 0.8, 0.5), ("Missing", 0.8, 0.5), ("None", 0.8, 0.5))
    keys = [entry.product.key for entry in scored]

    result = apply_image_scores(scored, {keys[0]: 0.8, keys[2]: None}, SETTINGS)

    by_title = {entry.product.title: entry.scores for entry in result}
    text_and_price = combine_scores(0.8, None, 0.5, SETTINGS.ranking_weights)
    assert by_title["Scored"].image == 0.8
    assert by_title["Missing"].image is None
    assert by_title["None"].image is None
    assert by_title["Missing"].total == pytest.approx(text_and_price)
    assert by_title["None"].total == pytest.approx(text_and_price)


def test_products_below_the_minimum_match_score_are_removed() -> None:
    settings = make_settings(min_match_score=0.5)
    scored = _scored(("Strong", 0.9, 1.0), ("Weak", 0.1, 0.2), ("Edge", 0.5, 0.5))

    result = apply_image_scores(scored, {}, settings)

    assert titles(result) == ["Strong", "Edge"]  # Edge is exactly 0.5 and stays


def test_an_image_score_can_lift_a_product_over_the_minimum() -> None:
    settings = make_settings(min_match_score=0.5)
    scored = _scored(("Weak text", 0.3, 0.3))
    key = scored[0].product.key

    assert apply_image_scores(scored, {}, settings) == []
    assert titles(apply_image_scores(scored, {key: 1.0}, settings)) == ["Weak text"]


def test_a_low_image_score_can_push_a_product_under_the_minimum() -> None:
    settings = make_settings(min_match_score=0.5)
    scored = _scored(("Looks different", 0.55, 0.55))
    key = scored[0].product.key

    assert titles(apply_image_scores(scored, {}, settings)) == ["Looks different"]
    assert apply_image_scores(scored, {key: 0.0}, settings) == []


def test_the_minimum_score_is_taken_from_settings() -> None:
    scored = _scored(("A", 0.4, 0.4))

    assert apply_image_scores(scored, {}, make_settings(min_match_score=0.3)) != []
    assert apply_image_scores(scored, {}, make_settings(min_match_score=0.5)) == []


@pytest.mark.parametrize(
    ("given", "stored"),
    [(1.7, 1.0), (-0.4, 0.0), (float("nan"), None), (float("inf"), None)],
)
def test_out_of_range_image_scores_are_clamped_and_nan_means_not_scored(
    given: float, stored: float | None
) -> None:
    scored = _scored(("A", 0.8, 0.5))

    [result] = apply_image_scores(scored, {scored[0].product.key: given}, SETTINGS)

    assert result.scores.image == stored


def test_the_reason_and_flags_survive_and_an_empty_reason_gets_a_plain_one() -> None:
    with_reason = make_scored_product(
        product("A", 1), reason="Kept as is.", flags=[Flag.OVER_BUDGET]
    )
    without_reason = make_scored_product(
        product("B", 2, store="Gulf Threads"), reason="", flags=[Flag.OVER_BUDGET]
    )

    result = {
        entry.product.title: entry
        for entry in apply_image_scores([with_reason, without_reason], {}, SETTINGS)
    }

    assert result["A"].reason == "Kept as is."
    assert result["A"].flags == [Flag.OVER_BUDGET]
    assert result["B"].reason == "Above your budget. Sold by Gulf Threads."


def test_the_inputs_are_not_modified() -> None:
    scored = _scored(("A", 0.8, 0.5))
    snapshot = scored[0].model_dump()

    apply_image_scores(scored, {scored[0].product.key: 0.9}, SETTINGS)

    assert scored[0].model_dump() == snapshot


def test_the_weights_come_from_settings() -> None:
    scored = _scored(("Text strong", 0.9, 0.5), ("Image strong", 0.5, 0.5))
    keys = {entry.product.title: entry.product.key for entry in scored}
    images = {keys["Text strong"]: 0.0, keys["Image strong"]: 1.0}
    image_heavy = make_settings(ranking_weights={"text": 0.1, "image": 0.8, "price": 0.1})
    text_heavy = make_settings(ranking_weights={"text": 0.8, "image": 0.1, "price": 0.1})

    assert titles(apply_image_scores(scored, images, image_heavy))[0] == "Image strong"
    assert titles(apply_image_scores(scored, images, text_heavy))[0] == "Text strong"


def test_equal_totals_keep_a_stable_order() -> None:
    scored = _scored(("A", 0.7, 0.5), ("B", 0.7, 0.5), ("C", 0.7, 0.5))
    expected = [entry.product.key for entry in apply_image_scores(scored, {}, SETTINGS)]

    for seed in range(5):
        shuffled = random.Random(seed).sample(scored, len(scored))

        assert [e.product.key for e in apply_image_scores(shuffled, {}, SETTINGS)] == expected


# --------------------------------------------------------------------------------------------
# The two steps together
# --------------------------------------------------------------------------------------------


def test_the_full_flow_without_an_image_ranker() -> None:
    products = [
        product("Black Oversized Blazer", 1, price=250.0, store="Gulf Threads"),
        product("Black Blazer", 2, price=450.0, store="Oasis Luxe"),
        product("Red Blazer", 3, price=300.0),
        product("Black Shirt", 4),
        product("Black Dress", 5),
    ]

    stage_one = prefilter_and_score(ITEM, products, make_budget(max_price=400), SETTINGS)
    final = apply_image_scores(stage_one, {}, SETTINGS)

    assert titles(final) == ["Black Oversized Blazer", "Black Blazer", "Red Blazer"]
    assert [entry.flags for entry in final] == [[], [Flag.OVER_BUDGET], []]
    assert final[0].reason == (
        "Black, the colour you asked for. Within your 400 AED budget. Sold by Gulf Threads."
    )
    assert final[1].reason == (
        "Black, the colour you asked for. Above your 400 AED budget. Sold by Oasis Luxe."
    )
    assert all(entry.scores.image is None for entry in final)
