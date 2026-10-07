"""Shape the final list for ONE garment category into four price ranges (plan 9.2.x and 9.3.1).

Input: the scored products for one category, best first, already filtered and above the minimum
match score (Phase 7 removes weaker products). Output: four ``TierResult`` in display order. Pure
and deterministic: no network, no I/O, no model, no clock. Nothing is invented, re-scored or
re-ranked: a product's place is decided by ``scores.total`` alone, and only products that were
passed in can come out.

How a request is shaped, in order (the PRD section "Price ranges and the final list"):

1. Prepare. Sort by ``scores.total`` (stable, so equal scores keep the order they came in), drop a
   product scoring below ``settings.min_match_score`` (belt and braces: Phase 7 already did), and
   keep only the best copy of a product that appears twice (same ``Product.key``).
2. One currency. The demo is UAE-only, so every product should share a currency. If not, only the
   products in the most common currency are shaped (ties go to the currency of the best-scoring
   product), the rest are left out, and a warning says so. Nothing is converted.
3. Borders (``vga.tiers.borders``) from the prices of ALL these candidates, including the ones
   that are over the shopper's budget (plan assumption A4). Each product gets its natural range.
4. Counts (``vga.tiers.mix``) from ``settings.tier_mix`` and the total.
5. Pick. Inside a range the best-scoring products come first, and no store supplies more than
   ``settings.max_per_store`` products across the whole list (all four ranges together; a store is
   keyed by ``Product.store``). When the cap forces a choice between ranges, the ranges take turns,
   the one least filled relative to its target going first and ties going to the cheaper range, so
   a dominant store's slots are spread over the ranges instead of being spent on the cheapest one.
6. Fill thin ranges. A range whose own products cannot reach its target is thin: it gets the
   ``few_options`` flag and borrows the missing products from the nearest range, best score first,
   taking only products the other ranges did not need for their own targets.

   "Nearest" means the fewest steps along Budget, Mid-range, Premium, Luxury; when the range below
   and the range above are equally near, the CHEAPER one is tried first. If the nearest range has
   too little to give, the next nearest is tried, and so on, until the gap is filled or no product
   is left. Thin ranges are served cheapest first. A borrowed product is shown in the range it fills
   (its ``tier`` is that range), and the range's price span covers it, so the span stays honest.
7. Budget (plan assumption A4). With a budget, Budget and Mid-range may only hold products within
   it (price at or below the budget). Premium and Luxury may hold products over it; each carries
   the ``over_budget`` flag. A budget in another currency than the products is not applied (a
   warning says so) because the comparison would be meaningless.
8. Luxury only means "most expensive found" unless a luxury store is among the enabled stores
   passed in: otherwise the Luxury range carries the ``relative_range`` flag (always, even if the
   range is empty, so the flag depends on the stores alone).

If there are not enough products overall, fewer are returned. A range may then be empty; an empty
range has no price span and every range that fell short of its target (other than a range with a
target of 0) carries ``few_options``.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from vga.log import get_logger
from vga.models import (
    TIER_ORDER,
    Budget,
    Flag,
    ScoredProduct,
    StoreConfig,
    Tier,
    TierResult,
)
from vga.settings import Settings
from vga.tiers.borders import PriceBorders, compute_borders
from vga.tiers.mix import mix_to_counts

log = get_logger(__name__)

_MAY_EXCEED_BUDGET = frozenset({Tier.PREMIUM, Tier.LUXURY})
"""Only these ranges may hold a product over the shopper's budget (PRD rules)."""


def _donor_order(tier: Tier) -> tuple[Tier, ...]:
    """Other ranges from nearest to farthest; equally near, the cheaper range comes first."""
    position = TIER_ORDER.index(tier)
    others = (other for other in TIER_ORDER if other is not tier)
    return tuple(
        sorted(
            others,
            key=lambda other: (abs(TIER_ORDER.index(other) - position), TIER_ORDER.index(other)),
        )
    )


_DONOR_ORDER: dict[Tier, tuple[Tier, ...]] = {tier: _donor_order(tier) for tier in TIER_ORDER}


@dataclass(frozen=True, slots=True)
class ShapeResult:
    """What ``shape`` returns: the four price ranges plus what the caller should know."""

    tiers: list[TierResult]
    """Exactly four, in the order Budget, Mid-range, Premium, Luxury."""
    warnings: list[str] = field(default_factory=list)
    """Plain-language notes for ``SearchResponse.warnings`` (never contain the word "tier")."""
    borders: PriceBorders | None = None
    """The borders used, or ``None`` when there were no products to compute them from."""
    currency: str | None = None
    """The one currency that was shaped, or ``None`` when there were no products."""

    @property
    def products(self) -> list[ScoredProduct]:
        return [scored for tier in self.tiers for scored in tier.results]


