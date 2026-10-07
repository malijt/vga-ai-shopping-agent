"""Which URLs we may request (plan 6.1.2). This is a security control: nothing is fetched, and no
redirect is followed, unless ``check_url`` accepts it.

A URL passes only if all of these hold:

- the scheme is ``https`` (no ``http``, ``file``, ``ftp``, ...);
- it carries no user name or password, no whitespace, no control character and no backslash (the
  characters that make two URL parsers disagree about which host a URL means);
- the port is the default one (443);
- the host is a name, never an IP address in any notation, and not a local-looking name such as
  ``localhost``, ``*.local`` or ``*.internal``: loopback, private and link-local targets (for
  example ``127.0.0.1``, ``10.x.x.x``, ``169.254.169.254``, ``[::1]``) can never be reached, even
  when someone lists one in a store file;
- the host is exactly one of the store's ``allowed_hosts`` (no wildcard, no sub-domain matching).

Not covered: a listed host name whose DNS record points at a private address (DNS rebinding). The
host names come from our own store files, so this needs a hostile store; see the Phase 6 report.
"""

import ipaddress
import re
from collections.abc import Collection
from urllib.parse import urlsplit

import httpx

from vga.fetch.errors import UrlNotAllowedError
from vga.models import StoreConfig

_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f\\]")
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]+|\d+)(\.(0x[0-9a-f]+|\d+))*$", re.IGNORECASE)
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".lan", ".home", ".corp")
_LOCAL_NAMES = frozenset({"localhost", "ip6-localhost", "ip6-loopback", "broadcasthost"})

# Registered domain = the last two labels, or the last three under these two-level public
# suffixes. A short list on purpose: it only has to be right for the GCC and UK shops we meet, and
# the allow-list above is the primary control. Wrong in the strict direction (an unlisted
# suffix makes two sibling shops look like one domain) is harmless here, because both hosts
# must be on the allow-list anyway.
_TWO_LEVEL_SUFFIXES = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "com.au", "co.nz", "co.za", "co.in", "co.jp", "com.tr",
        "co.ae", "net.ae", "com.sa", "com.kw", "com.qa", "com.bh", "com.om", "com.eg", "com.jo",
    }
)  # fmt: skip


def registered_domain(host: str) -> str:
    """The registrable part of a host name: ``www.shop.example`` -> ``shop.example``."""
    labels = host.lower().rstrip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normalise_host(host: str) -> str:
    """Lower-case a host and drop a trailing dot (``Shop.Example.`` is ``shop.example``)."""
    return host.strip().lower().rstrip(".")


def belongs_to_store_site(store: StoreConfig, host: str) -> bool:
    """True for a host of the store's own site: the host of its search URL and any other host of
    the same registered domain (``www.`` and the bare domain, a market sub-domain). False for a
    separate domain such as the shared image CDN ``cdn.shopify.com``, even when the store lists it
    in ``allowed_hosts``. A pure name comparison: it says nothing about whether ``host`` is
    allowed (``check_url`` does that)."""
    search_host = normalise_host(urlsplit(store.search_url_template).hostname or "")
    return registered_domain(normalise_host(host)) == registered_domain(search_host)


def _refuse(url: str, why: str) -> UrlNotAllowedError:
    return UrlNotAllowedError(
        "We only contact a store's own https addresses, so this link was not opened.",
        detail=f"{why}: {url[:200]}",
    )


def _is_ip_or_local(host: str) -> str | None:
    """Why ``host`` is an address or local name we never contact, or ``None`` if it is a name."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        kind = "private/loopback/link-local" if not address.is_global else "IP"
        return f"{kind} address hosts are not allowed"
    if _NUMERIC_HOST.match(host):
        return "numeric (IP-style) hosts are not allowed"
    if host in _LOCAL_NAMES or host.endswith(_LOCAL_SUFFIXES):
        return "local host names are not allowed"
    return None


def check_url(url: str, allowed_hosts: Collection[str]) -> str:
    """Return the (lower-cased) host of ``url`` if it may be requested, else raise
    ``UrlNotAllowedError``. Never makes a request."""
    if _FORBIDDEN_CHARS.search(url):
        raise _refuse(url, "URL contains whitespace, a control character or a backslash")
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError) as exc:
        raise _refuse(url, f"URL could not be parsed ({exc})") from exc
    if parsed.scheme != "https":
        raise _refuse(url, f"scheme {parsed.scheme or '(none)'!r} is not https")
    if parsed.userinfo:
        raise _refuse(url, "URL contains credentials")
    if parsed.port is not None:  # httpx reports None for the default port 443
        raise _refuse(url, f"port {parsed.port} is not the default https port")
    host = normalise_host(parsed.host)
    if not host:
        raise _refuse(url, "URL has no host")
    # httpx decides which host the request really goes to; the standard library must agree, so a
    # URL that two parsers read differently is refused instead of guessed at.
    try:
        stdlib_host = normalise_host(urlsplit(url).hostname or "")
    except ValueError as exc:
        raise _refuse(url, f"URL could not be parsed ({exc})") from exc
    if stdlib_host != host:
        raise _refuse(url, f"URL parsers disagree about the host ({host!r} vs {stdlib_host!r})")
    why = _is_ip_or_local(host)
    if why is not None:
        raise _refuse(url, why)
    allowed = {normalise_host(item) for item in allowed_hosts}
    if host not in allowed:
        raise _refuse(url, f"host {host!r} is not in the store's allowed_hosts")
    return host


def is_allowed(url: str, allowed_hosts: Collection[str]) -> bool:
    """``check_url`` as a yes/no question."""
    try:
        check_url(url, allowed_hosts)
    except UrlNotAllowedError:
        return False
    return True
