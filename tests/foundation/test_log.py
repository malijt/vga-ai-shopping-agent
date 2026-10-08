"""Structured logger, request id, timing and redaction (plan feature 1.3.2)."""

import asyncio
import base64
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.factories import make_image_bytes
from tests.fakes import FakeClock
from vga.log import (
    REDACTED,
    configure_logging,
    current_request_id,
    get_logger,
    redact,
    redact_text,
    request_context,
    timed,
)

# Built at run time so no key-shaped string is committed to the repository.
FAKE_KEY = "sk-" + "AbCd1234" * 5
FAKE_BEARER = "Bearer " + "x9Y8z7W6" * 3


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    configure_logging(level="DEBUG", stream=buffer)
    yield buffer
    # Remove our handlers again so other tests start clean.
    root = logging.getLogger("vga")
    for handler in list(root.handlers):
        root.removeHandler(handler)


def lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


class TestJsonLines:
    def test_each_line_is_a_json_object_with_the_standard_fields(self, stream) -> None:
        get_logger("tests.demo").info("hello", extra={"store": "demo"})

        (line,) = lines(stream)
        assert line["message"] == "hello"
        assert line["level"] == "INFO"
        assert line["logger"] == "vga.tests.demo"
        assert line["store"] == "demo"
        assert {"ts", "request_id"} <= set(line)

    def test_every_line_carries_the_request_id(self, stream) -> None:
        log = get_logger("tests.demo")

        with request_context("req-123"):
            log.info("one")
            log.warning("two")

        assert [line["request_id"] for line in lines(stream)] == ["req-123", "req-123"]

    def test_request_id_is_null_outside_a_request(self, stream) -> None:
        get_logger("tests.demo").info("outside")

        assert lines(stream)[0]["request_id"] is None
        assert current_request_id() is None

    def test_request_id_reaches_tasks_started_inside_the_context(self, stream) -> None:
        log = get_logger("tests.demo")

        async def work(n: int) -> None:
            await asyncio.sleep(0)
            log.info("in task", extra={"n": n})

        async def main() -> None:
            with request_context("req-abc"):
                await asyncio.gather(work(1), work(2))

        asyncio.run(main())

        assert {line["request_id"] for line in lines(stream)} == {"req-abc"}

    def test_concurrent_requests_do_not_mix_ids(self, stream) -> None:
        log = get_logger("tests.demo")

        async def request(name: str) -> None:
            with request_context(name):
                await asyncio.sleep(0)
                log.info("work", extra={"who": name})

        async def main() -> None:
            await asyncio.gather(request("a"), request("b"))

        asyncio.run(main())

        assert {(line["who"], line["request_id"]) for line in lines(stream)} == {
            ("a", "a"),
            ("b", "b"),
        }

    def test_level_filters_output(self) -> None:
        buffer = io.StringIO()
        configure_logging(level="WARNING", stream=buffer)
        try:
            log = get_logger("tests.demo")
            log.info("quiet")
            log.warning("loud")
        finally:
            for handler in list(logging.getLogger("vga").handlers):
                logging.getLogger("vga").removeHandler(handler)

        assert [line["message"] for line in lines(buffer)] == ["loud"]

    def test_arabic_text_is_written_readably(self, stream) -> None:
        get_logger("tests.demo").info("بحث", extra={"q": "جاكيت"})

        assert "جاكيت" in stream.getvalue()

    def test_exceptions_are_included_and_redacted(self, stream) -> None:
        log = get_logger("tests.demo")

        try:
            raise RuntimeError(f"failed with {FAKE_KEY}")
        except RuntimeError:
            log.exception("boom")

        (line,) = lines(stream)
        assert "RuntimeError" in line["exception"]
        assert FAKE_KEY not in stream.getvalue()

    def test_file_handler_writes_to_the_log_dir(self, tmp_path: Path) -> None:
        configure_logging(level="INFO", log_dir=tmp_path / "logs", stream=io.StringIO())
        try:
            get_logger("tests.demo").info("to file")
        finally:
            for handler in list(logging.getLogger("vga").handlers):
                handler.flush()
                logging.getLogger("vga").removeHandler(handler)
                handler.close()

        written = (tmp_path / "logs" / "vga.jsonl").read_text(encoding="utf-8")
        assert json.loads(written.splitlines()[0])["message"] == "to file"

    def test_get_logger_has_no_side_effects(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        get_logger("tests.nothing")

        assert list(tmp_path.iterdir()) == []

    def test_logger_names_are_namespaced_once(self) -> None:
        assert get_logger("vga.rank").name == "vga.rank"
        assert get_logger("rank").name == "vga.rank"
        assert get_logger().name == "vga"

    def test_filters_are_attached_only_once(self) -> None:
        first = get_logger("tests.once")
        get_logger("tests.once")

        assert len(first.filters) == 2

    def test_records_seen_by_other_handlers_also_have_request_id_and_are_redacted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        log = get_logger("tests.caplog")

        with request_context("req-cap"), caplog.at_level(logging.INFO, logger="vga"):
            log.info("key is %s", FAKE_KEY)

        (record,) = [r for r in caplog.records if r.name == "vga.tests.caplog"]
        assert record.request_id == "req-cap"  # type: ignore[attr-defined]
        assert FAKE_KEY not in record.getMessage()


class TestRedaction:
    def test_api_key_in_the_message_is_not_written(self, stream) -> None:
        get_logger("tests.demo").info(f"calling with key {FAKE_KEY}")

        assert FAKE_KEY not in stream.getvalue()
        assert REDACTED in stream.getvalue()

    def test_api_key_in_an_extra_field_is_not_written(self, stream) -> None:
        get_logger("tests.demo").info("call", extra={"api_key": FAKE_KEY, "note": FAKE_KEY})

        assert FAKE_KEY not in stream.getvalue()

    def test_api_key_in_formatted_arguments_is_not_written(self, stream) -> None:
        get_logger("tests.demo").info("using %s for %s", FAKE_KEY, "openai")

        assert FAKE_KEY not in stream.getvalue()

    def test_api_key_from_the_environment_is_never_written(self, stream, monkeypatch) -> None:
        secret = "x" * 24
        monkeypatch.setenv("OPENAI_API_KEY", secret)

        get_logger("tests.demo").info(f"oops {secret}", extra={"data": {"nested": [secret]}})

        assert secret not in stream.getvalue()

    def test_bearer_tokens_are_not_written(self, stream) -> None:
        get_logger("tests.demo").info(f"header Authorization: {FAKE_BEARER}")

        assert FAKE_BEARER not in stream.getvalue()
        assert "x9Y8z7W6" not in stream.getvalue()

    @pytest.mark.parametrize(
        "text", ["password=hunter22hunter", "token: qqqqqq111111", "api_key='zzzzzz999999'"]
    )
    def test_key_value_secrets_in_text_are_not_written(self, stream, text: str) -> None:
        get_logger("tests.demo").info(f"config {text}")

        secret_part = text.split("=")[-1].split(": ")[-1].strip("'")
        assert secret_part not in stream.getvalue()

    def test_image_bytes_are_not_written(self, stream) -> None:
        photo = make_image_bytes()

        get_logger("tests.demo").info("got photo", extra={"photo": photo, "payload": photo})

        written = stream.getvalue()
        assert "PNG" not in written
        assert base64.b64encode(photo).decode() not in written
        assert "[REDACTED bytes" in written

    def test_bytes_inside_nested_structures_are_not_written(self, stream) -> None:
        photo = make_image_bytes()

        get_logger("tests.demo").info("nested", extra={"req": {"parts": [photo, {"x": photo}]}})

        assert written_has_no_image(stream, photo)

    def test_base64_photo_and_data_urls_are_not_written(self, stream) -> None:
        photo = make_image_bytes(size=(64, 64))
        encoded = base64.b64encode(photo).decode()
        data_url = f"data:image/png;base64,{encoded}"

        log = get_logger("tests.demo")
        log.info(f"sending {data_url}")
        log.info("raw", extra={"image_url": data_url, "blob": encoded + encoded})

        written = stream.getvalue()
        assert encoded[:60] not in written
        assert "data:image" not in written.replace("[REDACTED data-url]", "")

    def test_ordinary_values_are_untouched(self, stream) -> None:
        get_logger("tests.demo").info(
            "search done",
            extra={
                "store": "demo",
                "count": 12,
                "duration_ms": 130.5,
                "image_url": "https://cdn.demo-store.example/a.jpg",
                "input_tokens": 120,
            },
        )

        (line,) = lines(stream)
        assert line["count"] == 12
        assert line["image_url"] == "https://cdn.demo-store.example/a.jpg"
        assert line["input_tokens"] == 120

    def test_redact_hides_values_under_sensitive_keys(self) -> None:
        cleaned = redact({"Authorization": "x", "cache_key": "kept", "my_token": "y", "ok": 1})

        assert cleaned == {
            "Authorization": REDACTED,
            "cache_key": "kept",
            "my_token": REDACTED,
            "ok": 1,
        }

    def test_redact_text_leaves_normal_sentences_alone(self) -> None:
        sentence = "Searched 4 stores for black oversized blazer; tokens used: 120"

        assert redact_text(sentence) == sentence

    def test_embedding_is_not_written(self, stream) -> None:
        get_logger("tests.demo").info("scored", extra={"embedding": [0.111111, 0.222222]})

        assert "0.111111" not in stream.getvalue()


def written_has_no_image(stream: io.StringIO, photo: bytes) -> bool:
    written = stream.getvalue()
    return "PNG" not in written and base64.b64encode(photo).decode() not in written


class TestTimed:
    def test_writes_step_store_duration_status_and_request_id(self, stream) -> None:
        clock = FakeClock(start=0.0)

        with request_context("req-t"), timed("fetch", store="demo", clock=clock) as step:
            clock.advance(0.25)

        (line,) = lines(stream)
        assert line["step"] == "fetch"
        assert line["store"] == "demo"
        assert line["duration_ms"] == 250.0
        assert line["status"] == "ok"
        assert line["request_id"] == "req-t"
        assert step.duration_ms == 250.0

    def test_nested_durations_are_correct(self, stream) -> None:
        clock = FakeClock(start=0.0)

        with timed("outer", clock=clock):
            clock.advance(1.0)
            with timed("inner", clock=clock):
                clock.advance(2.0)
            clock.advance(0.5)

        by_step = {line["step"]: line["duration_ms"] for line in lines(stream)}
        assert by_step == {"inner": 2000.0, "outer": 3500.0}

    def test_inner_finishes_and_logs_before_outer(self, stream) -> None:
        clock = FakeClock(start=0.0)

        with timed("outer", clock=clock), timed("inner", clock=clock):
            clock.advance(1.0)

        assert [line["step"] for line in lines(stream)] == ["inner", "outer"]

    def test_status_can_be_set_by_the_block(self, stream) -> None:
        with timed("fetch", store="demo", clock=FakeClock()) as step:
            step.status = "blocked"

        assert lines(stream)[0]["status"] == "blocked"

    def test_exception_marks_error_and_still_propagates(self, stream) -> None:
        clock = FakeClock(start=0.0)

        def failing_step() -> None:
            with timed("parse", clock=clock):
                clock.advance(0.1)
                msg = "bad"
                raise ValueError(msg)

        with pytest.raises(ValueError, match="bad"):
            failing_step()

        (line,) = lines(stream)
        assert line["status"] == "error"
        assert line["duration_ms"] == pytest.approx(100.0)

    def test_status_set_before_an_exception_is_kept(self, stream) -> None:
        def failing_step() -> None:
            with timed("fetch", clock=FakeClock()) as step:
                step.status = "timeout"
                raise RuntimeError

        with pytest.raises(RuntimeError):
            failing_step()

        assert lines(stream)[0]["status"] == "timeout"

    def test_to_timing_builds_the_response_model(self) -> None:
        clock = FakeClock(start=0.0)

        with timed("rank", clock=clock) as step:
            clock.advance(0.5)

        timing = step.to_timing()
        assert (timing.step, timing.store, timing.duration_ms, timing.status) == (
            "rank",
            None,
            500.0,
            "ok",
        )

    def test_uses_the_real_clock_by_default(self, stream) -> None:
        with timed("quick"):
            pass

        assert lines(stream)[0]["duration_ms"] >= 0

    async def test_works_around_awaits_with_a_fake_clock(self, stream) -> None:
        clock = FakeClock(start=0.0)

        with timed("wait", clock=clock) as step:
            await clock.sleep(3)

        assert step.duration_ms == 3000.0
