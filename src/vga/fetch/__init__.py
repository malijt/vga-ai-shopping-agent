"""Polite HTTP: client, host allow-list, rate limiter, cooldown, robots.txt (Phase 6).

This package knows nothing about products or extraction; the store-aware layer on top of it is
``vga.stores``. Typical wiring (``vga.stores.StoreSearchEngine`` does this for you)::

    client = PoliteClient(settings)
    robots = RobotsChecker(client)
    await robots.ensure_allowed(url, store)
    response = await client.fetch(
        url, store, client.page_policy(store), vet_redirect=robots.ensure_allowed
    )
"""

from vga.fetch.allowlist import belongs_to_store_site, check_url, is_allowed, registered_domain
from vga.fetch.client import FetchPolicy, FetchResponse, PoliteClient
from vga.fetch.errors import (
    BlockedError,
    CooldownError,
    CrossDomainRedirectError,
    FetchError,
    FetchFailedError,
    FetchTimeoutError,
    ResponseTooLargeError,
    RobotsDeniedError,
    TooManyRedirectsError,
    UrlNotAllowedError,
)
from vga.fetch.platform import platform_of
from vga.fetch.ratelimit import Cooldowns, RateLimiter, SharedLimit
from vga.fetch.robots import RobotsChecker

__all__ = [
    "BlockedError",
    "CooldownError",
    "Cooldowns",
    "CrossDomainRedirectError",
    "FetchError",
    "FetchFailedError",
    "FetchPolicy",
    "FetchResponse",
    "FetchTimeoutError",
    "PoliteClient",
    "RateLimiter",
    "ResponseTooLargeError",
    "RobotsChecker",
    "RobotsDeniedError",
    "SharedLimit",
    "TooManyRedirectsError",
    "UrlNotAllowedError",
    "belongs_to_store_site",
    "check_url",
    "is_allowed",
    "platform_of",
    "registered_domain",
]
