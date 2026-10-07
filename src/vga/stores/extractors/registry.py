"""Name-based registry of extraction strategies (plan 6.4.1).

``default_registry()`` holds the strategies built so far. Only ``shopify`` is built: the stores
that qualified (Shopify storefronts) need nothing else. ``css``, ``store_json``, ``json_ld`` and
``embedded_json`` are deliberately absent (YAGNI); one is added by writing a class that satisfies
``Extractor`` and calling ``register`` on a registry, with no change to the chain.
"""

from vga.models import StrategyConfig
from vga.stores.extractors.base import Extractor
from vga.stores.extractors.shopify import ShopifyExtractor


class ExtractorRegistry:
    """Extractors by strategy name."""

    def __init__(self, extractors: list[Extractor] | None = None) -> None:
        self._by_name: dict[str, Extractor] = {}
        for extractor in extractors or []:
            self.register(extractor)

    def register(self, extractor: Extractor) -> None:
        """Add a strategy. Registering a name twice is a programming error."""
        if extractor.name in self._by_name:
            msg = f"an extractor named {extractor.name!r} is already registered"
            raise ValueError(msg)
        self._by_name[extractor.name] = extractor

    def get(self, name: str) -> Extractor | None:
        return self._by_name.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._by_name)

    def check(self, strategy: StrategyConfig) -> None:
        """Raise ``ValueError`` if the strategy is unknown or its settings are unusable."""
        extractor = self.get(strategy.name)
        if extractor is None:
            msg = f"unknown extraction strategy {strategy.name!r}; built strategies: {self.names}"
            raise ValueError(msg)
        extractor.validate(strategy)


def default_registry() -> ExtractorRegistry:
    """A new registry holding every strategy that is built."""
    return ExtractorRegistry([ShopifyExtractor()])
