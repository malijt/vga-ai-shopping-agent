"""Stage metrics (plan 11.2.2): the fetch stage and the rank stage, reported separately.

The same split the RAG doc asks for: when a query fails, did the stores not deliver (fetch) or did
the ranking lose them (rank)? The fetch stage is read from what the response says about each
store (``StoreReport``, copied from ``StoreResult``): valid product count, extraction strategy,
dropped records and why, cache hit. The rank stage is good@10 per garment group, which needs a
person's labels.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from eval.harness.criteria import CriteriaConfig, QueryEvaluation
from eval.harness.runner import QueryRun
from vga.models import SearchResponse, StoreReport, StoreStatus


@dataclass(frozen=True)
class FetchRow:
    """What one store returned for one query."""

    query_id: str
    store_id: str
    status: StoreStatus
    valid_products: int
    strategy: str | None
    dropped: dict[str, int]
    """Records dropped while extracting, as ``{reason: count}``."""
    from_cache: bool
    duration_ms: float
    reason: str | None


@dataclass(frozen=True)
class StoreSummary:
    """One store over the whole run."""

    store_id: str
    queries_ok: int
    queries_total: int
    valid_products: int
    strategies: tuple[str, ...]
    dropped: dict[str, int]
    cache_hits: int
    mean_ms: float
    max_ms: float


@dataclass(frozen=True)
class StepSummary:
    """One pipeline step over the whole run."""

    step: str
    runs: int
    mean_ms: float
    max_ms: float


@dataclass(frozen=True)
class RankRow:
    """The rank stage for one garment group of one query."""

    query_id: str
    group: str
    results: int
    good: str
    """good@10 as ``n/10``, ``max n/10`` when the group is too small, or ``not labelled``."""
    reaches_bar: str
    """``yes``, ``no`` or ``pending``."""


def _reports(response: SearchResponse) -> list[StoreReport]:
    return [*response.stores_used, *response.stores_skipped]


def fetch_rows(runs: Sequence[QueryRun]) -> list[FetchRow]:
    """One row per store per answered query, stores that worked first."""
    rows: list[FetchRow] = []
    for run in runs:
        if run.response is None:
            continue
        rows.extend(
            FetchRow(
                run.query.id,
                report.store_id,
                report.status,
                report.product_count,
                report.strategy,
                dict(report.dropped),
                report.from_cache,
                report.duration_ms,
                report.reason,
            )
            for report in _reports(run.response)
        )
    return rows


def format_dropped(dropped: dict[str, int]) -> str:
    """``missing_price: 2, off_domain_link: 1``, or ``none``."""
    return ", ".join(f"{reason}: {count}" for reason, count in sorted(dropped.items())) or "none"


def store_summaries(runs: Sequence[QueryRun]) -> list[StoreSummary]:
    """Per-store totals over every query, in the order the stores first appear."""
    by_store: dict[str, list[FetchRow]] = {}
    for row in fetch_rows(runs):
        by_store.setdefault(row.store_id, []).append(row)
    summaries: list[StoreSummary] = []
    for store_id, rows in by_store.items():
        dropped: dict[str, int] = {}
        for row in rows:
            for reason, count in row.dropped.items():
                dropped[reason] = dropped.get(reason, 0) + count
        durations = [row.duration_ms for row in rows]
        summaries.append(
            StoreSummary(
                store_id=store_id,
                queries_ok=sum(1 for row in rows if row.status is StoreStatus.OK),
                queries_total=len(rows),
                valid_products=sum(row.valid_products for row in rows),
                strategies=tuple(sorted({row.strategy for row in rows if row.strategy})),
                dropped=dropped,
                cache_hits=sum(1 for row in rows if row.from_cache),
                mean_ms=sum(durations) / len(durations),
                max_ms=max(durations),
            )
        )
    return summaries


def step_summaries(runs: Sequence[QueryRun]) -> list[StepSummary]:
    """Mean and slowest time of each pipeline step, in the order the steps first appear.

    Per-store ``fetch`` entries are left to ``store_summaries``; only whole-request steps count.
    """
    durations: dict[str, list[float]] = {}
    for run in runs:
        if run.response is None:
            continue
        for timing in run.response.timings:
            if timing.store is None:
                durations.setdefault(timing.step, []).append(timing.duration_ms)
    return [
        StepSummary(step, len(values), sum(values) / len(values), max(values))
        for step, values in durations.items()
    ]


def rank_rows(
    evaluations: Sequence[QueryEvaluation], config: CriteriaConfig | None = None
) -> list[RankRow]:
    """good@10 for every garment group of every answered query."""
    config = config or CriteriaConfig()
    rows: list[RankRow] = []
    for evaluation in evaluations:
        response = evaluation.run.response
        if response is None:
            continue
        for position, (name, count) in enumerate(
            zip(evaluation.group_names, evaluation.group_counts, strict=True)
        ):
            if evaluation.good is not None:
                figure = evaluation.good[position]
                good = figure.cell
                reaches = "yes" if figure.good >= config.min_good else "no"
            elif min(count, config.top_n) < config.min_good:
                good = f"max {min(count, config.top_n)}/{config.top_n}"
                reaches = "no"
            else:
                good, reaches = "not labelled", "pending"
            rows.append(RankRow(evaluation.query_id, name, count, good, reaches))
    return rows
