"""Shared by the Hanayen tests: the real store file, loaded the way the app loads it."""

import shutil
from pathlib import Path

import pytest

from vga.models import StoreConfig
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.registry import load_store_configs

STORE_FILE = DEFAULT_STORES_DIR / "hanayen.yaml"


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """``config/stores/hanayen.yaml`` through the real registry loader (strategy names checked
    against the built extractors). Only this one file is copied into the temporary folder the
    loader reads, so other stores' files, present or broken, cannot affect these tests."""
    shutil.copy(STORE_FILE, tmp_path)
    [loaded] = load_store_configs(tmp_path)
    return loaded
