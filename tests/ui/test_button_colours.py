"""Colour on the buttons (owner's request 2026-10-08).

The project allows one accent colour, set in ``.streamlit/config.toml``, and no custom CSS. So the
buttons that are the main action of their block use Streamlit's own ``type="primary"``, which the
theme fills with that accent; the quieter ones stay ``secondary``. AppTest exposes the type of a
button and of a link button in its element.
"""

import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.factories import load_sample_response
from tests.fakes import FakePipeline
from tests.ui.helpers import link_buttons, search

SAMPLE = load_sample_response()
CONFIG = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"


def button_types(at: AppTest) -> dict[str, str]:
    """The type of every button on the page, by key."""
    return {button.key: button.proto.type for button in at.button}


class TestTheMainActionOfEachBlockIsFilled:
    def test_search_stores_is_primary(self, at: AppTest) -> None:
        at.run()

        assert button_types(at)["search_button"] == "primary"

    def test_apply_changes_and_search_again_is_primary(self, results_at: AppTest) -> None:
        assert button_types(results_at)["chips_apply"] == "primary"

    def test_the_gender_answers_women_and_men_are_primary(self, results_at: AppTest) -> None:
        types = button_types(results_at)

        assert (types["gender_women"], types["gender_men"]) == ("primary", "primary")

    def test_every_view_product_link_is_primary(self, results_at: AppTest) -> None:
        links = link_buttons(results_at)

        assert len(links) == len(SAMPLE.products)
        assert {button.proto.type for button in links} == {"primary"}


class TestTheQuieterButtonsStayPlain:
    def test_reset_to_detected_and_show_both_are_secondary(self, results_at: AppTest) -> None:
        types = button_types(results_at)

        assert (types["chips_reset"], types["gender_both"]) == ("secondary", "secondary")

    def test_the_example_requests_on_the_first_screen_are_secondary(self, at: AppTest) -> None:
        at.run()

        examples = {
            key: kind for key, kind in button_types(at).items() if key.startswith("example_")
        }

        assert len(examples) == 3
        assert set(examples.values()) == {"secondary"}

    def test_no_other_button_on_the_page_is_primary(self, results_at: AppTest) -> None:
        primary = {key for key, kind in button_types(results_at).items() if kind == "primary"}

        assert primary == {"search_button", "chips_apply", "gender_women", "gender_men"}


class TestNoColourComesFromAnywhereElse:
    def test_the_only_style_rule_is_still_the_text_direction_rule(
        self, results_at: AppTest
    ) -> None:
        bodies = [str(node.proto.body) for node in results_at.get("html")]

        assert len(bodies) == 1
        assert "unicode-bidi" in bodies[0]
        assert "color" not in bodies[0].lower()

    def test_the_theme_has_one_accent_colour_and_the_buttons_take_it(self) -> None:
        theme = tomllib.loads(CONFIG.read_text())["theme"]

        assert theme["primaryColor"] == "#0E6E7E"


def test_a_button_stays_primary_after_a_search_again(at: AppTest, pipeline: FakePipeline) -> None:
    at.run()
    search(at)

    at.button(key="chips_apply").click().run()

    assert button_types(at)["chips_apply"] == "primary"
    assert {button.proto.type for button in link_buttons(at)} == {"primary"}
