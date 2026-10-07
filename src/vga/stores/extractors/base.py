"""The extractor interface (plan 6.4.1).

An extractor reads one kind of store response (a Shopify JSON body, an HTML page, ...) and returns
*raw* records: the store's own text for each field, unvalidated. Turning records into ``Product``s
is ``vga.stores.normalise``'s job, so every extractor gets the same validation, price parsing and
allow-list checks without repeating them.

A new strategy is a new class registered by name in ``ExtractorRegistry``; the chain and the
engine are not edited (Open/Closed).
"""

from typing import Protocol, runtime_checkable

from vga.models import StoreConfig, StrategyConfig
from vga.stores.normalise import RawRecord


class ExtractionError(ValueError):
    """The response could not be read at all by this strategy (not the expected format, wrong
    shape). Different from "read fine, found no products", which is an empty list."""


@runtime_checkable
class Extractor(Protocol):
    name: str
    """The strategy name used in store files (``extraction.strategies[].name``)."""

    def validate(self, strategy: StrategyConfig) -> None:
        """Raise ``ValueError`` (message names the field) if this strategy's ``fields`` or
        ``options`` in a store file are unusable. Called when the store files are loaded, so a typo
        stops start-up instead of silently returning nothing at search time."""
        ...

    def extract(self, body: str, store: StoreConfig, strategy: StrategyConfig) -> list[RawRecord]:
        """Read raw records out of a response body. Raise ``ExtractionError`` when the body is not
        in the format this strategy reads."""
        ...
