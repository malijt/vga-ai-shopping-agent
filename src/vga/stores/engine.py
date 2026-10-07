"""The store search engine: ``StoreSearcher`` plus thumbnail fetching (plan 6.5.4 and 6.5.5).

``StoreSearchEngine.search`` runs one task per store, in parallel. For each store it:

1. skips it, with no request, if it is not ``enabled`` or is not in the configured country;
2. skips it, with no request, while it is in cooldown after a block;
3. for each of the item's keyword variants (at most ``max_variants``), in order: answers from the
   cache if it can, else checks robots.txt, fetches the search page and reads it through the
   store's extraction chain; a redirect is followed only after the robots.txt of the page it leads
   to (another host of the store, say) allows it; it stops at the first variant that is blocked,
   refused, slow or broken, because asking again the same way would only repeat the failure;
4. merges the variants into one ``StoreResult``.

Every outcome is a ``StoreResult``; nothing a store does, and no bug in one store's code path, can
raise out of ``search`` or touch another store's result. There are **no retries to stores**
(politeness, and the 30 s deadline): a failure is reported, and the next *search* decides whether to
ask again.

``fetch_image`` lives on the same object because it needs the same client (rules, rate limits,
cooldowns) and the same store registry (to find the store a product came from).
"""

import asyncio
from collections.abc import Sequence

import httpx

from vga.fetch.allowlist import check_url
from vga.fetch.client import IMAGE_TIMEOUT_S, PoliteClient
from vga.fetch.deadline import run_with_deadline
from vga.fetch.errors import FetchError
from vga.fetch.robots import RobotsChecker
from vga.interfaces import Clock, SystemClock
from vga.log import get_logger
from vga.models import ItemIntent, Product, StoreConfig, StoreResult, StoreStatus
from vga.settings import Settings
from vga.stores.cache import ResultCache, variant_key
from vga.stores.extractors import ExtractionChain, ExtractorRegistry, default_registry
from vga.stores.normalise import dedupe_products
from vga.stores.registry import StoreRegistry
from vga.stores.urls import build_search_url

log = get_logger(__name__)


_FAILURE_PRIORITY = (
    StoreStatus.BLOCKED,
    StoreStatus.ROBOTS_DENIED,
    StoreStatus.COOLDOWN,
    StoreStatus.TIMEOUT,
    StoreStatus.ERROR,
)
_KEEP_GOING = frozenset({StoreStatus.OK, StoreStatus.EMPTY})


