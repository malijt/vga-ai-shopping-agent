"""Run the acceptance queries one after another (plan 11.1.2).

Queries run strictly in sequence, never in parallel: every query visits live stores, and the
BRD asks for about 1 request per second per store. The runner only calls ``Pipeline.run`` and
measures; it knows nothing about stores, models or recordings. A recording session (11.1.3) plugs
in through ``QueryScope``, which is told when each query starts and ends.

A query whose pipeline raises is not allowed to stop the run: the failure is kept (code and
plain message, never a stack trace) so the report lists it as a failed query and the other nine
still run. Nothing is swallowed silently.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from eval.harness.queries import AcceptanceQuery
from vga.errors import VgaError
from vga.interfaces import Clock, Pipeline
from vga.models import SearchRequest, SearchResponse
from vga.settings import Settings

ImageLoader = Callable[[AcceptanceQuery], bytes | None]
"""Gives the photo's bytes for a query, or ``None`` for a text-only query."""

DurationSource = Literal["measured", "recorded", "unavailable"]


class QueryScope(Protocol):
    """Told when each query starts and ends. A recording or replay session implements this."""

    def begin_query(self, query_id: str) -> None: ...

    def end_query(self, query_id: str, *, duration_ms: float) -> None: ...


@dataclass(frozen=True)
class PipelineFailure:
    """Why a query produced no response."""

    code: str
    message: str
    kind: str
    """The exception class name, for the developer reading the report."""


@dataclass(frozen=True)
class QueryRun:
    """What running one query produced: a response or a failure, and how long it took."""

    query: AcceptanceQuery
    response: SearchResponse | None
    failure: PipelineFailure | None
    wall_ms: float
    """Time the runner measured around ``Pipeline.run``."""
    duration_ms: float
    """The figure the 30 s limit is checked against: the slower of the pipeline's own
    ``duration_ms`` and the runner's wall time, or the recorded live figure on a replay."""
    duration_source: DurationSource = "measured"


def build_request(query: AcceptanceQuery, image: bytes | None) -> SearchRequest:
    """The request a shopper would have made for this query."""
    return SearchRequest(text=query.text, image=image)


def _failure_from(exc: Exception) -> PipelineFailure:
    if isinstance(exc, VgaError):
        return PipelineFailure(exc.code, exc.user_message, type(exc).__name__)
    return PipelineFailure("unexpected", f"{type(exc).__name__}: {exc}", type(exc).__name__)


async def run_query(
    query: AcceptanceQuery,
    pipeline: Pipeline,
    settings: Settings,
    *,
    clock: Clock,
    image: bytes | None,
) -> QueryRun:
    """Run one query and time it. A failing pipeline becomes a ``PipelineFailure``."""
    request = build_request(query, image)
    started = clock.monotonic()
    response: SearchResponse | None = None
    failure: PipelineFailure | None = None
    try:
        response = await pipeline.run(request, settings)
    except Exception as exc:  # a broken query must not stop the other nine; it is reported
        failure = _failure_from(exc)
    wall_ms = (clock.monotonic() - started) * 1000.0
    duration_ms = wall_ms if response is None else max(response.duration_ms, wall_ms)
    return QueryRun(query, response, failure, wall_ms, duration_ms)


async def run_queries(
    queries: list[AcceptanceQuery],
    pipeline: Pipeline,
    settings: Settings,
    *,
    clock: Clock,
    load_image: ImageLoader,
    scope: QueryScope | None = None,
    progress: Callable[[QueryRun], None] | None = None,
) -> list[QueryRun]:
    """Run ``queries`` in order, one at a time, and return one ``QueryRun`` each."""
    runs: list[QueryRun] = []
    for query in queries:
        image = load_image(query)
        try:
            if scope is not None:
                scope.begin_query(query.id)
        except VgaError as exc:
            # A replay cannot serve this query (not recorded, or recorded incompletely). That is
            # this query's failure, reported as such; the other queries still run.
            run = QueryRun(query, None, _failure_from(exc), 0.0, 0.0)
        else:
            run = await run_query(query, pipeline, settings, clock=clock, image=image)
            if scope is not None:
                scope.end_query(query.id, duration_ms=run.duration_ms)
        runs.append(run)
        if progress is not None:
            progress(run)
    return runs
