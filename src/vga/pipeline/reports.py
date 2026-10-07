"""Which stores were used and which were skipped, and why (plan 13.2.3).

Each item (garment) is searched on its own, so the same store has one outcome per item. The
response lists a store once: *used* when it gave products for at least one item, otherwise *skipped*
with the plain reason of its most serious outcome. A store left out because it does not sell the
garment's category, or does not sell for its gender, is skipped with that reason, not as a failure.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vga.models import (
    StepTiming,
    StoreConfig,
    StoreReport,
    StoreResult,
    StoreStatus,
)
from vga.pipeline import messages
from vga.pipeline.state import ItemRun
from vga.understand import effective_gender

_SEVERITY = (
    StoreStatus.BLOCKED,
    StoreStatus.ROBOTS_DENIED,
    StoreStatus.COOLDOWN,
    StoreStatus.TIMEOUT,
    StoreStatus.ERROR,
    StoreStatus.EMPTY,
)
"""Most serious first: the one shown when a store has different outcomes for different items."""

_FAILURES = frozenset(_SEVERITY) - {StoreStatus.EMPTY}


@dataclass(frozen=True)
class StoreOutcome:
    """A store's outcome for one item."""

    report: StoreReport
    searched: bool
    """False when the store was left out (for its category or gender) and no request was made."""


@dataclass(frozen=True)
class StoreSummary:
    used: list[StoreReport]
    skipped: list[StoreReport]
    timings: list[StepTiming]
    failed: list[StoreReport]
    """The skipped stores that failed (blocked, slow, broken), for warnings and logs."""
    partly_failed: list[StoreReport]
    """Used stores that gave products for one item but failed for another (an outfit), so some
    garment has fewer results than it should."""


def outcomes_for_item(run: ItemRun) -> list[StoreOutcome]:
    """One outcome for every active store, for this item."""
    if run.cached is not None:
        # Nothing was asked this time: say so, and charge no time. The cached reports already
        # include the stores left out for their category or gender.
        reused: list[StoreOutcome] = []
        for report in run.cached.reports:
            searched = report.store_id in run.cached.searched_ids
            if searched:
                report = report.model_copy(update={"from_cache": True, "duration_ms": 0.0})
            reused.append(StoreOutcome(report, searched))
        return reused

    outcomes: list[StoreOutcome] = []
    for store in run.skipped:
        report = StoreReport(
            store_id=store.id, status=StoreStatus.EMPTY, reason=_not_searched_reason(store, run)
        )
        outcomes.append(StoreOutcome(report, searched=False))
    for store in run.stores:
        outcomes.append(StoreOutcome(_report_for(store, run.store_results.get(store.id)), True))
    return outcomes


def _not_searched_reason(store: StoreConfig, run: ItemRun) -> str:
    """Why ``store`` was left out for this item. The garment comes first when both reasons hold:
    it is the more specific one, and it does not depend on what the shopper stated."""
    if not store.sells_category(run.item.category):
        return messages.store_not_for_category(store, run.item.category)
    gender = effective_gender(run.item)
    if gender is not None:
        return messages.store_not_for_gender(store, gender)
    return messages.store_reason(StoreStatus.EMPTY)


def _report_for(store: StoreConfig, result: StoreResult | None) -> StoreReport:
    if result is None:
        # The store had not answered when the time ran out.
        return StoreReport(
            store_id=store.id, status=StoreStatus.TIMEOUT, reason=messages.STORE_NOT_FINISHED
        )
    if result.status is StoreStatus.OK:
        return StoreReport.from_result(result)
    return StoreReport.from_result(result, reason=messages.store_reason(result.status))


def summarise(active: Sequence[StoreConfig], runs: Sequence[ItemRun]) -> StoreSummary:
    """Merge the per-item outcomes into one report per store, in the order of ``active``."""
    per_item = [outcomes_for_item(run) for run in runs]
    used: list[StoreReport] = []
    skipped: list[StoreReport] = []
    timings: list[StepTiming] = []
    failed: list[StoreReport] = []
    partly_failed: list[StoreReport] = []
    for store in active:
        outcomes = [o for item in per_item for o in item if o.report.store_id == store.id]
        if not outcomes:
            continue
        merged = _merge(store.id, outcomes)
        searched = any(o.searched for o in outcomes)
        if searched:
            timings.append(
                StepTiming(
                    step="fetch",
                    store=store.id,
                    duration_ms=merged.duration_ms,
                    status=merged.status.value,
                )
            )
        if merged.status is StoreStatus.OK:
            used.append(merged)
            if any(o.report.status in _FAILURES for o in outcomes):
                partly_failed.append(merged)
        else:
            skipped.append(merged)
            if merged.status in _FAILURES:
                failed.append(merged)
    return StoreSummary(
        used=used, skipped=skipped, timings=timings, failed=failed, partly_failed=partly_failed
    )


def _merge(store_id: str, outcomes: Sequence[StoreOutcome]) -> StoreReport:
    ok = [o.report for o in outcomes if o.report.status is StoreStatus.OK]
    duration = round(sum(o.report.duration_ms for o in outcomes), 3)
    dropped: dict[str, int] = {}
    for outcome in outcomes:
        for reason, count in outcome.report.dropped.items():
            dropped[reason] = dropped.get(reason, 0) + count

    if ok:
        return StoreReport(
            store_id=store_id,
            status=StoreStatus.OK,
            product_count=sum(report.product_count for report in ok),
            duration_ms=duration,
            strategy=ok[0].strategy,
            from_cache=all(report.from_cache for report in ok),
            dropped=dropped,
            reason=None,
        )

    # Not used: show the most serious outcome, preferring a real search over a skip.
    worst = min(outcomes, key=lambda o: (_SEVERITY.index(o.report.status), not o.searched)).report
    return StoreReport(
        store_id=store_id,
        status=worst.status,
        duration_ms=duration,
        from_cache=worst.from_cache,
        dropped=dropped,
        reason=worst.reason or messages.store_reason(worst.status),
    )
