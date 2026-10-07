"""The ``shopify`` strategy (plan 6.4.2): Shopify's predictive-search endpoint.

The store file's ``search_url_template`` is the endpoint, with the brackets as Shopify writes them
(the URL builder percent-encodes them)::

    https://ohpolly.ae/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10

The response is ``{"resources": {"results": {"products": [...]}}}``, at most 10 products. Each
product gives ``title``, ``price`` (a string such as ``"535.00"``), ``image`` (an absolute CDN
URL), ``url`` (relative, with tracking parameters), ``available`` (a boolean), plus ``vendor``,
``type`` and ``tags``. ``vendor`` is mapped only through ``name_field``; ``type`` and ``tags`` are
read only for the product's gender (``gender_fields``). The response has **no currency**: the store
file's ``currency`` is used.

Options (all optional)::

    options:
      name_field: title      # or "vendor"
      image_width: 400       # a positive whole number, or null for "leave the image URL alone"
      gender_fields: [type, tags]   # which fields say who a product is for; [] turns it off

``name_field`` says which response field holds the readable product name. It is ``title`` for
nearly every store; The Bear House puts a style code in ``title`` ("BOALI") and the real name in
``vendor`` ("Olive Checked Slim Fit Casual Shirt").

``image_width`` (default **400**) sets, or replaces, the ``width`` query parameter of each image
URL and keeps the others (``v=...``). The Shopify CDN then serves a resized image: measured on a
real Giordano image, 108,026 bytes became 20,243. The originals can be several MB, which is over the
response size cap, and the app shows and ranks thumbnails, so nothing needs more. ``null`` leaves
the URL as the store gave it.

``gender_fields`` (default **[type, tags]**) lists the record fields that may say who the product is
for; ``[]`` turns the reading off. Several stores sell for men and women and say which in these
fields: Sacoor Brothers writes ``type`` as "Winter 2025 / Man / Blazer", Nautica tags "Mens" or
"Women", Maison D'Vie tags "Men" or "Women". Titles often say nothing ("Nelson Pant - Black"). The
rule, applied to ``Product.gender``:

- A field "names" a gender when it holds one of these words, whole and in any case (apostrophes,
  hyphens, slashes and commas end a word, so "Men's", "womens-clothing-sale-all" and "Jackets for
  men" all work, and "women" is never read as "men"): ``man``, ``men``, ``mens`` for men;
  ``woman``, ``women``, ``womens``, ``ladies`` for women; ``unisex``. "Man-made" is not a cue.
- The fields are read **in the order listed** and the first one that names a gender decides, so
  ``type`` outranks ``tags``. This matters: Sacoor tags women's suits "Formalwear Men" while their
  ``type`` says "Woman", and pooling the two would leave them unlabelled.
- Inside the deciding field, "unisex" wins; otherwise men and women together mean the field
  contradicts itself, and the product's gender is ``None`` (unknown). A product whose listed fields
  name nothing is ``None`` too. ``None`` is not a verdict: the ranker then falls back to the title.

``fields`` is not used: the mapping is fixed.
"""

import json
import re
from typing import Any
from urllib.parse import urlsplit

from vga.models import Gender, StoreConfig, StrategyConfig
from vga.stores.extractors.base import ExtractionError
from vga.stores.normalise import RawRecord

NAME_FIELDS = ("title", "vendor")
DEFAULT_IMAGE_WIDTH = 400
GENDER_FIELDS = ("type", "tags")
"""The record fields ``gender_fields`` may name."""
DEFAULT_GENDER_FIELDS = GENDER_FIELDS
OPTIONS = ("name_field", "image_width", "gender_fields")

_LETTERS = re.compile(r"[^\W\d_]+")
"""A run of letters. Apostrophes (straight or curly), hyphens, slashes, commas, digits and
underscores all end a word, so "women's" is "women" + "s" and never contains the word "men"."""
_MAN_MADE = re.compile(r"\bman[\s-]+made\b")
_CUES: dict[str, Gender] = {
    "man": Gender.MEN,
    "men": Gender.MEN,
    "mens": Gender.MEN,
    "woman": Gender.WOMEN,
    "women": Gender.WOMEN,
    "womens": Gender.WOMEN,
    "ladies": Gender.WOMEN,
    "unisex": Gender.UNISEX,
}


