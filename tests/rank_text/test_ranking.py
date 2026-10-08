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


def test_a_dress_request_keeps_abayas_and_kaftans_and_drops_the_rest() -> None:
    request = make_item_intent(
        category=Category.DRESSES, colour="black", style="abaya", search_keywords=["black abaya"]
    )
    products = [
        product("Neda Plain Abaya Front Open with Buttons", 1),
        product("Embroidered Black Abaya Dress Design", 2),
        product("JALILA GREEN FLORAL KAFTAN", 3),
        product("Black Cotton Shirt", 4),
        product("Black Chiffon Sheila - Custom Size", 5),
        product("Black Oversized Blazer", 6),
    ]

    scored = prefilter_and_score(request, products, None, SETTINGS)

    assert set(titles(scored)) == {
        "Neda Plain Abaya Front Open with Buttons",
        "Embroidered Black Abaya Dress Design",
        "JALILA GREEN FLORAL KAFTAN",
    }
    assert all(entry.product.category is Category.DRESSES for entry in scored)


def test_a_dress_request_ranks_the_requested_garment_above_another_dress_shape() -> None:
    request = make_item_intent(
        category=Category.DRESSES, colour="black", style="abaya", search_keywords=["black abaya"]
    )
    products = [
        product("Black Satin Midi Dress", 1),
        product("Black Open Front Abaya", 2),
    ]

    scored = prefilter_and_score(request, products, None, SETTINGS)

    assert titles(scored) == ["Black Open Front Abaya", "Black Satin Midi Dress"]


def test_a_thobe_request_ranks_a_dishdasha_and_a_kandora_as_the_garment_asked_for() -> None:
    """Thobe, dishdasha and kandura are the same men's robe under a Saudi, a Kuwaiti and an
    Emirati name (Al Jazeera Clothing and a UAE thobe store sell it under the last two)."""
    request = make_item_intent(
        category=Category.DRESSES, colour=None, style=None, search_keywords=["thobe"]
    )
    products = [
        product("Burgundy Kaftan", 1),
        product("White Kuwaiti Dishdasha-Mens", 2),
        product("Khaki Green Emirati Kandora - Men", 3),
        product("Mens Qatari Thobe 3 Pcs Set", 4),
    ]

    scored = prefilter_and_score(request, products, None, SETTINGS)

    assert titles(scored)[-1] == "Burgundy Kaftan"
    assert all(entry.scores.text == pytest.approx(1.0) for entry in scored[:3])
    assert scored[-1].scores.text < 0.5
    assert all(entry.product.category is Category.DRESSES for entry in scored)


def test_a_kandura_request_ranks_a_thobe_as_the_garment_asked_for() -> None:
    request = make_item_intent(
        category=Category.DRESSES, colour=None, style=None, search_keywords=["kandura"]
    )
    products = [product("Burgundy Kaftan", 1), product("Mens Qatari Thobe 3 Pcs Set", 2)]

    scored = prefilter_and_score(request, products, None, SETTINGS)

    assert titles(scored) == ["Mens Qatari Thobe 3 Pcs Set", "Burgundy Kaftan"]


def test_a_daraa_request_does_not_count_a_kaftan_as_a_daraa() -> None:
    request = make_item_intent(
        category=Category.DRESSES, colour=None, style=None, search_keywords=["daraa"]
    )
    products = [product("Burgundy Kaftan", 1), product("Dara'a 2026", 2)]

    scored = prefilter_and_score(request, products, None, SETTINGS)

    assert titles(scored) == ["Dara'a 2026", "Burgundy Kaftan"]
    assert scored[0].scores.text == pytest.approx(1.0)
    assert scored[1].scores.text < 0.5


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


