"""Run the acceptance queries one after another (plan 11.1.2).

Queries run strictly in sequence, never in parallel: every query visits live stores, and the
BRD asks for about 1 request per second per store. The runner only calls ``Pipeline.run`` and
measures; it knows nothing about stores, models or recordings. A recording session (11.1.3) plugs
in through ``QueryScope``, which is told when each query starts and ends.

A query whose pipeline raises is not allowed to stop the run: the failure is kept (code and
plain message, never a stack trace) so the report lists it as a failed query and the other nine
still run. Nothing is swallowed silently.

**The gender question.** A query may record the shopper's answer to "Who is this for?"
(``shopper_gender``). After the first search, if the app would ask (some garment's gender was not
stated) the runner answers it as the page does: one more search with the answer applied
(``eval.harness.confirm``). That second response is the one scored, labelled and link-checked. The
30 s limit is checked against the first search alone, because that is the wait before the shopper
sees anything; the second search's time is kept beside it.
"""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from eval.harness.confirm import GenderAnswer, read_question, rerun_overrides, rerun_request
from eval.harness.queries import AcceptanceQuery
from vga.errors import VgaError
from vga.interfaces import Clock, Pipeline
from vga.models import RunOverrides, SearchRequest, SearchResponse, StepTiming
from vga.settings import Settings

ImageLoader = Callable[[AcceptanceQuery], bytes | None]
"""Gives the photo's bytes for a query, or ``None`` for a text-only query."""

AfterQuery = Callable[[Sequence["QueryRun"]], Awaitable[None]]
"""Called after each query with every run so far (the one just finished is the last). The live
run saves it here and checks that query's links, so the next query starts only when this one is
on disk and its links are checked."""

DurationSource = Literal["measured", "recorded", "unavailable"]


class QueryScope(Protocol):
    """Told when each query starts and ends. A recording or replay session implements this."""

    def begin_query(self, query_id: str) -> None: ...

    def end_query(
        self, query_id: str, *, duration_ms: float, confirm_ms: float | None = None
    ) -> None:
        """``duration_ms`` is the first search; ``confirm_ms`` the search after the gender question
        was answered, or ``None`` when there was none."""
        ...


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
    """The response that is scored, labelled and link-checked: what the shopper sees at the end.
    When the gender question was asked, that is the search after the answer."""
    failure: PipelineFailure | None
    wall_ms: float
    """Time the runner measured around the first ``Pipeline.run``."""
    duration_ms: float
    """The figure the 30 s limit is checked against: the first search only, the wait before the
    shopper sees anything. The slower of the pipeline's own ``duration_ms`` and the runner's wall
    time, or the recorded live figure on a replay."""
    duration_source: DurationSource = "measured"
    gender: GenderAnswer | None = None
    """What happened to the "Who is this for?" question; ``None`` when the query records no
    answer."""

    @property
    def first_timings(self) -> list[StepTiming]:
        """The step timings of the first search, which the 30 s limit is about."""
        if self.gender is not None and self.gender.asked:
            return list(self.gender.first_timings)
        return list(self.response.timings) if self.response is not None else []

    @property
    def confirm_ms(self) -> float | None:
        """The search after the answer, or ``None`` when the question was not asked."""
        return self.gender.duration_ms if self.gender is not None and self.gender.asked else None

    @property
    def total_ms(self) -> float:
        """The first search and the search after the answer, added up."""
        return self.duration_ms + (self.confirm_ms or 0.0)


def build_request(query: AcceptanceQuery, image: bytes | None) -> SearchRequest:
    """The request a shopper would have made for this query."""
    return SearchRequest(text=query.text, image=image)


_BYTES_LITERAL = re.compile(r"""\bb(['"]).*?(?<!\\)\1""", re.DOTALL)
_MAX_MESSAGE_CHARS = 500


def _without_bytes(text: str) -> str:
    """Hide anything printed as a bytes literal, and keep the message short.

    An unexpected exception's text is saved in ``run.json`` and the report, which may be committed.
    A library error that quotes the value it choked on (a validation error shows ``input_value``)
    could quote the shopper's photo, so no bytes literal is ever kept (BRD Rule 4)."""
    shown = _BYTES_LITERAL.sub("<bytes omitted>", text)
    return shown if len(shown) <= _MAX_MESSAGE_CHARS else shown[:_MAX_MESSAGE_CHARS] + "..."


