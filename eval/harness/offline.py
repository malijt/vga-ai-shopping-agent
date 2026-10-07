"""What ``--mock`` and ``--replay`` use instead of the real photos and the real network.

- ``placeholder_image``: a flat grey picture. Mock and replay never read the private photos: the
  stand-ins ignore image content, and a placeholder keeps a replay identical on every machine and
  keeps the photos untouched (BRD Rule 4). Only a live run (``--record``) reads them.
- ``MockLinkFetch``: answers every link as "200, the product's own page" so the report shows a
  full table. It checks nothing about a real store: a mock report says so at the top.
"""

from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from tests.factories import make_image_bytes

from eval.harness.links import LinkResult
from vga.models import Product, SearchResponse

PLACEHOLDER_SIZE = (800, 800)


def placeholder_image() -> bytes:
    """A valid 800 x 800 JPEG with nothing in it."""
    return make_image_bytes("JPEG", PLACEHOLDER_SIZE, (200, 200, 200))


class MockLinkFetch:
    """A ``LinkFetch`` for ``--mock``: no network, every known link opens its own product page."""

    def __init__(self, products: Iterable[Product]) -> None:
        self._titles = {product.product_url: product.title for product in products}

    async def __call__(self, url: str) -> LinkResult:
        return LinkResult(
            url=url, final_url=url, status=200, title=self._titles.get(url), elapsed_s=0.0
        )


def allowed_hosts_from_responses(
    responses: Iterable[SearchResponse],
) -> Mapping[str, frozenset[str]]:
    """For a mock run, which hosts each store's own links are on. A real run uses the store
    configs instead (``allowed_hosts_from_stores``)."""
    hosts: dict[str, set[str]] = {}
    for response in responses:
        for scored in response.products:
            product = scored.product
            for url in (product.product_url, product.image_url):
                host = urlsplit(url).hostname
                if host:
                    hosts.setdefault(product.store, set()).add(host.lower())
    return {store: frozenset(found) for store, found in hosts.items()}
