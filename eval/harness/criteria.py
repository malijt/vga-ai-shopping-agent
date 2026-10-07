"""The pass criteria for one query (plan 11.2.1, the PRD "Acceptance test", ``rubric.md``).

A query passes only if every criterion holds. Each criterion has one of three states, because the
harness runs before a person has labelled anything:

- ``pass``: met.
- ``fail``: not met, and nothing a person does later can change that.
- ``pending``: not decided yet (the labels are missing, or the links were not all checked).

The criteria, in the order of the report's columns:

====================  =====================================================================
Results               at least 20 results
Stores                at least 3 different stores among the results
Seconds               at most 30 s
Links ok              every checked link opens that store's own product page (11.2.3)
good@10               at least 7 of the top 10 labelled good (A15; outfit rule A14)
Price ranges ok       each price range within 1 of its target count, or flagged few_options
====================  =====================================================================

**Outfit photos.** The PRD gives an outfit 12 results per garment (assumption A2), so a floor of
20 results per garment could never be met. The 20-result floor is therefore applied to the
query's total, and the harness adds a floor of one result per garment. The price-range check
(each garment has its own four ranges and targets) and good@10 (every garment must reach 7) are
applied per garment group. The report shows one figure per garment and says so.

Failures carry a ``cause`` (store, ranking, LLM or price range) chosen from evidence in the
response. It is the harness's first guess for the failures table, not a verdict: the reviewer
confirms it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from eval.harness.groups import TOP_N, distinct_stores, group_names
from eval.harness.labels import GroupGood, LabelSet, good_at_10
from eval.harness.links import LinkCheck
from eval.harness.runner import QueryRun
from vga.models import Flag, InputType, SearchResponse, Tier

_MAX_LISTED = 5
_RANK_STEPS = frozenset({"filter", "rank", "image_rank", "shape", "assemble"})
_LLM_ERROR_CODES = frozenset({"llm_failure", "call_budget_exceeded"})


class Status(StrEnum):
    PASS = "pass"  # noqa: S105  (a status word, not a password)
    FAIL = "fail"
    PENDING = "pending"


class Cause(StrEnum):
    """The only causes the failures table allows (``results-template.md``)."""

    STORE = "store"
    RANKING = "ranking"
    LLM = "LLM"
    PRICE_RANGE = "price range"


class Criterion(StrEnum):
    """Named like the report's columns, in column order."""

    RESULTS = "Results"
    STORES = "Stores"
    SECONDS = "Seconds"
    LINKS = "Links ok"
    GOOD_AT_10 = "good@10"
    PRICE_RANGES = "Price ranges ok"


@dataclass(frozen=True)
class CriteriaConfig:
    """The numbers of the pass rule, in one place."""

    min_results: int = 20
    min_stores: int = 3
    max_seconds: float = 30.0
    price_range_tolerance: int = 1
    min_good: int = 7
    top_n: int = TOP_N
    required_queries: int = 7
    """Assumption A6: "most" of the 10 queries means at least 7."""


@dataclass(frozen=True)
class CriterionResult:
    criterion: Criterion
    status: Status
    cell: str
    """What goes in the report's table cell."""
    cause: Cause | None = None
    evidence: str = ""
    """Something a reader can check. Set when ``status`` is ``fail``."""


@dataclass(frozen=True)
class QueryEvaluation:
    run: QueryRun
    criteria: tuple[CriterionResult, ...]
    group_names: tuple[str, ...] = ()
    group_counts: tuple[int, ...] = ()
    good: tuple[GroupGood, ...] | None = None
    """good@10 per garment group, once labels are imported."""

    @property
    def query_id(self) -> str:
        return self.run.query.id

    @property
    def status(self) -> Status:
        states = {result.status for result in self.criteria}
        if Status.FAIL in states:
            return Status.FAIL
        if Status.PENDING in states:
            return Status.PENDING
        return Status.PASS

    def result(self, criterion: Criterion) -> CriterionResult:
        for item in self.criteria:
            if item.criterion is criterion:
                return item
        msg = f"no result for {criterion}"
        raise KeyError(msg)


@dataclass(frozen=True)
class FailureRow:
    """One row of the report's failures table."""

    query_id: str
    criterion: Criterion
    cause: Cause
    evidence: str


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def _shown(items: Sequence[str]) -> str:
    listed = list(items[:_MAX_LISTED])
    more = len(items) - len(listed)
    return "; ".join(listed) + (f"; and {more} more" if more > 0 else "")


