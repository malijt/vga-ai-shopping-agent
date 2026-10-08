"""Fixtures shared by the harness tests."""

from pathlib import Path

import pytest

from tests.harness.cli_support import Cli


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(tmp_path)
