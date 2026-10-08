"""8.2.2 Candidate selection: the top N, at most 10 per store, in a stable order."""

from collections import Counter

import pytest

from tests.factories import make_product
from tests.rank_image.support import products_for
from vga.rank.image.selection import (
    DEFAULT_CANDIDATE_LIMIT,
    MAX_CANDIDATE_LIMIT,
    MAX_PER_STORE,
    select_candidates,
)


def test_the_defaults_sit_inside_the_plans_range() -> None:
    assert 30 <= DEFAULT_CANDIDATE_LIMIT <= MAX_CANDIDATE_LIMIT == 50
    assert MAX_PER_STORE == 10


def test_the_count_is_capped_at_the_limit() -> None:
    products = products_for({"Store A": 8, "Store B": 8, "Store C": 8, "Store D": 8})

    selected = select_candidates(products, limit=30)

    assert len(selected) == 30


def test_at_most_ten_products_are_taken_from_one_store() -> None:
    products = products_for({"Store A": 25, "Store B": 25})

    selected = select_candidates(products, limit=50)

    assert Counter(p.store for p in selected) == {"Store A": 10, "Store B": 10}


def test_a_store_over_its_cap_does_not_use_up_the_limit() -> None:
    products = products_for({"Store A": 30, "Store B": 5, "Store C": 5})

    selected = select_candidates(products, limit=50)

    assert Counter(p.store for p in selected) == {"Store A": 10, "Store B": 5, "Store C": 5}


def test_the_best_products_win_and_the_input_order_is_kept() -> None:
    products = products_for({"Store A": 3, "Store B": 3})
    best_first = [products[0], products[3], products[1], products[4], products[2], products[5]]

    selected = select_candidates(best_first, limit=4)

    assert selected == best_first[:4]


def test_a_lower_ranked_product_of_a_full_store_is_skipped_not_reordered() -> None:
    products = products_for({"Store A": 3, "Store B": 2})
    best_first = [products[0], products[1], products[2], products[3], products[4]]

    selected = select_candidates(best_first, limit=10, per_store=2)

    assert selected == [products[0], products[1], products[3], products[4]]


def test_the_same_input_always_gives_the_same_selection() -> None:
    products = products_for({"Store A": 20, "Store B": 20, "Store C": 20})

    assert select_candidates(products) == select_candidates(list(products))


def test_a_product_listed_twice_counts_once() -> None:
    first = make_product(1)
    second = make_product(2)

    selected = select_candidates([first, second, first])

    assert selected == [first, second]


def test_fewer_products_than_the_limit_are_all_kept() -> None:
    products = products_for({"Store A": 3})

    assert select_candidates(products, limit=40) == products


def test_no_products_gives_an_empty_selection() -> None:
    assert select_candidates([]) == []


def test_a_limit_of_zero_selects_nothing() -> None:
    assert select_candidates(products_for({"Store A": 3}), limit=0) == []


@pytest.mark.parametrize(("limit", "per_store"), [(-1, 10), (10, 0)])
def test_nonsense_limits_are_refused(limit: int, per_store: int) -> None:
    with pytest.raises(ValueError, match="must"):
        select_candidates(products_for({"Store A": 3}), limit=limit, per_store=per_store)
