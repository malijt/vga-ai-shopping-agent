"""The shipped Nautica UAE store file, loaded through the real registry, for the tests here."""

import shutil
from pathlib import Path

import pytest

from vga.models import StoreConfig
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.registry import load_store_configs

STORE_ID = "nautica-uae"
STORE_FILE = DEFAULT_STORES_DIR / f"{STORE_ID}.yaml"


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """The store exactly as ``config/stores/nautica-uae.yaml`` writes it, loaded with the real
    registry (all its checks: https template, allowed hosts, a built strategy, file name = id).

    Only this one file is copied to a temporary folder and loaded, so a mistake in another
    store's file cannot fail these tests.
    """
    shutil.copy(STORE_FILE, tmp_path / STORE_FILE.name)
    [loaded] = load_store_configs(tmp_path)
    return loaded