class ShopifyExtractor:
    name = "shopify"

    def validate(self, strategy: StrategyConfig) -> None:
        if strategy.fields:
            msg = (
                "the shopify strategy has a fixed field mapping; remove 'fields' "
                f"(got {sorted(strategy.fields)})"
            )
            raise ValueError(msg)
        unknown = sorted(set(strategy.options) - set(OPTIONS))
        if unknown:
            msg = f"unknown option(s) {unknown} for the shopify strategy; allowed: {list(OPTIONS)}"
            raise ValueError(msg)
        name_field = strategy.options.get("name_field", "title")
        if name_field not in NAME_FIELDS:
            msg = f"options.name_field must be one of {list(NAME_FIELDS)}, got {name_field!r}"
            raise ValueError(msg)
        _image_width(strategy)
        _gender_fields(strategy)

    def extract(self, body: str, store: StoreConfig, strategy: StrategyConfig) -> list[RawRecord]:
        name_field = str(strategy.options.get("name_field", "title"))
        image_width = _image_width(strategy)
        gender_fields = _gender_fields(strategy)
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
        return [
            self._record(item, name_field, image_width, gender_fields)
            for item in products
            if isinstance(item, dict)
        ]

    @staticmethod
    def _record(
        item: dict[str, Any],
        name_field: str,
        image_width: int | None,
        gender_fields: tuple[str, ...],
    ) -> RawRecord:
        featured = item.get("featured_image")
        image = item.get("image") or (featured.get("url") if isinstance(featured, dict) else None)
        handle = item.get("handle")
        link = item.get("url") or (f"/products/{handle}" if handle else None)
        available = item.get("available")
        return {
            "title": item.get(name_field),
            "price": item.get("price"),
            "image_url": _with_width(image, image_width),
            "product_url": _without_tracking(link),
            "in_stock": available if isinstance(available, bool) else None,
            "gender": _gender(item, gender_fields),
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


def _image_width(strategy: StrategyConfig) -> int | None:
    """The ``image_width`` option: 400 when absent, ``None`` when set to null, else a positive
    whole number. Raises ``ValueError`` for anything else."""
    if "image_width" not in strategy.options:
        return DEFAULT_IMAGE_WIDTH
    width = strategy.options["image_width"]
    if width is None:
        return None
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        msg = f"options.image_width must be a positive whole number or null, got {width!r}"
        raise ValueError(msg)
    return width


def _gender_fields(strategy: StrategyConfig) -> tuple[str, ...]:
    """The ``gender_fields`` option: ``type`` then ``tags`` when absent, else a list of those two
    names (each at most once, in the order that decides). Raises ``ValueError`` for anything
    else."""
    if "gender_fields" not in strategy.options:
        return DEFAULT_GENDER_FIELDS
    value = strategy.options["gender_fields"]
    allowed = list(GENDER_FIELDS)
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        msg = f"options.gender_fields must be a list of field names from {allowed}, got {value!r}"
        raise ValueError(msg)
    unknown = sorted(set(value) - set(GENDER_FIELDS))
    if unknown:
        msg = f"options.gender_fields names unknown field(s) {unknown}; allowed: {allowed}"
        raise ValueError(msg)
    if len(set(value)) != len(value):
        msg = f"options.gender_fields names a field more than once: {value!r}"
        raise ValueError(msg)
    return tuple(value)


def _cues(value: object) -> set[Gender]:
    """The genders that ``value`` (text, or a list of texts such as ``tags``) names."""
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = "\n".join(part for part in value if isinstance(part, str))
    else:
        return set()
    words = _LETTERS.findall(_MAN_MADE.sub(" ", text.lower()))
    return {_CUES[word] for word in words if word in _CUES}


def _gender(item: dict[str, Any], fields: tuple[str, ...]) -> Gender | None:
    """Who the product is for, from the first of ``fields`` that names a gender; see the module
    docstring. ``None`` when none does, or when the deciding field names both men and women."""
    for field in fields:
        cues = _cues(item.get(field))
        if not cues:
            continue
        if Gender.UNISEX in cues:
            return Gender.UNISEX
        return next(iter(cues)) if len(cues) == 1 else None
    return None


def _with_width(image: object, width: int | None) -> object:
    """``image`` with its ``width`` query parameter set to ``width`` (replaced in place if it is
    there, else added at the end). Other parameters, such as ``v=``, are left exactly as written.
    Anything that is not a non-empty string, or a ``None`` width, is returned unchanged."""
    if width is None or not isinstance(image, str) or not image:
        return image
    parts = urlsplit(image)
    segments = [segment for segment in parts.query.split("&") if segment]
    out: list[str] = []
    replaced = False
    for segment in segments:
        if segment.partition("=")[0] == "width":
            if not replaced:
                out.append(f"width={width}")
                replaced = True
            continue  # a repeated width parameter is dropped
        out.append(segment)
    if not replaced:
        out.append(f"width={width}")
    return parts._replace(query="&".join(out)).geturl()
