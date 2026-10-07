"""The candidate dump (plan 13.2.4): every ranked candidate of a request, one JSON line each.

With ``VGA_DEBUG_DUMP=1`` (``Settings.debug_dump``) each request writes
``<log_dir>/candidates-<request_id>.jsonl``. It answers "why was this product (not) shown?" when
the ranking is tuned, and it is how the fetch stage and the rank stage are told apart: a product
missing here was never returned or was filtered, one present but unshown was outranked.

A line holds the product link, store, title, price, the scores, the price range it was placed in
(``null`` when it was ranked but not shown), the range's price span and the extraction strategy that
read the store. It holds no image data of any kind: no photo, no embedding, not even the product
thumbnail's address.
"""

import json
from pathlib import Path
from typing import Any

from vga.log import get_logger
from vga.models import GarmentGroup, Product, ScoredProduct, StoreConfig, Tier
from vga.pipeline.reports import outcomes_for_item
from vga.pipeline.state import ItemRun, RunState

log = get_logger(__name__)


def dump_path(log_dir: str | Path, request_id: str) -> Path:
    return Path(log_dir) / f"candidates-{request_id}.jsonl"


def write_candidate_dump(state: RunState) -> Path | None:
    """Write the dump for ``state`` and return its path, or ``None`` when it could not be written.

    A dump that fails never fails the request: debugging output is not worth a lost search.
    """
    strategies = _strategies(state)
    lines = [
        json.dumps(line, ensure_ascii=False)
        for run in state.items
        for line in _item_lines(state.req.request_id, run, strategies)
    ]
    path = dump_path(state.settings.log_dir, state.req.request_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    except OSError as exc:
        log.warning(
            "candidate dump could not be written",
            extra={"path": str(path), "reason": type(exc).__name__},
        )
        return None
    log.info("candidate dump written", extra={"path": str(path), "candidates": len(lines)})
    return path


def _strategies(state: RunState) -> dict[str, str | None]:
    """The extraction strategy of each store, by the store's display name (``Product.store``)."""
    by_id: dict[str, StoreConfig] = {store.id: store for store in state.active_stores}
    strategies: dict[str, str | None] = {}
    for run in state.items:
        for outcome in outcomes_for_item(run):
            store = by_id.get(outcome.report.store_id)
            if store is not None and outcome.report.strategy:
                strategies.setdefault(store.display_name, outcome.report.strategy)
    return strategies


def _item_lines(
    request_id: str, run: ItemRun, strategies: dict[str, str | None]
) -> list[dict[str, Any]]:
    shown = _shown(run.group)
    lines: list[dict[str, Any]] = []
    for rank, scored in enumerate(run.ranked or [], start=1):
        product = scored.product
        placed = shown.get(product.key)
        lines.append(_line(request_id, run, rank, scored, product, placed, strategies))
    return lines


def _shown(group: GarmentGroup | None) -> dict[str, tuple[Tier, float | None, float | None]]:
    """Product key to the price range it was shown in, with that range's price span."""
    shown: dict[str, tuple[Tier, float | None, float | None]] = {}
    if group is None:
        return shown
    for tier in group.tiers:
        for scored in tier.results:
            shown[scored.product.key] = (tier.name, tier.price_min, tier.price_max)
    return shown


def _line(
    request_id: str,
    run: ItemRun,
    rank: int,
    scored: ScoredProduct,
    product: Product,
    placed: tuple[Tier, float | None, float | None] | None,
    strategies: dict[str, str | None],
) -> dict[str, Any]:
    scores = scored.scores
    return {
        "request_id": request_id,
        "item_index": run.index,
        "category": run.item.category.value,
        "rank": rank,
        "url": product.product_url,
        "store": product.store,
        "strategy": strategies.get(product.store),
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "scores": {
            "text": scores.text,
            "image": scores.image,
            "price": scores.price,
            "total": scores.total,
        },
        "flags": [flag.value for flag in scored.flags],
        "shown": placed is not None,
        "price_range": placed[0].value if placed else None,
        "price_range_min": placed[1] if placed else None,
        "price_range_max": placed[2] if placed else None,
    }
