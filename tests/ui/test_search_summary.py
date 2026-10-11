"""The summary of what the AI saw in the photo (owner's request 2026-10-08): the reference photo
beside one plain line per garment, built only from what the response already holds.
"""

import pytest
from streamlit.testing.v1 import AppTest

from app.components.search_summary import (
    EDIT_MAX_CHARS,
    STYLE_MAX_CHARS,
    budget_line,
    edits_line,
    item_line,
    summary_lines,
)
from app.copy import (
    CATEGORY_LABELS,
    SUMMARY_HEADING,
    SUMMARY_NO_PHOTO_COPY,
    SUMMARY_PHOTO_ALT,
    SUMMARY_PHOTO_CAPTION,
)
from tests.factories import (
    load_sample_response,
    make_budget,
    make_image_bytes,
    make_item_intent,
    make_search_response,
    make_understand_result,
)
from tests.fakes import FakePipeline
from tests.ui.conftest import InstallPipeline
from tests.ui.helpers import SEARCH_BUTTON, TEXT_BOX, markdown_bodies, plain_texts, search
from tests.ui.scenario import search_with_photo
from vga.models import Category, Gender, GenderSource, InputType

SAMPLE = load_sample_response()
PREVIEW = make_image_bytes("JPEG", (64, 48))

# The wording the owner asked for, to the letter.
OWNER_EXAMPLE = (
    "Item 1: Dresses and ethnic wear. Colour: dark teal. "
    "Style: long open-front abaya with a matching scarf. Material: crepe. "
    "Likely for: women (a guess, not applied)."
)

HOSTILE_STYLE = (
    "[click](https://evil.example) <b>bold</b> <script>alert(1)</script> **md** "
    "![p](https://evil.example/p.png) :smile: \x00\x07\x1b‮"
)
# Distinctive pieces of the string above. None may reach anything that reads markdown.
HOSTILE_FRAGMENTS = ("evil", "alert(", "smile", "<script", "[click]", "**md**", "<b>")


def abaya(**overrides: object):
    fields: dict[str, object] = {
        "category": Category.DRESSES,
        "colour": "dark teal",
        "style": "long open-front abaya with a matching scarf",
        "material": "crepe",
        "gender": Gender.WOMEN,
        "gender_source": GenderSource.INFERRED,
        "search_keywords": ["dark teal abaya"],
    }
    return make_item_intent(**{**fields, **overrides})


def summary_at(understood, preview: bytes | None = PREVIEW) -> AppTest:
    """Just the summary block, drawn on its own."""

    def script(understood, preview) -> None:
        from app.components.search_summary import render_search_summary

        render_search_summary(understood, preview)

    at = AppTest.from_function(script, args=(understood, preview)).run()
    assert not at.exception
    return at


