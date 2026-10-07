"""One result card (plan 10.2.3, PRD R10).

Every string that came from a store (title, store name, colour, reason) is shown with ``st.text``,
which does no markdown or HTML parsing. The link goes only to ``Product.product_url`` and opens in
a new tab (``st.link_button`` does that). See ``app.safe_text`` for the one place a store name
enters a label that reads markdown.

Limit: whether the picture loads is decided by the browser, not by this code, so a picture that
fails to load shows the browser's own broken-image mark with the product title as its alt text.
The "No image available" placeholder below covers a missing or unusable image address.
"""

import streamlit as st

from app.copy import FLAG_TEXT, NOT_LISTED, PLACEHOLDER_NO_IMAGE
from app.safe_text import format_price, label_fragment, plain_text
from vga.models import ScoredProduct

TITLE_MAX_CHARS = 120
STORE_MAX_CHARS = 60
REASON_MAX_CHARS = 200
COLOUR_MAX_CHARS = 60


def _is_https(url: str) -> bool:
    return url.startswith("https://")


def render_result_card(scored: ScoredProduct, *, key: str) -> None:
    """Draw one product. ``key`` makes the link button's identity stable and unique."""
    product = scored.product
    title = plain_text(product.title, TITLE_MAX_CHARS)
    store = plain_text(product.store, STORE_MAX_CHARS)

    with st.container(border=True, key=f"card_{key}"):
        # Only https addresses go to st.image: given a bare path it would read a local file.
        if product.image_url and _is_https(product.image_url):
            st.image(product.image_url, alt=title, width="stretch")
        else:
            st.text(PLACEHOLDER_NO_IMAGE)

        st.text(title)
        st.markdown(f"**{format_price(product.price)} {product.currency}**")
        details = [
            f"Store: {store}",
            f"Colour: {plain_text(product.colour, COLOUR_MAX_CHARS) or NOT_LISTED}",
        ]
        details.extend(FLAG_TEXT[flag] for flag in scored.flags)
        st.text("\n".join(details))
        if scored.reason:
            st.text(plain_text(scored.reason, REASON_MAX_CHARS))

        if _is_https(product.product_url):
            name = label_fragment(product.store) or "the store"
            st.link_button(
                f"View product on {name}",
                product.product_url,
                key=f"view_{key}",
                width="stretch",
            )
        else:
            st.text("The store link is not available.")
