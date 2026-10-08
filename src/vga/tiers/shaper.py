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
2. One currency. Prices, borders, spans and the budget are all in the base currency
   (``Settings.base_currency``, AED). A product priced in another currency (the Kuwaiti stores, in
   dinars) is converted at the fixed rate in ``Settings.fx_rates`` (``vga.money.to_base``) and
   every product that has a base-currency figure is shaped together. The figure is stored on the
   shown product as ``ScoredProduct.base_price`` (only when its own currency differs from the
   base; it is cleared otherwise). A product whose currency has no rate is left out, and a
   warning says so: the app never guesses a rate.
3. Borders (``vga.tiers.borders``) from the base-currency prices of ALL these candidates,
   including the ones that are over the shopper's budget (plan assumption A4). Each product gets
   its natural range.
4. Counts (``vga.tiers.mix``) from ``settings.tier_mix`` and the total.
5. Pick. Inside a range the best-scoring products come first, and no store supplies more than
   ``settings.max_per_store`` products across the whole list (all four ranges together; a store is
   keyed by ``Product.store``). When the cap forces a choice between ranges, the ranges take turns,
   the one least filled relative to its target going first and ties going to the cheaper range, so
   a dominant store's slots are spread over the ranges instead of being spent on the cheapest one.
6. Fill thin ranges. A range whose own products cannot reach its target is thin: it gets the
   ``few_options`` flag and borrows the missing products from an ADJACENT range, best score first,
   taking only products the other ranges did not need for their own targets.

   Adjacent means the range directly below or directly above: Budget may borrow only from
   Mid-range, Mid-range from Budget or Premium, Premium from Mid-range or Luxury, Luxury only from
   Premium. When both neighbours have spare products the CHEAPER one is tried first. Nothing is
   ever borrowed from two or more steps away, because each range's header shows its real price
   span (PRD R16) and a 1,600 AED item must not make a "Budget" list. If the neighbours cannot
   fill the gap, fewer results are returned. Thin ranges are served cheapest first. A borrowed
   product is shown in the range it fills (its ``tier`` is that range), and the range's price span
   covers it, so the span stays honest. A span is in the base currency; when the range holds a
   converted product it is widened outward to whole base units (59.60 to 345.68 shows as 59-346),
   so a header does not claim cents from a fixed approximate rate.
7. Budget (plan assumption A4). With a budget, Budget and Mid-range may only hold products within
   it (base-currency price at or below the budget, the budget converted too when it is in another
   currency). Premium and Luxury may hold products over it; each carries the ``over_budget``
   flag. A budget in a currency with no rate is not applied (a warning says so) because the
   comparison would be meaningless.
8. Luxury only means "most expensive found" unless a luxury store is among the enabled stores
   passed in: otherwise the Luxury range carries the ``relative_range`` flag (always, even if the
   range is empty, so the flag depends on the stores alone).

If there are not enough products overall, fewer are returned. A range may then be empty; an empty
range has no price span and every range that fell short of its target (other than a range with a
target of 0) carries ``few_options``.
"""

import math
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
from vga.money import to_base
from vga.settings import Settings
from vga.tiers.borders import PriceBorders, compute_borders
from vga.tiers.mix import mix_to_counts

log = get_logger(__name__)

_MAY_EXCEED_BUDGET = frozenset({Tier.PREMIUM, Tier.LUXURY})
"""Only these ranges may hold a product over the shopper's budget (PRD rules)."""


def _donor_order(tier: Tier) -> tuple[Tier, ...]:
    """The ranges a thin ``tier`` may borrow from: only the one directly below and the one
    directly above, the cheaper one first. Budget has only Mid-range, Luxury only Premium."""
    position = TIER_ORDER.index(tier)
    return tuple(other for other in TIER_ORDER if abs(TIER_ORDER.index(other) - position) == 1)


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
    """The currency the ranges are in (``Settings.base_currency``), or ``None`` when there were no
    products to shape."""

    @property
    def products(self) -> list[ScoredProduct]:
        return [scored for tier in self.tiers for scored in tier.results]


@dataclass(frozen=True, slots=True)
class _Candidate:
    index: int
    """Position in the best-first order after preparation; also the final tie-breaker."""
    scored: ScoredProduct
    base: float
    """The product's price in the base currency: the number borders, spans and the budget use."""
    converted: bool
    """True when the product's own currency is not the base currency (``base`` is converted)."""
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
        """Step 6: thin ranges borrow from their neighbours' leftovers, cheapest range first."""
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