def _failure_from(exc: Exception) -> PipelineFailure:
    if isinstance(exc, VgaError):
        return PipelineFailure(exc.code, exc.user_message, type(exc).__name__)
    message = _without_bytes(f"{type(exc).__name__}: {exc}")
    return PipelineFailure("unexpected", message, type(exc).__name__)


@dataclass(frozen=True)
class _Timed:
    """One ``Pipeline.run`` call: its response or failure, and how long it took."""

    response: SearchResponse | None
    failure: PipelineFailure | None
    wall_ms: float
    duration_ms: float


async def _timed_run(
    pipeline: Pipeline,
    request: SearchRequest,
    settings: Settings,
    overrides: RunOverrides | None,
    clock: Clock,
) -> _Timed:
    started = clock.monotonic()
    response: SearchResponse | None = None
    failure: PipelineFailure | None = None
    try:
        response = await pipeline.run(request, settings, overrides)
    except Exception as exc:  # a broken query must not stop the other nine; it is reported
        failure = _failure_from(exc)
    wall_ms = (clock.monotonic() - started) * 1000.0
    duration_ms = wall_ms if response is None else max(response.duration_ms, wall_ms)
    return _Timed(response, failure, wall_ms, duration_ms)


async def run_query(
    query: AcceptanceQuery,
    pipeline: Pipeline,
    settings: Settings,
    *,
    clock: Clock,
    image: bytes | None,
) -> QueryRun:
    """Run one query and time it. A failing pipeline becomes a ``PipelineFailure``.

    When the query records the shopper's answer to "Who is this for?" and the app would ask, the
    answer is given as the page gives it (see ``eval.harness.confirm``) and the second response
    is the one returned."""
    first = await _timed_run(pipeline, build_request(query, image), settings, None, clock)
    if first.response is None or query.shopper_gender is None:
        return QueryRun(query, first.response, first.failure, first.wall_ms, first.duration_ms)

    question = read_question(first.response.understood, query.shopper_gender)
    if question.edits is None:
        # Every garment's gender was stated, so the page would not ask. What was typed stands.
        answer = GenderAnswer(
            answer=question.answer,
            asked=False,
            typed_differently=list(question.typed_differently),
        )
        return QueryRun(
            query, first.response, None, first.wall_ms, first.duration_ms, gender=answer
        )

    second = await _timed_run(
        pipeline,
        rerun_request(first.response),
        settings,
        rerun_overrides(first.response, question.edits),
        clock,
    )
    answer = GenderAnswer(
        answer=question.answer,
        asked=True,
        garments=list(question.asked_about),
        typed_differently=list(question.typed_differently),
        first_timings=list(first.response.timings),
        wall_ms=second.wall_ms,
        duration_ms=second.duration_ms,
    )
    failure = _failure_after_the_answer(second.failure, question.answer.value)
    return QueryRun(
        query, second.response, failure, first.wall_ms, first.duration_ms, gender=answer
    )


def _failure_after_the_answer(
    failure: PipelineFailure | None, answer: str
) -> PipelineFailure | None:
    """The second search's failure, worded so the report says where in the shopper's path it
    happened: the first search had worked and the answer was given."""
    if failure is None:
        return None
    message = (
        f"After the shopper answered '{answer}' the search could not be repeated. {failure.message}"
    )
    return PipelineFailure(failure.code, message, failure.kind)


async def run_queries(
    queries: list[AcceptanceQuery],
    pipeline: Pipeline,
    settings: Settings,
    *,
    clock: Clock,
    load_image: ImageLoader,
    scope: QueryScope | None = None,
    progress: Callable[[QueryRun], None] | None = None,
    after_query: AfterQuery | None = None,
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
                scope.end_query(query.id, duration_ms=run.duration_ms, confirm_ms=run.confirm_ms)
        runs.append(run)
        if progress is not None:
            progress(run)
        if after_query is not None:
            await after_query(runs)
    return runs
