"""The daily OpenAI call cap and the two-calls-per-request limit (plan 5.2.6). Fails closed."""

from datetime import timedelta

import pytest

from tests.factories import make_search_request, make_settings
from tests.understand.conftest import TEST_DAY, TEST_MODEL, RigFactory
from tests.understand.fake_openai import answer, http_error
from tests.understand.readings import make_reading, make_reading_item
from vga.errors import CallBudgetExceededError, VgaError
from vga.understand import FALLBACK_MARKER, CallBudget, process_call_budget

REQUEST_TEXT = "black oversized blazer"


def _invalid():
    return make_reading(items=[make_reading_item(category="handbags")])


# --------------------------------------------------------------------------------------------
# The counter on its own
# --------------------------------------------------------------------------------------------


def test_the_counter_allows_calls_up_to_the_cap_and_then_refuses() -> None:
    budget = CallBudget(today=lambda: TEST_DAY)

    budget.acquire(2)
    budget.acquire(2)
    with pytest.raises(CallBudgetExceededError):
        budget.acquire(2)

    assert budget.used_today == 2


def test_a_refused_call_is_not_counted() -> None:
    budget = CallBudget(today=lambda: TEST_DAY)
    budget.acquire(1)

    for _ in range(3):
        with pytest.raises(CallBudgetExceededError):
            budget.acquire(1)

    assert budget.used_today == 1


def test_a_cap_of_zero_allows_no_call() -> None:
    with pytest.raises(CallBudgetExceededError):
        CallBudget(today=lambda: TEST_DAY).acquire(0)


def test_the_count_starts_again_on_a_new_day() -> None:
    day = [TEST_DAY]
    budget = CallBudget(today=lambda: day[0])
    budget.acquire(1)
    with pytest.raises(CallBudgetExceededError):
        budget.acquire(1)

    day[0] = TEST_DAY + timedelta(days=1)

    assert budget.used_today == 0
    budget.acquire(1)  # allowed again
    assert budget.used_today == 1


def test_a_changed_cap_applies_at_once() -> None:
    budget = CallBudget(today=lambda: TEST_DAY)
    budget.acquire(1)

    with pytest.raises(CallBudgetExceededError):
        budget.acquire(1)
    budget.acquire(5)  # the setting was raised: no restart needed


def test_the_process_wide_budget_is_one_shared_object() -> None:
    assert process_call_budget() is process_call_budget()
    assert isinstance(process_call_budget().used_today, int)


# --------------------------------------------------------------------------------------------
# In the understander
# --------------------------------------------------------------------------------------------


async def test_at_the_cap_no_openai_call_is_made_and_the_shopper_gets_a_plain_message(
    rig: RigFactory,
) -> None:
    r = rig(settings_override=make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=0))

    with pytest.raises(CallBudgetExceededError) as caught:
        await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert r.fake.requests == []
    assert "daily limit" in str(caught.value)
    assert "try again tomorrow" in str(caught.value).lower()
    assert isinstance(caught.value, VgaError)


async def test_the_cap_applies_across_requests(rig: RigFactory) -> None:
    r = rig(
        answer(make_reading()),
        settings_override=make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=1),
    )

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))
    with pytest.raises(CallBudgetExceededError):
        await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1


async def test_a_retried_or_failed_call_still_counts_against_the_cap(rig: RigFactory) -> None:
    r = rig(
        http_error(429),
        http_error(500),
        settings_override=make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=2),
    )

    first = await r.understander.understand(make_search_request(text=REQUEST_TEXT))
    assert first.model == FALLBACK_MARKER
    assert r.budget.used_today == 2

    with pytest.raises(CallBudgetExceededError):
        await r.understander.understand(make_search_request(text=REQUEST_TEXT))
    assert len(r.fake.requests) == 2


async def test_the_cap_is_checked_before_the_corrective_retry_too(rig: RigFactory) -> None:
    r = rig(
        answer(_invalid()),
        answer(make_reading()),
        settings_override=make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=1),
    )

    with pytest.raises(CallBudgetExceededError):
        await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(r.fake.requests) == 1  # the corrective call was never made


async def test_two_understanders_in_one_process_share_the_counter(rig: RigFactory) -> None:
    # A Streamlit page may build a new understander on every click; the cap must still hold.
    settings = make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=2)
    first = rig(answer(make_reading()), settings_override=settings)
    second = rig(answer(make_reading()), answer(make_reading()), settings_override=settings)

    await first.understander.understand(make_search_request(text=REQUEST_TEXT))
    await second.understander.understand(make_search_request(text=REQUEST_TEXT))
    with pytest.raises(CallBudgetExceededError):
        await first.understander.understand(make_search_request(text=REQUEST_TEXT))

    assert len(first.fake.requests) == 1
    assert len(second.fake.requests) == 1


async def test_one_request_never_makes_more_than_two_calls(rig: RigFactory) -> None:
    # A 429 and an invalid answer use the two calls; a third would fail the test at teardown.
    r = rig(http_error(429), answer(_invalid()))

    await r.understander.understand(make_search_request(text="black leather jacket"))

    assert len(r.fake.requests) == 2
    assert r.budget.used_today == 2