def _with_base_prices(
    products: Sequence[ScoredProduct], settings: Settings
) -> tuple[list[tuple[ScoredProduct, float]], Counter[str]]:
    """Step 2: each product with its base-currency price, and a count by currency of the products
    that have none (no rate in settings) and so cannot be shaped."""
    priced: list[tuple[ScoredProduct, float]] = []
    without_rate: Counter[str] = Counter()
    for scored in products:
        base = to_base(scored.product.price, scored.product.currency, settings)
        if base is None:
            without_rate[scored.product.currency] += 1
        else:
            priced.append((scored, base))
    return priced, without_rate


def _no_rate_warning(without_rate: Counter[str], shaped: int) -> str:
    """The plain-language note for products left out because their currency has no rate."""
    listed = ", ".join(f"{count} in {name}" for name, count in sorted(without_rate.items()))
    if shaped:
        return (
            "The products came in more than one currency, and the app has no exchange rate for "
            f"some of them, so those ({listed}) were left out."
        )
    names = ", ".join(sorted(without_rate))
    return (
        f"The products are priced in {names}, and the app has no exchange rate for it, so none "
        f"of them ({listed}) could be shown."
    )


def _mark(candidate: _Candidate, tier: Tier) -> ScoredProduct:
    """The product as shown: placed in ``tier``, carrying ``over_budget`` exactly when it is, and
    ``base_price`` exactly when its own currency is not the base currency.

    The shaper owns both: they are recomputed from the budget and the rates passed in, so a
    re-shape with a different budget or rate (or none) never keeps a stale flag or figure from an
    earlier step.
    """
    flags: list[Flag] = [flag for flag in candidate.scored.flags if flag is not Flag.OVER_BUDGET]
    if candidate.over_budget:
        flags.append(Flag.OVER_BUDGET)
    base_price = candidate.base if candidate.converted else None
    return candidate.scored.model_copy(
        update={"tier": tier, "flags": flags, "base_price": base_price}
    )


def _span(picks: Sequence[_Candidate]) -> tuple[float, float]:
    """The lowest and highest base-currency price in a range.

    A range holding a converted product is widened outward to whole base units (the lower end
    down, the upper end up): a converted figure comes from a fixed, approximate rate, so a header
    must not claim cents, and the span still covers every product in it. A range of products
    priced in the base currency keeps its exact prices. A lower end under 1 is left as it is,
    because a span may not start at 0.
    """
    prices = [candidate.base for candidate in picks]
    low, high = min(prices), max(prices)
    if any(candidate.converted for candidate in picks):
        high = float(math.ceil(high))
        if low >= 1:
            low = float(math.floor(low))
    return low, high


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
    low, high = _span(ordered) if ordered else (None, None)
    return TierResult(
        name=tier,
        price_min=low,
        price_max=high,
        currency=currency if ordered else None,
        target_count=target,
        count=len(ordered),
        flags=flags,
        results=[_mark(c, tier) for c in ordered],
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
    shaped, without_rate = _with_base_prices(prepared, settings)
    if without_rate:
        warnings.append(_no_rate_warning(without_rate, len(shaped)))
        log.warning(
            "products in other currencies left out: no exchange rate",
            extra={"base_currency": settings.base_currency, "left_out": dict(without_rate)},
        )
    currency = settings.base_currency if shaped else None

    ceiling: float | None = None
    if budget is not None and currency is not None:
        ceiling = to_base(budget.max_price, budget.currency, settings)
        if ceiling is None:
            warnings.append(
                f"Your budget is in {budget.currency} but the prices found are in {currency}, "
                "so the budget was not applied."
            )
            log.warning(
                "budget currency has no exchange rate, budget not applied",
                extra={"budget_currency": budget.currency, "base_currency": currency},
            )

    borders: PriceBorders | None = None
    pools: dict[Tier, list[_Candidate]] = {tier: [] for tier in TIER_ORDER}
    if shaped:
        borders = compute_borders([base for _, base in shaped])
        for index, (scored, base) in enumerate(shaped):
            candidate = _Candidate(
                index=index,
                scored=scored,
                base=base,
                converted=scored.product.currency != settings.base_currency,
                natural=borders.tier_for(base),
                over_budget=ceiling is not None and base > ceiling,
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
