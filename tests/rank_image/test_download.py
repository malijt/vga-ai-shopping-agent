"""8.1.4 The weights download step: `python -m vga.rank.image.download`."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.factories import make_settings
from tests.rank_image.ml_fakes import REVISION, FakeMlPackages
from vga.errors import ConfigError
from vga.rank.image import download
from vga.rank.image.model import REQUIRED_FILES
from vga.settings import PROJECT_ROOT, Settings


@pytest.fixture
def pinned_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
    monkeypatch.setattr(download, "load_settings", lambda: settings)
    return settings


def test_it_downloads_the_pinned_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)

    code = download.main([])

    assert code == download.EXIT_OK
    (call,) = packages.hub.downloads
    assert call["revision"] == REVISION
    assert call["repo_id"] == "Marqo/marqo-fashionSigLIP"
    assert all((packages.hub.folder / name).is_file() for name in REQUIRED_FILES)
    assert str(packages.hub.folder) in capsys.readouterr().out


def test_running_it_twice_downloads_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)

    first = download.main([])
    capsys.readouterr()
    second = download.main([])

    assert (first, second) == (download.EXIT_OK, download.EXIT_OK)
    assert len(packages.hub.downloads) == 1
    assert "already downloaded" in capsys.readouterr().out


def test_with_the_weights_already_present_it_downloads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_settings: Settings
) -> None:
    packages = FakeMlPackages(tmp_path, cached=True).install(monkeypatch)

    assert download.main([]) == download.EXIT_OK
    assert packages.hub.downloads == []


def test_an_unpinned_revision_is_refused_before_any_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
    monkeypatch.setattr(download, "load_settings", lambda: make_settings(siglip_revision=None))

    code = download.main([])

    assert code == download.EXIT_BAD_SETTINGS
    assert packages.hub.calls == []
    assert "siglip_revision" in capsys.readouterr().err


def test_invalid_settings_are_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> Settings:
        raise ConfigError(detail="siglip_revision: not a commit hash")

    monkeypatch.setattr(download, "load_settings", broken)

    assert download.main([]) == download.EXIT_BAD_SETTINGS
    assert "not a commit hash" in capsys.readouterr().err


def test_missing_ml_packages_are_reported_with_the_install_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    FakeMlPackages(tmp_path, cached=False, missing=["huggingface_hub"]).install(monkeypatch)

    code = download.main([])

    assert code == download.EXIT_FAILED
    assert "uv sync --group ml" in capsys.readouterr().err


def test_a_failed_download_is_reported_and_can_be_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
    packages.hub.fail_download = ConnectionError("network is unreachable")

    first = download.main([])
    error_output = capsys.readouterr().err
    packages.hub.fail_download = None
    second = download.main([])

    assert first == download.EXIT_FAILED
    assert "network is unreachable" in error_output
    assert "python -m vga.rank.image.download" in error_output
    assert second == download.EXIT_OK


def test_the_command_runs_as_a_module_and_explains_itself() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vga.rank.image.download", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""},
    )

    assert result.returncode == 0
    assert "816 MB" in result.stdout
    assert "RuntimeWarning" not in result.stderr
