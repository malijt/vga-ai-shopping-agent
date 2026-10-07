"""A scripted fake of the OpenAI HTTP API, for the Understand tests.

OpenAI is a boundary, so it is the only thing faked (CLAUDE.md, QA rules). The fake sits at the
HTTP level: the tests drive the real ``AsyncOpenAI`` SDK against it, so request building, schema
generation, response parsing and the SDK's error classes are the real ones, and a test fails if
the SDK is used wrongly. No test using it touches the network.

Usage::

    fake = FakeOpenAI(answer(make_reading()), http_error(429))
    client = fake.client()          # a real AsyncOpenAI wired to the fake
    ...
    assert len(fake.requests) == 2  # parsed request bodies, in order

Steps are consumed in order, one per HTTP request. Past the end of the script the ``default`` step
answers, if one is given; otherwise the request is recorded in ``unexpected`` and refused, and the
``fake_openai`` fixture in ``conftest.py`` fails the test at teardown, so an extra call (for
example a third attempt) can never pass unnoticed behind a fallback.

The SDK is built with its default retries on (2) on purpose: the code under test must switch them
off itself, and a test proves it by counting the requests the fake sees.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx2
from openai import AsyncOpenAI

from vga.understand.schema import UnderstandReading

API_KEY = "sk-test-key-not-a-real-key-0000000000"


@dataclass
class RecordedRequest:
    """One request the fake received: its JSON body and the timeout the SDK set on it."""

    body: dict[str, Any]
    timeout: Mapping[str, Any]

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self.body["input"])

    @property
    def system_messages(self) -> list[str]:
        return [m["content"] for m in self.messages if m["role"] == "system"]

    @property
    def user_message(self) -> dict[str, Any]:
        [user] = [m for m in self.messages if m["role"] == "user"]
        return user

    @property
    def user_text(self) -> str:
        parts = [p["text"] for p in self.user_message["content"] if p["type"] == "input_text"]
        return "\n".join(parts)

    @property
    def image_url(self) -> str | None:
        urls = [p["image_url"] for p in self.user_message["content"] if p["type"] == "input_image"]
        return urls[0] if urls else None

    @property
    def schema(self) -> dict[str, Any]:
        return dict(self.body["text"]["format"]["schema"])


Step = Callable[[RecordedRequest, httpx2.Request], httpx2.Response]


def reading_json(reading: UnderstandReading) -> str:
    """The JSON text a model would write for ``reading`` (works for deliberately invalid ones)."""
    return json.dumps(reading.model_dump(mode="json", warnings=False), ensure_ascii=False)


def _payload(
    output: list[dict[str, Any]],
    *,
    status: str = "completed",
    input_tokens: int = 100,
    output_tokens: int = 40,
    incomplete: str | None = None,
) -> dict[str, Any]:
    return {
        "id": "resp_fake",
        "object": "response",
        "created_at": 1,
        "status": status,
        "model": "gpt-5-mini-2025-08-07",
        "output": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 10},
        },
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "error": None,
        "incomplete_details": {"reason": incomplete} if incomplete else None,
    }


def _message(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": "rs_fake", "type": "reasoning", "summary": []},
        {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": content,
        },
    ]


def _text_part(text: str) -> dict[str, Any]:
    return {"type": "output_text", "text": text, "annotations": []}


# --------------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------------


def answer(reading: UnderstandReading, *, input_tokens: int = 100, output_tokens: int = 40) -> Step:
    """A normal answer containing ``reading``."""
    return raw_text(reading_json(reading), input_tokens=input_tokens, output_tokens=output_tokens)


def answer_from(make: Callable[[RecordedRequest], UnderstandReading]) -> Step:
    """An answer computed from the request: how a model that obeys the shopper's text behaves."""
    return lambda recorded, _request: httpx2.Response(
        200, json=_payload(_message([_text_part(reading_json(make(recorded)))]))
    )


def raw_text(text: str, *, input_tokens: int = 100, output_tokens: int = 40) -> Step:
    """An answer whose text is exactly ``text``, valid JSON or not."""
    body = _payload(
        _message([_text_part(text)]), input_tokens=input_tokens, output_tokens=output_tokens
    )
    return lambda _recorded, _request: httpx2.Response(200, json=body)


def cut_off() -> Step:
    """An answer that stopped at the token cap in the middle of the JSON."""
    body = _payload(
        _message([_text_part('{"verdict": "ok", "input_type": "te')]),
        status="incomplete",
        incomplete="max_output_tokens",
    )
    return lambda _recorded, _request: httpx2.Response(200, json=body)


def refusal(message: str = "I can't help with that.") -> Step:
    body = _payload(_message([{"type": "refusal", "refusal": message}]))
    return lambda _recorded, _request: httpx2.Response(200, json=body)


def http_error(status: int, headers: Mapping[str, str] | None = None) -> Step:
    """An error response such as 429 (with ``{"retry-after": "2"}``), 500, 400 or 401."""
    error = {"error": {"message": f"fake error {status}", "type": "fake_error"}}
    return lambda _recorded, _request: httpx2.Response(
        status, headers=dict(headers or {}), json=error
    )


def html_page() -> Step:
    """A 200 whose body is a web page, as a proxy or a captive portal would serve."""
    return lambda _recorded, _request: httpx2.Response(
        200, headers={"content-type": "text/html"}, content=b"<html><body>Sign in</body></html>"
    )


def empty_body() -> Step:
    return lambda _recorded, _request: httpx2.Response(200, content=b"")


def timeout() -> Step:
    def step(_recorded: RecordedRequest, request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("fake read timeout", request=request)

    return step


def connection_error() -> Step:
    def step(_recorded: RecordedRequest, request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("fake connection refused", request=request)

    return step


# --------------------------------------------------------------------------------------------
# The fake server
# --------------------------------------------------------------------------------------------


class FakeOpenAI:
    """The scripted server. ``steps`` answer requests in order; ``default`` answers the rest;
    ``on_request`` is called for every request first (for example to advance a fake clock)."""

    def __init__(
        self,
        *steps: Step,
        default: Step | None = None,
        on_request: Callable[[RecordedRequest], None] | None = None,
    ) -> None:
        self.steps = list(steps)
        self.default = default
        self.on_request = on_request
        self.requests: list[RecordedRequest] = []
        """Every request received, in order."""
        self.unexpected: list[RecordedRequest] = []
        """Requests that arrived with no step left to answer them."""
        self._http: httpx2.AsyncClient | None = None

    def client(self) -> AsyncOpenAI:
        """A real ``AsyncOpenAI`` whose HTTP goes to this fake."""
        self._http = httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))
        return AsyncOpenAI(api_key=API_KEY, http_client=self._http)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        recorded = RecordedRequest(
            body=json.loads(request.content), timeout=request.extensions.get("timeout", {})
        )
        if self.on_request is not None:
            self.on_request(recorded)
        position = len(self.requests)
        self.requests.append(recorded)
        if position < len(self.steps):
            return self.steps[position](recorded, request)
        if self.default is not None:
            return self.default(recorded, request)
        self.unexpected.append(recorded)
        return httpx2.Response(400, json={"error": {"message": "no scripted answer", "type": "x"}})
