"""Text direction for Arabic (plan 10.1.2: "Arabic displays correctly").

Streamlit draws every text box left-to-right. Arabic letters still join and read right to left, but
the line hugs the left edge and a closing full stop lands on the wrong side. The browser can work
out each paragraph's direction from its first strong letter (``unicode-bidi: plaintext``), so this
one fixed rule asks it to, for the description box and other one-line inputs and for plain text.

This is the only style rule in the app. It is not a theme choice (the theme lives in
``.streamlit/config.toml``), it holds no shopper or store text, and it uses ``st.html``, not
``unsafe_allow_html``.
"""

import streamlit as st

TEXT_DIRECTION_CSS = """
<style>
input[type="text"], [data-testid="stText"] {
    unicode-bidi: plaintext;
    text-align: start;
}
</style>
"""


def apply_text_direction() -> None:
    st.html(TEXT_DIRECTION_CSS)
