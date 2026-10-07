"""The overall verdict (plan 11.2.4, assumption A6).

The demo passes when "most" of the 10 queries pass, and "most" means at least 7 (A6). A query
passes only if every criterion holds (``criteria.py``). Because a run is scored before a person
has labelled it, a query may be undecided, and so may the verdict:

- ``PASS``: at least 7 queries already pass. Nothing still pending can change that.
- ``FAIL``: so many queries have failed that 7 can no longer be reached, even if every pending
  query ends up passing.
- ``PENDING``: neither yet. The report says how many queries are still undecided.

The harness never says ``PASS`` on evidence that is still missing.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from eval.harness.criteria import QueryEvaluation, Status


@dataclass(frozen=True)
class Verdict:
    status: Status
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    pending: tuple[str, ...]
    required: int
    total: int

    @property
    def label(self) -> str:
        """``PASS``, ``FAIL`` or ``PENDING``."""
        return self.status.value.upper()

    @property
    def headline(self) -> str:
        return (
            f"{len(self.passed)} of {self.total} queries pass "
            f"(list their ids: {', '.join(self.passed) or 'none'})"
        )


def overall_verdict(evaluations: Sequence[QueryEvaluation], required: int = 7) -> Verdict:
    """Apply the "most queries" rule to a run's evaluations."""
    passed = tuple(e.query_id for e in evaluations if e.status is Status.PASS)
    failed = tuple(e.query_id for e in evaluations if e.status is Status.FAIL)
    pending = tuple(e.query_id for e in evaluations if e.status is Status.PENDING)
    if len(passed) >= required:
        status = Status.PASS
    elif len(passed) + len(pending) < required:
        status = Status.FAIL
    else:
        status = Status.PENDING
    return Verdict(status, passed, failed, pending, required, len(evaluations))