@dataclass(frozen=True, slots=True)
class _Candidate:
    index: int
    """Position in the best-first order after preparation; also the final tie-breaker."""
    scored: ScoredProduct
    natural: Tier
    over_budget: bool

    @property
    def store(self) -> str:
        return self.scored.product.store


class _Picker:
    """Chooses which candidate goes into which range, honouring targets, the cap and the budget."""

    def __init__(
        self, pools: dict[Tier, list[_Candidate]], targets: dict[Tier, int], max_per_store: int
    ) -> None:
        self._pools = pools
        self._targets = targets
        self._max_per_store = max_per_store
        self.picked: dict[Tier, list[_Candidate]] = {tier: [] for tier in TIER_ORDER}
        self._taken: set[int] = set()
        self._store_load: Counter[str] = Counter()

    def _eligible(self, candidate: _Candidate, tier: Tier) -> bool:
        if candidate.index in self._taken:
            return False
        if self._store_load[candidate.store] >= self._max_per_store:
            return False
        return tier in _MAY_EXCEED_BUDGET or not candidate.over_budget

    def _take(self, candidate: _Candidate, tier: Tier) -> None:
        self._taken.add(candidate.index)
        self._store_load[candidate.store] += 1
        self.picked[tier].append(candidate)

    def _is_short(self, tier: Tier) -> bool:
        return len(self.picked[tier]) < self._targets[tier]

    def pick_own(self) -> None:
        """Step 5: each range takes its own best products, ranges taking turns by fill ratio."""
        cursors = dict.fromkeys(TIER_ORDER, 0)

        def head(tier: Tier) -> _Candidate | None:
            # Eligibility only ever gets worse for a range (stores fill up, the budget is fixed),
            # so a candidate skipped here can be skipped for good.
            pool = self._pools[tier]
            while cursors[tier] < len(pool):
                candidate = pool[cursors[tier]]
                if self._eligible(candidate, tier):
                    return candidate
                cursors[tier] += 1
            return None

        while True:
            chosen: tuple[Tier, _Candidate] | None = None
            for tier in TIER_ORDER:
                if not self._is_short(tier):
                    continue
                candidate = head(tier)
                if candidate is not None and (chosen is None or self._less_filled(tier, chosen[0])):
                    chosen = (tier, candidate)
            if chosen is None:
                return
            self._take(chosen[1], chosen[0])

    def _less_filled(self, tier: Tier, other: Tier) -> bool:
        """True when ``tier`` is strictly less full than ``other`` relative to their targets.

        Compares picked/target without division. Strict, so on a tie the range that was looked at
        first (the cheaper one) keeps its turn.
        """
        return len(self.picked[tier]) * self._targets[other] < (
            len(self.picked[other]) * self._targets[tier]
        )

    def thin_tiers(self) -> frozenset[Tier]:
        return frozenset(tier for tier in TIER_ORDER if self._is_short(tier))

    def fill_gaps(self) -> None:
        """Step 6: thin ranges borrow from the nearest ranges' leftovers, cheapest range first."""
        for tier in TIER_ORDER:
            for donor in _DONOR_ORDER[tier]:
                for candidate in self._pools[donor]:
                    if not self._is_short(tier):
                        break
                    if self._eligible(candidate, tier):
                        self._take(candidate, tier)


def _prepare(products: Sequence[ScoredProduct], min_match_score: float) -> list[ScoredProduct]:
    """Step 1: best first, nothing below the minimum score, one copy of each product."""
    ordered = sorted(enumerate(products), key=lambda pair: (-pair[1].scores.total, pair[0]))
    seen: set[str] = set()
    prepared: list[ScoredProduct] = []
    for _, scored in ordered:
        if scored.scores.total < min_match_score or scored.product.key in seen:
            continue
        seen.add(scored.product.key)
        prepared.append(scored)
    return prepared


def _most_common_currency(products: list[ScoredProduct]) -> str | None:
    """The currency with the most products; ties go to the one the best-scoring product has."""
    counts = Counter(scored.product.currency for scored in products)
    if not counts:
        return None
    # Counter keeps first-seen order for equal counts and max() returns the first maximum.
    return max(counts, key=lambda currency: counts[currency])


