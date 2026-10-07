"""Extraction strategies: the ``Extractor`` protocol, a name-based registry and the chain."""

from vga.stores.extractors.base import ExtractionError, Extractor
from vga.stores.extractors.chain import ChainOutcome, ExtractionChain
from vga.stores.extractors.registry import ExtractorRegistry, default_registry
from vga.stores.extractors.shopify import ShopifyExtractor

__all__ = [
    "ChainOutcome",
    "ExtractionChain",
    "ExtractionError",
    "Extractor",
    "ExtractorRegistry",
    "ShopifyExtractor",
    "default_registry",
]
