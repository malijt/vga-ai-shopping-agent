"""One structured OpenAI call, with a timeout, bounded retries, a call budget and a log line.

This is the only module that talks to the OpenAI SDK, and it takes the client by injection, so the
tests run it against a fake HTTP server and never reach the network (Dependency Inversion).

What it guarantees (plan 5.2.1, 5.2.5, 5.2.6; ``docs/Best Practices/genai-best-practices.md`` s6):

- A timeout on every call, and never a call that starts too close to the request deadline to finish.
- Retries only for 429, 5xx and timeouts, with exponential backoff and jitter, slept on the
  injected ``Clock``. Any other error (400, 401, 403, 404, a refused connection) is not retried.
- At most ``MAX_CALLS_PER_REQUEST`` calls for one shopper request, and every call is counted
  against the daily cap before it is made. The corrective retry for a bad answer counts too.
- One log line per call carrying model id, prompt version, tokens and latency together. The photo
  is never in a log line. The parsed answer is logged only when ``log_prompts`` is on.

It raises ``ModelPathFailure`` when the model path cannot give an answer (the caller falls back),
``OutputValidationError`` when an answer came back but is unusable (the caller may retry once), and
``CallBudgetExceededError`` when the daily cap stops a call (the caller does not catch it).
"""

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import openai
import pydantic
from openai import AsyncOpenAI
from openai.types.responses import ParsedResponse, ResponseInputParam
from openai.types.shared import ReasoningEffort

from vga.errors import LlmError
from vga.interfaces import Clock
from vga.log import get_logger
from vga.models import Usage
from vga.understand.budget import CallBudget
from vga.understand.prompt import PROMPT_VERSION
from vga.understand.schema import (
    ReadingBudget,
    ReadingItem,
    UnderstandReading,
)
from vga.understand.validation import OutputValidationError

log = get_logger(__name__)

OPENAI_TIMEOUT_S = 15.0
"""Longest wait for one call (plan 5.2.1). httpx applies it to each phase (connect, read, write),
not to the whole call. A call is not started with less than ``MIN_TIME_FOR_CALL_S`` left before the
deadline, and its timeout is cut to the time that is left."""

MAX_OUTPUT_TOKENS = 3000
"""Cap on generated tokens. The visible answer is under 500 tokens; the rest is headroom for the
model's hidden reasoning, which counts against this cap: a cap that is too tight returns an empty,
cut-off answer."""

REASONING_EFFORT: ReasoningEffort = "low"
"""Reading a short request needs little reasoning. ``low`` is accepted by the GPT-5 family and by
GPT-5.4; ``minimal`` is not accepted by every model, so it is not used."""

_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def supports_reasoning_effort(model: str) -> bool:
    """Only reasoning models accept ``reasoning.effort``; any other model answers it with a 400."""
    return model.startswith(_REASONING_MODEL_PREFIXES)


MAX_CALLS_PER_REQUEST = 2
"""Hard cap on OpenAI calls for one shopper request, transport retries and the corrective retry
together (plan 5.2.6)."""

MAX_ATTEMPTS = 2
"""Attempts at one question when the failure is a 429, a 5xx or a timeout (plan 5.2.1)."""

BASE_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0
MIN_TIME_FOR_CALL_S = 1.0
"""Do not start a call with less than this left before the deadline: it cannot finish."""

_SYSTEM_RANDOM = random.SystemRandom()