def store_summary(response: SearchResponse) -> str:
    """What each store returned, for evidence: ``alpha: 12 products (ok); beta: blocked``."""
    parts = [
        f"{report.store_id}: {report.product_count} products ({report.status.value})"
        for report in response.stores_used
    ]
    parts += [f"{report.store_id}: {report.status.value}" for report in response.stores_skipped]
    return "; ".join(parts) or "no store reports"


def _fetched_products(response: SearchResponse) -> int:
    return sum(report.product_count for report in response.stores_used)


def _understood_summary(response: SearchResponse) -> str:
    items = ", ".join(
        f"{item.category.value} ({item.colour or 'no colour'}; {item.search_keywords[0]})"
        for item in response.understood.items
    )
    return f"understood as {response.understood.input_type.value}: {items}"


def _stage_seconds(response: SearchResponse) -> tuple[float, float, float]:
    """Seconds spent in understand, search and everything after the search."""
    own = [timing for timing in response.timings if timing.store is None]
    understand = sum(t.duration_ms for t in own if t.step == "understand")
    searches = [t.duration_ms for t in own if t.step == "search"]
    fetches = [t.duration_ms for t in response.timings if t.step == "fetch"]
    search = sum(searches) if searches else max(fetches, default=0.0)
    rank = sum(t.duration_ms for t in own if t.step in _RANK_STEPS)
    return understand / 1000, search / 1000, rank / 1000


# --------------------------------------------------------------------------------------------
# The six criteria
# --------------------------------------------------------------------------------------------


def check_results(
    run: QueryRun, response: SearchResponse, config: CriteriaConfig
) -> CriterionResult:
    names = group_names(response)
    counts = [group.result_count for group in response.groups]
    total = sum(counts)
    cell = " / ".join(str(count) for count in counts) if counts else "0"

    problems: list[str] = []
    if total < config.min_results:
        problems.append(f"{total} results in total, at least {config.min_results} needed")
    is_outfit = run.query.type is InputType.OUTFIT_PHOTO or len(counts) > 1
    empty = [name for name, count in zip(names, counts, strict=True) if is_outfit and count == 0]
    if empty:
        problems.append(f"no results for {', '.join(empty)}")
    if not problems:
        return CriterionResult(Criterion.RESULTS, Status.PASS, cell)

    per_garment = ""
    if len(counts) > 1:
        listed = ", ".join(f"{name} {count}" for name, count in zip(names, counts, strict=True))
        per_garment = f" (per garment: {listed})"
    fetched = _fetched_products(response)
    cause = Cause.RANKING if fetched >= config.min_results else Cause.STORE
    evidence = (
        f"{'; '.join(problems)}{per_garment}. Stores returned {fetched} valid products: "
        f"{store_summary(response)}"
    )
    return CriterionResult(Criterion.RESULTS, Status.FAIL, cell, cause, evidence)


def check_stores(response: SearchResponse, config: CriteriaConfig) -> CriterionResult:
    stores = distinct_stores(response)
    cell = str(len(stores))
    if len(stores) >= config.min_stores:
        return CriterionResult(Criterion.STORES, Status.PASS, cell)
    cause = Cause.RANKING if len(response.stores_used) >= config.min_stores else Cause.STORE
    evidence = (
        f"results come from {len(stores)} store(s) ({', '.join(stores) or 'none'}), at least "
        f"{config.min_stores} needed. {store_summary(response)}"
    )
    return CriterionResult(Criterion.STORES, Status.FAIL, cell, cause, evidence)


def check_seconds(
    run: QueryRun, response: SearchResponse | None, config: CriteriaConfig
) -> CriterionResult:
    seconds = run.duration_ms / 1000
    recorded = run.duration_source == "recorded"
    cell = f"{seconds:.1f}" + (" (recorded)" if recorded else "")
    if seconds <= config.max_seconds:
        return CriterionResult(Criterion.SECONDS, Status.PASS, cell)

    cause = Cause.STORE
    breakdown = "no step timings are available"
    if response is not None and not recorded and response.timings:
        understand, search, rank = _stage_seconds(response)
        stages = {Cause.LLM: understand, Cause.STORE: search, Cause.RANKING: rank}
        cause = max(stages, key=lambda stage: stages[stage])
        breakdown = (
            f"understand {understand:.1f} s, search {search:.1f} s, rank and shape {rank:.1f} s"
        )
    elif recorded:
        breakdown = "the recorded live run's step timings are not kept in a recording"
    evidence = f"took {seconds:.1f} s, at most {config.max_seconds:g} s allowed. {breakdown}"
    return CriterionResult(Criterion.SECONDS, Status.FAIL, cell, cause, evidence)


