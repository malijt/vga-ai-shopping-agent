"""Understand step: one OpenAI call turns a photo and/or text into an UnderstandResult (Phase 5).

What other phases import:

- ``OpenAIUnderstander(settings, client=None, *, clock=None, budget=None, ...)``: the real
  ``Understander``. ``create_openai_client()`` builds the client it needs from ``OPENAI_API_KEY``.
- ``apply_overrides(result, chip_edits)`` and ``rebuild_keywords(item)``: chip edits with no
  model call. ``effective_gender(item)``: the gender the search may use (stated or confirmed).
- ``PROMPT_VERSION``, ``FALLBACK_MARKER`` and the ``FALLBACK_WARNING*`` texts: to recognise which
  prompt made a result and whether it came from the fallback.
- ``process_call_budget()`` and ``CallBudget``: the daily OpenAI call counter.
"""

from vga.understand.budget import CallBudget, process_call_budget
from vga.understand.fallback import (
    FALLBACK_MARKER,
    FALLBACK_WARNING,
    FALLBACK_WARNING_WITH_PHOTO,
)
from vga.understand.keywords import rebuild_keywords
from vga.understand.overrides import apply_overrides, effective_gender
from vga.understand.prompt import PROMPT_VERSION
from vga.understand.understander import OpenAIUnderstander, create_openai_client

__all__ = [
    "FALLBACK_MARKER",
    "FALLBACK_WARNING",
    "FALLBACK_WARNING_WITH_PHOTO",
    "PROMPT_VERSION",
    "CallBudget",
    "OpenAIUnderstander",
    "apply_overrides",
    "create_openai_client",
    "effective_gender",
    "process_call_budget",
    "rebuild_keywords",
]
