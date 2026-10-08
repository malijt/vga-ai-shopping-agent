"""How we recognise that a store has turned an honest request away (plan 6.1.4, BRD Rule 2).

The behaviour is the one ``scripts/qualify_store.py`` proved on 34 real sites: an HTTP 403 or 429, a
login wall, or a bot-challenge page. The answer is always the same: stop, make no second request,
leave the store alone for the cooldown. Nothing here changes headers, tries again or works around a
block.
"""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

BLOCKING_STATUSES = frozenset({401, 403, 429})
"""401 means the page needs a login, which we never use; 403 and 429 are a refusal or a rate
limit. None of them is retried."""

RATE_LIMITED_STATUS = 429
"""HTTP "too many requests". On a platform shared by many shops it is the platform's answer, not
the shop's, so it stops every store of the platform (``PoliteClient``), not only the one that got
it."""

MAX_RETRY_AFTER_S = 24 * 3600
"""The longest ``Retry-After`` we honour. A server (or whatever sits in front of it) that asks for
more is read as asking for a day: the answer is untrusted input and must not be able to switch a
store off for ever."""

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

CHALLENGE_SCAN_BYTES = 20_000

# Specific page-level markers of a bot challenge, looked for in the first 20 KB of an HTML response.
CHALLENGE_MARKERS = (
    "just a moment...",
    "cf-browser-verification",
    "cf-chl-",
    "px-captcha",
    "captcha-delivery",
    "attention required! | cloudflare",
    "access denied",
    "pardon our interruption",
    "_incapsula_resource",
    "are you a robot",
    "verify you are human",
    "enable javascript and cookies to continue",
)

LOGIN_PATH = re.compile(
    r"/(log-?in|sign-?in|customer/account/login|account/login)\b", re.IGNORECASE
)
"""A redirect to a path like this means the page is behind a login."""


def looks_like_html(body: bytes, content_type: str) -> bool:
    """True for an HTML page, judged by the content type or by the first character."""
    if "html" in content_type.lower():
        return True
    return body.lstrip()[:1] == b"<"


def find_challenge_marker(body: bytes, content_type: str) -> str | None:
    """The first bot-challenge marker found in an HTML response, else ``None``.

    Only HTML is scanned: JSON and plain text (a product list, a robots.txt) can legitimately
    contain a phrase such as "access denied" in a product description or a comment.
    """
    if not looks_like_html(body, content_type):
        return None
    head = body[:CHALLENGE_SCAN_BYTES].decode("utf-8", errors="replace").lower()
    return next((marker for marker in CHALLENGE_MARKERS if marker in head), None)


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds a server asked us to wait, from its ``Retry-After`` header, else ``None``.

    The header is either a number of seconds or an HTTP date (RFC 9110 section 10.2.3); ``now`` is
    the current wall-clock time, for a date. Anything else, a time already past and zero all mean
    "no wait was asked for" (``None``). The result is at most ``MAX_RETRY_AFTER_S``.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.isascii() and text.isdigit():
        seconds = float(text)
    else:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - now).total_seconds()
    if seconds <= 0:
        return None
    return min(seconds, MAX_RETRY_AFTER_S)
