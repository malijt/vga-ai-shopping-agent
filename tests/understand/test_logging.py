"""Usage and prompt logging (plan 5.2.5): matched versions on every call, never the photo."""

import base64
import json
import logging

import pytest

from tests.factories import make_image_bytes, make_search_request, make_settings
from tests.understand.conftest import TEST_MODEL, RigFactory
from tests.understand.fake_openai import API_KEY, answer, http_error
from tests.understand.readings import make_reading
from vga.log import JsonFormatter
from vga.understand import PROMPT_VERSION
from vga.understand.image import prepare_image

REQUEST_TEXT = "black oversized blazer for men"


def _call_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "openai call"]


def _all_output(caplog: pytest.LogCaptureFixture) -> str:
    """Everything the logger would write: the formatted JSON of every captured record."""
    formatter = JsonFormatter()
    return "\n".join(formatter.format(record) for record in caplog.records)


async def test_every_call_logs_model_prompt_version_tokens_and_latency_together(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    r = rig(
        answer(make_reading(), input_tokens=321, output_tokens=45),
        on_request=lambda _request: r.clock.advance(0.25),
    )
    request = make_search_request(text=REQUEST_TEXT)

    await r.understander.understand(request)

    [line] = _call_lines(caplog)
    assert line.model == TEST_MODEL  # type: ignore[attr-defined]
    assert line.prompt_version == PROMPT_VERSION  # type: ignore[attr-defined]
    assert line.input_tokens == 321  # type: ignore[attr-defined]
    assert line.output_tokens == 45  # type: ignore[attr-defined]
    assert line.latency_ms == 250.0  # type: ignore[attr-defined]
    assert line.outcome == "ok"  # type: ignore[attr-defined]
    assert line.request_id == request.request_id  # type: ignore[attr-defined]


async def test_a_retried_request_logs_one_line_per_call(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    r = rig(http_error(429), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    first, second = _call_lines(caplog)
    assert (first.outcome, first.status_code, first.call) == ("error", 429, 1)  # type: ignore[attr-defined]
    assert (second.outcome, second.call) == ("ok", 2)  # type: ignore[attr-defined]
    assert first.levelno == logging.WARNING
    for line in (first, second):
        assert line.model == TEST_MODEL  # type: ignore[attr-defined]
        assert line.prompt_version == PROMPT_VERSION  # type: ignore[attr-defined]


async def test_an_unparseable_answer_still_logs_its_tokens(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    from tests.understand.fake_openai import cut_off

    r = rig(cut_off(), answer(make_reading()))

    await r.understander.understand(make_search_request(text=REQUEST_TEXT))

    first, _ = _call_lines(caplog)
    assert first.outcome == "malformed"  # type: ignore[attr-defined]
    assert first.input_tokens == 100  # type: ignore[attr-defined]
    assert first.output_tokens == 40  # type: ignore[attr-defined]


async def test_no_image_data_appears_in_any_log_output(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    photo = make_image_bytes("PNG", (600, 400))
    prepared_b64 = base64.b64encode(prepare_image(photo)).decode()
    r = rig(
        answer(make_reading()),
        settings_override=make_settings(
            openai_model=TEST_MODEL, log_prompts=True, daily_llm_call_cap=100
        ),
    )

    await r.understander.understand(make_search_request(image=photo, text="same but darker"))

    output = _all_output(caplog)
    assert output  # something was logged
    assert prepared_b64[:60] not in output
    assert base64.b64encode(photo).decode()[:60] not in output
    assert "data:image" not in output
    assert '"has_image": true' in output  # only the fact that a photo was sent


async def test_the_api_key_never_appears_in_any_log_output(
    rig: RigFactory, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", API_KEY)
    r = rig(http_error(401))

    await r.understander.understand(make_search_request(text="black leather jacket"))

    assert API_KEY not in _all_output(caplog)


async def test_prompt_text_and_parsed_result_are_not_logged_by_default(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    r = rig(answer(make_reading()))

    await r.understander.understand(make_search_request(text="my private request words"))

    output = _all_output(caplog)
    assert "my private request words" not in output
    assert "oversized blazer" not in output  # the parsed result


async def test_prompt_text_and_parsed_result_are_logged_when_the_setting_is_on(
    rig: RigFactory, caplog: pytest.LogCaptureFixture
) -> None:
    r = rig(
        answer(make_reading()),
        settings_override=make_settings(
            openai_model=TEST_MODEL, log_prompts=True, daily_llm_call_cap=100
        ),
    )

    await r.understander.understand(make_search_request(text="my request words"))

    parsed_lines = [rec for rec in caplog.records if rec.getMessage() == "understand parsed answer"]
    input_lines = [rec for rec in caplog.records if rec.getMessage() == "understand input"]
    assert [rec.user_text for rec in input_lines] == ["my request words"]  # type: ignore[attr-defined]
    [parsed] = parsed_lines
    assert parsed.parsed_result["items"][0]["category"] == "outerwear"  # type: ignore[attr-defined]
    assert json.loads(JsonFormatter().format(parsed))["request_id"]
