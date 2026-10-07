"""Search URL builder (plan 6.3.2)."""

import pytest

from tests.factories import make_store_config
from tests.fetch.conftest import OHPOLLY_BLAZER_URL, shopify_store
from vga.stores.urls import MAX_QUERY_CHARS, build_search_url, clean_query


def test_spaces_become_percent_20() -> None:
    store = make_store_config()

    assert (
        build_search_url(store, "black oversized blazer")
        == "https://www.demo-store.example/search?q=black%20oversized%20blazer"
    )


def test_an_ampersand_cannot_start_a_new_parameter() -> None:
    store = make_store_config()

    url = build_search_url(store, "shirts & ties")

    assert url == "https://www.demo-store.example/search?q=shirts%20%26%20ties"
    assert "&" not in url.split("?q=")[1]


@pytest.mark.parametrize(
    ("query", "encoded"),
    [
        ("قميص أسود", "%D9%82%D9%85%D9%8A%D8%B5%20%D8%A3%D8%B3%D9%88%D8%AF"),
        ("café", "caf%C3%A9"),
        ("100% cotton", "100%25%20cotton"),
        ("a+b", "a%2Bb"),
        ("what?#frag", "what%3F%23frag"),
        ("a/b\\c", "a%2Fb%5Cc"),
        ("quote'\"", "quote%27%22"),
    ],
)
def test_the_query_is_percent_encoded_as_utf8(query: str, encoded: str) -> None:
    store = make_store_config()

    assert build_search_url(store, query).endswith(f"?q={encoded}")


def test_a_query_cannot_change_the_host_or_the_path() -> None:
    store = make_store_config()

    url = build_search_url(store, "../../admin@evil.example/x")

    assert url.startswith("https://www.demo-store.example/search?q=")
    assert "evil.example/x" not in url.split("?q=")[0]
    assert "@" not in url


def test_brackets_in_the_template_are_percent_encoded_like_the_reports_saw_them_work() -> None:
    assert build_search_url(shopify_store(), "black blazer") == OHPOLLY_BLAZER_URL


def test_a_path_style_template_is_filled_too() -> None:
    store = make_store_config(search_url_template="https://www.demo-store.example/s/{query}/p1")

    assert build_search_url(store, "red dress") == "https://www.demo-store.example/s/red%20dress/p1"


def test_white_space_is_collapsed_and_control_characters_removed() -> None:
    assert clean_query("  black \t\n blazer\x00\x07 ") == "black blazer"


def test_unicode_is_normalised() -> None:
    decomposed = "cafe" + chr(0x301)  # "e" followed by a combining acute accent
    composed = "caf" + chr(0xE9)

    assert clean_query(decomposed) == composed


def test_the_query_is_capped() -> None:
    assert len(clean_query("a" * 5000)) == MAX_QUERY_CHARS


@pytest.mark.parametrize("query", ["", "   ", "\t\n", "\x00\x01"])
def test_an_empty_query_is_an_error(query: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        build_search_url(make_store_config(), query)
