"""The host allow-list is a security control (plan 6.1.2): test the refusals hard."""

import pytest

from vga.fetch.allowlist import check_url, is_allowed, registered_domain
from vga.fetch.errors import UrlNotAllowedError

ALLOWED = ["www.shop.example", "cdn.shop.example"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.shop.example/search?q=blazer",
        "https://WWW.SHOP.EXAMPLE/search",
        "https://www.shop.example./search",
        "https://cdn.shop.example/img/a.jpg?v=1",
        "https://www.shop.example:443/search",
    ],
)
def test_an_https_url_on_an_allowed_host_passes(url: str) -> None:
    assert check_url(url, ALLOWED) in ALLOWED


@pytest.mark.parametrize(
    ("url", "why"),
    [
        ("http://www.shop.example/search", "http scheme"),
        ("ftp://www.shop.example/file", "ftp scheme"),
        ("file:///etc/passwd", "file scheme"),
        ("//www.shop.example/search", "no scheme"),
        ("www.shop.example/search", "no scheme or host"),
        ("https:///www.shop.example/search", "empty host"),
        ("https://other.example/search", "host not on the list"),
        ("https://shop.example/search", "apex of an allowed host is not allowed"),
        ("https://evil.www.shop.example/search", "sub-domain of an allowed host"),
        ("https://www.shop.example.evil.example/search", "allowed host as a prefix"),
        ("https://evil.example/www.shop.example", "allowed host in the path"),
        ("https://evil.example?www.shop.example", "allowed host in the query"),
        ("https://user:pw@www.shop.example/search", "credentials"),
        ("https://www.shop.example@evil.example/search", "credential-style host trick"),
        ("https://www.shop.example\\@evil.example/search", "backslash host trick"),
        ("https://evil.example#@www.shop.example/search", "fragment host trick"),
        ("https://www.shop.example:8443/search", "non-default port"),
        ("https://www.shop.example:80/search", "port 80 on https"),
        ("https://www.shop.example/a b", "space in the URL"),
        ("https://www.shop.example/a\tb", "tab in the URL"),
        ("https://www.shop.example/a\nb", "newline in the URL"),
        ("https://www.shop.example/\x00", "NUL in the URL"),
        ("https://www.shop.example%2eevil.example/", "encoded dot in the host"),
        ("https://www.shop.exämple/search", "non-ASCII look-alike host"),
        ("", "empty string"),
    ],
)
def test_a_url_that_is_not_https_on_the_list_is_refused(url: str, why: str) -> None:
    with pytest.raises(UrlNotAllowedError):
        check_url(url, ALLOWED)
    assert not is_allowed(url, ALLOWED), why


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.1",
        "127.0.0.254",
        "0.0.0.0",  # noqa: S104 - a literal under test, not a bind address
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "169.254.0.1",
        "100.64.0.1",
        "8.8.8.8",
        "[::1]",
        "[::]",
        "[fe80::1]",
        "[fc00::1]",
        "[::ffff:127.0.0.1]",
        "2130706433",
        "0x7f000001",
        "0x7f.0.0.1",
        "0177.0.0.1",
        "localhost",
        "app.localhost",
        "printer.local",
        "metadata.google.internal",
        "box.lan",
    ],
)
def test_ip_addresses_and_local_names_are_refused_even_if_someone_lists_them(host: str) -> None:
    bare = host.strip("[]")
    url = f"https://{host}/search"

    # Even when the store file lists the address as an allowed host, it is still refused.
    with pytest.raises(UrlNotAllowedError):
        check_url(url, [*ALLOWED, bare])
    assert not is_allowed(url, ALLOWED)


def test_the_refusal_names_the_url_in_detail_and_keeps_the_user_message_plain() -> None:
    with pytest.raises(UrlNotAllowedError) as excinfo:
        check_url("https://169.254.169.254/latest/meta-data", ALLOWED)

    assert "169.254.169.254" in (excinfo.value.detail or "")
    assert "169.254.169.254" not in str(excinfo.value)
    assert excinfo.value.code == "url_not_allowed"


def test_matching_is_exact_not_by_suffix() -> None:
    assert not is_allowed("https://notwww.shop.example/", ALLOWED)
    assert not is_allowed("https://www.shop.example.cn/", ALLOWED)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("www.ohpolly.ae", "ohpolly.ae"),
        ("ohpolly.ae", "ohpolly.ae"),
        ("cdn.shopify.com", "shopify.com"),
        ("WWW.ClubLLondon.AE.", "clubllondon.ae"),
        ("shop.example.co.uk", "example.co.uk"),
        ("www.brand.co.ae", "brand.co.ae"),
        ("a.b.c.example.com", "example.com"),
        ("localhost", "localhost"),
    ],
)
def test_registered_domain(host: str, expected: str) -> None:
    assert registered_domain(host) == expected