def _mark(scored: ScoredProduct, tier: Tier, over_budget: bool) -> ScoredProduct:
    """The product as shown: placed in ``tier`` and carrying ``over_budget`` exactly when it is.

    The shaper owns ``over_budget``: it is recomputed from the budget passed in, so a re-shape with
    a different budget (or none) never keeps a stale flag from an earlier step.
    """
    flags: list[Flag] = [flag for flag in scored.flags if flag is not Flag.OVER_BUDGET]
    if over_budget:
        flags.append(Flag.OVER_BUDGET)
    return scored.model_copy(update={"tier": tier, "flags": flags})


def _tier_result(
    tier: Tier,
    picks: list[_Candidate],
    target: int,
    currency: str | None,
    *,
    thin: bool,
    relative: bool,
) -> TierResult:
    flags: list[Flag] = []
    if thin:
        flags.append(Flag.FEW_OPTIONS)
    if relative:
        flags.append(Flag.RELATIVE_RANGE)
    ordered = sorted(picks, key=lambda candidate: candidate.index)
    prices = [candidate.scored.product.price for candidate in ordered]
    return TierResult(
        name=tier,
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
        currency=currency if prices else None,
        target_count=target,
        count=len(ordered),
        flags=flags,
        results=[_mark(c.scored, tier, c.over_budget) for c in ordered],
    )


def shape(
    products: Sequence[ScoredProduct],
    settings: Settings,
    budget: Budget | None,
    stores: Sequence[StoreConfig],
    *,
    total: int | None = None,
) -> ShapeResult:
    """Split one category's scored products into four price ranges. See the module docstring.

    ``products`` are best first and for ONE category. ``settings`` supplies ``tier_mix``,
    ``max_per_store``, ``min_match_score`` and, unless ``total`` is given, ``results``. ``budget``
    is the shopper's ceiling or ``None``. ``stores`` are the stores in play: the Luxury range gets
    the ``relative_range`` flag unless one of the enabled ones has ``tier_hint`` luxury. Pass
    ``total`` for a per-garment list (``settings.outfit_results_per_garment``).

    Returns four ``TierResult`` (cheapest first) with their warnings. Raises ``ValueError`` only
    for a negative ``total``.
    """
    targets = mix_to_counts(settings.tier_mix, settings.results if total is None else total)
    warnings: list[str] = []

    prepared = _prepare(products, settings.min_match_score)
    currency = _most_common_currency(prepared)
    shaped = [s for s in prepared if s.product.currency == currency]
    if len(shaped) < len(prepared):
        left_out = Counter(s.product.currency for s in prepared if s.product.currency != currency)
        listed = ", ".join(f"{count} in {name}" for name, count in sorted(left_out.items()))
        message = (
            f"The products came in more than one currency, so only the {len(shaped)} priced in "
            f"{currency} were used and the others ({listed}) were left out."
        )
        warnings.append(message)
        log.warning(
            "products in other currencies left out",
            extra={"used_currency": currency, "left_out": dict(left_out)},
        )

    ceiling: float | None = None
    if budget is not None and currency is not None:
        if budget.currency == currency:
            ceiling = budget.max_price
        else:
            warnings.append(
                f"Your budget is in {budget.currency} but the prices found are in {currency}, "
                "so the budget was not applied."
            )
            log.warning(
                "budget currency differs from product currency, budget not applied",
                extra={"budget_currency": budget.currency, "used_currency": currency},
            )

    borders: PriceBorders | None = None
    pools: dict[Tier, list[_Candidate]] = {tier: [] for tier in TIER_ORDER}
    if shaped:
        borders = compute_borders([s.product.price for s in shaped])
        for index, scored in enumerate(shaped):
            price = scored.product.price
            candidate = _Candidate(
                index=index,
                scored=scored,
                natural=borders.tier_for(price),
                over_budget=ceiling is not None and price > ceiling,
            )
            pools[candidate.natural].append(candidate)

    picker = _Picker(pools, targets, settings.max_per_store)
    picker.pick_own()
    thin = picker.thin_tiers()
    picker.fill_gaps()

    has_luxury_store = any(store.enabled and store.tier_hint is Tier.LUXURY for store in stores)
    tiers = [
        _tier_result(
            tier,
            picker.picked[tier],
            targets[tier],
            currency,
            thin=tier in thin,
            relative=tier is Tier.LUXURY and not has_luxury_store,
        )
        for tier in TIER_ORDER
    ]
    return ShapeResult(tiers=tiers, warnings=warnings, borders=borders, currency=currency)