class ModelPathFailure(LlmError):
    """The model path gave no usable answer after its retries. The caller applies the fallback.

    The user message is the generic ``LlmError`` one; ``detail`` (logged, never shown) says why.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(detail=reason)
        self.reason = reason


@dataclass
class CallState:
    """What one shopper request has used so far. Created per request, shared by all its calls."""

    deadline: float
    """``Clock.monotonic()`` value after which no new call is started."""
    calls_made: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def usage(self) -> Usage:
        return Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            llm_calls=self.calls_made,
        )


class OpenAIGateway:
    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        model: str,
        daily_cap: int,
        budget: CallBudget,
        clock: Clock,
        timeout_s: float = OPENAI_TIMEOUT_S,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        reasoning_effort: ReasoningEffort | None = REASONING_EFFORT,
        jitter: Callable[[], float] | None = None,
        log_prompts: bool = False,
    ) -> None:
        # The SDK would retry 429s and 5xx on its own, out of sight of the call budget and the
        # deadline. Retries are done here, so the SDK must not do any.
        self._client = client.with_options(max_retries=0)
        self._model = model
        self._daily_cap = daily_cap
        self._budget = budget
        self._clock = clock
        self._timeout_s = timeout_s
        self._max_output_tokens = max_output_tokens
        self._reasoning_effort = reasoning_effort
        self._jitter = jitter or _SYSTEM_RANDOM.random
        self._log_prompts = log_prompts

    async def ask(
        self, messages: ResponseInputParam, state: CallState, *, has_image: bool
    ) -> UnderstandReading:
        """Send ``messages`` and return the parsed answer. See the module docstring for raises."""
        attempt = 0
        while True:
            attempt += 1
            remaining = self._reserve_call(state)
            started = self._clock.monotonic()
            try:
                raw = await self._client.responses.with_raw_response.parse(
                    model=self._model,
                    input=messages,
                    text_format=UnderstandReading,
                    max_output_tokens=self._max_output_tokens,
                    reasoning=(
                        {"effort": self._reasoning_effort}
                        if self._reasoning_effort
                        else openai.omit
                    ),
                    store=False,  # do not keep the request, and so the photo, on OpenAI's side
                    timeout=min(self._timeout_s, remaining),
                )
            except openai.OpenAIError as exc:
                self._log_failed_call(state, started, has_image, exc)
                delay = self._retry_delay(exc, attempt, state)
                if delay is None:
                    raise ModelPathFailure(_describe(exc)) from exc
                await self._clock.sleep(delay)
                continue
            return self._read(raw, state, started, has_image)

    # ----------------------------------------------------------------------------------------

    def _reserve_call(self, state: CallState) -> float:
        """Check the per-request cap and the deadline, then count the call against the daily cap.
        Returns the seconds left before the deadline."""
        if state.calls_made >= MAX_CALLS_PER_REQUEST:
            raise ModelPathFailure(f"per-request limit of {MAX_CALLS_PER_REQUEST} calls reached")
        remaining = state.deadline - self._clock.monotonic()
        if remaining < MIN_TIME_FOR_CALL_S:
            raise ModelPathFailure("request deadline reached before another call could finish")
        self._budget.acquire(self._daily_cap)  # raises CallBudgetExceededError at the cap
        state.calls_made += 1
        return remaining

    def _retry_delay(self, exc: openai.OpenAIError, attempt: int, state: CallState) -> float | None:
        """Seconds to wait before the next attempt, or ``None`` when the error must not be retried
        or the next attempt would not fit before the deadline."""
        if not _is_retryable(exc) or attempt >= MAX_ATTEMPTS:
            return None
        if state.calls_made >= MAX_CALLS_PER_REQUEST:
            return None  # the per-request limit would refuse the retry, so do not wait for it
        backoff = min(MAX_BACKOFF_S, BASE_BACKOFF_S * 2.0 ** (attempt - 1))
        delay = backoff * (1 + self._jitter())
        asked_for = _retry_after_s(exc)
        if asked_for is not None:
            delay = min(max(delay, asked_for), MAX_BACKOFF_S)
        if self._clock.monotonic() + delay + MIN_TIME_FOR_CALL_S > state.deadline:
            return None
        return delay

    def _read(
        self, raw: Any, state: CallState, started: float, has_image: bool
    ) -> UnderstandReading:
        """Count the tokens, then parse. Tokens come from the raw body, so they are counted and
        logged even when the answer cannot be parsed (for example cut off at the token cap)."""
        input_tokens, output_tokens = _tokens_in(raw.text)
        state.input_tokens += input_tokens
        state.output_tokens += output_tokens
        tokens = (input_tokens, output_tokens)

        try:
            response: ParsedResponse[UnderstandReading] = raw.parse()
        except pydantic.ValidationError as exc:
            self._log_call(state, started, has_image, outcome="malformed", tokens=tokens)
            raise OutputValidationError(_schema_problems(exc)) from exc
        except Exception as exc:
            # A 200 whose body is not a Responses API object (an HTML page from a proxy, an empty
            # body) fails inside the SDK with an error of no useful type. It must not escape as a
            # stack trace: the model path failed, so the fallback applies.
            self._log_call(state, started, has_image, outcome="unreadable", tokens=tokens)
            raise ModelPathFailure(f"unreadable response ({type(exc).__name__})") from exc
        if _was_refused(response):
            self._log_call(state, started, has_image, outcome="refused", tokens=tokens)
            raise ModelPathFailure("the model refused the request")
        parsed = response.output_parsed
        if parsed is None or response.status == "incomplete":
            self._log_call(state, started, has_image, outcome="incomplete", tokens=tokens)
            raise OutputValidationError(["answer: missing or cut off; answer again, briefly"])
        self._log_call(state, started, has_image, outcome="ok", tokens=tokens)
        if self._log_prompts:
            log.info(
                "understand parsed answer", extra={"parsed_result": parsed.model_dump(mode="json")}
            )
        return parsed

    def _log_call(
        self,
        state: CallState,
        started: float,
        has_image: bool,
        *,
        outcome: str,
        tokens: tuple[int, int] | None = None,
        **extra: object,
    ) -> None:
        """The one line per call: model, prompt version, tokens and latency side by side."""
        fields: dict[str, object] = {
            "model": self._model,
            "prompt_version": PROMPT_VERSION,
            "call": state.calls_made,
            "outcome": outcome,
            "latency_ms": round((self._clock.monotonic() - started) * 1000, 1),
            "input_tokens": tokens[0] if tokens else None,
            "output_tokens": tokens[1] if tokens else None,
            "has_image": has_image,  # whether a photo was sent, never the photo
            **extra,
        }
        level = log.info if outcome == "ok" else log.warning
        level("openai call", extra=fields)

    def _log_failed_call(
        self, state: CallState, started: float, has_image: bool, exc: openai.OpenAIError
    ) -> None:
        self._log_call(
            state,
            started,
            has_image,
            outcome="error",
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
        )


# --------------------------------------------------------------------------------------------
# Reading SDK results and errors
# --------------------------------------------------------------------------------------------


def _is_retryable(exc: openai.OpenAIError) -> bool:
    """429, 5xx and timeouts only (plan 5.2.1). A 4xx or a refused connection will not improve."""
    if isinstance(exc, openai.APITimeoutError):
        return True
    return isinstance(exc, openai.APIStatusError) and (
        exc.status_code == 429 or exc.status_code >= 500
    )


def _retry_after_s(exc: openai.OpenAIError) -> float | None:
    """The wait the server asked for, from its ``retry-after-ms`` or ``retry-after`` header."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            return max(0.0, float(raw) * scale)
        except ValueError:
            continue
    return None


