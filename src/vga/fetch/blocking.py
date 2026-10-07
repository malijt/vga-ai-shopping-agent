"""How we recognise that a store has turned an honest request away (plan 6.1.4, BRD Rule 2).

The behaviour is the one ``scripts/qualify_store.py`` proved on 34 real sites: an HTTP 403 or 429, a
login wall, or a bot-challenge page. The answer is always the same: stop, make no second request,
leave the store alone for the cooldown. Nothing here changes headers, tries again or works around a
block.
"""

import re

BLOCKING_STATUSES = frozenset({401, 403, 429})
"""401 means the page needs a login, which we never use; 403 and 429 are a refusal or a rate
limit. None of them is retried."""

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
