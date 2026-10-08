"""Errors the polite HTTP layer raises on purpose (one per way a store request can end badly).

Each carries the ``StoreStatus`` the search engine reports for it, so mapping an exception to a
``StoreResult`` is one attribute read, not a chain of ``isinstance`` checks. They are all
``VgaError`` subclasses, so ``user_message`` is plain language and ``detail`` (HTTP status, URL,
reason) is for the log only.
"""

from typing import ClassVar

from vga.errors import StoreBlockedError, VgaError
from vga.models import StoreStatus


class FetchError(VgaError):
    """A store request failed in a way we can name. Never retried (BRD Rule 2)."""

    default_code = "fetch_error"
    default_message = "We couldn't read this store right now, so we skipped it."
    store_status: ClassVar[StoreStatus] = StoreStatus.ERROR


class UrlNotAllowedError(FetchError):
    """The URL is not https, not on the store's ``allowed_hosts``, or points at an IP address.

    Raised before any request is made, and again for every redirect hop."""

    default_code = "url_not_allowed"
    store_status = StoreStatus.ERROR


class CrossDomainRedirectError(FetchError):
    """The store redirected to another registered domain (it moved, or something is wrong). The
    redirect is not followed."""

    default_code = "cross_domain_redirect"
    store_status = StoreStatus.ERROR


class TooManyRedirectsError(FetchError):
    default_code = "too_many_redirects"
    store_status = StoreStatus.ERROR


class ResponseTooLargeError(FetchError):
    """The response is bigger than the size cap. The download is aborted."""

    default_code = "response_too_large"
    store_status = StoreStatus.ERROR


class FetchTimeoutError(FetchError):
    default_code = "fetch_timeout"
    default_message = "This store took too long to answer, so we skipped it."
    store_status = StoreStatus.TIMEOUT


class FetchFailedError(FetchError):
    """Connection failure, TLS failure or any other transport error."""

    default_code = "fetch_failed"
    store_status = StoreStatus.ERROR


class BlockedError(StoreBlockedError, FetchError):
    """403, 429, 401, a login wall or a bot-challenge page. One request was made; the store now
    sits in cooldown and is never bypassed (BRD Rule 2)."""

    default_code = "store_blocked"
    store_status = StoreStatus.BLOCKED


class RobotsDeniedError(StoreBlockedError, FetchError):
    """robots.txt disallows the URL, or could not be read (RFC 9309: unreachable means disallow)."""

    default_code = "robots_denied"
    default_message = "This store's robots.txt does not allow the search, so we skipped it."
    store_status = StoreStatus.ROBOTS_DENIED


ROBOTS_UNREADABLE_DETAIL = "robots.txt could not be read"
"""Every ``RobotsUnreadableError.detail`` starts with this, and ``StoreResult.detail`` carries it
on to the pipeline, which uses it to tell the shopper "we could not check" instead of "the store
asks not to be searched". One constant, so the two sides cannot drift apart."""


class RobotsUnreadableError(RobotsDeniedError):
    """robots.txt could not be read (a timeout, a network error, a 5xx, an HTML page): the store
    said nothing, so nothing is sent to it, but it did not ask us to stay away. Still the
    ``robots_denied`` status; the difference is in the words the shopper reads."""

    default_code = "robots_unreadable"
    default_message = "We could not check whether this store allows searching, so we skipped it."


class CooldownError(StoreBlockedError, FetchError):
    """The store blocked us recently and is still in cooldown: no request is made."""

    default_code = "store_cooldown"
    default_message = "This store recently turned our request away, so we are leaving it alone."
    store_status = StoreStatus.COOLDOWN