class TestTheWording:
    def test_a_garment_reads_exactly_as_the_owner_asked(self) -> None:
        assert item_line(1, abaya()) == OWNER_EXAMPLE

    def test_a_part_the_ai_did_not_find_is_left_out_not_printed_as_none(self) -> None:
        bare = make_item_intent(
            category=Category.TOPS,
            colour=None,
            style=None,
            material=None,
            gender=None,
            gender_source=GenderSource.NONE,
        )

        assert item_line(2, bare) == "Item 2: Tops."

    def test_a_part_that_tidies_to_nothing_is_left_out_too(self) -> None:
        # `model_copy` skips validation: control characters are all the model sent for the style.
        item = abaya().model_copy(update={"style": "\x00\x1f ‮", "colour": "  "})

        assert item_line(1, item) == (
            "Item 1: Dresses and ethnic wear. Material: crepe. "
            "Likely for: women (a guess, not applied)."
        )

    @pytest.mark.parametrize("category", list(Category))
    def test_every_category_is_named_with_the_pages_own_label(self, category: Category) -> None:
        line = item_line(1, make_item_intent(category=category))

        assert line.startswith(f"Item 1: {CATEGORY_LABELS[category]}.")

    @pytest.mark.parametrize(
        ("gender", "words"),
        [(Gender.WOMEN, "women"), (Gender.MEN, "men"), (Gender.UNISEX, "unisex")],
    )
    def test_a_guessed_gender_is_called_a_guess_that_is_not_applied(
        self, gender: Gender, words: str
    ) -> None:
        item = abaya(gender=gender, gender_source=GenderSource.INFERRED)

        assert item_line(1, item).endswith(f"Likely for: {words} (a guess, not applied).")

    def test_a_gender_the_shopper_stated_or_confirmed_is_not_called_a_guess(self) -> None:
        item = abaya(gender=Gender.MEN, gender_source=GenderSource.EXPLICIT)

        line = item_line(1, item)

        assert line.endswith("For: men.")
        assert "guess" not in line

    def test_a_value_that_ends_with_a_full_stop_does_not_give_two(self) -> None:
        line = item_line(1, abaya(style="long abaya.", material=None))

        assert "Style: long abaya. Likely" in line
        assert ".." not in line

    def test_the_budget_is_said_in_its_own_currency(self) -> None:
        assert budget_line(make_budget(max_price=400, currency="AED")) == "Budget: up to 400 AED."
        assert (
            budget_line(make_budget(max_price=89.5, currency="AED")) == "Budget: up to 89.50 AED."
        )
        assert budget_line(make_budget(max_price=50, currency="KWD")) == "Budget: up to 50.000 KWD."

    def test_changes_asked_for_are_listed_and_nothing_is_said_when_there_are_none(self) -> None:
        assert (
            edits_line(["dark brown", "cheaper"]) == "Changes you asked for: dark brown; cheaper."
        )
        assert edits_line([]) is None
        assert edits_line(["\x00", "  "]) is None

    def test_the_summary_is_one_line_per_garment_then_the_budget_then_the_changes(self) -> None:
        understood = make_understand_result(
            input_type=InputType.PHOTO_TEXT,
            items=[abaya(), make_item_intent(category=Category.SHOES, colour="white")],
            budget=make_budget(max_price=400, currency="AED"),
            edits=["dark brown"],
        )

        lines = summary_lines(understood)

        assert len(lines) == 4
        assert lines[0].startswith("Item 1: Dresses and ethnic wear.")
        assert lines[1].startswith("Item 2: Shoes. Colour: white.")
        assert lines[2] == "Budget: up to 400 AED."
        assert lines[3] == "Changes you asked for: dark brown."

    def test_no_budget_and_no_changes_add_no_line(self) -> None:
        understood = make_understand_result(items=[abaya()], budget=None, edits=[])

        assert summary_lines(understood) == [OWNER_EXAMPLE]


