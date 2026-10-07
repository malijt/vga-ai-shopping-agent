"""The daily cap on OpenAI calls (plan 5.2.6). Fails closed: at the cap, no call is made.

The counter lives in this process and nowhere else (no database, by design: the app has none). It
is shared by every ``OpenAIUnderstander`` in the process through ``process_call_budget()``. That
matters because a Streamlit page re-runs its script on every click and may build a new
understander each time: a per-instance counter would reset on every search and cap nothing.

The cap is passed in at each call rather than stored, so a changed setting takes effect at once.
The day rolls over at midnight UTC.
"""

import threading
from collections.abc import Callable
from datetime import UTC, date, datetime

from vga.errors import CallBudgetExceededError
from vga.log import get_logger

log = get_logger(__name__)


def utc_today() -> date:
    return datetime.now(UTC).date()


class CallBudget:
    """Counts OpenAI calls for the current day. Thread-safe: Streamlit runs scripts in threads."""

    def __init__(self, today: Callable[[], date] = utc_today) -> None:
        self._today = today
        self._lock = threading.Lock()
        self._day: date | None = None
        self._used = 0

    @property
    def used_today(self) -> int:
        with self._lock:
            return self._used if self._day == self._today() else 0

    def acquire(self, daily_cap: int) -> None:
        """Reserve one call, or raise ``CallBudgetExceededError`` when the cap is used up.

        Call it immediately before every OpenAI request, including retries. A failed request still
        counts: the cap protects spend and rate limits, and a call that errors may still be billed.
        """
        with self._lock:
            today = self._today()
            if self._day != today:
                self._day, self._used = today, 0
            if self._used >= daily_cap:
                used = self._used
            else:
                self._used += 1
                return
        log.warning(
            "daily OpenAI call cap reached, no call made",
            extra={"daily_cap": daily_cap, "used_today": used},
        )
        raise CallBudgetExceededError(
            detail=f"daily cap of {daily_cap} calls reached ({used} used)"
        )


_PROCESS_BUDGET = CallBudget()


def process_call_budget() -> CallBudget:
    """The one budget shared by the whole process."""
    return _PROCESS_BUDGET
