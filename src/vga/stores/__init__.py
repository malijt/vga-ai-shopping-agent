"""Store registry, extraction strategies and the search engine (Phase 6).

This is the store-aware layer on top of ``vga.fetch``. What other phases import::

    from vga.stores import StoreRegistry, StoreSearchEngine

    registry = StoreRegistry.from_directory()          # config/stores/*.yaml (may be empty)
    engine = StoreSearchEngine(settings, registry)     # implements vga.interfaces.StoreSearcher
    results = await engine.search(item, registry.active(settings))
    image = await engine.fetch_image(product)          # bytes | None, for the image ranker
"""

from vga.stores.cache import ResultCache
from vga.stores.engine import IMAGE_TIMEOUT_S, StoreSearchEngine
from vga.stores.extractors import (
    ChainOutcome,
    ExtractionChain,
    ExtractionError,
    Extractor,
    ExtractorRegistry,
    ShopifyExtractor,
    default_registry,
)
from vga.stores.normalise import DropReason, NormalisedBatch, normalise_records
from vga.stores.prices import ParsedPrice, PriceFormatError, parse_price
from vga.stores.registry import StoreRegistry, load_store_configs
from vga.stores.urls import build_search_url

__all__ = [
    "IMAGE_TIMEOUT_S",
    "ChainOutcome",
    "DropReason",
    "ExtractionChain",
    "ExtractionError",
    "Extractor",
    "ExtractorRegistry",
    "NormalisedBatch",
    "ParsedPrice",
    "PriceFormatError",
    "ResultCache",
    "ShopifyExtractor",
    "StoreRegistry",
    "StoreSearchEngine",
    "build_search_url",
    "default_registry",
    "load_store_configs",
    "normalise_records",
    "parse_price",
]