class TestTheBlock:
    def test_it_shows_the_photo_beside_the_lines_and_says_the_ai_can_be_wrong(self) -> None:
        at = summary_at(make_understand_result(items=[abaya()]))

        assert [header.value for header in at.header] == [SUMMARY_HEADING]
        intro = [markdown.value for markdown in at.markdown]
        assert len(intro) == 1
        assert "what the AI understood" in intro[0]
        assert "can be wrong" in intro[0]
        assert plain_texts(at) == [OWNER_EXAMPLE]
        (image,) = at.image
        assert image.proto.imgs[0].caption == SUMMARY_PHOTO_CAPTION

    def test_the_picture_has_a_text_alternative_that_says_what_it_is(self) -> None:
        # Streamlit never turns a caption into the alternative, so the page passes its own.
        at = summary_at(make_understand_result(items=[abaya()]))

        (image,) = at.image
        assert image.proto.imgs[0].alt == SUMMARY_PHOTO_ALT
        assert "photo you searched with" in SUMMARY_PHOTO_ALT

    def test_without_a_preview_the_lines_stay_and_the_block_says_no_copy_could_be_made(
        self,
    ) -> None:
        at = summary_at(make_understand_result(items=[abaya()]), preview=None)

        assert not at.image
        assert plain_texts(at) == [SUMMARY_NO_PHOTO_COPY, OWNER_EXAMPLE]

    def test_four_garments_give_four_lines(self) -> None:
        items = [
            abaya(category=category) for category in Category if category is not Category.DRESSES
        ]
        assert len(items) == 4

        at = summary_at(make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=items))

        lines = plain_texts(at)
        assert [line.split(".")[0] for line in lines] == [
            f"Item {n}: {CATEGORY_LABELS[item.category]}" for n, item in enumerate(items, start=1)
        ]

    def test_one_garment_with_nothing_found_but_its_category_still_gives_a_line(self) -> None:
        bare = make_item_intent(
            category=Category.BOTTOMS, colour=None, style=None, gender=None,
            gender_source=GenderSource.NONE,
        )  # fmt: skip

        at = summary_at(make_understand_result(items=[bare]))

        assert plain_texts(at) == ["Item 1: Bottoms."]

    def test_a_very_long_style_is_cut_with_an_ellipsis(self) -> None:
        # `model_copy` skips validation: the contract refuses a style this long, the page must
        # cope if one ever got through.
        item = abaya().model_copy(update={"style": "flowing " * 100})

        (line,) = plain_texts(summary_at(make_understand_result(items=[item])))

        style = line.split("Style: ")[1].split(". Material")[0]
        assert len(style) <= STYLE_MAX_CHARS
        assert style.endswith("…")

    def test_very_long_changes_asked_for_are_cut_too(self) -> None:
        understood = make_understand_result(items=[abaya()]).model_copy(
            update={"edits": ["a much darker shade " * 20]}
        )

        lines = plain_texts(summary_at(understood))

        assert len(lines[-1].removeprefix("Changes you asked for: ")) <= EDIT_MAX_CHARS + 1

    def test_arabic_words_come_through_unchanged(self) -> None:
        item = abaya(colour="أخضر داكن", style="عباءة طويلة مفتوحة من الأمام", material="كريب")

        (line,) = plain_texts(summary_at(make_understand_result(language="ar", items=[item])))

        assert "Colour: أخضر داكن." in line
        assert "Style: عباءة طويلة مفتوحة من الأمام." in line
        assert "Material: كريب." in line

    def test_hostile_text_from_the_model_shows_as_plain_text_and_reaches_no_markdown_reader(
        self,
    ) -> None:
        # A style derives from the shopper's photo and words, so it is untrusted. `model_copy`
        # skips the contract's own cleaning, so the page's must hold on its own.
        item = abaya().model_copy(
            update={"style": HOSTILE_STYLE, "colour": "**red** <i>x</i>", "material": "[m](x)"}
        )
        understood = make_understand_result(items=[item]).model_copy(
            update={"edits": ["<img src=x onerror=alert(1)> [more](https://evil.example)"]}
        )

        at = summary_at(understood)

        (line, changes) = plain_texts(at)
        # Control characters and bidirectional overrides are gone; every other character is shown
        # exactly as sent: a link stays the characters of a link, a tag stays a tag.
        assert "[click](https://evil.example) <b>bold</b> <script>alert(1)</script> **md**" in line
        assert ":smile:" in line
        assert not any(character in line for character in "\x00\x07\x1b‮")
        assert "Colour: **red** <i>x</i>." in line
        assert "<img src=x onerror=alert(1)>" in changes
        readers = markdown_bodies(at)
        assert readers  # the heading and the intro
        for body in readers:
            for fragment in HOSTILE_FRAGMENTS:
                assert fragment not in body.lower(), f"{fragment!r} reached {body!r}"
        assert not any(node.allow_html for node in [*at.markdown, *at.caption])
        assert len(at.image) == 1  # the preview only; the hostile ![p](..) did not become one

    def test_the_block_has_a_stable_key(self) -> None:
        at = summary_at(make_understand_result(items=[abaya()]))

        assert "search_summary" in [getattr(node, "key", None) for node in at.get("container")]


