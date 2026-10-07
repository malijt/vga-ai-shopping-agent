"""Retries, backoff and the deadline (plan 5.2.1). Time is the injected FakeClock."""

import pytest

from tests.factories import make_search_request
from tests.understand.conftest import FIRST_BACKOFF_S, RigFactory
from tests.understand.fake_openai import (
    RecordedRequest,
    answer,
    connection_error,
    http_error,
    timeout,
)
from tests.understand.readings import make_reading
from vga.understand import FALLBACK_MARKER, PROMPT_VERSION
from vga.understand.gateway import MAX_BACKOFF_S, OPENAI_TIMEOUT_S

REQUEST_TEXT = "black oversized blazer"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 529])
async def test_a_429_or_5xx_is_retried_once_after_a_backoff(rig: RigFactory, status: int) -> None:
    r = rig(http_error(status), answer(make_reading()))

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 2
    assert r.clock.sleeps == [FIRST_BACKOFF_S]
    assert result.model != FALLBACK_MARKER
    assert result.usage.llm_calls == 2


async def test_a_timeout_is_retried_once(rig: RigFactory) -> None:
    r = rig(timeout(), answer(make_reading()))

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 2
    assert result.prompt_version == PROMPT_VERSION


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_any_other_http_error_is_not_retried(rig: RigFactory, status: int) -> None:
    r = rig(http_error(status))

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1
    assert r.clock.sleeps == []
    assert result.model == FALLBACK_MARKER  # text request: it falls back to the shopper's words


async def test_a_refused_connection_is_not_retried(rig: RigFactory) -> None:
    r = rig(connection_error())

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1
    assert result.model == FALLBACK_MARKER


async def test_at_most_two_attempts_are_made_and_then_the_fallback_applies(
    rig: RigFactory,
) -> None:
    # The fake would refuse a third request and fail the test at teardown.
    r = rig(http_error(429), http_error(429))

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 2
    assert len(r.clock.sleeps) == 1
    assert result.model == FALLBACK_MARKER
    assert result.usage.llm_calls == 2


async def test_the_sdks_own_retries_are_switched_off(rig: RigFactory) -> None:
    # The fake client is built with the SDK default of 2 retries. If the gateway left them on, one
    # 429 would reach the fake three times and cost three calls, unseen by the call budget.
    r = rig(http_error(429), http_error(429))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 2
    assert r.budget.used_today == 2


@pytest.mark.parametrize(
    ("jitter", "expected"), [(0.0, 0.5), (0.5, 0.75), (0.999, pytest.approx(0.9995))]
)
async def test_backoff_is_half_a_second_plus_up_to_that_much_jitter(
    rig: RigFactory, jitter: float, expected: float
) -> None:
    r = rig(http_error(500), answer(make_reading()), jitter=lambda: jitter)

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [expected]


async def test_a_retry_after_header_is_honoured_when_it_is_longer_than_the_backoff(
    rig: RigFactory,
) -> None:
    r = rig(http_error(429, {"retry-after": "3"}), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [3.0]


async def test_a_retry_after_in_milliseconds_is_understood(rig: RigFactory) -> None:
    r = rig(http_error(429, {"retry-after-ms": "1500"}), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [1.5]


async def test_a_huge_retry_after_is_capped(rig: RigFactory) -> None:
    r = rig(http_error(429, {"retry-after": "120"}), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [MAX_BACKOFF_S]


async def test_a_retry_that_cannot_finish_before_the_deadline_is_not_made(
    rig: RigFactory,
) -> None:
    # 1.5 s allowed: the backoff (0.75 s) plus the 1 s a call needs does not fit.
    r = rig(http_error(500), deadline_s=1.5)

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1
    assert r.clock.sleeps == []
    assert result.model == FALLBACK_MARKER


async def test_a_slow_first_call_leaves_no_time_to_retry(rig: RigFactory) -> None:
    r = rig(
        http_error(500),
        deadline_s=30,
        on_request=lambda _request: r.clock.advance(28.5),
    )

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1
    assert result.model == FALLBACK_MARKER


async def test_a_late_attempt_is_given_only_the_time_that_is_left(rig: RigFactory) -> None:
    advanced: list[RecordedRequest] = []

    def slow_first_call(request: RecordedRequest) -> None:
        if not advanced:
            r.clock.advance(20.0)
        advanced.append(request)

    r = rig(http_error(500), answer(make_reading()), deadline_s=30, on_request=slow_first_call)

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    first, second = r.fake.requests
    assert first.timeout["read"] == OPENAI_TIMEOUT_S
    # 20 s slow call + 0.75 s backoff leaves 9.25 s of the 30 s deadline.
    assert second.timeout["read"] == pytest.approx(9.25)


async def test_no_call_is_made_when_the_deadline_has_already_gone(rig: RigFactory) -> None:
    r = rig(deadline_s=0.5)

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.fake.requests == []
    assert result.model == FALLBACK_MARKER
    assert result.usage.llm_calls == 0


async def test_an_unreadable_retry_after_header_is_ignored(rig: RigFactory) -> None:
    r = rig(http_error(429, {"retry-after": "soon"}), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [FIRST_BACKOFF_S]


async def test_a_retry_after_shorter_than_the_backoff_does_not_shorten_it(rig: RigFactory) -> None:
    r = rig(http_error(429, {"retry-after": "0"}), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.clock.sleeps == [FIRST_BACKOFF_S]


async def test_by_default_this_step_may_spend_at_most_twenty_seconds(rig: RigFactory) -> None:
    # The request deadline is 30 s; the stores must keep a share of it. A first call that took
    # 18.5 s leaves too little for a retry (18.5 + 0.75 backoff + 1 s to be worth a call > 20).
    r = rig(http_error(500), on_request=lambda _request: r.clock.advance(18.5))

    result = await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1
    assert result.model == FALLBACK_MARKER
