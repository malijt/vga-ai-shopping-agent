"""``OpenAIUnderstander``: the real ``Understander``. One structured OpenAI call per request.

The path of a request, and where each plan feature lives:

1. Clean the shopper's text. Text with no letter or digit counts as no text. A request with
   nothing left to read is "nothing to shop for" and no call is made.
2. Prepare the photo (``image.py``, 5.2.2).
3. Ask the model (``gateway.py``, 5.2.1) with the versioned prompt (``prompt.py``, 5.1.1, 5.1.2).
4. Check the answer in code (``validation.py``, 5.2.3). If it is unusable, ask once more with the
   problems listed by field (5.2.4). The retry shares the two-call limit (5.2.6).
5. If the model said there is nothing to shop for, raise the invalid-input error with a plain
   message (assumption A16). No search happens.
6. If the model path fails, fall back (``fallback.py``, 5.3.1): a text request searches with the
   shopper's cleaned words; a photo-only request gets a friendly error. Every fallback is logged
   at warn level with the request id.

Settings it reads: ``openai_model`` (must be a dated snapshot), ``daily_llm_call_cap``,
``log_prompts`` and ``request_deadline_s``.
"""

import os
from collections.abc import Callable

from openai import AsyncOpenAI

from vga.errors import ConfigError
from vga.interfaces import Clock, SystemClock
from vga.log import get_logger, request_context
from vga.models import SearchRequest, UnderstandResult
from vga.settings import Settings, load_dotenv
from vga.understand.budget import CallBudget, process_call_budget
from vga.understand.fallback import fallback_result
from vga.understand.gateway import (
    MAX_OUTPUT_TOKENS,
    OPENAI_TIMEOUT_S,
    REASONING_EFFORT,
    CallState,
    ModelPathFailure,
    OpenAIGateway,
    supports_reasoning_effort,
)
from vga.understand.image import prepare_image_data_url
from vga.understand.messages import nothing_to_shop_for, photo_only_failure
from vga.understand.prompt import PROMPT_VERSION, build_input
from vga.understand.schema import Verdict
from vga.understand.text import has_letters_or_digits
from vga.understand.validation import (
    NothingToShopFor,
    OutputValidationError,
    validate_reading,
)

log = get_logger(__name__)

DEFAULT_DEADLINE_S = 20.0
"""Most of the request deadline this step may use when the caller sets none: two 15 s timeouts
must not leave the stores no time at all."""

MAX_ROUNDS = 2
"""The first try and, if its answer is unusable, one corrective retry (plan 5.2.4)."""

MODEL_NOT_SET_MESSAGE = (
    "The AI model is not set up. Set openai_model in config/settings.yaml (or the OPENAI_MODEL "
    "environment variable) to a dated model snapshot, then restart."
)
API_KEY_MISSING_MESSAGE = (
    "The OpenAI API key is missing. Set OPENAI_API_KEY in your environment or in .env, "
    "then restart."
)


def create_openai_client(timeout_s: float = OPENAI_TIMEOUT_S) -> AsyncOpenAI:
    """An ``AsyncOpenAI`` client for the demo: key from ``OPENAI_API_KEY``, no SDK-side retries.

    Raises ``ConfigError`` when the key is missing, so the problem shows at start-up. The client
    is tied to the event loop it is first used in: if the caller starts a fresh loop for every
    search (``asyncio.run`` per request), create the client inside it.
    """
    load_dotenv()  # fills OPENAI_API_KEY from .env if the shell has not set it
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise ConfigError(API_KEY_MISSING_MESSAGE, detail="OPENAI_API_KEY is not set")
    return AsyncOpenAI(max_retries=0, timeout=timeout_s)


class OpenAIUnderstander:
    """Turns a photo and/or text into an ``UnderstandResult`` with one OpenAI call.

    ``client`` is injected so tests pass a client whose HTTP is faked; left out, a real one is
    built from ``OPENAI_API_KEY``. ``clock`` times backoff and the deadline. ``budget`` is the
    daily call counter, shared by the whole process unless a test passes its own. ``deadline_s``
    bounds everything one request may spend here, retries included (default: the request deadline
    in the settings, at most ``DEFAULT_DEADLINE_S``). ``jitter`` returns a number in [0, 1) for the
    backoff.
    """

    def __init__(
        self,
        settings: Settings,
        client: AsyncOpenAI | None = None,
        *,
        clock: Clock | None = None,
        budget: CallBudget | None = None,
        deadline_s: float | None = None,
        timeout_s: float = OPENAI_TIMEOUT_S,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        if not settings.openai_model:
            raise ConfigError(MODEL_NOT_SET_MESSAGE, detail="settings.openai_model is not set")
        self._settings = settings
        self._model = settings.openai_model
        self._clock = clock or SystemClock()
        self._deadline_s = (
            min(settings.request_deadline_s, DEFAULT_DEADLINE_S)
            if deadline_s is None
            else deadline_s
        )
        self._gateway = OpenAIGateway(
            client or create_openai_client(timeout_s),
            model=self._model,
            daily_cap=settings.daily_llm_call_cap,
            budget=budget or process_call_budget(),
            clock=self._clock,
            timeout_s=timeout_s,
            max_output_tokens=max_output_tokens,
            reasoning_effort=(REASONING_EFFORT if supports_reasoning_effort(self._model) else None),
            jitter=jitter,
            log_prompts=settings.log_prompts,
        )

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        with request_context(req.request_id):
            return await self._understand(req)

    # ----------------------------------------------------------------------------------------

    async def _understand(self, req: SearchRequest) -> UnderstandResult:
        text = req.text if req.text is not None and has_letters_or_digits(req.text) else None
        has_image = req.image is not None
        if text is None and not has_image:
            log.info("nothing to read in the request, no model call made")
            raise nothing_to_shop_for(Verdict.NOT_A_REQUEST)

        image_url = prepare_image_data_url(req.image) if req.image is not None else None
        if self._settings.log_prompts:
            log.info("understand input", extra={"user_text": text, "has_image": has_image})

        state = CallState(deadline=self._clock.monotonic() + self._deadline_s)
        problems: list[str] = []
        for _ in range(MAX_ROUNDS):
            try:
                reading = await self._gateway.ask(
                    build_input(text, image_url, problems), state, has_image=has_image
                )
                checked = validate_reading(reading, text=text, has_image=has_image)
            except NothingToShopFor as nothing:
                log.info("nothing to shop for", extra={"verdict": nothing.verdict.value})
                raise nothing_to_shop_for(nothing.verdict) from None
            except OutputValidationError as invalid:
                problems = invalid.problems
                log.warning("model answer rejected", extra={"problems": problems})
                continue
            except ModelPathFailure as failure:
                return self._fall_back(text, has_image, state, failure.reason)
            return UnderstandResult(
                input_type=checked.input_type,
                items=checked.items,
                budget=checked.budget,
                edits=checked.edits,
                language=checked.language,
                prompt_version=PROMPT_VERSION,
                model=self._model,
                usage=state.usage(),
                warnings=checked.warnings,
            )
        return self._fall_back(text, has_image, state, "answer still invalid after one retry")

    def _fall_back(
        self, text: str | None, has_image: bool, state: CallState, reason: str
    ) -> UnderstandResult:
        log.warning(
            "understand fallback",
            extra={"reason": reason, "photo_only": text is None, "calls_made": state.calls_made},
        )
        if text is None:
            raise photo_only_failure(reason)
        return fallback_result(text, has_image=has_image, usage=state.usage())
