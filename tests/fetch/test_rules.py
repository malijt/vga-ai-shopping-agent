"""Guards on the source of Phase 6: the libraries and options CLAUDE.md forbids never appear.

BRD Rule 2 and the stack table: an honest ``httpx`` client only; ``protego`` and never
``urllib.robotparser``; no browser impersonation, headless browser, proxy or CAPTCHA tooling.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "vga"
PHASE_6_FILES = sorted([*(SRC / "fetch").rglob("*.py"), *(SRC / "stores").rglob("*.py")])

FORBIDDEN_MODULES = {
    "curl_cffi",
    "scrapling",
    "playwright",
    "selenium",
    "undetected_chromedriver",
    "pyppeteer",
    "cloudscraper",
    "requests",
    "aiohttp",
    "urllib3",
    "fake_useragent",
    "twocaptcha",
    "anticaptcha",
    "urllib.robotparser",
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_the_phase_6_sources_are_found() -> None:
    assert len(PHASE_6_FILES) >= 15


@pytest.mark.parametrize("path", PHASE_6_FILES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_forbidden_library_is_imported(path: Path) -> None:
    banned = {
        module
        for module in imported_modules(path)
        if any(module == name or module.startswith(f"{name}.") for name in FORBIDDEN_MODULES)
    }

    assert banned == set()


def test_robots_are_read_with_protego() -> None:
    assert "protego" in imported_modules(SRC / "fetch" / "robots.py")


def test_only_the_client_module_builds_an_http_client() -> None:
    builders = [
        path.relative_to(SRC).as_posix()
        for path in PHASE_6_FILES
        if "httpx.AsyncClient(" in path.read_text(encoding="utf-8")
    ]

    assert builders == ["fetch/client.py"]


@pytest.mark.parametrize("option", ["proxy=", "proxies=", "http2=True", "follow_redirects=True"])
def test_the_client_never_enables_proxies_http2_or_automatic_redirects(option: str) -> None:
    source = (SRC / "fetch" / "client.py").read_text(encoding="utf-8")

    assert option not in source


def test_the_client_ignores_the_environment_and_follows_redirects_by_hand() -> None:
    source = (SRC / "fetch" / "client.py").read_text(encoding="utf-8")

    assert "trust_env=False" in source
    assert "follow_redirects=False" in source
