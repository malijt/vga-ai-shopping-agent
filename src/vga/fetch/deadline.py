"""A deadline measured on the injected ``Clock``, so timeouts are tested without real waiting.

``asyncio.timeout`` uses the event loop's own clock, which a test cannot control. This is the same
idea built on ``clock.sleep``: a small watchdog task sleeps for the deadline and, if it wakes first,
cancels the task that is waiting. With the ``FakeClock`` a "slow store" costs no real time; with the
``SystemClock`` it behaves like an ordinary timeout.

The work runs in the caller's own task (it is awaited, not wrapped in a second task), so finishing
in time cancels the watchdog in the same step. That matters for the ``FakeClock``, which only lets
virtual time pass once the event loop has been quiet for a few iterations: a stale watchdog must
not outlive the work by more than that.

A deadline can be **pausable**. A request that is waiting its turn in a queue (the rate limiter,
the platform queue, someone else's robots.txt fetch) has not started, so the time it waits is not
time the store has taken. Code that waits like that says so with ``waiting_in_queue()``; every
pausable deadline around it stops counting for the wait and carries on afterwards with the time it
had left. A plain deadline (the whole request's 30 s, for one) is never paused: the shopper's
time runs while a request queues.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from vga.interfaces import Clock


class _Watchdog:
    """The timer behind one deadline: it can be stopped and restarted with the time it has left."""

    def __init__(self, clock: Clock, seconds: float, task: asyncio.Task[object]) -> None:
        self._clock = clock
        self._task = task
        self._left = seconds
        self._started_at = 0.0
        self._timer: asyncio.Future[None] | None = None
        self._pauses = 0
        self.fired = False

    def start(self) -> None:
        self._started_at = self._clock.monotonic()
        self._timer = asyncio.ensure_future(self._run(self._left))

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def pause(self) -> None:
        self._pauses += 1
        if self._pauses == 1 and self._timer is not None:
            self._left -= self._clock.monotonic() - self._started_at
            self.stop()

    def resume(self) -> None:
        self._pauses -= 1
        if self._pauses == 0 and not self.fired:
            self.start()

    async def _run(self, seconds: float) -> None:
        await self._clock.sleep(seconds)
        self.fired = True
        self._task.cancel()


_PAUSABLE: ContextVar[list[_Watchdog] | None] = ContextVar("pausable_deadlines", default=None)
"""The pausable deadlines the running task is inside, outermost first."""


@asynccontextmanager
async def deadline(clock: Clock, seconds: float, *, pausable: bool = False) -> AsyncIterator[None]:
    """Inside the block, raise ``TimeoutError`` (cancelling whatever is awaited) once ``seconds``
    have passed on ``clock``. Cancelling the caller from outside still cancels it normally.

    With ``pausable=True`` the seconds do not run while the task is inside ``waiting_in_queue()``.
    """
    task = asyncio.current_task()
    if task is None:  # pragma: no cover - always inside a task when awaited
        msg = "deadline() must be used inside a running task"
        raise RuntimeError(msg)
    cancelling_on_entry = task.cancelling()
    watchdog = _Watchdog(clock, seconds, task)
    watchdog.start()
    token = None
    if pausable:
        token = _PAUSABLE.set([*(_PAUSABLE.get() or []), watchdog])
    try:
        yield
    except asyncio.CancelledError:
        if watchdog.fired and task.uncancel() <= cancelling_on_entry:
            msg = f"no answer within {seconds:g} s"
            raise TimeoutError(msg) from None
        raise
    finally:
        if token is not None:
            _PAUSABLE.reset(token)
        watchdog.stop()


@contextmanager
def waiting_in_queue() -> Iterator[None]:
    """Mark the code inside as waiting for its turn, not working: every pausable deadline the task
    is inside stops counting until the block ends. Outside any such deadline it does nothing."""
    watchdogs = _PAUSABLE.get() or []
    for watchdog in watchdogs:
        watchdog.pause()
    try:
        yield
    finally:
        for watchdog in watchdogs:
            watchdog.resume()


async def run_with_deadline[T](
    clock: Clock, seconds: float, work: Awaitable[T], *, pausable: bool = False
) -> T:
    """Await ``work``; raise ``TimeoutError`` and cancel it when ``seconds`` pass first.

    Exceptions raised by ``work`` propagate unchanged. See ``deadline`` for ``pausable``.
    """
    async with deadline(clock, seconds, pausable=pausable):
        return await work
