"""The re-run cache's side of "a gender answer costs nothing": when is an earlier search a basis for
the answer, and what does it look like once the answer is applied (``reusable_after_gender`` and
``narrowed_to``). The whole thing through the pipeline is in ``test_gender_answer.py``."""

import pytest

from tests.factories import make_item_intent, make_product, make_store_config
from tests.fakes import FakeClock
from vga.models import Category, Gender, GenderSource, StoreReport, StoreStatus
from vga.pipeline.rerun import CachedItem, CachedRun, RerunCache, narrowed_to, same_garment

ALPHA = make_store_config(id="alpha", name="Alpha")
BETA = make_store_config(id="beta", name="Beta")
MENS = make_store_config(id="mens", name="Mens", genders=frozenset({Gender.MEN}))
STORES = (ALPHA, BETA, MENS)

NEUTRAL = make_item_intent(search_keywords=["black oversized blazer", "oversized blazer"])


def answered(gender: Gender, **overrides: object):
    """``NEUTRAL`` after the shopper's answer: the gender is stated and the keywords carry it."""
    fields = {
        "gender": gender,
        "gender_source": GenderSource.EXPLICIT,
        "search_keywords": [f"black oversized blazer {gender.value}", "oversized blazer"],
        **overrides,
    }
    return make_item_intent(**fields)


def cached_item(item=NEUTRAL, *, expires_at: float = 10_000.0, **overrides: object) -> CachedItem:
    products = (
        make_product(1, store="Alpha"),
        make_product(2, store="Beta"),
        make_product(3, store="Mens"),
    )
    fields: dict[str, object] = {
        "item": item,
        "store_ids": ("alpha", "beta", "mens"),
        "products": products,
        "image_scores": {product.key: 0.5 for product in products},
        "reports": tuple(
            StoreReport(store_id=store.id, status=StoreStatus.OK, product_count=1)
            for store in STORES
        ),
        "searched_ids": frozenset({"alpha", "beta", "mens"}),
        "expires_at": expires_at,
    }
    return CachedItem(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def cache(clock: FakeClock) -> RerunCache:
    return RerunCache(clock)


def run_of(item: CachedItem) -> CachedRun:
    return CachedRun(items={0: item})


# --------------------------------------------------------------------------------------------
# Is it the same garment?
# --------------------------------------------------------------------------------------------


def test_the_gender_and_the_words_it_adds_do_not_make_another_garment() -> None:
    assert same_garment(NEUTRAL, answered(Gender.WOMEN))
    assert same_garment(answered(Gender.MEN), answered(Gender.WOMEN))


@pytest.mark.parametrize(
    "change",
    [
        {"colour": "red"},
        {"category": Category.TOPS},
        {"style": "tailored jacket"},
        {"material": "wool"},
    ],
    ids=["colour", "category", "style", "material"],
)
def test_another_colour_category_style_or_material_is_another_garment(
    change: dict[str, object],
) -> None:
    other = make_item_intent(**{"search_keywords": ["black oversized blazer"], **change})

    assert not same_garment(NEUTRAL, other)


# --------------------------------------------------------------------------------------------
# When is an earlier search a basis for the answer?
# --------------------------------------------------------------------------------------------


def test_a_search_that_asked_for_no_gender_is_a_basis_for_any_answer(cache: RerunCache) -> None:
    earlier = cached_item()

    for gender in (Gender.WOMEN, Gender.MEN):
        assert cache.reusable_after_gender(run_of(earlier), 0, answered(gender), STORES) is earlier


def test_a_guessed_gender_that_was_never_applied_is_still_no_gender(cache: RerunCache) -> None:
    guessed = make_item_intent(
        search_keywords=["black oversized blazer", "oversized blazer"],
        gender=Gender.MEN,
        gender_source=GenderSource.INFERRED,
    )
    earlier = cached_item(guessed)

    assert (
        cache.reusable_after_gender(run_of(earlier), 0, answered(Gender.WOMEN), STORES) is earlier
    )


def test_a_search_that_applied_a_gender_is_no_basis_for_another(cache: RerunCache) -> None:
    earlier = cached_item(answered(Gender.MEN))

    assert cache.reusable_after_gender(run_of(earlier), 0, answered(Gender.WOMEN), STORES) is None


def test_another_garment_is_not_answered_from_this_one(cache: RerunCache) -> None:
    earlier = cached_item()
    red = answered(Gender.WOMEN, colour="red")

    assert cache.reusable_after_gender(run_of(earlier), 0, red, STORES) is None


def test_an_expired_search_is_no_basis(cache: RerunCache, clock: FakeClock) -> None:
    earlier = cached_item(expires_at=clock.monotonic() + 5)
    clock.advance(6)

    assert cache.reusable_after_gender(run_of(earlier), 0, answered(Gender.WOMEN), STORES) is None


def test_an_unknown_request_or_item_is_no_basis(cache: RerunCache) -> None:
    assert cache.reusable_after_gender(None, 0, answered(Gender.WOMEN), STORES) is None
    assert (
        cache.reusable_after_gender(run_of(cached_item()), 1, answered(Gender.WOMEN), STORES)
        is None
    )


def test_a_store_the_earlier_search_never_asked_is_no_basis(cache: RerunCache) -> None:
    earlier = cached_item(store_ids=("alpha", "mens"))

    assert cache.reusable_after_gender(run_of(earlier), 0, answered(Gender.WOMEN), STORES) is None


def test_fewer_stores_than_before_is_fine(cache: RerunCache) -> None:
    earlier = cached_item()

    assert (
        cache.reusable_after_gender(run_of(earlier), 0, answered(Gender.WOMEN), (ALPHA, BETA))
        is earlier
    )


# --------------------------------------------------------------------------------------------
# The search as it is once the answer is applied
# --------------------------------------------------------------------------------------------


def test_the_products_of_a_store_that_does_not_sell_for_the_answer_are_taken_out() -> None:
    earlier = cached_item()
    women = answered(Gender.WOMEN)

    narrowed = narrowed_to(earlier, women, (ALPHA, BETA), (MENS,))

    assert [product.store for product in narrowed.products] == ["Alpha", "Beta"]
    assert set(narrowed.image_scores) == {product.key for product in narrowed.products}
    assert narrowed.store_ids == ("alpha", "beta")
    assert narrowed.searched_ids == frozenset({"alpha", "beta"})
    assert narrowed.item == women


def test_a_store_that_is_left_out_is_reported_as_not_searched_in_plain_words() -> None:
    narrowed = narrowed_to(cached_item(), answered(Gender.WOMEN), (ALPHA, BETA), (MENS,))

    by_id = {report.store_id: report for report in narrowed.reports}
    assert by_id["mens"].status is StoreStatus.EMPTY
    assert by_id["mens"].reason == "Not searched: Mens does not sell clothing for women."
    assert by_id["alpha"].status is StoreStatus.OK  # the others are reported as they were


def test_narrowing_changes_nothing_else_and_least_of_all_the_expiry() -> None:
    earlier = cached_item(expires_at=1234.5, image_done=False)

    narrowed = narrowed_to(earlier, answered(Gender.MEN), (ALPHA, BETA, MENS), ())

    assert narrowed.expires_at == 1234.5
    assert narrowed.image_done is False
    assert narrowed.products == earlier.products
    assert narrowed.reports == earlier.reports
    assert earlier.item == NEUTRAL  # the original is untouched
    assert len(earlier.products) == 3
