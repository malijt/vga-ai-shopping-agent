"""A deadline measured on the injected ``Clock``, so timeouts are tested without real waiting.

``asyncio.timeout`` uses the event loop's own clock, which a test cannot control. This races the
work against ``clock.sleep(seconds)`` instead: with the ``FakeClock`` a "slow store" costs no real
time, with the ``SystemClock`` it behaves like an ordinary timeout.
"""

import asyncio
from collections.abc import Awaitable
from typing import Any

from vga.interfaces import Clock


async def run_with_deadline[T](clock: Clock, seconds: float, work: Awaitable[T]) -> T:
    """Await ``work``; raise ``TimeoutError`` and cancel it when ``seconds`` pass first.

    Exceptions raised by ``work`` propagate unchanged. Cancelling the caller cancels both the work
    and the timer.
    """
    task: asyncio.Future[T] = asyncio.ensure_future(work)
    timer: asyncio.Future[None] = asyncio.ensure_future(clock.sleep(seconds))
    pending: set[asyncio.Future[Any]] = {task, timer}
    try:
        await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            return task.result()
        msg = f"no answer within {seconds:g} s"
        raise TimeoutError(msg)
    finally:
        for future in pending:
            if not future.done():
                future.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
