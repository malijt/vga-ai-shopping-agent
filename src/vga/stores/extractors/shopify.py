"""The ``shopify`` strategy (plan 6.4.2): Shopify's predictive-search endpoint.

The store file's ``search_url_template`` is the endpoint, with the brackets as Shopify writes them
(the URL builder percent-encodes them)::

    https://ohpolly.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10

The response is ``{"resources": {"results": {"products": [...]}}}``, at most 10 products. Each
product gives ``title``, ``price`` (a string such as ``"535.00"``), ``image`` (an absolute CDN
URL), ``url`` (relative, with tracking parameters), ``available`` (a boolean), plus ``vendor``,
``type`` and ``tags``, which are not mapped (except ``vendor`` through ``name_field``). The response
has **no currency**: the store file's ``currency`` is used.

Options (all optional)::

    options:
      name_field: title      # or "vendor"

``name_field`` says which response field holds the readable product name. It is ``title`` for
nearly every store; The Bear House puts a style code in ``title`` ("BOALI") and the real name in
``vendor`` ("Olive Checked Slim Fit Casual Shirt"). ``fields`` is not used: the mapping is fixed.
"""

import json
from typing import Any
from urllib.parse import urlsplit

from vga.models import StoreConfig, StrategyConfig
from vga.stores.extractors.base import ExtractionError
from vga.stores.normalise import RawRecord

NAME_FIELDS = ("title", "vendor")


class ShopifyExtractor:
    name = "shopify"

    def validate(self, strategy: StrategyConfig) -> None:
        if strategy.fields:
            msg = (
                "the shopify strategy has a fixed field mapping; remove 'fields' "
                f"(got {sorted(strategy.fields)})"
            )
            raise ValueError(msg)
        unknown = sorted(set(strategy.options) - {"name_field"})
        if unknown:
            msg = f"unknown option(s) {unknown} for the shopify strategy; allowed: ['name_field']"
            raise ValueError(msg)
        name_field = strategy.options.get("name_field", "title")
        if name_field not in NAME_FIELDS:
            msg = f"options.name_field must be one of {list(NAME_FIELDS)}, got {name_field!r}"
            raise ValueError(msg)

    def extract(self, body: str, store: StoreConfig, strategy: StrategyConfig) -> list[RawRecord]:
        name_field = str(strategy.options.get("name_field", "title"))
        try:
            data = json.loads(body)
        except ValueError as exc:
            msg = "the response is not JSON"
            raise ExtractionError(msg) from exc
        results = _dig(data, "resources", "results")
        if not isinstance(results, dict):
            msg = "the JSON has no resources.results object (not a Shopify suggest response)"
            raise ExtractionError(msg)
        products = results.get("products", [])
        if not isinstance(products, list):
            msg = "resources.results.products is not a list"
            raise ExtractionError(msg)
        return [self._record(item, name_field) for item in products if isinstance(item, dict)]

    @staticmethod
    def _record(item: dict[str, Any], name_field: str) -> RawRecord:
        featured = item.get("featured_image")
        image = item.get("image") or (featured.get("url") if isinstance(featured, dict) else None)
        handle = item.get("handle")
        link = item.get("url") or (f"/products/{handle}" if handle else None)
        available = item.get("available")
        return {
            "title": item.get(name_field),
            "price": item.get("price"),
            "image_url": image,
            "product_url": _without_tracking(link),
            "in_stock": available if isinstance(available, bool) else None,
        }


def _dig(data: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _without_tracking(link: object) -> object:
    """The product link without its query string and fragment. Shopify appends tracking parameters
    (``_pos``, ``_psq``, ``_psid``, ``_ss``) to suggest results; the page itself needs none."""
    if not isinstance(link, str):
        return link
    parts = urlsplit(link)
    return parts._replace(query="", fragment="").geturl()