def _was_refused(response: Any) -> bool:
    return any(
        getattr(part, "type", None) == "refusal"
        for item in response.output or []
        if getattr(item, "type", None) == "message"
        for part in item.content or []
    )


def _describe(exc: openai.OpenAIError) -> str:
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


def _tokens_in(body: str) -> tuple[int, int]:
    """(input, output) tokens from a raw Responses API body; (0, 0) if it has none."""
    try:
        usage = json.loads(body).get("usage") or {}
        return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    except (ValueError, TypeError, AttributeError):
        return 0, 0


_REASONS = {
    "json_invalid": "is not valid JSON (the answer may have been cut off)",
    "missing": "is missing",
    "extra_forbidden": "is not allowed",
}


_SCHEMA_FIELDS = frozenset(
    {*UnderstandReading.model_fields, *ReadingItem.model_fields, *ReadingBudget.model_fields}
)


def _schema_problems(exc: pydantic.ValidationError) -> list[str]:
    """Value-free description of a schema failure: where it is and what is wrong, never the value.

    The allowed values of an enum come from the schema we sent, not from the model or the shopper,
    so they are safe to name. A path is named only when every part of it is a field of that schema:
    an extra key the model invented could be text of its choosing.
    """
    problems: list[str] = []
    for error in exc.errors(include_input=False)[:5]:
        known = all(isinstance(part, int) or part in _SCHEMA_FIELDS for part in error["loc"])
        where = (
            "".join(
                f"[{part}]" if isinstance(part, int) else f".{part}" if index else str(part)
                for index, part in enumerate(error["loc"])
            )
            if known
            else ""
        )
        expected = (error.get("ctx") or {}).get("expected")
        reason = (
            f"must be {expected}"
            if error["type"] in {"enum", "literal_error"} and expected
            else _REASONS.get(error["type"], "does not match the required schema")
        )
        problems.append(f"{where or 'answer'}: {reason}")
    return problems or ["answer: does not match the required schema"]
