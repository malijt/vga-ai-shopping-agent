"""Setup shared by every test.

One autouse fixture keeps the default suite independent of the developer's machine: no test reads
the project's real ``.env`` and none sees real credentials. Without it, the loader in
``vga.settings`` copies ``.env`` into ``os.environ`` the first time a test calls ``load_settings()``
(the Streamlit page does), so a real ``OPENAI_API_KEY`` leaks into the test process and a real
``OPENAI_MODEL`` or ``VGA_*`` value changes what the tests see. That is how a developer's ``.env``
made the whole ``tests/ui`` suite fail while the same suite passed on a clean checkout.

``pytester`` is enabled for ``tests/foundation/test_environment_isolation.py``, which runs this very
file in a nested session against a hostile ``.env`` to prove the fixture holds.
"""

import os

import pytest

from vga import settings as settings_module

pytest_plugins = ["pytester"]

ISOLATED_PREFIXES = ("OPENAI_", "VGA_")
"""Environment variables that carry credentials or configuration: ``OPENAI_API_KEY``,
``OPENAI_MODEL`` and the rest of ``OPENAI_*``, and every ``VGA_*`` setting. Each test starts
without them and sets what it needs through ``monkeypatch``."""


@pytest.fixture(autouse=True)
def _isolated_environment(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Hide the real ``.env`` and the real credentials from the test.

    Tests marked ``live`` are exempt: they need the key and read the project's own settings.
    Everything is undone by ``monkeypatch`` when the test ends, and a test that sets its own
    variables with ``monkeypatch.setenv`` still can (its fixtures run after this one).
    """
    if request.node.get_closest_marker("live") is not None:
        return

    # A path under pytest's temporary base folder that is never created, so nothing is read.
    nowhere = tmp_path_factory.getbasetemp() / "no-dotenv-in-tests" / ".env"
    assert not nowhere.exists()

    # `load_settings()` reads the module-level path when it runs, so patching the name is enough.
    monkeypatch.setattr(settings_module, "DEFAULT_DOTENV_PATH", nowhere)
    # `load_dotenv()` called with no argument (as `create_openai_client()` does) uses the default
    # that was bound when the function was defined, so that one has to be replaced as well.
    path_default, *other_defaults = settings_module.load_dotenv.__defaults__ or ()
    assert path_default is not None, "load_dotenv no longer has a default path to replace"
    monkeypatch.setattr(settings_module.load_dotenv, "__defaults__", (nowhere, *other_defaults))

    for name in [name for name in os.environ if name.startswith(ISOLATED_PREFIXES)]:
        monkeypatch.delenv(name)
