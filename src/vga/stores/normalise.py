"""From raw store records to validated ``Product``s (plan 6.5.1 and 6.5.2).

An extractor hands over *raw* records: dictionaries of text exactly as the store wrote it. This
module is the one place that decides whether a record becomes a ``Product``. A record is dropped,
with a counted and logged reason, when:

- a required field is missing (title, price, image, link; PRD R6);
- the price is not one of the formats we have seen, is zero or negative, or is written in a
  currency other than the store's;
- a link is not https, not valid, or not on the store's ``allowed_hosts`` (relative links are made
  absolute against the page they came from first); a *product* link must also be on the store's
  own site, never on a shared image host that ``allowed_hosts`` lists for the thumbnails;
- it repeats an earlier record: the same ``product_url``, or the same normalised title at the same
  price (stores list one shirt under several handles, and the per-store cap would be spent on
  repeats).

Store data is untrusted: titles are reduced to single-spaced text and never interpreted.
"""

import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urldefrag, urljoin

from pydantic import ValidationError

from vga.fetch.allowlist import belongs_to_store_site, check_url
from vga.fetch.errors import UrlNotAllowedError
from vga.log import get_logger
from vga.models import Gender, Product, StoreConfig
from vga.stores.prices import PriceFormatError, parse_price

log = get_logger(__name__)

RawRecord = Mapping[str, Any]
"""One product as an extractor read it: keys are ``Product`` field names (``title``, ``price``,
``image_url``, ``product_url``, ``colour``, ``in_stock``, ``gender``), values are the store's own
text (``gender`` is already a ``Gender``, or ``None`` when the store does not say)."""


class DropReason(StrEnum):
    """Why a record did not become a product. The values are the keys of
    ``StoreResult.dropped``."""

    MISSING_TITLE = "missing_title"
    MISSING_PRICE = "missing_price"
    MISSING_IMAGE_URL = "missing_image_url"
    MISSING_PRODUCT_URL = "missing_product_url"
    UNKNOWN_PRICE_FORMAT = "unknown_price_format"
    CURRENCY_MISMATCH = "currency_mismatch"
    PRICE_NOT_POSITIVE = "price_not_positive"
    IMAGE_URL_NOT_ALLOWED = "image_url_not_allowed"
    PRODUCT_URL_NOT_ALLOWED = "product_url_not_allowed"
    INVALID_RECORD = "invalid_record"
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_TITLE_PRICE = "duplicate_title_price"


@dataclass
class NormalisedBatch:
    products: list[Product] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    examined: int = 0
    """How many raw records were looked at (kept plus dropped)."""


def normalise_title(title: str) -> str:
    """A title as used to compare products: Unicode-folded, lower case, single-spaced."""
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def dedupe_products(products: Sequence[Product]) -> tuple[list[Product], dict[str, int]]:
    """Keep the first of each product. Two products are the same when they share a ``product_url``
    or share a normalised title *and* a price. Returns the survivors in order and the counts of
    what was collapsed."""
    seen_urls: set[str] = set()
    seen_title_price: set[tuple[str, float]] = set()
    kept: list[Product] = []
    collapsed: Counter[str] = Counter()
    for product in products:
        if product.product_url in seen_urls:
            collapsed[DropReason.DUPLICATE_URL.value] += 1
            continue
        title_price = (normalise_title(product.title), product.price)
        if title_price in seen_title_price:
            collapsed[DropReason.DUPLICATE_TITLE_PRICE.value] += 1
            continue
        seen_urls.add(product.product_url)
        seen_title_price.add(title_price)
        kept.append(product)
    return kept, dict(collapsed)


def normalise_records(
    records: Sequence[RawRecord], store: StoreConfig, base_url: str
) -> NormalisedBatch:
    """Validate ``records`` read from ``base_url`` for ``store``; see the module docstring."""
    dropped: Counter[str] = Counter()
    candidates: list[Product] = []
    for record in records:
        outcome = _to_product(record, store, base_url)
        if isinstance(outcome, DropReason):
            dropped[outcome.value] += 1
            log.info(
                "record dropped",
                extra={
                    "store": store.id,
                    "reason": outcome.value,
                    "title": _preview(record.get("title")),
                    "price": _preview(record.get("price")),
                },
            )
        else:
            candidates.append(outcome)

    products, collapsed = dedupe_products(candidates)
    if collapsed:
        dropped.update(collapsed)
        log.info(
            "repeated products collapsed",
            extra={
                "store": store.id,
                "collapsed": sum(collapsed.values()),
                "reasons": collapsed,
                "kept": len(products),
            },
        )
    return NormalisedBatch(products=products, dropped=dict(dropped), examined=len(records))


