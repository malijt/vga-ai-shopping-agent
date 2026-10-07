"""The helpers that tidy untrusted text for display (``app.safe_text``)."""

import re

import pytest

from app.safe_text import ELLIPSIS, clamp, format_price, label_fragment, plain_text

HOSTILE = [
    "<script>alert(1)</script>",
    "**bold** _it_ ~~gone~~ `code`",
    "[click](https://evil.example)",
    "![pic](https://evil.example/p.png)",
    ":smile: :red[coloured] :material/home:",
    "www.evil.example https://evil.example mail@evil.example",
    "# heading\n- list\n> quote\n1. one",
    "a|b\n---|---",
    "back\\slash &amp; &#x41; <b>",
    "line1\nline2\u202eoverride\u2066x",
]


class TestPlainText:
    def test_it_leaves_markup_untouched_because_the_text_element_shows_it_literally(self) -> None:
        single_line = [text for text in HOSTILE if "\n" not in text and "\u202e" not in text]

        assert single_line
        for text in single_line:
            assert plain_text(text, max_chars=500) == text

    def test_it_collapses_whitespace_and_drops_control_and_bidi_override_characters(self) -> None:
        assert plain_text("a\n\n  b\t\tc\x00d\u202ee\u2066f") == "a b cdef"

    def test_it_keeps_arabic_and_the_joiners_arabic_and_emoji_text_use(self) -> None:
        text = "جاكيت\u200c جلد \u200f أسود"

        assert plain_text(text) == " ".join(text.split())
        assert "\u200c" in plain_text(text)
        assert "\u200f" in plain_text(text)

    def test_nothing_gives_an_empty_string(self) -> None:
        assert plain_text(None) == ""
        assert plain_text("") == ""

    def test_long_text_is_cut_with_an_ellipsis_within_the_limit(self) -> None:
        cleaned = plain_text("word " * 100, max_chars=50)

        assert len(cleaned) <= 50
        assert cleaned.endswith(ELLIPSIS)

    def test_a_long_unbroken_string_is_cut_too(self) -> None:
        assert len(plain_text("A" * 1000, max_chars=120)) == 120


class TestClamp:
    def test_short_text_is_unchanged(self) -> None:
        assert clamp("short", 10) == "short"

    def test_text_exactly_at_the_limit_is_unchanged(self) -> None:
        assert clamp("x" * 10, 10) == "x" * 10

    def test_longer_text_ends_with_an_ellipsis_at_exactly_the_limit(self) -> None:
        assert clamp("x" * 11, 10) == "x" * 9 + ELLIPSIS


class TestLabelFragment:
    """The store name inside "View product on ...": a button label that reads markdown."""

    SAFE_CHARACTERS = re.compile(r"^[\w\s'\-…]*$")
    MARKUP_CHARACTERS = '*_~`[]()<>\\!:&#|@/.=+{}"%$^'

    @pytest.mark.parametrize("hostile", HOSTILE)
    def test_nothing_that_could_start_markup_survives(self, hostile: str) -> None:
        cleaned = label_fragment(hostile)

        assert self.SAFE_CHARACTERS.match(cleaned)
        assert not any(char in cleaned for char in self.MARKUP_CHARACTERS)

    def test_ordinary_names_are_unchanged(self) -> None:
        for name in ("Souq Atelier", "Level Shoes", "6thStreet", "Namshi", "Max Fashion"):
            assert label_fragment(name) == name

    def test_arabic_and_hyphenated_names_survive(self) -> None:
        assert label_fragment("متجر الأزياء") == "متجر الأزياء"
        assert label_fragment("Club L London-UAE") == "Club L London-UAE"

    def test_a_name_that_is_all_markup_becomes_empty_so_the_caller_can_use_a_fallback(self) -> None:
        assert label_fragment("<>[]()**") == ""

    def test_nothing_gives_an_empty_string(self) -> None:
        assert label_fragment(None) == ""

    def test_a_long_name_is_cut(self) -> None:
        assert len(label_fragment("Store " * 50)) <= 40


class TestFormatPrice:
    @pytest.mark.parametrize(
        ("value", "shown"),
        [(129.0, "129"), (1250.0, "1,250"), (2400.0, "2,400"), (89.5, "89.50"), (0.99, "0.99")],
    )
    def test_whole_amounts_have_no_decimals_and_thousands_are_grouped(
        self, value: float, shown: str
    ) -> None:
        assert format_price(value) == shown