@dataclass(frozen=True)
class RangeProblem:
    """A price range that misses its target by more than the tolerance and is not flagged."""

    group: str
    tier: Tier
    target: int
    count: int
    span: str

    @property
    def gap(self) -> int:
        return abs(self.count - self.target)


def price_range_problems(response: SearchResponse, tolerance: int = 1) -> list[RangeProblem]:
    problems: list[RangeProblem] = []
    for name, group in zip(group_names(response), response.groups, strict=True):
        for tier in group.tiers:
            if abs(tier.count - tier.target_count) <= tolerance:
                continue
            if Flag.FEW_OPTIONS in tier.flags:
                continue
            span = tier.display_label.split(" · ", 1)[1] if tier.results else "no results"
            problems.append(RangeProblem(name, tier.name, tier.target_count, tier.count, span))
    return problems


def check_price_ranges(response: SearchResponse, config: CriteriaConfig) -> CriterionResult:
    if not response.groups:
        return CriterionResult(
            Criterion.PRICE_RANGES,
            Status.FAIL,
            "no: no price ranges returned",
            Cause.PRICE_RANGE,
            "the response has no garment groups, so there are no price ranges to check",
        )
    problems = price_range_problems(response, config.price_range_tolerance)
    if not problems:
        return CriterionResult(Criterion.PRICE_RANGES, Status.PASS, "yes")
    several = len(response.groups) > 1
    cell = "no: " + "; ".join(
        f"{p.group + ' ' if several else ''}{p.tier.label} {p.count}/{p.target} (gap {p.gap})"
        for p in problems
    )
    evidence = _shown(
        [
            f"{p.group}, {p.tier.label}: {p.count} results for a target of {p.target} "
            f"(gap {p.gap}), no few_options flag; span {p.span}"
            for p in problems
        ]
    )
    return CriterionResult(Criterion.PRICE_RANGES, Status.FAIL, cell, Cause.PRICE_RANGE, evidence)


def check_links(
    response: SearchResponse, link_checks: Sequence[LinkCheck] | None
) -> CriterionResult:
    wanted = {scored.product.product_url for scored in response.products}
    if not wanted:
        return CriterionResult(
            Criterion.LINKS,
            Status.FAIL,
            "no results",
            Cause.STORE,
            "there are no results, so there are no links to open",
        )
    if not link_checks:
        return CriterionResult(Criterion.LINKS, Status.PENDING, "not checked")

    good = [check for check in link_checks if check.ok]
    bad = [check for check in link_checks if not check.ok]
    cell = f"{len(good)}/{len(link_checks)}"
    if bad:
        evidence = _shown([f"{c.url} ({c.store}): {'; '.join(c.problems)}" for c in bad])
        return CriterionResult(Criterion.LINKS, Status.FAIL, cell, Cause.STORE, evidence)
    if wanted <= {check.url for check in link_checks}:
        return CriterionResult(Criterion.LINKS, Status.PASS, cell)
    return CriterionResult(
        Criterion.LINKS,
        Status.PENDING,
        f"{cell} (top 10 only; {len(wanted)} results)",
    )


