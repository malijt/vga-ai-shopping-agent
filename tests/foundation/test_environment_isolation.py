"""The default test suite never reads the developer's real ``.env`` and never sees real credentials.

A real ``.env`` once made every test under ``tests/ui`` fail: the page calls ``load_settings()``,
which copied the file's ``OPENAI_MODEL`` (and the real ``OPENAI_API_KEY``) into ``os.environ``.
``tests/conftest.py`` now hides the file and scrubs ``OPENAI_*`` / ``VGA_*`` for every test that is
not marked ``live``.

The proof runs three small tests in a separate pytest process (a nested in-process session would
unload numpy and break later tests), with a hostile ``.env``, built in a temporary folder, standing
in at the loader's default location. They are run twice: without ``tests/conftest.py`` they must
fail (so the hostile file really does bite), and with it they must pass. No ``.env`` is ever
created in the repository.
"""

import os
from pathlib import Path

import pytest

from app import runner
from vga import settings as settings_module

ROOT = Path(__file__).resolve().parents[2]
CONFTEST = ROOT / "tests" / "conftest.py"
APP_PATH = ROOT / "app" / "main.py"

# Low-entropy and built at run time, so no secret scanner mistakes it for a real key.
FAKE_KEY = "fake-key-" + "0" * 12
HOSTILE_DOTENV = f"OPENAI_MODEL=not-a-real-alias\nVGA_UI_FIXTURE=0\nOPENAI_API_KEY={FAKE_KEY}\n"

NESTED_INI = (
    f"[pytest]\npythonpath = {ROOT / 'src'} {ROOT}\nasyncio_default_fixture_loop_scope = function\n"
)
NESTED_ARGS = ("-q", "-p", "no:cacheprovider", "--tb=line")
"""``--tb=line`` on purpose: a long traceback prints the arguments of every frame, and in the run
without isolation that is the whole real environment."""

INNER_TESTS = """
import os

import pytest
from streamlit.testing.v1 import AppTest

from app import runner
from vga.errors import ConfigError
from vga.settings import DEFAULT_SETTINGS_PATH, load_settings
from vga.understand import create_openai_client


def test_default_settings_come_from_the_yaml_not_the_dotenv():
    settings = load_settings()

    assert settings == load_settings(DEFAULT_SETTINGS_PATH, env={})
    assert settings.ui_fixture is False
    assert "OPENAI_MODEL" not in os.environ


def test_no_key_reaches_the_environment_and_the_client_does_not_find_one():
    with pytest.raises(ConfigError):
        create_openai_client()  # reads .env through load_dotenv() with no argument: no key found

    assert "OPENAI_API_KEY" not in os.environ


def test_the_page_starts_in_fixture_mode_whatever_the_dotenv_says(monkeypatch, tmp_path):
    monkeypatch.setenv("VGA_UI_FIXTURE", "1")
    monkeypatch.setenv("VGA_LOG_DIR", str(tmp_path / "logs"))

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()

    assert not at.exception
    assert [info.value for info in at.info] == [runner.FIXTURE_NOTICE]
""".replace("APP_PATH", repr(str(APP_PATH)))


def _developer_machine(dotenv: Path) -> str:
    """Conftest lines that make ``dotenv`` the loader's default file, as a real ``.env`` is."""
    return (
        "from pathlib import Path\n"
        "from vga import settings as _settings\n"
        f"_HOSTILE = Path({str(dotenv)!r})\n"
        "_settings.DEFAULT_DOTENV_PATH = _HOSTILE\n"
        "_settings.load_dotenv.__defaults__ = (_HOSTILE, *_settings.load_dotenv.__defaults__[1:])\n"
    )


@pytest.fixture
def hostile_dotenv(tmp_path: Path) -> Path:
    """A ``.env`` that would break the suite, in a temporary folder."""
    dotenv = tmp_path / "developer-home" / ".env"
    dotenv.parent.mkdir()
    dotenv.write_text(HOSTILE_DOTENV, encoding="utf-8")
    return dotenv


def test_a_hostile_dotenv_breaks_the_tests_without_the_conftest(
    pytester: pytest.Pytester, hostile_dotenv: Path
) -> None:
    pytester.makeini(NESTED_INI)
    pytester.makeconftest(_developer_machine(hostile_dotenv))
    pytester.makepyfile(test_inner=INNER_TESTS)

    result = pytester.runpytest_subprocess(*NESTED_ARGS)

    result.assert_outcomes(failed=3)
    # The failure is the hostile file's doing, not something else in the nested session.
    shown = result.stdout.str()
    assert "not-a-real-alias" in shown  # the alias reached the settings
    assert "DID NOT RAISE" in shown  # the key was found, so the client had no reason to refuse


def test_the_conftest_keeps_a_hostile_dotenv_and_its_key_out_of_the_tests(
    pytester: pytest.Pytester, hostile_dotenv: Path
) -> None:
    pytester.makeini(NESTED_INI)
    pytester.makeconftest(_developer_machine(hostile_dotenv) + CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(test_inner=INNER_TESTS)

    result = pytester.runpytest_subprocess(*NESTED_ARGS)

    result.assert_outcomes(passed=3)


def test_a_default_test_starts_without_credentials_or_settings_in_its_environment() -> None:
    leaked = [name for name in os.environ if name.startswith(("OPENAI_", "VGA_"))]

    assert leaked == []


def test_a_default_test_can_still_set_its_own_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VGA_UI_FIXTURE", "1")

    assert runner.load_ui_settings().ui_fixture is True


def test_the_loader_has_no_dotenv_to_read_in_a_default_test() -> None:
    defaults = settings_module.load_dotenv.__defaults__

    assert not settings_module.DEFAULT_DOTENV_PATH.exists()
    assert defaults is not None
    assert not Path(defaults[0]).exists()
