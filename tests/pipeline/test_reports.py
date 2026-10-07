"""How the per-item outcomes of each store become one used-or-skipped report per store."""

from tests.factories import make_item_intent, make_product, make_store_config, make_store_result
from vga.models import Gender, GenderSource, StoreReport, StoreStatus
from vga.pipeline.reports import outcomes_for_item, summarise
from vga.pipeline.rerun import CachedItem
from vga.pipeline.state import ItemRun

ALPHA = make_store_config(id="alpha", name="Alpha")
BETA = make_store_config(
    id="beta", name="Beta", search_url_template="https://www.demo-store.example/b?q={query}"
)
WOMENS = make_store_config(
    id="womens",
    name="Womens",
    search_url_template="https://www.demo-store.example/w?q={query}",
    genders=frozenset({Gender.WOMEN}),
)


def item_run(index: int = 0, *stores, skipped=(), **results) -> ItemRun:
    """An item searched at ``stores``; ``results`` maps a store id to its ``StoreResult``."""
    run = ItemRun(
        index=index,
        item=make_item_intent(),
        stores=list(stores),
        gender_skipped=list(skipped),
    )
    run.store_results = dict(results)
    return run


def ok(store_id: str, count: int = 3, **fields):
    products = [make_product(n, store=store_id.title()) for n in range(1, count + 1)]
    return make_store_result(StoreStatus.OK, store_id=store_id, products=products, **fields)


def failed(store_id: str, status: StoreStatus):
    return make_store_result(status, store_id=store_id)


def test_a_store_that_gave_products_for_any_item_is_used_with_the_counts_added() -> None:
    first = item_run(0, ALPHA, alpha=ok("alpha", 3, duration_ms=100.0))
    second = item_run(1, ALPHA, alpha=ok("alpha", 2, duration_ms=250.0))

    summary = summarise([ALPHA], [first, second])

    [used] = summary.used
    assert (used.status, used.product_count, used.duration_ms) == (StoreStatus.OK, 5, 350.0)
    assert summary.skipped == []
    assert [t.store for t in summary.timings] == ["alpha"]


def test_success_for_one_item_outweighs_a_failure_for_another() -> None:
    first = item_run(0, ALPHA, alpha=failed("alpha", StoreStatus.TIMEOUT))
    second = item_run(1, ALPHA, alpha=ok("alpha"))

    summary = summarise([ALPHA], [first, second])

    assert [r.store_id for r in summary.used] == ["alpha"]
    assert summary.failed == []


def test_the_most_serious_failure_is_the_one_reported() -> None:
    first = item_run(0, ALPHA, alpha=failed("alpha", StoreStatus.EMPTY))
    second = item_run(1, ALPHA, alpha=failed("alpha", StoreStatus.BLOCKED))

    summary = summarise([ALPHA], [first, second])

    [skipped] = summary.skipped
    assert skipped.status is StoreStatus.BLOCKED
    assert [r.store_id for r in summary.failed] == ["alpha"]


def test_a_store_with_nothing_to_show_is_skipped_but_is_not_a_failure() -> None:
    summary = summarise([ALPHA], [item_run(0, ALPHA, alpha=failed("alpha", StoreStatus.EMPTY))])

    [skipped] = summary.skipped
    assert skipped.reason
    assert summary.failed == []


def test_a_store_that_never_answered_is_a_timeout_with_its_own_reason() -> None:
    summary = summarise([ALPHA, BETA], [item_run(0, ALPHA, BETA, alpha=ok("alpha"))])

    assert [r.store_id for r in summary.used] == ["alpha"]
    [slow] = summary.skipped
    assert (slow.store_id, slow.status) == ("beta", StoreStatus.TIMEOUT)
    assert "time limit" in (slow.reason or "")


def test_a_store_left_out_for_its_gender_has_no_fetch_timing_and_a_gender_reason() -> None:
    men = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)
    run = item_run(0, ALPHA, skipped=[WOMENS], alpha=ok("alpha"))
    run.item = men

    summary = summarise([WOMENS, ALPHA], [run])

    [skipped] = summary.skipped
    assert skipped.store_id == "womens"
    assert skipped.reason == "Not searched: Womens does not sell clothing for men."
    assert [t.store for t in summary.timings] == ["alpha"]


def test_a_real_search_beats_a_gender_skip_when_choosing_what_to_report() -> None:
    men = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)
    skipped_for_men = item_run(0, ALPHA, skipped=[WOMENS], alpha=ok("alpha"))
    skipped_for_men.item = men
    searched_for_anyone = item_run(1, WOMENS, womens=failed("womens", StoreStatus.EMPTY))

    summary = summarise([WOMENS], [skipped_for_men, searched_for_anyone])

    [skipped] = summary.skipped
    assert "does not sell clothing" not in (skipped.reason or "")
    assert [t.store for t in summary.timings] == ["womens"]


def test_a_reused_item_reports_each_store_once_with_no_time_charged() -> None:
    men = make_item_intent(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)
    cached = CachedItem(
        item=men,
        store_ids=("alpha",),
        products=(),
        image_scores={},
        reports=(
            StoreReport(store_id="womens", status=StoreStatus.EMPTY, reason="Not searched."),
            StoreReport(
                store_id="alpha", status=StoreStatus.OK, product_count=4, duration_ms=900.0
            ),
        ),
        searched_ids=frozenset({"alpha"}),
        expires_at=1.0,
    )
    run = ItemRun(index=0, item=men, stores=[ALPHA], gender_skipped=[WOMENS], cached=cached)

    outcomes = outcomes_for_item(run)

    assert [o.report.store_id for o in outcomes] == ["womens", "alpha"]
    assert [o.searched for o in outcomes] == [False, True]
    alpha = outcomes[1].report
    assert (alpha.from_cache, alpha.duration_ms, alpha.product_count) == (True, 0.0, 4)
