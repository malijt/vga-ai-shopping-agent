"""The one error shape: ``VgaError(code, user_message, detail)``.

- ``code``: a short machine-readable string for logs and tests.
- ``user_message``: plain language that says what happened and what to do next. This is the ONLY
  text a shopper ever sees, and it is what ``str(error)`` returns.
- ``detail``: technical context for the log (HTTP status, field name, ...). It never appears in
  ``str()`` or ``repr()`` and is never shown in the UI, so it cannot leak internals.

Raise a subclass where one fits; modules may define more subclasses of their own. Never swallow an
error silently: a fallback logs at warn level with the request id.
"""

from typing import ClassVar

GENERIC_USER_MESSAGE = "Something went wrong on our side. Please try again in a moment."


class VgaError(Exception):
    """Base class for every error this application raises on purpose."""

    default_code: ClassVar[str] = "error"
    default_message: ClassVar[str] = GENERIC_USER_MESSAGE

    def __init__(
        self,
        user_message: str | None = None,
        *,
        detail: str | None = None,
        code: str | None = None,
    ) -> None:
        message = user_message or self.default_message
        super().__init__(message)
        self.code: str = code or self.default_code
        self.user_message: str = message
        self.detail: str | None = detail

    def __str__(self) -> str:
        return self.user_message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, user_message={self.user_message!r})"


class InvalidInputError(VgaError):
    """The request is not something we can search with (no input, wrong file type, too big)."""

    default_code = "invalid_input"
    default_message = (
        "We couldn't use that input. Please add a clear photo (PNG, JPG or WebP) "
        "or describe what you are looking for, then try again."
    )


class LlmError(VgaError):
    """The language / vision model failed, refused, or returned something unusable."""

    default_code = "llm_failure"
    default_message = (
        "We couldn't understand your request right now. "
        "Please try again in a moment, or type what you are looking for."
    )


class StoreBlockedError(VgaError):
    """A store refused an honest request (403/429, CAPTCHA, robots.txt). It is skipped, never
    bypassed (BRD Rule 2)."""

    default_code = "store_blocked"
    default_message = "This store did not allow the search, so we skipped it."


class CallBudgetExceededError(VgaError):
    """The daily cap on OpenAI calls is used up. This is the call budget, not the shopper's
    price budget."""

    default_code = "call_budget_exceeded"
    default_message = (
        "The demo has reached its daily limit for AI requests. Please try again tomorrow."
    )


class ConfigError(VgaError):
    """Settings are invalid. ``detail`` names each bad field; the cause is chained for the
    developer who runs the app."""

    default_code = "config"
    default_message = (
        "The app settings are not valid. Check config/settings.yaml and your environment "
        "variables, then restart."
    )


def user_message_for(error: BaseException) -> str:
    """The text a shopper may see for any exception: a ``VgaError``'s own plain message, or a
    generic one. Never ``str(error)`` of an arbitrary exception, which could leak internals."""
    if isinstance(error, VgaError):
        return error.user_message
    return GENERIC_USER_MESSAGE