def test_a_dinar_product_is_compared_with_an_aed_budget_in_dirhams() -> None:
    fx = make_settings(fx_rates={"KWD": 10.0})  # 1 KWD is 10 AED
    products = [
        product("Black Oversized Blazer", 1, price=35.0, currency="KWD"),  # AED 350
        product("Black Blazer", 2, price=45.0, currency="KWD"),  # AED 450
        product("Black Jacket", 3, price=300.0, currency="AED"),
    ]

    scored = prefilter_and_score(ITEM, products, make_budget(max_price=400), fx)

    by_title = {entry.product.title: entry for entry in scored}
    assert by_title["Black Oversized Blazer"].flags == []
    assert by_title["Black Oversized Blazer"].scores.price == 1.0
    assert by_title["Black Blazer"].flags == [Flag.OVER_BUDGET]
    assert 0 < by_title["Black Blazer"].scores.price < 1.0
    assert by_title["Black Jacket"].flags == []
    assert "Within your 400 AED budget." in by_title["Black Oversized Blazer"].reason
    assert "Above your 400 AED budget." in by_title["Black Blazer"].reason


def test_a_product_in_a_currency_with_no_rate_is_neutral_and_makes_no_budget_claim() -> None:
    fx = make_settings(fx_rates={"KWD": 10.0}, neutral_price_score=0.4)

    [scored] = prefilter_and_score(
        ITEM,
        [product("Black Oversized Blazer", 1, price=9000.0, currency="SAR")],
        make_budget(max_price=400),
        fx,
    )

    assert scored.flags == []
    assert scored.scores.price == 0.4
    assert "budget" not in scored.reason.lower()


def test_scoring_leaves_the_base_price_to_the_price_range_shaper() -> None:
    fx = make_settings(fx_rates={"KWD": 10.0})

    [scored] = prefilter_and_score(
        ITEM, [product("Black Oversized Blazer", 1, price=35.0, currency="KWD")], None, fx
    )

    assert scored.base_price is None


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


def test_a_missing_or_none_image_score_stays_unrecorded_but_is_totalled_neutrally() -> None:
    scored = _scored(("Scored", 0.8, 0.5), ("Missing", 0.8, 0.5), ("None", 0.8, 0.5))
    keys = [entry.product.key for entry in scored]

    result = apply_image_scores(scored, {keys[0]: 0.4, keys[2]: None}, SETTINGS)

    by_title = {entry.product.title: entry.scores for entry in result}
    # The record still says "not compared" ...
    assert by_title["Scored"].image == 0.4
    assert by_title["Missing"].image is None
    assert by_title["None"].image is None
    # ... but the total uses the mean of the image scores there are (here just 0.4), so an
    # equal product that was compared and one that was not end up with equal totals.
    neutral = combine_scores(0.8, 0.4, 0.5, SETTINGS.ranking_weights)
    assert by_title["Scored"].total == pytest.approx(neutral)
    assert by_title["Missing"].total == pytest.approx(neutral)
    assert by_title["None"].total == pytest.approx(neutral)


# A product the photo was not compared with (only the best 40 candidates are) must not outrank
# one that was: its total uses a neutral image value, the mean of the image scores in the call.


def test_a_compared_product_is_not_ranked_below_an_uncompared_one_for_being_compared() -> None:
    # Real figures from a run on a product photo of a burgundy gown: real image scores for good
    # matches sit around 0.35 to 0.5. Before the neutral value, "Deema" (no image score) was
    # totalled on text and price only, 0.84, and ranked above "Heliora" (0.75).
    scored = _scored(
        ("Heliora | Black V-Neck Maxi Dress With Sash", 1.00, 0.5),
        ("Deema | Black Jersey High Neck Long Sleeve Maxi Dress", 0.97, 0.5),
    )
    heliora = scored[0].product.key

    result = apply_image_scores(scored, {heliora: 0.49}, SETTINGS)

    assert titles(result) == [
        "Heliora | Black V-Neck Maxi Dress With Sash",
        "Deema | Black Jersey High Neck Long Sleeve Maxi Dress",
    ]
    heliora_scores, deema_scores = (entry.scores for entry in result)
    assert heliora_scores.image == 0.49
    assert deema_scores.image is None  # still recorded as not compared
    assert heliora_scores.total == pytest.approx(
        combine_scores(1.00, 0.49, 0.5, SETTINGS.ranking_weights)
    )
    assert deema_scores.total == pytest.approx(
        combine_scores(0.97, 0.49, 0.5, SETTINGS.ranking_weights)
    )
    assert heliora_scores.total > deema_scores.total


