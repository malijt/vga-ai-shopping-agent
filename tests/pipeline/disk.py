"""Reading the disk from the tests. Plain functions, so an ``async`` test can call them without
doing blocking file work itself."""

from pathlib import Path


def files_under(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def exists(path: str | Path) -> bool:
    return Path(path).exists()


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
