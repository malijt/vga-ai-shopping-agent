"""Builders for valid contract objects, shared by every phase's tests.

Each ``make_*`` function returns a valid object with sensible defaults; pass keyword arguments to
override any field. Use these instead of writing models by hand so a contract change touches one
file. Builders are deterministic (no randomness) except the request id, which follows the model.
"""

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from vga.models import (
    Budget,
    Category,
    ChipEdits,
    ExtractionConfig,
    Flag,
    GarmentGroup,
    GenderSource,
    InputType,
    ItemIntent,
    Product,
    ScoredProduct,
    Scores,
    SearchRequest,
    SearchResponse,
    StepTiming,
    StoreConfig,
    StoreReport,
    StoreResult,
    StoreStatus,
    StrategyConfig,
    Tier,
    TierResult,
    UnderstandResult,
    Usage,
)
from vga.settings import Settings

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_RESPONSE_PATH = FIXTURES_DIR / "response_sample.json"

DEMO_STORE_ID = "demo-store"
DEMO_STORE_NAME = "Demo Store"
DEMO_HOST = "www.demo-store.example"
DEMO_IMAGE_HOST = "cdn.demo-store.example"

__all__ = [
    "load_sample_response",
    "make_budget",
    "make_chip_edits",
    "make_garment_group",
    "make_image_bytes",
    "make_item_intent",
    "make_product",
    "make_products",
    "make_scored_product",
    "make_scores",
    "make_search_request",
    "make_search_response",
    "make_settings",
    "make_store_config",
    "make_store_report",
    "make_store_result",
    "make_tier_result",
    "make_understand_result",
]


def make_budget(**overrides: Any) -> Budget:
    return Budget.model_validate({"max_price": 400, "currency": "AED", **overrides})


def make_item_intent(**overrides: Any) -> ItemIntent:
    """Black oversized blazer, no gender known."""
    fields: dict[str, Any] = {
        "category": Category.OUTERWEAR,
        "colour": "black",
        "style": "oversized blazer",
        "material": None,
        "gender": None,
        "gender_source": GenderSource.NONE,
        "search_keywords": ["black oversized blazer", "oversized blazer"],
    }
    return ItemIntent.model_validate({**fields, **overrides})


def make_understand_result(**overrides: Any) -> UnderstandResult:
    fields: dict[str, Any] = {
        "input_type": InputType.TEXT,
        "items": [make_item_intent()],
        "budget": None,
        "edits": [],
        "language": "en",
        "prompt_version": "test-1",
        "model": "test-model-2026-01-01",
        "usage": Usage(input_tokens=120, output_tokens=40, llm_calls=1),
        "warnings": [],
    }
    return UnderstandResult.model_validate({**fields, **overrides})


def make_search_request(**overrides: Any) -> SearchRequest:
    """A text request unless ``text``/``image`` are given."""
    if "text" not in overrides and "image" not in overrides:
        overrides["text"] = "black oversized blazer for men under 400 AED"
    return SearchRequest.model_validate(overrides)


def make_chip_edits(**overrides: Any) -> ChipEdits:
    return ChipEdits.model_validate(overrides)


def make_store_config(**overrides: Any) -> StoreConfig:
    """An enabled demo store whose hosts are on the reserved ``.example`` domain."""
    fields: dict[str, Any] = {
        "id": DEMO_STORE_ID,
        "name": DEMO_STORE_NAME,
        "country": "AE",
        "currency": "AED",
        "search_url_template": f"https://{DEMO_HOST}/search?q={{query}}",
        "allowed_hosts": [DEMO_HOST, DEMO_IMAGE_HOST],
        "extraction": ExtractionConfig(
            strategies=[
                StrategyConfig(
                    name="store_json",
                    fields={
                        "title": "name",
                        "price": "price.value",
                        "image_url": "image",
                        "product_url": "url",
                    },
                    options={"items_path": "products"},
                )
            ]
        ),
        "enabled": True,
    }
    return StoreConfig.model_validate({**fields, **overrides})


def make_product(index: int = 1, **overrides: Any) -> Product:
    """A valid product; ``index`` makes the title, URLs and price unique and predictable."""
    store_name = overrides.get("store", DEMO_STORE_NAME)
    slug = str(store_name).lower().replace(" ", "-")
    fields: dict[str, Any] = {
        "title": f"Oversized Wool Blazer {index}",
        "price": 100.0 + 25.0 * index,
        "currency": "AED",
        "image_url": f"https://cdn.{slug}.example/img/blazer-{index}.jpg",
        "product_url": f"https://www.{slug}.example/p/oversized-wool-blazer-{index}",
        "store": DEMO_STORE_NAME,
        "colour": "black",
        "in_stock": True,
        "category": Category.OUTERWEAR,
    }
    return Product.model_validate({**fields, **overrides})


