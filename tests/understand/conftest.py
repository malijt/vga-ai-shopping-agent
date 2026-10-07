"""Fixtures for the Understand tests: a real ``OpenAIUnderstander`` wired to a fake OpenAI."""

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from tests.factories import make_settings
from tests.fakes import FakeClock
from tests.understand.fake_openai import FakeOpenAI, Step
from vga.settings import Settings
from vga.understand import OpenAIUnderstander
from vga.understand.budget import CallBudget

TEST_MODEL = "gpt-5-mini-2025-08-07"
TEST_DAY = date(2026, 10, 7)
FIXED_JITTER = 0.5
"""Backoff is ``0.5 s * (1 + jitter)`` for the first retry: 0.75 s with this jitter."""
FIRST_BACKOFF_S = 0.75


@dataclass
class Rig:
    """An understander plus everything a test needs to inspect it."""

    understander: OpenAIUnderstander
    fake: FakeOpenAI
    clock: FakeClock
    budget: CallBudget
    settings: Settings


RigFactory = Callable[..., Rig]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return make_settings(openai_model=TEST_MODEL, daily_llm_call_cap=100)


@pytest.fixture
def budget() -> CallBudget:
    return CallBudget(today=lambda: TEST_DAY)


@pytest.fixture(autouse=True)
def _log_info(caplog: pytest.LogCaptureFixture) -> None:
    """Capture the ``vga`` loggers at INFO, so tests can read the lines the code writes."""
    caplog.set_level(logging.INFO, logger="vga")


@pytest.fixture
async def rig(
    clock: FakeClock, settings: Settings, budget: CallBudget
) -> AsyncIterator[RigFactory]:
    """``rig(*steps, default=None, settings=None, **understander_options)`` builds a rig.

    At teardown every fake is closed and the test fails if any request arrived that no step was
    scripted for.
    """
    built: list[Rig] = []

    def build(
        *steps: Step,
        default: Step | None = None,
        on_request: Callable[..., None] | None = None,
        settings_override: Settings | None = None,
        **options: Any,
    ) -> Rig:
        fake = FakeOpenAI(*steps, default=default, on_request=on_request)
        chosen = settings_override or settings
        options.setdefault("jitter", lambda: FIXED_JITTER)
        understander = OpenAIUnderstander(
            chosen, fake.client(), clock=clock, budget=budget, **options
        )
        rig_ = Rig(understander, fake, clock, budget, chosen)
        built.append(rig_)
        return rig_

    yield build

    for rig_ in built:
        await rig_.fake.aclose()
        assert not rig_.fake.unexpected, "OpenAI received a request the test did not script"
