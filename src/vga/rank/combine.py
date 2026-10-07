"""The combiner: one total score from the text, image and price scores (plan 7.2.4, PRD R8).

A weighted sum with the weights from ``settings.ranking_weights`` (ADR 0004; rank fusion is
deliberately not used). When a product has no image score (no photo, the image ranker is off or
failed, or this product could not be scored) the image weight is dropped and the other weights
are renormalised, so the total stays on the same 0-1 scale.
"""

from vga.settings import RankingWeights


def _clamp(value: float) -> float:
    # Float rounding can leave 1.0000000000000002, which the 0-1 ``Score`` type rejects.
    return min(1.0, max(0.0, value))


def combine_scores(
    text: float, image: float | None, price: float, weights: RankingWeights
) -> float:
    """Weighted average of the scores that exist.

    ``total = (w_text * text + w_image * image + w_price * price) / (w_text + w_image + w_price)``,
    leaving out the image term and its weight when ``image`` is ``None``. If every remaining
    weight is zero (for example only the image weight is set and there is no image score), the
    plain average of the remaining scores is used instead of dividing by zero.
    """
    parts = [(weights.text, text), (weights.price, price)]
    if image is not None:
        parts.append((weights.image, image))
    total_weight = sum(weight for weight, _ in parts)
    if total_weight <= 0:
        return _clamp(sum(score for _, score in parts) / len(parts))
    return _clamp(sum(weight * score for weight, score in parts) / total_weight)
