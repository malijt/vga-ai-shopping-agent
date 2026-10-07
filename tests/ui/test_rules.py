"""Rules that cannot be seen on one page run: the single theme source, and what the app's source
must never contain (CLAUDE.md "Rendering", the UI rules of plan Phase 10, assumption A12)."""

import ast
import re
import tomllib
from pathlib import Path

import pytest
from app.components.input_panel import MAX_PHOTO_MB

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
APP_FILES = sorted(APP_DIR.rglob("*.py"))
CONFIG = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))

EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿️]")


def contrast(foreground: str, background: str) -> float:
    """WCAG contrast ratio of two ``#RRGGBB`` colours."""

    def luminance(colour: str) -> float:
        channels = [int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class TestTheme:
    theme = CONFIG["theme"]

    def test_it_is_the_light_theme_with_one_accent_colour(self) -> None:
        assert self.theme["base"] == "light"
        assert set(self.theme) == {
            "base",
            "primaryColor",
            "backgroundColor",
            "secondaryBackgroundColor",
            "textColor",
        }

    def test_the_accent_is_readable_as_button_fill_and_as_link_text(self) -> None:
        accent = self.theme["primaryColor"]

        assert contrast("#FFFFFF", accent) >= 4.5  # white label on an accent button
        assert contrast(accent, self.theme["backgroundColor"]) >= 4.5
        assert contrast(accent, self.theme["secondaryBackgroundColor"]) >= 4.5

    def test_body_text_is_readable_on_both_backgrounds(self) -> None:
        text = self.theme["textColor"]

        assert contrast(text, self.theme["backgroundColor"]) >= 4.5
        assert contrast(text, self.theme["secondaryBackgroundColor"]) >= 4.5

    def test_error_details_never_reach_the_browser(self) -> None:
        # In Streamlit 1.65 `false` is a deprecated alias of "stacktrace", which would show it.
        assert CONFIG["client"]["showErrorDetails"] == "none"

    def test_the_server_upload_limit_matches_the_uploader(self) -> None:
        assert CONFIG["server"]["maxUploadSize"] == MAX_PHOTO_MB

    def test_usage_statistics_are_off(self) -> None:
        assert CONFIG["browser"]["gatherUsageStats"] is False


class TestSourceRules:
    @pytest.mark.parametrize("path", APP_FILES, ids=lambda p: str(p.relative_to(APP_DIR)))
    def test_nothing_is_rendered_as_trusted_html(self, path: Path) -> None:
        source = path.read_text(encoding="utf-8")

        assert not re.search(r"unsafe_allow_html\s*=\s*True", source)

    def test_only_the_text_direction_module_uses_html(self) -> None:
        users = [p.name for p in APP_FILES if "st.html(" in p.read_text(encoding="utf-8")]

        assert users == ["direction.py"]

    @pytest.mark.parametrize("path", APP_FILES, ids=lambda p: str(p.relative_to(APP_DIR)))
    def test_nothing_can_show_a_stack_trace_or_write_untrusted_text_as_markdown(
        self, path: Path
    ) -> None:
        source = path.read_text(encoding="utf-8")

        for forbidden in ("st.exception(", "st.write(", "import traceback", "st.json("):
            assert forbidden not in source

    @pytest.mark.parametrize("path", APP_FILES, ids=lambda p: str(p.relative_to(APP_DIR)))
    def test_no_emoji_is_used_as_an_icon(self, path: Path) -> None:
        assert not EMOJI.search(path.read_text(encoding="utf-8"))

    def test_only_the_runner_reaches_the_pipeline(self) -> None:
        reaching = [
            p.name
            for p in APP_FILES
            if re.search(
                r"vga\.pipeline|tests\.fakes|FakePipeline|asyncio|get_pipeline",
                p.read_text(encoding="utf-8"),
            )
        ]

        assert reaching == ["runner.py"]

    def test_no_widget_is_created_without_a_stable_key(self) -> None:
        widgets = {
            "button",
            "file_uploader",
            "text_area",
            "text_input",
            "number_input",
            "selectbox",
            "radio",
            "link_button",
            "expander",
        }
        missing: list[str] = []
        for path in APP_FILES:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "st"
                    and node.func.attr in widgets
                    and "key" not in {keyword.arg for keyword in node.keywords}
                ):
                    missing.append(f"{path.name}:{node.lineno} st.{node.func.attr}")

        assert not missing


def test_the_page_turns_error_details_off_itself_so_a_wrong_start_folder_cannot_show_a_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("VGA_UI_FIXTURE", "1")
    st.set_option("client.showErrorDetails", "full")  # as if config.toml had not been found

    AppTest.from_file(str(APP_DIR / "main.py"), default_timeout=20).run()

    assert st.get_option("client.showErrorDetails") == "none"