def make_products(count: int, *, start: int = 1, **overrides: Any) -> list[Product]:
    """``count`` distinct products with rising prices (index ``start`` upwards)."""
    return [make_product(index, **overrides) for index in range(start, start + count)]


def make_scores(**overrides: Any) -> Scores:
    fields: dict[str, Any] = {"text": 0.8, "image": None, "price": 0.5, "total": 0.7}
    return Scores.model_validate({**fields, **overrides})


def make_scored_product(product: Product | None = None, **overrides: Any) -> ScoredProduct:
    fields: dict[str, Any] = {
        "product": product or make_product(),
        "scores": make_scores(),
        "tier": None,
        "reason": "Matches your colour.",
        "flags": [],
    }
    return ScoredProduct.model_validate({**fields, **overrides})


def make_tier_result(
    name: Tier = Tier.BUDGET,
    products: Sequence[Product] | None = None,
    *,
    target_count: int | None = None,
    flags: Sequence[Flag] = (),
) -> TierResult:
    """A price range holding ``products`` (default: two), with the real span computed from them."""
    items = list(products) if products is not None else make_products(2)
    prices = [item.price for item in items]
    return TierResult(
        name=name,
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
        currency=items[0].currency if items else None,
        target_count=len(items) if target_count is None else target_count,
        count=len(items),
        flags=list(flags),
        results=[make_scored_product(item, tier=name) for item in items],
    )


def make_garment_group(
    category: Category = Category.OUTERWEAR,
    *,
    item_index: int = 0,
    per_tier: int = 2,
) -> GarmentGroup:
    """Four price ranges of ``per_tier`` products each, prices rising from range to range."""
    tiers: list[TierResult] = []
    for position, name in enumerate(Tier):
        start = 1 + position * per_tier
        products = [
            make_product(index, category=category, price=50.0 * index)
            for index in range(start, start + per_tier)
        ]
        tiers.append(make_tier_result(name, products))
    return GarmentGroup(item_index=item_index, category=category, tiers=tiers)


def make_store_result(
    status: StoreStatus = StoreStatus.OK,
    *,
    store_id: str = DEMO_STORE_ID,
    products: Sequence[Product] | None = None,
    **overrides: Any,
) -> StoreResult:
    """``ok`` results carry three products by default; any other status carries none."""
    if status is StoreStatus.OK:
        items = list(products) if products is not None else make_products(3)
    else:
        items = []
    fields: dict[str, Any] = {
        "store_id": store_id,
        "status": status,
        "products": items,
        "duration_ms": 120.0,
        "strategy": "store_json" if status is StoreStatus.OK else None,
        "from_cache": False,
    }
    return StoreResult.model_validate({**fields, **overrides})


def make_store_report(
    status: StoreStatus = StoreStatus.OK,
    *,
    store_id: str = DEMO_STORE_ID,
    **overrides: Any,
) -> StoreReport:
    """A report for a used store (``ok``) or, for any other status, a skipped one with a reason."""
    fields: dict[str, Any] = {
        "store_id": store_id,
        "status": status,
        "product_count": 3 if status is StoreStatus.OK else 0,
        "duration_ms": 120.0,
        "strategy": "store_json" if status is StoreStatus.OK else None,
        "reason": None if status is StoreStatus.OK else "This store did not respond in time.",
    }
    return StoreReport.model_validate({**fields, **overrides})


def make_search_response(**overrides: Any) -> SearchResponse:
    """A one-garment response: four price ranges of two products each, one store used."""
    request = make_search_request()
    fields: dict[str, Any] = {
        "request_id": request.request_id,
        "understood": make_understand_result(),
        "groups": [make_garment_group()],
        "stores_used": [make_store_report()],
        "stores_skipped": [],
        "timings": [StepTiming(step="understand", duration_ms=900.0)],
        "usage": Usage(input_tokens=120, output_tokens=40, llm_calls=1),
        "warnings": [],
        "duration_ms": 4200.0,
    }
    return SearchResponse.model_validate({**fields, **overrides})


def make_settings(**overrides: Any) -> Settings:
    """Settings from the code defaults only: reads no file and no environment variable."""
    return Settings.model_validate(overrides)


def load_sample_response() -> SearchResponse:
    """The bundled sample: an outfit photo with two garments, one thin price range, one skipped
    store, a very long title, a missing colour and over-budget items."""
    return SearchResponse.model_validate_json(SAMPLE_RESPONSE_PATH.read_text(encoding="utf-8"))


def make_image_bytes(
    fmt: str = "PNG", size: tuple[int, int] = (16, 16), colour: tuple[int, int, int] = (190, 40, 40)
) -> bytes:
    """A real, tiny image (``PNG``, ``JPEG`` or ``WEBP``) for tests that need valid photo bytes."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format=fmt)
    return buffer.getvalue()
