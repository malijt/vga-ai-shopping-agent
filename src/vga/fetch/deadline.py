"""A deadline measured on the injected ``Clock``, so timeouts are tested without real waiting.

``asyncio.timeout`` uses the event loop's own clock, which a test cannot control. This is the same
idea built on ``clock.sleep``: a small watchdog task sleeps for the deadline and, if it wakes first,
cancels the task that is waiting. With the ``FakeClock`` a "slow store" costs no real time; with the
``SystemClock`` it behaves like an ordinary timeout.

The work runs in the caller's own task (it is awaited, not wrapped in a second task), so finishing
in time cancels the watchdog in the same step. That matters for the ``FakeClock``, which only lets
virtual time pass once the event loop has been quiet for a few iterations: a stale watchdog must
not outlive the work by more than that.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

from vga.interfaces import Clock


@asynccontextmanager
async def deadline(clock: Clock, seconds: float) -> AsyncIterator[None]:
    """Inside the block, raise ``TimeoutError`` (cancelling whatever is awaited) once ``seconds``
    have passed on ``clock``. Cancelling the caller from outside still cancels it normally."""
    task = asyncio.current_task()
    if task is None:  # pragma: no cover - always inside a task when awaited
        msg = "deadline() must be used inside a running task"
        raise RuntimeError(msg)
    cancelling_on_entry = task.cancelling()
    fired = False

    async def watchdog() -> None:
        nonlocal fired
        await clock.sleep(seconds)
        fired = True
        task.cancel()

    timer = asyncio.ensure_future(watchdog())
    try:
        yield
    except asyncio.CancelledError:
        if fired and task.uncancel() <= cancelling_on_entry:
            msg = f"no answer within {seconds:g} s"
            raise TimeoutError(msg) from None
        raise
    finally:
        timer.cancel()


async def run_with_deadline[T](clock: Clock, seconds: float, work: Awaitable[T]) -> T:
    """Await ``work``; raise ``TimeoutError`` and cancel it when ``seconds`` pass first.

    Exceptions raised by ``work`` propagate unchanged.
    """
    async with deadline(clock, seconds):
        return await work
