"""Price-range shaper: quartile borders, mix, store cap and fill rules (Phase 9).

Pure functions, no I/O. "Tier" is the code word; every user-visible text says "price range".
"""

from vga.tiers.borders import PriceBorders, compute_borders
from vga.tiers.mix import mix_to_counts
from vga.tiers.shaper import ShapeResult, shape

__all__ = [
    "PriceBorders",
    "ShapeResult",
    "compute_borders",
    "mix_to_counts",
    "shape",
]