def test_the_neutral_image_value_is_the_mean_of_the_usable_scores_in_the_call() -> None:
    scored = _scored(("A", 0.9, 0.5), ("B", 0.9, 0.5), ("C", 0.9, 0.5), ("D", 0.9, 0.5))
    a, b, c, _ = (entry.product.key for entry in scored)
    # 1.7 is clamped to 1.0, NaN is "not scored" and does not count towards the mean.
    images = {a: 0.2, b: 1.7, c: float("nan")}

    result = {e.product.title: e.scores for e in apply_image_scores(scored, images, SETTINGS)}

    mean = (0.2 + 1.0) / 2
    assert result["C"].image is None
    assert result["D"].image is None
    for title in ("C", "D"):
        assert result[title].total == pytest.approx(
            combine_scores(0.9, mean, 0.5, SETTINGS.ranking_weights)
        )


def test_among_compared_products_a_higher_image_score_still_ranks_higher() -> None:
    scored = _scored(("Low", 0.8, 0.5), ("High", 0.8, 0.5), ("Uncompared", 0.8, 0.5))
    keys = {entry.product.title: entry.product.key for entry in scored}

    result = apply_image_scores(scored, {keys["Low"]: 0.3, keys["High"]: 0.5}, SETTINGS)

    # "Uncompared" gets the mean, 0.4, so it lands between the two it was not compared with.
    assert titles(result) == ["High", "Uncompared", "Low"]


def test_a_better_text_match_is_not_lost_to_a_worse_one_that_was_compared() -> None:
    scored = _scored(("Best text, uncompared", 0.95, 0.5), ("Worse text, compared", 0.5, 0.5))
    compared = scored[1].product.key

    result = apply_image_scores(scored, {compared: 0.4}, SETTINGS)

    assert titles(result) == ["Best text, uncompared", "Worse text, compared"]


@pytest.mark.parametrize("nothing", [{}, "all None", "all NaN", "keys of other products"])
def test_when_no_product_has_a_usable_image_score_the_totals_are_text_and_price_only(
    nothing: object,
) -> None:
    scored = _scored(("A", 0.8, 0.5), ("B", 0.6, 1.0))
    if nothing == "all None":
        images: dict[str, float | None] = {entry.product.key: None for entry in scored}
    elif nothing == "all NaN":
        images = {entry.product.key: float("nan") for entry in scored}
    elif nothing == "keys of other products":
        images = {"https://elsewhere.example/p/1": 0.9}  # scores for products not in this call
    else:
        images = {}

    result = apply_image_scores(scored, images, SETTINGS)

    assert all(entry.scores.image is None for entry in result)
    assert {entry.product.title: entry.scores.total for entry in result} == pytest.approx(
        {
            "A": combine_scores(0.8, None, 0.5, SETTINGS.ranking_weights),
            "B": combine_scores(0.6, None, 1.0, SETTINGS.ranking_weights),
        }
    )


def test_the_minimum_score_is_applied_to_the_neutral_totals() -> None:
    settings = make_settings(min_match_score=0.5)
    scored = _scored(("Compared", 0.9, 0.9), ("Uncompared, fine on text and price", 0.55, 0.55))
    compared = scored[0].product.key

    # On text and price alone the second product (0.55) clears the 0.5 minimum. With the neutral
    # image value (the mean, 0.0 here) its total is 0.385, so it is removed like any other
    # product whose total falls below the minimum.
    assert len(apply_image_scores(scored, {}, settings)) == 2
    result = apply_image_scores(scored, {compared: 0.0}, settings)

    assert titles(result) == ["Compared"]


def test_an_uncompared_product_can_be_lifted_over_the_minimum_by_the_neutral_value() -> None:
    settings = make_settings(min_match_score=0.5)
    scored = _scored(("Compared", 0.9, 0.9), ("Uncompared, weak text", 0.3, 0.3))
    compared = scored[0].product.key

    assert titles(apply_image_scores(scored, {}, settings)) == ["Compared"]
    result = apply_image_scores(scored, {compared: 1.0}, settings)

    # 0.5 * 0.3 + 0.3 * 1.0 + 0.2 * 0.3 = 0.51: the same rule, applied to the same kind of total.
    assert titles(result) == ["Compared", "Uncompared, weak text"]
    assert result[1].scores.image is None


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