def check_good_at_10(
    run: QueryRun,
    response: SearchResponse,
    good: Sequence[GroupGood] | None,
    labels: LabelSet | None,
    config: CriteriaConfig,
) -> CriterionResult:
    """good@10 per garment group. A person labels; but a group too small to reach the bar fails
    without any label, because the missing places count as not good (``rubric.md``, step 4)."""
    names = group_names(response)
    sizes = [min(config.top_n, group.result_count) for group in response.groups]
    if not response.groups:
        return CriterionResult(
            Criterion.GOOD_AT_10,
            Status.FAIL,
            "0/10",
            Cause.RANKING,
            "there are no results, so no place in the top 10 can be a good match",
        )

    cells: list[str] = []
    failing: list[str] = []
    for position, (name, size) in enumerate(zip(names, sizes, strict=True)):
        if good is not None:
            figure = good[position]
            cells.append(figure.cell)
            if figure.good < config.min_good:
                failing.append(
                    f"{name}: {figure.good}/{config.top_n} good, at least {config.min_good} needed"
                    + _not_good(labels, run.query.id, name)
                )
        elif size < config.min_good:
            cells.append(f"max {size}/{config.top_n}")
            failing.append(
                f"{name}: only {size} result(s) in the top {config.top_n}, so "
                f"{config.min_good} good matches are impossible (missing places count as not good)"
            )
        else:
            cells.append("?")

    if failing:
        cause = Cause.RANKING
        input_note = ""
        if response.understood.input_type is not run.query.type:
            cause = Cause.LLM
            input_note = (
                f" The input was detected as {response.understood.input_type.value}, "
                f"the query is {run.query.type.value}."
            )
        evidence = f"{_shown(failing)}.{input_note} {_understood_summary(response)}"
        return CriterionResult(
            Criterion.GOOD_AT_10, Status.FAIL, " / ".join(cells), cause, evidence
        )
    if good is None:
        return CriterionResult(Criterion.GOOD_AT_10, Status.PENDING, "not labelled")
    return CriterionResult(Criterion.GOOD_AT_10, Status.PASS, " / ".join(cells))


def _not_good(labels: LabelSet | None, query_id: str, group: str) -> str:
    if labels is None:
        return ""
    rows = [row for row in labels.for_group(query_id, group) if row.label == 0]
    if not rows:
        return ""
    listed = [f'rank {row.rank} "{row.title}" ({row.store})' for row in rows]
    return f". Not good: {_shown(listed)}"


# --------------------------------------------------------------------------------------------
# One query, and a run's failures table
# --------------------------------------------------------------------------------------------


def _failed_run_criteria(run: QueryRun, config: CriteriaConfig) -> tuple[CriterionResult, ...]:
    failure = run.failure
    code = failure.code if failure else "unknown"
    cause = Cause.LLM if code in _LLM_ERROR_CODES else Cause.STORE
    what = (
        f"the pipeline failed ({failure.kind}, code {code}): {failure.message}"
        if failure
        else "the pipeline returned nothing"
    )
    fail = {
        Criterion.RESULTS: "0",
        Criterion.STORES: "0",
        Criterion.LINKS: "no results",
        Criterion.GOOD_AT_10: "0/10",
        Criterion.PRICE_RANGES: "no: no results",
    }
    seconds = check_seconds(run, None, config)
    results: dict[Criterion, CriterionResult] = {
        criterion: CriterionResult(criterion, Status.FAIL, cell, cause, what)
        for criterion, cell in fail.items()
    }
    results[Criterion.SECONDS] = seconds
    return tuple(results[criterion] for criterion in Criterion)


def evaluate_query(
    run: QueryRun,
    *,
    config: CriteriaConfig | None = None,
    link_checks: Sequence[LinkCheck] | None = None,
    labels: LabelSet | None = None,
) -> QueryEvaluation:
    """Judge one query against every criterion."""
    config = config or CriteriaConfig()
    response = run.response
    if response is None:
        return QueryEvaluation(run, _failed_run_criteria(run, config))

    good = good_at_10(run.query.id, run, labels) if labels is not None else None
    criteria = (
        check_results(run, response, config),
        check_stores(response, config),
        check_seconds(run, response, config),
        check_links(response, link_checks),
        check_good_at_10(run, response, good, labels, config),
        check_price_ranges(response, config),
    )
    return QueryEvaluation(
        run,
        criteria,
        tuple(group_names(response)),
        tuple(group.result_count for group in response.groups),
        tuple(good) if good is not None else None,
    )


def failure_rows(evaluations: Sequence[QueryEvaluation]) -> list[FailureRow]:
    """Every failed criterion of every query, one row each. None is left out."""
    rows: list[FailureRow] = []
    for evaluation in evaluations:
        for result in evaluation.criteria:
            if result.status is Status.FAIL and result.cause is not None:
                rows.append(
                    FailureRow(evaluation.query_id, result.criterion, result.cause, result.evidence)
                )
    return rows
