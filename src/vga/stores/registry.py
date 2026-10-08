"""The store registry (plan 6.3.1): ``config/stores/*.yaml`` loaded into ``StoreConfig``.

One file per store, named ``<store id>.yaml``. A bad file never half-loads: every problem in every
file is collected and reported together, each naming the file and the field, so one start-up shows
everything to fix. A missing or empty directory is fine and gives an empty registry (the shipped
directory is empty until the store-adapter phase fills it).

Only stores with ``enabled: true`` in the home country or one of ``Settings.extra_store_countries``
(and, when ``Settings.stores`` is not empty, listed there) are used; ``StoreRegistry.active``
applies exactly that rule.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import ValidationError

from vga.errors import ConfigError
from vga.log import get_logger
from vga.models import StoreConfig
from vga.settings import DEFAULT_STORES_DIR, Settings
from vga.stores.extractors import ExtractorRegistry, default_registry

log = get_logger(__name__)


def _field_path(location: Sequence[Any]) -> str:
    return ".".join(str(part) for part in location) or "(file)"


def load_store_configs(
    directory: Path | str = DEFAULT_STORES_DIR,
    extractors: ExtractorRegistry | None = None,
) -> list[StoreConfig]:
    """Load every ``*.yaml`` file in ``directory``, in file-name order.

    Raises ``ConfigError`` listing each invalid file and field. ``extractors`` is the registry
    strategy names are checked against (default: the built strategies).
    """
    folder = Path(directory)
    if not folder.is_dir():
        log.info("no store directory; no stores loaded", extra={"directory": str(folder)})
        return []
    known = extractors or default_registry()
    stores: list[tuple[Path, StoreConfig]] = []
    problems: list[str] = []
    for path in sorted(folder.glob("*.yaml")):
        store, file_problems = _load_one(path, known)
        problems.extend(file_problems)
        if store is not None:
            stores.append((path, store))
    problems.extend(_name_clashes(stores))
    if problems:
        raise ConfigError(
            "The store settings are not valid: " + "; ".join(problems) + ". "
            "Fix the file(s) in config/stores/ and restart.",
            detail="; ".join(problems),
        )
    return [store for _path, store in stores]


def _load_one(path: Path, known: ExtractorRegistry) -> tuple[StoreConfig | None, list[str]]:
    name = path.name
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return None, [f"{name}: cannot be read as YAML ({str(exc).splitlines()[0]})"]
    if not isinstance(raw, dict):
        return None, [f"{name}: must contain a mapping of store settings"]
    try:
        store = StoreConfig.model_validate(raw)
    except ValidationError as exc:
        return None, [
            f"{name}: {_field_path(e['loc'])}: {str(e['msg']).removeprefix('Value error, ')}"
            for e in exc.errors()
        ]
    problems: list[str] = []
    if store.id != path.stem:
        problems.append(f"{name}: id: is {store.id!r} but the file must be named {store.id}.yaml")
    for index, strategy in enumerate(store.extraction.strategies):
        try:
            known.check(strategy)
        except ValueError as exc:
            where = f"extraction.strategies.{index}"
            problems.append(f"{name}: {where} ({strategy.name}): {exc}")
    return (None if problems else store), problems


def _name_clashes(stores: list[tuple[Path, StoreConfig]]) -> list[str]:
    """Display names must be unique among enabled stores: ``Product.store`` carries the display
    name and the per-store cap counts by it."""
    owner: dict[str, Path] = {}
    problems: list[str] = []
    for path, store in stores:
        if not store.enabled:
            continue
        first = owner.setdefault(store.display_name, path)
        if first is not path:
            problems.append(
                f"{path.name}: name: {store.display_name!r} is already used by enabled store "
                f"{first.name}"
            )
    return problems


class StoreRegistry:
    """The stores the app knows, by id and by the display name carried on each ``Product``."""

    def __init__(self, stores: Iterable[StoreConfig] = ()) -> None:
        self._by_id: dict[str, StoreConfig] = {}
        for store in stores:
            self.add(store)

    @classmethod
    def from_directory(
        cls,
        directory: Path | str = DEFAULT_STORES_DIR,
        extractors: ExtractorRegistry | None = None,
    ) -> Self:
        return cls(load_store_configs(directory, extractors))

    def add(self, store: StoreConfig) -> None:
        """Add a store, or replace the one with the same id."""
        self._by_id[store.id] = store

    @property
    def stores(self) -> list[StoreConfig]:
        return list(self._by_id.values())

    def get(self, store_id: str) -> StoreConfig | None:
        return self._by_id.get(store_id)

    def by_display_name(self, name: str) -> StoreConfig | None:
        """The store whose ``Product.store`` is ``name`` (the newest one when two share it)."""
        for store in reversed(list(self._by_id.values())):
            if store.display_name == name:
                return store
        return None

    def active(self, settings: Settings) -> list[StoreConfig]:
        """The stores to search: enabled, in a country that is searched (``settings.country``
        or one of ``settings.extra_store_countries``), and listed in ``settings.stores`` when
        that list is not empty."""
        wanted = set(settings.stores)
        for unknown in sorted(wanted - self._by_id.keys()):
            log.warning(
                "settings.stores names a store that has no file; ignored", extra={"store": unknown}
            )
        chosen: list[StoreConfig] = []
        for store in self._by_id.values():
            if not store.enabled:
                log.info("store disabled; not searched", extra={"store": store.id})
            elif not settings.searches_country(store.country):
                log.info(
                    "store is for a country that is not searched; not searched",
                    extra={"store": store.id, "country": store.country},
                )
            elif wanted and store.id not in wanted:
                log.info("store not selected in settings; not searched", extra={"store": store.id})
            else:
                chosen.append(store)
        return chosen
