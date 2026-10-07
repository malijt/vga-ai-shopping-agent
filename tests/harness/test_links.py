"""11.2.3: the link checker applies points 1 to 3 of "A working link" through a fake fetch."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from eval.harness.links import (
    THROTTLED_LINK_NOTE,
    LinkChecker,
    LinkResult,
    LinkRules,
    LinksMode,
    allowed_hosts_from_stores,
    evaluate_link,
    products_to_check,
    title_words,
)
from tests.factories import make_product, make_store_config
from tests.harness.helpers import make_group, make_response
from vga.models import Category, Product, SearchResponse

HOST = "www.alpha-store.example"
ALLOWED = {"Alpha Store": {HOST, "cdn.alpha-store.example"}}
URL = f"https://{HOST}/p/oversized-wool-blazer"


def product(**overrides: object) -> Product:
    fields: dict[str, object] = {
        "title": "Oversized Wool Blazer",
        "store": "Alpha Store",
        "product_url": URL,
        "image_url": "https://cdn.alpha-store.example/img/blazer.jpg",
    }
    return make_product(1, **{**fields, **overrides})


def opens(**overrides: object) -> LinkResult:
    """What the fetch saw for a healthy product page; override any field."""
    fields: dict[str, object] = {
        "url": URL,
        "final_url": URL,
        "status": 200,
        "title": "Oversized Wool Blazer | Alpha Store",
        "redirects": 0,
        "elapsed_s": 0.8,
    }
    return LinkResult.model_validate({**fields, **overrides})


def fetching(result: LinkResult) -> Callable[[str], Awaitable[LinkResult]]:
    async def fetch(url: str) -> LinkResult:
        return result

    return fetch


async def check(result: LinkResult, **overrides: object) -> list[str]:
    checker = LinkChecker(fetching(result), ALLOWED)
    return (await checker.check(product(**overrides))).problems


class TestAWorkingLink:
    async def test_a_200_on_the_stores_own_product_page_passes(self) -> None:
        checker = LinkChecker(fetching(opens()), ALLOWED)

        checked = await checker.check(product())

        assert checked.ok
        assert checked.problems == []
        assert checked.result == opens()

    async def test_a_404_fails_with_the_status(self) -> None:
        problems = await check(opens(status=404, title="Page not found"))

        assert problems == ["HTTP 404, not 200"]

    async def test_a_redirect_to_another_host_fails(self) -> None:
        elsewhere = "https://www.other-shop.example/p/oversized-wool-blazer"

        problems = await check(opens(final_url=elsewhere, redirects=1))

        assert problems == [
            "the final host 'www.other-shop.example' is not one of the store's own hosts"
        ]

    async def test_a_redirect_to_the_home_page_fails(self) -> None:
        home = f"https://{HOST}/"

        problems = await check(opens(final_url=home, redirects=1, title="Alpha Store"))

        assert any("home page" in problem for problem in problems)

    async def test_a_timeout_reported_by_the_fetch_fails(self) -> None:
        problems = await check(LinkResult(url=URL, error="timeout"))

        assert problems == ["no page opened: timeout"]

    async def test_a_fetch_that_raises_a_timeout_fails_and_does_not_stop_the_run(self) -> None:
        async def fetch(url: str) -> LinkResult:
            raise TimeoutError

        checker = LinkChecker(fetch, ALLOWED)

        checked = await checker.check(product())

        assert not checked.ok
        assert checked.problems == ["the request failed (TimeoutError)"]
        assert checked.result is None

    async def test_a_page_that_took_longer_than_six_seconds_fails(self) -> None:
        problems = await check(opens(elapsed_s=6.5))

        assert problems == ["took 6.5 s (at most 6 s)"]

    async def test_exactly_six_seconds_and_three_redirects_are_allowed(self) -> None:
        assert await check(opens(elapsed_s=6.0, redirects=3)) == []

    async def test_a_page_that_opened_but_reported_no_timing_cannot_be_called_ok(self) -> None:
        bare = LinkResult(url=URL, status=200, title="Oversized Wool Blazer")

        problems = await check(bare)

        assert problems == [
            "the fetch did not report how long the request took, so 6 s is unchecked"
        ]

    async def test_a_redirect_without_a_reported_final_address_fails(self) -> None:
        problems = await check(opens(final_url=None, redirects=2))

        assert len(problems) == 1
        assert "final address was not reported" in problems[0]

    async def test_a_fourth_redirect_fails(self) -> None:
        problems = await check(opens(redirects=4))

        assert problems == ["4 redirects (at most 3)"]

    @pytest.mark.parametrize("status", [None, 301, 403, 500])
    async def test_only_a_200_counts_as_opening(self, status: int | None) -> None:
        problems = await check(opens(status=status))

        assert len(problems) == 1
        assert "not 200" in problems[0]

    async def test_an_http_final_address_fails(self) -> None:
        problems = await check(opens(final_url=f"http://{HOST}/p/oversized-wool-blazer"))

        assert any("not https" in problem for problem in problems)

    async def test_an_image_cdn_host_is_one_of_the_stores_hosts(self) -> None:
        # allowed_hosts includes the image CDN; the page check (point 3) catches a non-product.
        on_cdn = "https://cdn.alpha-store.example/p/oversized-wool-blazer"

        assert await check(opens(final_url=on_cdn)) == []

    async def test_a_store_that_is_not_known_cannot_be_checked(self) -> None:
        checker = LinkChecker(fetching(opens()), {})

        checked = await checker.check(product())

        assert not checked.ok
        assert "is not known" in checked.problems[0]


class TestIsItTheProductPage:
    @pytest.mark.parametrize(
        ("final_path", "expected"),
        [
            ("/", "home page"),
            ("", "home page"),
            ("/en", "home page"),
            ("/en-ae/", "home page"),
            ("/search?q=blazer", "search page"),
            ("/catalogsearch/result?q=blazer", "search page"),
            ("/collections/blazers", "listing page"),
            ("/women", "listing page"),
            ("/p", "parent page"),
        ],
    )
    async def test_home_search_and_listing_pages_are_not_product_pages(
        self, final_path: str, expected: str
    ) -> None:
        problems = await check(
            opens(final_url=f"https://{HOST}{final_path}", title="Oversized Wool Blazer")
        )

        assert any(expected in problem for problem in problems), problems

    @pytest.mark.parametrize(
        "final_path",
        [
            "/products/oversized-wool-blazer",
            "/collections/blazers/products/oversized-wool-blazer",
            "/en-ae/p/oversized-wool-blazer-12345.html",
            "/p/oversized-wool-blazer?variant=42",
        ],
    )
    async def test_ordinary_product_addresses_pass(self, final_path: str) -> None:
        assert await check(opens(final_url=f"https://{HOST}{final_path}")) == []


class TestTheTitleOverlap:
    async def test_a_page_title_with_most_of_the_product_words_passes(self) -> None:
        assert await check(opens(title="Black Oversized Wool Blazer - Men | Alpha Store")) == []

    async def test_a_page_about_something_else_fails(self) -> None:
        problems = await check(opens(title="Leather Biker Jacket | Alpha Store"))

        assert len(problems) == 1
        assert "shares 0%" in problems[0]

    async def test_exactly_half_the_words_passes_and_less_fails(self) -> None:
        half = await check(opens(title="Wool Blazer"), title="Oversized Wool Blazer Black")
        less = await check(opens(title="Wool"), title="Oversized Wool Blazer Black")

        assert half == []
        assert len(less) == 1

    async def test_a_missing_title_cannot_be_compared(self) -> None:
        problems = await check(opens(title=None))

        assert problems == ["the page has no title to compare with the product"]

    @pytest.mark.parametrize(
        "title", ["404 Not Found", "Just a moment...", "Sign in to continue", "Access Denied"]
    )
    async def test_error_login_and_captcha_titles_fail(self, title: str) -> None:
        problems = await check(opens(title=f"{title} Oversized Wool Blazer"))

        assert any("error, login or CAPTCHA" in problem for problem in problems)

    async def test_arabic_titles_are_compared_by_their_words(self) -> None:
        arabic = product(title="قميص قطن أبيض للرجال")

        checker = LinkChecker(fetching(opens(title="قميص قطن أبيض | متجر")), ALLOWED)

        assert (await checker.check(arabic)).ok

    def test_title_words_ignore_case_punctuation_and_single_letters(self) -> None:
        assert title_words("Men's  Wool-Blend BLAZER, size M!") == {
            "men",
            "wool",
            "blend",
            "blazer",
            "size",
        }

    async def test_the_overlap_threshold_is_a_rule_not_a_constant(self) -> None:
        strict = LinkRules(min_title_overlap=1.0)
        problems = evaluate_link(
            product(),
            opens(title="Wool Blazer"),
            ALLOWED["Alpha Store"],
            strict,
        )

        assert len(problems) == 1


class TestTheChecker:
    async def test_asks_for_each_url_once_even_when_several_queries_return_it(self) -> None:
        asked: list[str] = []

        async def fetch(url: str) -> LinkResult:
            asked.append(url)
            return opens()

        checker = LinkChecker(fetch, ALLOWED)

        await checker.check_all([product(), product(), product()])

        assert asked == [URL]
        assert checker.requests_made == 1

    async def test_checks_one_url_at_a_time_never_in_parallel(self) -> None:
        active = 0
        peak = 0

        async def fetch(url: str) -> LinkResult:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return opens(url=url, final_url=url)

        checker = LinkChecker(fetch, ALLOWED)
        many = [
            product(product_url=f"https://{HOST}/p/oversized-wool-blazer-{n}") for n in range(5)
        ]

        await checker.check_all(many)

        assert peak == 1

    async def test_one_failing_link_does_not_stop_the_others(self) -> None:
        async def fetch(url: str) -> LinkResult:
            if url.endswith("-2"):
                raise ConnectionError
            return opens(url=url, final_url=url)

        checker = LinkChecker(fetch, ALLOWED)
        many = [
            product(product_url=f"https://{HOST}/p/oversized-wool-blazer-{n}") for n in (1, 2, 3)
        ]

        results = await checker.check_all(many)

        assert [checked.ok for checked in results] == [True, False, True]

    async def test_a_failure_names_the_url_store_and_title_for_the_report(self) -> None:
        checker = LinkChecker(fetching(opens(status=404)), ALLOWED)

        checked = await checker.check(product())

        assert (checked.url, checked.store, checked.product_title) == (
            URL,
            "Alpha Store",
            "Oversized Wool Blazer",
        )


class TestALinkAStoreTurnedAway:
    """A store that answered 429 (or is cooling down after it did) said nothing about the link."""

    async def test_it_is_not_checked_and_not_broken(self) -> None:
        turned_away = LinkResult(url=URL, error="store_blocked (HTTP 429)", throttled=True)
        checker = LinkChecker(fetching(turned_away), ALLOWED)

        checked = await checker.check(product())

        assert checked.not_checked is True
        assert checked.ok is False
        assert checked.problems == [THROTTLED_LINK_NOTE]
        assert "not checked" in checked.problems[0]

    async def test_a_link_that_is_broken_is_still_broken(self) -> None:
        checker = LinkChecker(fetching(opens(status=404)), ALLOWED)

        checked = await checker.check(product())

        assert checked.not_checked is False
        assert checked.ok is False

    async def test_a_good_link_is_not_marked(self) -> None:
        checked = await LinkChecker(fetching(opens()), ALLOWED).check(product())

        assert (checked.ok, checked.not_checked) == (True, False)


class TestWhichLinksAreChecked:
    def response(self) -> SearchResponse:
        return make_response(
            [
                make_group(Category.TOPS, counts=(4, 4, 4, 4)),
                make_group(Category.SHOES, counts=(3, 3, 3, 3), item_index=1),
            ]
        )

    def test_none_checks_nothing(self) -> None:
        assert products_to_check(self.response(), LinksMode.NONE) == []

    def test_all_checks_every_result_once(self) -> None:
        chosen = products_to_check(self.response(), LinksMode.ALL)

        assert len(chosen) == 28
        assert len({p.product_url for p in chosen}) == 28

    def test_top10_checks_the_ten_best_of_each_garment_group(self) -> None:
        chosen = products_to_check(self.response(), LinksMode.TOP10)

        assert len(chosen) == 20
        assert [p.title for p in chosen][:3] == ["Tops item 1", "Tops item 2", "Tops item 3"]

    def test_a_product_returned_twice_is_listed_once(self) -> None:
        group = make_group(Category.TOPS, counts=(2, 2, 2, 2))
        twin = make_response([group, group.model_copy(update={"item_index": 1})])

        assert len(products_to_check(twin, LinksMode.ALL)) == 8


class TestAllowedHosts:
    def test_maps_the_display_name_and_the_id_to_the_stores_hosts(self) -> None:
        store = make_store_config(id="alpha", name="Alpha Store")

        mapping = allowed_hosts_from_stores([store])

        assert mapping["Alpha Store"] == frozenset(store.allowed_hosts)
        assert mapping["alpha"] == frozenset(store.allowed_hosts)
