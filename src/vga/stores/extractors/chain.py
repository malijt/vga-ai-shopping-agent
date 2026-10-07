"""The extraction chain (plan 6.4.1): try a store's strategies in order, first success wins."""

from collections import Counter
from dataclasses import dataclass, field

from vga.log import get_logger
from vga.models import Product, StoreConfig
from vga.stores.extractors.base import ExtractionError
from vga.stores.extractors.registry import ExtractorRegistry
from vga.stores.normalise import normalise_records

log = get_logger(__name__)


@dataclass
class ChainOutcome:
    strategy: str | None = None
    """The strategy that produced ``products``; ``None`` when none did."""
    products: list[Product] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    """Records dropped by validation, as ``{reason: count}`` (the winner's, or all strategies' when
    none won)."""
    examined: int = 0
    """Raw records the strategies found (kept plus dropped)."""
    ran_cleanly: int = 0
    """How many strategies read the response without an error."""
    errors: list[str] = field(default_factory=list)
    """One line for each strategy that could not read the response."""


class ExtractionChain:
    """Runs ``store.extraction.strategies`` in order against one response body.

    The first strategy that yields at least one valid product wins and its name is reported. A
    strategy that finds nothing, or fails to read the body, hands over to the next; failures are
    logged and kept in ``errors``, never raised, so one broken strategy cannot break a search.
    """

    def __init__(self, registry: ExtractorRegistry) -> None:
        self._registry = registry

    def run(self, body: str, store: StoreConfig, base_url: str) -> ChainOutcome:
        outcome = ChainOutcome()
        dropped: Counter[str] = Counter()
        for strategy in store.extraction.strategies:
            extractor = self._registry.get(strategy.name)
            if extractor is None:
                self._fail(outcome, store, strategy.name, "unknown extraction strategy")
                continue
            try:
                records = extractor.extract(body, store, strategy)
            except ExtractionError as exc:
                self._fail(outcome, store, strategy.name, str(exc))
                continue
            except Exception as exc:  # a bug in one strategy must not break the search
                log.exception(
                    "extractor crashed", extra={"store": store.id, "strategy": strategy.name}
                )
                self._fail(outcome, store, strategy.name, f"crashed: {type(exc).__name__}")
                continue

            outcome.ran_cleanly += 1
            batch = normalise_records(records, store, base_url)
            outcome.examined += batch.examined
            if batch.products:
                outcome.strategy = strategy.name
                outcome.products = batch.products
                outcome.dropped = batch.dropped
                return outcome
            dropped.update(batch.dropped)
            log.info(
                "strategy found no valid products; trying the next",
                extra={"store": store.id, "strategy": strategy.name, "examined": batch.examined},
            )
        outcome.dropped = dict(dropped)
        return outcome

    @staticmethod
    def _fail(outcome: ChainOutcome, store: StoreConfig, strategy: str, why: str) -> None:
        outcome.errors.append(f"{strategy}: {why}")
        log.warning(
            "extraction strategy could not read the response",
            extra={"store": store.id, "strategy": strategy, "reason": why},
        )
