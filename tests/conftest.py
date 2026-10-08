"""Setup shared by every test.

One autouse fixture keeps the default suite independent of the developer's machine: no test reads
the project's real ``.env`` and none sees real credentials. Without it, the loader in
``vga.settings`` copies ``.env`` into ``os.environ`` the first time a test calls ``load_settings()``
(the Streamlit page does), so a real ``OPENAI_API_KEY`` leaks into the test process and a real
``OPENAI_MODEL`` or ``VGA_*`` value changes what the tests see. That is how a developer's ``.env``
made the whole ``tests/ui`` suite fail while the same suite passed on a clean checkout.

``pytester`` is enabled for ``tests/foundation/test_environment_isolation.py``, which runs this very
file in a nested session against a hostile ``.env`` to prove the fixture holds.

The second job of this file is the critical suite. ``tests/critical_suite.txt`` is the one
reviewable list of the few tests whose failure would mean a broken rule or a broken demo, and CI
runs only those (``pytest -m critical``). The hook below gives every test the list names the
``critical`` marker, so no decorator is scattered over the test files, and keeps what it found so
that ``tests/foundation/test_critical_suite.py`` can fail when the list rots. The complete suite is
unchanged: a plain ``pytest`` still runs everything.
"""

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from vga import settings as settings_module

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_LIST = Path(__file__).with_name("critical_suite.txt")
"""The list of critical tests. Missing next to a copy of this file (the nested session of
``test_environment_isolation.py`` writes one), which then simply marks nothing."""

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


# --------------------------------------------------------------------------------------------
# The critical suite: the few tests CI runs, named in one list
# --------------------------------------------------------------------------------------------


def read_critical_entries(path: Path = CRITICAL_LIST) -> list[str]:
    """The entries of the list in file order: one per line, blank lines and ``#`` lines skipped."""
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def critical_names(nodeid: str) -> set[str]:
    """Every list entry that would name this test.

    An entry is a pytest node id, and it names the test case itself (``file::test[case]``), the
    test with all its cases (``file::test``), a class (``file::TestClass``) or a whole file.
    """
    parts = nodeid.split("[", 1)[0].split("::")
    return {nodeid, *("::".join(parts[:end]) for end in range(1, len(parts) + 1))}


@dataclass
class CriticalSuite:
    """What the collection hook found, kept for the tests of the list itself."""

    entries: list[str]
    matches: Counter[str]
    """For each entry, how many collected tests it names."""
    critical: list[str]
    """Node ids of the tests marked ``critical``."""
    critical_and_live: list[str]
    """Node ids of critical tests that are also marked ``live``: there must be none."""
    whole_paths: list[Path]
    """Files and folders this session was asked to collect in full (arguments without ``::``)."""

    def collected_the_whole_suite(self) -> bool:
        """True when this session was asked for the whole of ``tests`` (a plain ``pytest``)."""
        return any(root in (REPO_ROOT, REPO_ROOT / "tests") for root in self.whole_paths)

    def unmatched_entries(self) -> list[str]:
        """Entries that name no test although they should.

        An entry is wrong if its file is gone, or if its file was collected in full by this
        session and still no test matched (a renamed test, a changed case id). In a partial run
        (``pytest tests/ui``) the entries of files outside the run cannot be judged and are left
        to the full run, which CI and a plain ``pytest`` both are.
        """
        wrong = []
        for entry in self.entries:
            if self.matches[entry]:
                continue
            file = (REPO_ROOT / entry.split("::", 1)[0]).resolve()
            in_full = any(root == file or root in file.parents for root in self.whole_paths)
            if not file.is_file() or in_full:
                wrong.append(entry)
        return wrong


CRITICAL_KEY = pytest.StashKey[CriticalSuite]()


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker here, not in ``pyproject.toml``, whose marker list a test pins."""
    config.addinivalue_line(
        "markers",
        "critical: named in tests/critical_suite.txt; CI runs only these (pytest -m critical)",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every test the list names as ``critical``.

    ``tryfirst`` so that it runs before pytest applies ``-m``: the marker has to be there when
    ``-m critical`` decides what to keep. It looks at every collected test, also the ones ``-m``
    and ``-k`` are about to drop, so the checks on the list see the whole suite.
    """
    entries = read_critical_entries()
    wanted = set(entries)
    matches: Counter[str] = Counter()
    critical: list[str] = []
    critical_and_live: list[str] = []

    for item in items:
        named_by = wanted & critical_names(item.nodeid)
        if not named_by:
            continue
        matches.update(named_by)
        item.add_marker(pytest.mark.critical)
        critical.append(item.nodeid)
        if item.get_closest_marker("live") is not None:
            critical_and_live.append(item.nodeid)

    invoked_from = config.invocation_params.dir
    whole_paths = [(invoked_from / arg).resolve() for arg in config.args if "::" not in arg]
    config.stash[CRITICAL_KEY] = CriticalSuite(
        entries, matches, critical, critical_and_live, whole_paths
    )


@pytest.fixture(scope="session")
def critical_suite(request: pytest.FixtureRequest) -> CriticalSuite:
    return request.config.stash[CRITICAL_KEY]
