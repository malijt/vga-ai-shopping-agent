"""Search URL builder (plan 6.3.2): a store's ``{query}`` template filled with an encoded query."""

import unicodedata
from urllib.parse import quote

from vga.models import StoreConfig

MAX_QUERY_CHARS = 200
"""Keywords are at most 80 characters (``ItemIntent``); this only stops an absurd query."""


def clean_query(query: str) -> str:
    """The query as it is sent: Unicode-normalised, control characters removed, runs of white
    space collapsed to one space. Raises ``ValueError`` when nothing is left."""
    text = unicodedata.normalize("NFC", query)
    text = "".join(" " if ch.isspace() else ch for ch in text if unicodedata.category(ch) != "Cc")
    text = " ".join(text.split())[:MAX_QUERY_CHARS].strip()
    if not text:
        msg = "the search query is empty"
        raise ValueError(msg)
    return text


def build_search_url(store: StoreConfig, query: str) -> str:
    """Fill the store's ``search_url_template`` with ``query``.

    The query is percent-encoded as UTF-8 with nothing left safe, so spaces become ``%20``, ``&``
    becomes ``%26`` and Arabic text becomes its ``%XX`` bytes. Square brackets written in the
    template itself (Shopify's ``resources[type]=product``) are percent-encoded too, so the URL
    that is sent is the one the qualification reports saw working.
    """
    encoded = quote(clean_query(query), safe="")
    url = store.search_url_template.replace("{query}", encoded)
    return url.replace("[", "%5B").replace("]", "%5D")