# --------------------------------------------------------------------------------------------


def _preview(value: object) -> str:
    return str(value)[:80]


def _clean_text(value: object) -> str:
    """Single-spaced text without control characters, or ``""`` when it is not text."""
    if not isinstance(value, str):
        return ""
    printable = "".join(ch for ch in value if unicodedata.category(ch) != "Cc" or ch.isspace())
    return " ".join(printable.split())


def _checked_url(
    raw: object,
    base_url: str,
    store: StoreConfig,
    missing: DropReason,
    refused: DropReason,
    *,
    own_site_only: bool = False,
) -> str | DropReason:
    """An absolute https URL on one of the store's hosts, or the reason it is not one.

    With ``own_site_only`` the host must also belong to the store's own site (see
    ``belongs_to_store_site``): a link the shopper is sent to is the store's page, and
    ``allowed_hosts`` also lists hosts, such as ``cdn.shopify.com``, that only serve its files.
    """
    text = _clean_text(raw)
    if not text:
        return missing
    url, _fragment = urldefrag(urljoin(base_url, text))
    try:
        host = check_url(url, store.allowed_hosts)
        if own_site_only and not belongs_to_store_site(store, host):
            raise UrlNotAllowedError(
                detail=f"host {host!r} is not part of the store's own site: {url[:200]}"
            )
    except UrlNotAllowedError as exc:
        log.info(
            "record link refused",
            extra={"store": store.id, "reason": refused.value, "detail": exc.detail},
        )
        return refused
    return url


def _to_product(record: RawRecord, store: StoreConfig, base_url: str) -> Product | DropReason:
    title = _clean_text(record.get("title"))
    if not title:
        return DropReason.MISSING_TITLE

    raw_price = record.get("price")
    if raw_price is None or (isinstance(raw_price, str) and not raw_price.strip()):
        return DropReason.MISSING_PRICE
    try:
        parsed = parse_price(raw_price)
    except PriceFormatError as exc:
        log.warning(
            "price format not recognised; record dropped",
            extra={"store": store.id, "detail": str(exc)},
        )
        return DropReason.UNKNOWN_PRICE_FORMAT
    if parsed.currency is not None and parsed.currency != store.currency:
        return DropReason.CURRENCY_MISMATCH
    if parsed.amount <= 0:
        return DropReason.PRICE_NOT_POSITIVE

    image_url = _checked_url(
        record.get("image_url"),
        base_url,
        store,
        DropReason.MISSING_IMAGE_URL,
        DropReason.IMAGE_URL_NOT_ALLOWED,
    )
    if isinstance(image_url, DropReason):
        return image_url
    product_url = _checked_url(
        record.get("product_url"),
        base_url,
        store,
        DropReason.MISSING_PRODUCT_URL,
        DropReason.PRODUCT_URL_NOT_ALLOWED,
        own_site_only=True,
    )
    if isinstance(product_url, DropReason):
        return product_url

    colour = _clean_text(record.get("colour")) or None
    in_stock = record.get("in_stock")
    gender = record.get("gender")
    try:
        return Product(
            title=title,
            price=parsed.amount,
            currency=store.currency,
            image_url=image_url,
            product_url=product_url,
            store=store.display_name,
            colour=colour if colour is None or len(colour) <= 60 else None,
            in_stock=in_stock if isinstance(in_stock, bool) else None,
            gender=gender if isinstance(gender, Gender) else None,
        )
    except ValidationError as exc:
        log.warning(
            "record failed validation; dropped",
            extra={"store": store.id, "detail": str(exc.errors()[0]["loc"])},
        )
        return DropReason.INVALID_RECORD