class TestOnThePage:
    @pytest.fixture
    def photo(self) -> bytes:
        return make_image_bytes("JPEG", (96, 64), (10, 120, 200))

    def test_a_search_with_a_photo_shows_what_the_ai_saw_under_the_input_panel(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()

        search_with_photo(at, photo)

        assert SUMMARY_HEADING in [header.value for header in at.header]
        texts = plain_texts(at)
        assert (
            "Item 1: Outerwear. Colour: black. Style: oversized blazer. Material: wool blend. "
            "Likely for: men (a guess, not applied)."
        ) in texts
        assert (
            "Item 2: Shoes. Colour: white. Style: low-top leather sneakers. Material: leather. "
            "Likely for: men (a guess, not applied)."
        ) in texts
        assert "Budget: up to 400 AED." in texts
        assert len(at.get("image")) >= 1

    def test_the_photo_is_drawn_with_its_caption(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()

        search_with_photo(at, photo)

        captions = [img.proto.imgs[0].caption for img in at.image]
        assert captions.count(SUMMARY_PHOTO_CAPTION) == 1

    def test_a_search_with_text_only_draws_no_block(
        self, at: AppTest, pipeline: FakePipeline
    ) -> None:
        at.run()

        search(at)

        assert SUMMARY_HEADING not in [header.value for header in at.header]
        assert not [img for img in at.image if img.proto.imgs[0].caption == SUMMARY_PHOTO_CAPTION]

    def test_a_response_that_looks_like_a_photo_search_still_draws_nothing_for_a_text_search(
        self, at: AppTest, install_pipeline: InstallPipeline
    ) -> None:
        # The sample answers every request with an outfit-photo reading. What decides is whether
        # the search used a photo, not what the response says about its input.
        install_pipeline(SAMPLE.model_copy(update={}))
        at.run()

        search(at)

        assert SAMPLE.understood.input_type is InputType.OUTFIT_PHOTO
        assert SUMMARY_HEADING not in [header.value for header in at.header]

    def test_the_block_goes_when_a_search_without_a_photo_finishes(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        at.run()
        at.text_input(key=TEXT_BOX).set_value("black blazer").run()
        search_with_photo(at, photo)
        assert SUMMARY_HEADING in [header.value for header in at.header]

        at.button(key=SEARCH_BUTTON).click().run()  # the same description, now without a photo

        assert pipeline.calls[-1].req.image is None
        assert SUMMARY_HEADING not in [header.value for header in at.header]

    def test_a_reading_with_no_budget_has_no_budget_line(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        install_pipeline(make_search_response(understood=make_understand_result(budget=None)))
        at.run()

        search_with_photo(at, photo)

        assert not [text for text in plain_texts(at) if text.startswith("Budget:")]

    def test_hostile_model_text_in_a_photo_search_reaches_no_markdown_reader_anywhere_on_the_page(
        self, at: AppTest, install_pipeline: InstallPipeline, photo: bytes
    ) -> None:
        item = abaya().model_copy(update={"style": HOSTILE_STYLE})
        understood = make_understand_result(input_type=InputType.PHOTO_TEXT, items=[item])
        install_pipeline(make_search_response(understood=understood))
        at.run()

        search_with_photo(at, photo)

        assert not at.exception
        assert any("<script>alert(1)</script>" in text for text in plain_texts(at))
        for body in markdown_bodies(at):
            for fragment in HOSTILE_FRAGMENTS:
                assert fragment not in body.lower(), f"{fragment!r} reached {body!r}"

    def test_the_text_direction_rule_is_still_the_only_style_rule_and_the_lines_are_plain_text(
        self, at: AppTest, pipeline: FakePipeline, photo: bytes
    ) -> None:
        # The rule reaches plain text elements (stText), which is how every summary line is drawn,
        # so an Arabic line lines up like the rest of the page (plan 10.1.2).
        at.run()

        search_with_photo(at, photo)

        (rule,) = [str(node.proto.body) for node in at.get("html")]
        assert 'data-testid="stText"' in rule
        assert "unicode-bidi: plaintext" in rule
        assert "<script" not in rule.lower()
        summary_lines_shown = [
            t for t in plain_texts(at) if t.startswith("Item ") and "Colour:" in t
        ]
        assert len(summary_lines_shown) == len(SAMPLE.understood.items)
