"""Turn the percentage mix into result counts (plan 9.1.2, PRD R14 and "Mix").

Largest-remainder rounding: every range gets the whole part of its exact share, then the leftover
results go one each to the ranges with the largest fractional remainder. The counts always sum to
the total. Ties on the remainder go to the cheaper range, which is how 25/25/25/25 of 30 becomes
8/8/7/7 and not 7/7/8/8.
"""

from vga.models import TIER_ORDER, Tier, TierMix


def mix_to_counts(mix: TierMix, total: int) -> dict[Tier, int]:
    """Results per price range for ``total`` results, in display order (cheapest first).

    ``mix`` is already validated to sum to 100. Integer arithmetic only, so there is no floating
    point drift. A range with a 0 share always gets 0. Raises ``ValueError`` for a negative total.
    """
    if total < 0:
        msg = f"total must not be negative, got {total}"
        raise ValueError(msg)
    shares = {tier: mix.share(tier) for tier in TIER_ORDER}
    counts = {tier: total * share // 100 for tier, share in shares.items()}
    remainders = {tier: total * share % 100 for tier, share in shares.items()}
    leftover = total - sum(counts.values())
    # Largest remainder first; sorted() is stable and TIER_ORDER is cheapest first, so equal
    # remainders keep the cheaper range ahead. The remainders add up to 100 * leftover and each is
    # below 100, so more than ``leftover`` ranges have a positive remainder: a range with remainder
    # 0 (in particular a 0 share) is never reached.
    by_remainder = sorted(TIER_ORDER, key=lambda tier: -remainders[tier])
    for tier in by_remainder[:leftover]:
        counts[tier] += 1
    return counts
