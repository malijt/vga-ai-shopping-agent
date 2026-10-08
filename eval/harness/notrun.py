"""A query that was not run: neither a pass nor a fail (plan 16.1.1, run of 2026-10-08).

The first recorded run sent its ten queries back to back. The platform turned all thirteen stores
away during the first one, and the other nine found every store in its cooldown. The report then
said ``0 of 10 queries pass`` and ``FAIL``, which describes nine queries that were never really
run. A query like that is *not run*:

``stores_unavailable``
    The search came back with no result because every store that could be asked was blocked or in
    its cooldown. Nothing was found out about the app, so there is nothing to judge.
``not_sent``
    The query was never sent: the run stopped before it (after a query whose stores were not
    available), was interrupted, or has not got to it yet; or a replay's recording ends before it
    because the live run stopped.

A query that got results from some stores is *not* here, however many other stores were turned
away: it is judged on what it got, and the report lists the stores that were skipped.
"""

from typing import Literal

from pydantic import Field

from vga.models import SearchResponse, StoreReport, StoreStatus, VgaModel

NotRunKind = Literal["stores_unavailable", "not_sent"]

THROTTLED = frozenset({StoreStatus.BLOCKED, StoreStatus.COOLDOWN})
"""A store that turned the search away, or that the app is leaving alone because it just did."""

_NEUTRAL = frozenset({StoreStatus.EMPTY})
"""A store that answered "nothing matched", or that was left out because it does not sell the
garment, says nothing about whether the other stores were reachable."""

STORES_UNAVAILABLE_WHY = "the stores were blocked or in cooldown"
NOT_SENT_WHY = "the run stopped before sending them"


class ThrottledStore(VgaModel):
    """One store that could not be asked, with the reason the response gave."""

    store_id: str
    status: StoreStatus
    reason: str | None = None


class NotRun(VgaModel):
    """Why a query has no verdict of its own."""

    kind: NotRunKind
    reason: str
    """One plain sentence: what happened to this query."""
    stores: list[ThrottledStore] = Field(default_factory=list)
    """For ``stores_unavailable``: the stores that were blocked or in cooldown, with the reasons the
    response gave. A store that does not sell the garment, or that found nothing, is not listed."""
    cooldown_s: int | None = Field(default=None, ge=0)
    """For ``stores_unavailable``: how long the app leaves a blocked store alone (the
    ``store_cooldown_s`` setting). The response does not say how much of it is left, so this is
    the longest it can be."""


def stores_unavailable(response: SearchResponse, cooldown_s: int) -> NotRun | None:
    """``NotRun`` when ``response`` has no result because the stores could not be asked, else
    ``None``.

    The test: there is no result, at least one store was blocked or in cooldown, and every other
    skipped store merely had nothing to show (``empty``). A store that timed out, failed or is
    barred by its robots.txt is a different problem, so such a query is judged as it always was."""
    if response.result_count > 0 or response.stores_used:
        return None
    throttled = [report for report in response.stores_skipped if report.status in THROTTLED]
    if not throttled:
        return None
    if any(r.status not in THROTTLED | _NEUTRAL for r in response.stores_skipped):
        return None
    return NotRun(
        kind="stores_unavailable",
        reason=(
            f"Every store that could be asked turned the search away ({len(throttled)} blocked or "
            "in cooldown), so there is nothing to judge."
        ),
        stores=[_store_of(report) for report in throttled],
        cooldown_s=cooldown_s,
    )


def _store_of(report: StoreReport) -> ThrottledStore:
    return ThrottledStore(store_id=report.store_id, status=report.status, reason=report.reason)


def not_sent(reason: str) -> NotRun:
    """A query that was never sent, and why."""
    return NotRun(kind="not_sent", reason=reason)


def describe_wait(seconds: float) -> str:
    """``15 minutes`` for 900, ``90 s`` for 90: a wait as a person would say it."""
    if seconds >= 120:
        minutes = round(seconds / 60)
        return f"{minutes} minutes"
    return f"{seconds:g} s"
