"""The runner is the one place that produces a ``SearchResponse`` for the page. Phase 15 swaps
the pipeline behind ``get_pipeline`` and keeps ``run_search``, so its shape is pinned here."""

import inspect

import pytest

from app import runner
from tests.factories import load_sample_response, make_search_request
from tests.fakes import FakePipeline
from vga.errors import VgaError
from vga.models import RunOverrides, SettingsOverride, Step
from vga.settings import Settings


def test_run_search_keeps_the_signature_phase_15_relies_on() -> None:
    parameters = inspect.signature(runner.run_search).parameters

    assert list(parameters) == ["request", "overrides", "on_step"]
    assert parameters["overrides"].default is None
    assert parameters["on_step"].default is None


def test_fixture_mode_returns_the_sample_response_for_the_request() -> None:
    request = make_search_request()

    response = runner.run_search(request)

    assert response.request_id == request.request_id
    assert response.groups == load_sample_response().groups


def test_fixture_mode_reports_every_step_in_order() -> None:
    seen: list[Step] = []

    runner.run_search(make_search_request(), None, seen.append)

    assert seen == list(Step)


def test_overrides_reach_the_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePipeline()
    monkeypatch.setattr(runner, "get_pipeline", lambda settings: fake)
    overrides = RunOverrides(settings=SettingsOverride())

    runner.run_search(make_search_request(), overrides)

    assert fake.calls[0].overrides == overrides


def test_without_fixture_mode_there_is_no_pipeline_and_the_error_is_friendly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VGA_UI_FIXTURE", "0")

    with pytest.raises(runner.NotConnectedError) as raised:
        runner.run_search(make_search_request())

    assert isinstance(raised.value, VgaError)
    assert "not connected yet" in raised.value.user_message


def test_the_mode_notice_follows_the_setting() -> None:
    assert runner.mode_notice(Settings(ui_fixture=True)) == runner.FIXTURE_NOTICE
    assert runner.mode_notice(Settings(ui_fixture=False)) == runner.NOT_CONNECTED_NOTICE
