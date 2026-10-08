"""Cosine similarity and its mapping to a 0-1 image score (plan 8.1.2).

Plain Python on purpose: a request compares one 768-number vector with at most 50 others, which
costs a few milliseconds and keeps ``numpy`` out of the default install.
"""

import math
from collections.abc import Sequence


def cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Cosine similarity of two vectors, or ``None`` when it is undefined (a zero vector or a
    non-finite value). Raises ``ValueError`` when the sizes differ, which means the two vectors
    came from different models."""
    if len(a) != len(b):
        msg = f"embedding sizes differ: {len(a)} and {len(b)}"
        raise ValueError(msg)
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0.0 or not math.isfinite(dot) or not math.isfinite(norm):
        return None
    return dot / norm


def cosine_to_score(cos: float, lo: float, hi: float) -> float:
    """Map a cosine to 0-1: ``clip((cos - lo) / (hi - lo), 0, 1)``.

    ``lo`` and ``hi`` come from ``Settings.siglip_cos_lo`` and ``siglip_cos_hi``. At or below
    ``lo`` the score is 0, at or above ``hi`` it is 1.
    """
    if not lo < hi:
        msg = f"cos_lo ({lo}) must be below cos_hi ({hi})"
        raise ValueError(msg)
    return min(1.0, max(0.0, (cos - lo) / (hi - lo)))


def similarity_score(
    query: Sequence[float], vector: Sequence[float], *, lo: float, hi: float
) -> float | None:
    """The 0-1 image score of ``vector`` against ``query``, or ``None`` when undefined."""
    cos = cosine(query, vector)
    return None if cos is None else cosine_to_score(cos, lo, hi)
