"""Builders for the harness tests: queries, responses with exact counts, and a toy pipeline.

Responses are built from ``tests.factories`` so a contract change touches one file. The toy
pipeline stands in for the real pipeline of Phase 13 (which does not exist yet) so the
record-then-replay tests can run "a pipeline built from three boundaries" end to end.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from eval.harness.labels import LabelSet, label_rows
from eval.harness.links import LinkCheck
from eval.harness.queries import AcceptanceQuery
from eval.harness.runner import QueryRun
from tests.factories import (
    make_item_intent,
    make_product,
    make_scored_product,
    make_scores,
    make_store_report,
    make_understand_result,
)
from vga.interfaces import ImageRanker, StoreSearcher, Understander
from vga.models import (
    Category,
    Flag,
    GarmentGroup,
    ItemIntent,
    QueryImage,
    ScoredProduct,
    SearchRequest,
    SearchResponse,
    StepTiming,
    StoreConfig,
    StoreStatus,
    Tier,
    TierResult,
    Usage,
)
from vga.settings import Settings

STORE_NAMES = ("Alpha Store", "Beta Store", "Gamma Store", "Delta Store")
PHOTO_PATH = "eval/data/assets/private/dress_burgundy_gown.png"


def make_query(
    query_id: str = "q01_product_gown", kind: str = "text", **overrides: Any
) -> AcceptanceQuery:
    """A valid query of ``kind``; photo kinds get a placeholder photo path (it need not exist)."""
    has_text = kind in {"text", "photo_text"}
    has_image = kind != "text"
    fields: dict[str, Any] = {
        "id": query_id,
        "type": kind,
        "text": "black oversized blazer" if has_text else None,
        "image": PHOTO_PATH if has_image else None,
        "notes": "A test query.",
    }
    return AcceptanceQuery.model_validate({**fields, **overrides})


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def make_group(
    category: Category = Category.OUTERWEAR,
    *,
    counts: Sequence[int] = (8, 8, 7, 7),
    targets: Sequence[int] | None = None,
    flags: Mapping[Tier, Sequence[Flag]] | None = None,
    stores: Sequence[str] = STORE_NAMES[:3],
    item_index: int = 0,
    total: Callable[[int], float] | None = None,
) -> GarmentGroup:
    """One garment group with ``counts[i]`` results in price range ``i``.

    Prices rise from range to range. Products are spread over ``stores`` in turn, their URLs are
    unique across groups, and ``total`` maps a result's overall position (0 = first displayed)
    to its overall score; by default the first displayed result scores highest.
    """
    wanted = tuple(targets) if targets is not None else tuple(counts)
    score_of = total or (lambda position: max(0.0, 0.99 - position * 0.01))
    tiers: list[TierResult] = []
    position = 0
    for tier_index, tier in enumerate(Tier):
        results: list[ScoredProduct] = []
        for within in range(counts[tier_index]):
            store = stores[position % len(stores)]
            name = f"{category.value}-{item_index}-{position + 1}"
            product = make_product(
                position + 1,
                title=f"{category.value.title()} item {position + 1}",
                price=100.0 * (tier_index + 1) + within,
                store=store,
                category=category,
                image_url=f"https://cdn.{slug(store)}.example/img/{name}.jpg",
                product_url=f"https://www.{slug(store)}.example/p/{name}",
            )
            scores = make_scores(total=score_of(position))
            results.append(make_scored_product(product, scores=scores, tier=tier))
            position += 1
        prices = [item.product.price for item in results]
        tiers.append(
            TierResult(
                name=tier,
                price_min=min(prices) if prices else None,
                price_max=max(prices) if prices else None,
                currency="AED" if results else None,
                target_count=wanted[tier_index],
                count=len(results),
                flags=list((flags or {}).get(tier, [])),
                results=results,
            )
        )
    return GarmentGroup(item_index=item_index, category=category, tiers=tiers)


def make_response(
    groups: Sequence[GarmentGroup] | None = None,
    *,
    duration_ms: float = 5000.0,
    skipped: Sequence[str] = (),
    timings: Sequence[StepTiming] | None = None,
    **overrides: Any,
) -> SearchResponse:
    """A response around ``groups`` (default: one full group). Stores come from the products."""
    chosen = list(groups) if groups is not None else [make_group()]
    understood = make_understand_result(
        items=[make_item_intent(category=group.category) for group in chosen]
        or [make_item_intent()]
    )
    per_store: dict[str, int] = {}
    for group in chosen:
        for tier in group.tiers:
            for scored in tier.results:
                per_store[scored.product.store] = per_store.get(scored.product.store, 0) + 1
    used = [
        make_store_report(store_id=slug(name), product_count=count, strategy="shopify")
        for name, count in per_store.items()
    ]
    skipped_reports = [
        make_store_report(
            StoreStatus.BLOCKED, store_id=name, reason="This store did not allow the search."
        )
        for name in skipped
    ]
    fields: dict[str, Any] = {
        "request_id": "r" * 32,
        "understood": understood,
        "groups": chosen,
        "stores_used": used,
        "stores_skipped": skipped_reports,
        "timings": list(timings) if timings is not None else [],
        "usage": Usage(input_tokens=100, output_tokens=20, llm_calls=1),
        "warnings": [],
        "duration_ms": duration_ms,
    }
    return SearchResponse.model_validate({**fields, **overrides})


def ok_links(response: SearchResponse, only_top: int | None = None) -> list[LinkCheck]:
    """Passing link checks for every result (or only the first ``only_top`` displayed)."""
    products = [scored.product for scored in response.products]
    chosen = products if only_top is None else products[:only_top]
    return [
        LinkCheck(url=p.product_url, store=p.store, product_title=p.title, ok=True) for p in chosen
    ]


def labels_for(run: QueryRun, good_in_group: dict[str, int]) -> LabelSet:
    """Label the first ``good_in_group[group]`` ranks of each group good, the rest not good."""
    rows = [
        replace(row, label=1 if row.rank <= good_in_group[row.group] else 0)
        for row in label_rows([run])
    ]
    return LabelSet(tuple(rows))


class ToyPipeline:
    """A tiny pipeline built from the three boundaries, for the record/replay tests.

    Understand, then search each garment, score images, rank by overall score and split the
    products into four equal price ranges. It is not the real pipeline (Phase 13); it only has to
    use the three boundaries the way the real one does, so the recorders and stand-ins are
    exercised through a pipeline built by a factory.
    """

    def __init__(
        self,
        understander: Understander,
        searcher: StoreSearcher,
        image_ranker: ImageRanker,
        stores: Sequence[StoreConfig],
    ) -> None:
        self._understander = understander
        self._searcher = searcher
        self._image_ranker = image_ranker
        self._stores = list(stores)

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: object = None,
        on_step: object = None,
    ) -> SearchResponse:
        understood = await self._understander.understand(req)
        groups: list[GarmentGroup] = []
        reports = []
        for index, item in enumerate(understood.items):
            results = await self._searcher.search(item, self._stores)
            products = [product for result in results for product in result.products]
            query = QueryImage(image=req.image) if req.image is not None else None
            image_scores = await self._image_ranker.score(query, products)
            groups.append(self._group(index, item, products, image_scores))
            if index == 0:
                reports = [
                    make_store_report(
                        result.status,
                        store_id=result.store_id,
                        product_count=len(result.products),
                        strategy=result.strategy,
                    )
                    for result in results
                ]
        return SearchResponse(
            request_id=req.request_id,
            understood=understood,
            groups=groups,
            stores_used=[r for r in reports if r.status is StoreStatus.OK],
            stores_skipped=[r for r in reports if r.status is not StoreStatus.OK],
            usage=understood.usage,
            duration_ms=1234.0,
        )

    @staticmethod
    def _group(
        index: int,
        item: ItemIntent,
        products: list[Any],
        image_scores: dict[str, float | None],
    ) -> GarmentGroup:
        scored: list[ScoredProduct] = []
        for product in sorted(products, key=lambda p: p.price):
            image = image_scores.get(product.key)
            total = 0.7 if image is None else 0.5 + 0.4 * image
            scored.append(
                make_scored_product(product, scores=make_scores(image=image, total=min(total, 1.0)))
            )
        size, extra = divmod(len(scored), 4)
        tiers: list[TierResult] = []
        start = 0
        for position, tier in enumerate(Tier):
            end = start + size + (1 if position < extra else 0)
            chunk = [item.model_copy(update={"tier": tier}) for item in scored[start:end]]
            prices = [entry.product.price for entry in chunk]
            tiers.append(
                TierResult(
                    name=tier,
                    price_min=min(prices) if prices else None,
                    price_max=max(prices) if prices else None,
                    currency=chunk[0].product.currency if chunk else None,
                    target_count=len(chunk),
                    count=len(chunk),
                    results=chunk,
                )
            )
            start = end
        return GarmentGroup(item_index=index, category=item.category, tiers=tiers)
