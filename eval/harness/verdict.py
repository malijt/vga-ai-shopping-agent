"""The overall verdict (plan 11.2.4, assumption A6).

The demo passes when "most" of the 10 queries pass, and "most" means at least 7 (A6). A query
passes only if every criterion holds (``criteria.py``). Because a run is scored before a person
has labelled it, a query may be undecided, and so may the verdict:

- ``PASS``: at least 7 queries already pass. Nothing still pending can change that.
- ``FAIL``: so many queries have failed that 7 can no longer be reached, even if every pending
  query ends up passing.
- ``PENDING``: neither yet. The report says how many queries are still undecided.
- ``INCOMPLETE``: some query was *not run* (its stores were blocked or in cooldown, or it was never
  sent because the run stopped). A query that was not run is neither a pass nor a fail, and a
  verdict over the queries that did run would describe a different test. The verdict says how many
  ran, how many did not and why, and the run is repeated for the rest.

The harness never says ``PASS`` on evidence that is still missing.

An *extra set* (for example the 11 extra photos) is not part of the pass rule. It gets no demo
verdict: ``required`` is ``None``, the label reads ``EXTRA SET``, and the headline only counts how
many of its N queries pass the per-query rule.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from eval.harness.criteria import QueryEvaluation, Status
from eval.harness.notrun import NOT_SENT_WHY, STORES_UNAVAILABLE_WHY, NotRunKind

NOT_RUN_WHY: dict[NotRunKind, str] = {
    "stores_unavailable": STORES_UNAVAILABLE_WHY,
    "not_sent": NOT_SENT_WHY,
}
"""The reason for each kind of query that was not run, as the one-sentence verdict gives it."""


@dataclass(frozen=True)
class NotRunQuery:
    """A query that has no verdict of its own, and the kind of reason."""

    query_id: str
    kind: NotRunKind


@dataclass(frozen=True)
class Verdict:
    status: Status
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    pending: tuple[str, ...]
    required: int | None
    """Queries that must pass for the demo to pass; ``None`` for an extra set, which has no rule."""
    total: int
    not_run: tuple[NotRunQuery, ...] = ()
    """The queries that were not run, in run order."""

    @property
    def label(self) -> str:
        """``PASS``, ``FAIL``, ``PENDING`` or, when any query was not run, ``INCOMPLETE``;
        ``EXTRA SET`` when no pass rule applies."""
        if self.required is None:
            return "EXTRA SET"
        return "INCOMPLETE" if self.not_run else self.status.value.upper()

    @property
    def ran(self) -> int:
        return self.total - len(self.not_run)

    @property
    def headline(self) -> str:
        if self.not_run:
            return self.incomplete_sentence
        return (
            f"{len(self.passed)} of {self.total} queries pass "
            f"(list their ids: {', '.join(self.passed) or 'none'})"
        )

    @property
    def incomplete_sentence(self) -> str:
        """How many queries ran, how many did not and why, in one sentence."""
        counts = {
            NOT_RUN_WHY[kind]: sum(1 for item in self.not_run if item.kind == kind)
            for kind in NOT_RUN_WHY
        }
        why = ", ".join(f"{count} because {text}" for text, count in counts.items() if count)
        return f"{self.ran} of {self.total} queries ran and {len(self.not_run)} did not ({why})"


def overall_verdict(evaluations: Sequence[QueryEvaluation], required: int | None = 7) -> Verdict:
    """Apply the "most queries" rule to a run's evaluations. ``required=None`` is an extra set:
    the counts are kept and no rule is applied."""
    passed = tuple(e.query_id for e in evaluations if e.status is Status.PASS)
    failed = tuple(e.query_id for e in evaluations if e.status is Status.FAIL)
    pending = tuple(e.query_id for e in evaluations if e.status is Status.PENDING)
    not_run = tuple(
        NotRunQuery(e.query_id, e.run.not_run.kind)
        for e in evaluations
        if e.run.not_run is not None
    )
    if required is None:
        # No rule applies, so `status` means nothing here (PENDING by convention); callers check
        # `required is None` first and print the counts only.
        return Verdict(Status.PENDING, passed, failed, pending, None, len(evaluations), not_run)
    if len(passed) >= required:
        status = Status.PASS
    elif len(passed) + len(pending) + len(not_run) < required:  # a query not run is undecided
        status = Status.FAIL
    else:
        status = Status.PENDING
    return Verdict(status, passed, failed, pending, required, len(evaluations), not_run)