class StoreSearchEngine:
    """Searches stores for an item and fetches product thumbnails. Implements ``StoreSearcher``.

    ``registry`` holds the stores the engine knows (it also learns every store passed to
    ``search``); ``fetch_image`` uses it to find a product's store. ``clock`` and ``transport`` are
    for tests; ``extractors`` lets a test (or a later phase) register more strategies.
    """

    def __init__(
        self,
        settings: Settings,
        registry: StoreRegistry | None = None,
        *,
        clock: Clock | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        extractors: ExtractorRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry or StoreRegistry()
        self.clock: Clock = clock or SystemClock()
        self.client = PoliteClient(settings, clock=self.clock, transport=transport)
        self.robots = RobotsChecker(self.client)
        self.cache = ResultCache(self.clock, settings.store_cache_ttl_s)
        self._extractors = extractors or default_registry()
        self._chain = ExtractionChain(self._extractors)

    async def aclose(self) -> None:
        await self.client.aclose()

    # ------------------------------------------------------------------------------------
    # StoreSearcher
    # ------------------------------------------------------------------------------------

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        """One ``StoreResult`` per store, in the order of ``stores``. Never raises for a store."""
        for store in stores:
            self.registry.add(store)
        results = await asyncio.gather(*(self._search_store(item, store) for store in stores))
        return list(results)

    async def _search_store(self, item: ItemIntent, store: StoreConfig) -> StoreResult:
        started = self.clock.monotonic()
        try:
            result = await self._search_store_unsafe(item, store, started)
        except Exception as exc:  # complete isolation: one store's bug never reaches the others
            log.exception("store search crashed", extra={"store": store.id})
            result = StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=self._elapsed_ms(started),
                detail=f"unexpected {type(exc).__name__}",
            )
        log.info(
            "store search finished",
            extra={
                "store": store.id,
                "status": result.status.value,
                "products": len(result.products),
                "duration_ms": result.duration_ms,
                "strategy": result.strategy,
                "from_cache": result.from_cache,
                "detail": result.detail,
            },
        )
        return result

    async def _search_store_unsafe(
        self, item: ItemIntent, store: StoreConfig, started: float
    ) -> StoreResult:
        skip = self._skip_reason(store)
        if skip is not None:
            log.warning("store skipped; no request made", extra={"store": store.id, "reason": skip})
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=self._elapsed_ms(started),
                detail=skip,
            )

        variants = self._variants(item, store)
        # One budget for robots.txt and one per variant: the requests run one after another.
        timeout_s = (store.timeout_s or self.settings.timeout_s) * (len(variants) + 1)
        done: list[StoreResult] = []
        timed_out = False
        try:
            await run_with_deadline(
                self.clock, timeout_s, self._search_variants(store, variants, done)
            )
        except TimeoutError:
            timed_out = True
            log.warning(
                "store search timed out",
                extra={"store": store.id, "timeout_s": timeout_s, "variants_done": len(done)},
            )
        return self._merge(store, done, self._elapsed_ms(started), timed_out=timed_out)

    async def _search_variants(
        self, store: StoreConfig, variants: list[str], done: list[StoreResult]
    ) -> None:
        for variant in variants:
            result = await self._search_variant(store, variant)
            done.append(result)
            if result.status not in _KEEP_GOING:
                return  # asking again the same way would only repeat the failure

    async def _search_variant(self, store: StoreConfig, variant: str) -> StoreResult:
        """Search one store for one query variant. Always returns a result."""
        started = self.clock.monotonic()
        remaining = self.client.cooldowns.remaining(store.id)
        if remaining > 0:
            log.warning(
                "store in cooldown; no request made",
                extra={"store": store.id, "remaining_s": round(remaining)},
            )
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.COOLDOWN,
                detail=f"blocked recently; {remaining:.0f} s of cooldown left",
            )

        cached = self.cache.get(store.id, variant)
        if cached is not None:
            log.info(
                "cache hit; no request made",
                extra={"store": store.id, "variant": variant, "status": cached.status.value},
            )
            return cached.model_copy(update={"duration_ms": self._elapsed_ms(started)})

        result = await self._fetch_and_extract(store, variant, started)
        self.cache.put(store.id, variant, result)
        return result

    async def _fetch_and_extract(
        self, store: StoreConfig, variant: str, started: float
    ) -> StoreResult:
        try:
            url = build_search_url(store, variant)
        except ValueError as exc:  # an unusable query (empty after cleaning)
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=self._elapsed_ms(started),
                detail=str(exc),
            )
        try:
            await self.robots.ensure_allowed(url, store)
            response = await self.client.fetch(
                url, store, self.client.page_policy(store), vet_redirect=self.robots.ensure_allowed
            )
        except FetchError as exc:
            return StoreResult(
                store_id=store.id,
                status=exc.store_status,
                duration_ms=self._elapsed_ms(started),
                detail=exc.detail or str(exc),
            )

        if not response.ok:
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=self._elapsed_ms(started),
                detail=f"HTTP {response.status} from the search page",
            )

        outcome = self._chain.run(response.text, store, response.url)
        duration = self._elapsed_ms(started)
        if outcome.products:
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.OK,
                products=outcome.products,
                duration_ms=duration,
                strategy=outcome.strategy,
                dropped=outcome.dropped,
            )
        if outcome.examined > 0:
            reasons = ", ".join(f"{name} x{count}" for name, count in outcome.dropped.items())
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=duration,
                dropped=outcome.dropped,
                detail=f"all {outcome.examined} records were dropped ({reasons})",
            )
        if outcome.ran_cleanly == 0:
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.ERROR,
                duration_ms=duration,
                detail="no extraction strategy could read the response: "
                + "; ".join(outcome.errors),
            )
        return StoreResult(store_id=store.id, status=StoreStatus.EMPTY, duration_ms=duration)

    # ------------------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------------------

    def _skip_reason(self, store: StoreConfig) -> str | None:
        """Why this store is not searched at all (no request, not even robots.txt), or ``None``."""
        if not store.enabled:
            return "the store is not enabled"
        if store.country != self.settings.country:
            return f"the store is for {store.country}, not the configured country"
        names = [strategy.name for strategy in store.extraction.strategies]
        if not any(self._extractors.get(name) for name in names):
            return f"no extraction strategy of this store is built (it asks for {names})"
        return None

    @staticmethod
    def _variants(item: ItemIntent, store: StoreConfig) -> list[str]:
        """The item's distinct keyword variants, in order, at most ``store.max_variants``."""
        distinct: dict[str, str] = {}
        for keyword in item.search_keywords:
            distinct.setdefault(variant_key(keyword), keyword)
        variants = list(distinct.values())
        return variants[: store.max_variants] if store.max_variants else variants

    def _elapsed_ms(self, started: float) -> float:
        return round(max(self.clock.monotonic() - started, 0.0) * 1000, 3)

    def _merge(
        self,
        store: StoreConfig,
        results: Sequence[StoreResult],
        duration_ms: float,
        *,
        timed_out: bool,
    ) -> StoreResult:
        """One result for the store from its variants' results."""
        successes = [result for result in results if result.status is StoreStatus.OK]
        dropped: dict[str, int] = {}
        for result in results:
            for reason, count in result.dropped.items():
                dropped[reason] = dropped.get(reason, 0) + count
        details = list(dict.fromkeys(r.detail for r in results if r.detail))
        if timed_out:
            details.append("the store did not finish all its searches in time")

        if successes:
            products, repeats = dedupe_products([p for r in successes for p in r.products])
            if repeats:
                log.info(
                    "variants overlapped; repeats collapsed",
                    extra={"store": store.id, "collapsed": sum(repeats.values())},
                )
            return StoreResult(
                store_id=store.id,
                status=StoreStatus.OK,
                products=products,
                duration_ms=duration_ms,
                strategy=successes[0].strategy,
                from_cache=all(result.from_cache for result in results),
                dropped=dropped,
                detail="; ".join(details) or None,
            )

        status = StoreStatus.EMPTY
        if timed_out:
            status = StoreStatus.TIMEOUT
        else:
            for failure in _FAILURE_PRIORITY:
                if any(result.status is failure for result in results):
                    status = failure
                    break
        return StoreResult(
            store_id=store.id,
            status=status,
            duration_ms=duration_ms,
            from_cache=bool(results) and all(result.from_cache for result in results),
            dropped=dropped,
            detail="; ".join(details) or None,
        )

    # ------------------------------------------------------------------------------------
    # Thumbnails (6.5.5)
    # ------------------------------------------------------------------------------------

    async def fetch_image(self, product: Product) -> bytes | None:
        """The bytes of ``product``'s thumbnail, or ``None`` on any failure.

        Meant to be handed to the image ranker as a ``Callable[[Product], Awaitable[bytes |
        None]]``. It finds the product's store, checks the image URL is https and on that store's
        ``allowed_hosts``, checks the image host's robots.txt (fetched once per host and cached,
        like the store's own; a redirect target is checked the same way), takes a slot from the
        image-host rate limiter, allows 4 seconds,
        keeps the response size cap, never retries and keeps the bytes in memory only. The response
        must be an image (a challenge page or an error body is not). A robots refusal (or an
        unreadable robots.txt) gives ``None`` and is logged with its reason.
        """
        try:
            store = self.registry.by_display_name(product.store)
            if store is None:
                log.warning("image not fetched: unknown store", extra={"store_name": product.store})
                return None
            host = check_url(product.image_url, store.allowed_hosts)
            await self.robots.ensure_allowed(product.image_url, store)
            policy = self.client.image_policy(store, host, timeout_s=IMAGE_TIMEOUT_S)
            response = await self.client.fetch(
                product.image_url, store, policy, vet_redirect=self.robots.ensure_allowed
            )
        except asyncio.CancelledError:
            raise
        except FetchError as exc:
            log.info(
                "image not fetched",
                extra={"store_name": product.store, "reason": exc.code, "detail": exc.detail},
            )
            return None
        except Exception:
            log.exception("image fetch crashed", extra={"store_name": product.store})
            return None

        if not response.ok:
            log.info(
                "image not fetched: bad status",
                extra={"store": store.id, "status": response.status},
            )
            return None
        if not response.content_type.lower().startswith("image/"):
            log.info(
                "image not fetched: not an image",
                extra={"store": store.id, "content_type": response.content_type[:60]},
            )
            return None
        return response.body
