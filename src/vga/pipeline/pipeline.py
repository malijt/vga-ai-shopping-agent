"""``SearchPipeline``: the real ``Pipeline``. It wires the parts and owns every failure path.

One run, in order (each stage reports its ``Step`` to ``on_step`` and is timed):

1. validate   the request, on the server side (``validation.py``)
2. understand one OpenAI call, or the earlier understanding reused with the chip edits applied
3. search     every item (garment) is searched in its own task, started in item order, against the
              stores that sell for its stated gender; or reused from the re-run cache
4. filter     hard filters, text and price scores (``vga.rank.prefilter_and_score``)
5. rank       the best matches are chosen to be compared with the photo
6. image_rank the photo is compared with those products; the totals are recomputed
7. shape      four price ranges per item (``vga.tiers.build_group``)
8. assemble   the response: stores used and skipped, warnings, usage, timings

The whole run has one deadline (``Settings.request_deadline_s``, measured on the injected clock).
When it passes, whatever is still running is cancelled and the response is built from what the
stages had finished: every stage writes its partial result into the ``RunState`` as it goes, so
nothing is lost by stopping one half-way.

Failure policy: a failure degrades the result and says so. Each one is logged at warning level with
the request id and appears in ``SearchResponse.warnings``. Only input that cannot be searched, or a
request that ran out of time before it was even understood, raises a ``VgaError``.

The pipeline holds no per-request state except the re-run cache, so one instance serves any number
of runs, one after another or at the same time. It never writes the photo anywhere: after the image
step the photo is dropped and only its embedding (numbers) is kept, in the response.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager

from vga.errors import LlmError, VgaError
from vga.fetch.deadline import deadline
from vga.interfaces import (
    Clock,
    ImageRanker,
    StepCallback,
    StoreSearcher,
    SystemClock,
    Understander,
)
from vga.log import TimedStep, get_logger, request_context, timed
from vga.models import (
    GenderSource,
    Product,
    QueryImage,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    Step,
    StoreConfig,
    StoreResult,
    StoreStatus,
    UnderstandResult,
    Usage,
)
from vga.pipeline import messages
from vga.pipeline.dump import write_candidate_dump
from vga.pipeline.errors import RequestTimeoutError
from vga.pipeline.planning import (
    items_to_search,
    resolve_budget,
    settings_for_run,
    stores_for_item,
)
from vga.pipeline.reports import StoreSummary, outcomes_for_item, summarise
from vga.pipeline.rerun import CachedItem, CachedRun, RerunCache
from vga.pipeline.state import ItemRun, RunState
from vga.pipeline.validation import validate_request
from vga.rank import apply_image_scores, prefilter_and_score
from vga.rank.image import select_candidates
from vga.settings import Settings
from vga.stores import StoreRegistry
from vga.tiers import build_group, results_total
from vga.understand import (
    FALLBACK_MARKER,
    FALLBACK_WARNING,
    FALLBACK_WARNING_WITH_PHOTO,
    apply_overrides,
    effective_gender,
)

log = get_logger(__name__)


class SearchPipeline:
    """Wires the understander, the store searcher and the image ranker into one ``Pipeline``.

    ``stores`` is a ``StoreRegistry`` or a list of ``StoreConfig``; the stores searched are the
    ones ``StoreRegistry.active`` picks for the run's settings (enabled, in the configured country,
    and listed in ``settings.stores`` when that is not empty). ``clock`` times the deadline, the
    step timings and the re-run cache (default: the real clock). ``on_close`` is awaited by
    ``aclose``, for whatever the parts hold open (``build_pipeline`` passes the store engine's).

    To use it where a ``Callable[[Understander, StoreSearcher, ImageRanker], Pipeline]`` is wanted
    (the acceptance harness), bind the stores with ``vga.pipeline.pipeline_factory(stores)``.
    """

    def __init__(
        self,
        understander: Understander,
        searcher: StoreSearcher,
        image_ranker: ImageRanker,
        stores: StoreRegistry | Iterable[StoreConfig],
        *,
        clock: Clock | None = None,
        on_close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._understander = understander
        self._searcher = searcher
        self._image_ranker = image_ranker
        self._registry = stores if isinstance(stores, StoreRegistry) else StoreRegistry(stores)
        self._clock: Clock = clock or SystemClock()
        self._on_close = on_close
        self._cache = RerunCache(self._clock)

    # ------------------------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------------------------

    async def warm_up(self) -> bool:
        """Load the image model now so the first search does not wait for it. ``True`` when image
        scoring is ready (or the ranker needs no loading), ``False`` when it is unavailable."""
        warm = getattr(self._image_ranker, "warm_up", None)
        if warm is None:
            return True
        return bool(await warm())

    async def aclose(self) -> None:
        """Release what the parts hold open (the store engine's HTTP client)."""
        if self._on_close is not None:
            await self._on_close()

    # ------------------------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------------------------

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: StepCallback | None = None,
    ) -> SearchResponse:
        state = RunState(
            req=req, settings=settings, started=self._clock.monotonic(), on_step=on_step
        )
        with request_context(req.request_id):
            log.info(
                "search started",
                extra={
                    "has_text": req.text is not None,
                    "has_photo": req.image is not None,
                    "rerun_of": req.rerun_of,
                },
            )
            try:
                try:
                    async with deadline(self._clock, settings.request_deadline_s):
                        await self._stages(state, settings, overrides)
                except TimeoutError:
                    self._deadline_reached(state, settings)
                    self._finish_without_waiting(state)
            finally:
                await self._cancel_unfinished(state)
                if state.query is not None:
                    state.query.image = None  # BRD Rule 4: the photo is not kept
            response = self._assemble(state)
            self._remember(state)
            return response

    # ------------------------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------------------------

    async def _stages(
        self, state: RunState, settings: Settings, overrides: RunOverrides | None
    ) -> None:
        self._step(state, Step.VALIDATE)
        with self._stage(state, Step.VALIDATE.value):
            validate_request(state.req, overrides, settings)

        self._step(state, Step.UNDERSTAND)
        with self._stage(state, Step.UNDERSTAND.value) as handle:
            understood, fresh = await self._understand(state, overrides)
            if not fresh:
                handle.status = "reused"
        self._plan(state, settings, overrides, understood, fresh=fresh)

        await self._search(state)
        self._filter(state)
        self._rank(state)
        await self._image_rank(state)
        self._shape(state)

    async def _understand(
        self, state: RunState, overrides: RunOverrides | None
    ) -> tuple[UnderstandResult, bool]:
        """The understanding to search with, and whether the model was called for it."""
        earlier = overrides.understood if overrides is not None else None
        if earlier is not None:
            understood, fresh = earlier, False
        else:
            understood, fresh = await self._ask_the_model(state.req), True
            if understood.model == FALLBACK_MARKER or understood.prompt_version == FALLBACK_MARKER:
                log.warning(
                    "the model path failed; searching with the shopper's own words",
                    extra={"warnings": understood.warnings},
                )
                if not understood.warnings:
                    note = FALLBACK_WARNING_WITH_PHOTO if state.req.has_image else FALLBACK_WARNING
                    understood = understood.model_copy(update={"warnings": [note]})
        chips = overrides.chips if overrides is not None else None
        if chips is not None:
            understood = apply_overrides(understood, chips)
        return understood, fresh

    async def _ask_the_model(self, req: SearchRequest) -> UnderstandResult:
        try:
            return await self._understander.understand(req)
        except VgaError:
            raise
        except Exception as exc:  # a bug in the understander must not reach the shopper raw
            log.exception("the understander failed unexpectedly")
            raise LlmError(detail=f"understander raised {type(exc).__name__}") from exc

    def _plan(
        self,
        state: RunState,
        settings: Settings,
        overrides: RunOverrides | None,
        understood: UnderstandResult,
        *,
        fresh: bool,
    ) -> None:
        """Decide what will be searched: budget, mix, stores per item, what the cache can answer."""
        state.understood = understood
        state.reused_understanding = not fresh
        state.usage = understood.usage if fresh else Usage()
        state.budget = resolve_budget(understood, overrides)
        state.settings, cheaper_default = settings_for_run(
            settings, overrides, understood, state.budget
        )

        for note in understood.warnings:
            state.warn(note)
        if cheaper_default:
            state.warn(messages.CHEAPER_WITHOUT_BUDGET)
        for item in understood.items:
            if item.gender is not None and item.gender_source is GenderSource.INFERRED:
                state.warn(messages.inferred_gender_note(item.gender))

        state.active_stores = self._registry.active(state.settings)
        if not state.active_stores:
            log.warning("no store is enabled for this search")
            state.warn(messages.NO_STORES_CONFIGURED)

        # A re-run reuses the earlier search only when it carries no new photo: a new photo is a
        # new search, and the earlier image scores belong to the earlier photo.
        reusable = state.req.rerun_of is not None and state.req.image is None
        state.previous = self._cache.get(state.req.rerun_of) if reusable else None
        for index, item in enumerate(items_to_search(understood)):
            searched, skipped = stores_for_item(state.active_stores, item)
            run = ItemRun(index=index, item=item, stores=searched, gender_skipped=skipped)
            run.cached = self._cache.reusable(
                state.previous, index, item, tuple(store.id for store in searched)
            )
            state.items.append(run)

        embedding = overrides.query_embedding if overrides is not None else None
        if embedding is None and state.previous is not None and state.previous.query_embedding:
            embedding = list(state.previous.query_embedding)
        if state.req.image is not None:
            state.query = QueryImage(image=state.req.image)
        elif embedding:
            state.query = QueryImage(embedding=list(embedding))

    async def _search(self, state: RunState) -> None:
        pending: list[ItemRun] = []
        for run in state.items:
            if run.cached is not None:
                continue
            if run.stores:
                pending.append(run)
            else:
                run.results = []  # nothing to ask: no store sells for this item's gender
                self._log_no_store(state, run)
        if not pending:
            return

        self._step(state, Step.SEARCH)
        with self._stage(state, Step.SEARCH.value):
            # Start every search before waiting for any, in item order: the order the searches
            # begin in is the order a recording of the run keeps them in.
            for run in pending:
                run.task = asyncio.create_task(self._searcher.search(run.item, run.stores))
            for run in pending:
                await self._collect(state, run)

    async def _collect(self, state: RunState, run: ItemRun) -> None:
        assert run.task is not None  # noqa: S101 - set by the caller just before
        try:
            results = await run.task
        except Exception:  # the searcher promises not to raise; if it does, one item is lost
            self._search_crashed(state, run)
        else:
            self._record_results(state, run, results)

    def _record_results(self, state: RunState, run: ItemRun, results: list[StoreResult]) -> None:
        run.results = results
        run.products = merge_products(results)
        run.fetched_expires_at = self._clock.monotonic() + state.settings.store_cache_ttl_s

    def _search_crashed(self, state: RunState, run: ItemRun) -> None:
        log.exception("the store search failed unexpectedly", extra={"item_index": run.index})
        run.search_crashed = True
        run.results = [
            StoreResult(store_id=store.id, status=StoreStatus.ERROR, detail="search crashed")
            for store in run.stores
        ]
        state.warn(messages.SEARCH_CRASHED)

    def _filter(self, state: RunState) -> None:
        self._step(state, Step.FILTER)
        with self._stage(state, Step.FILTER.value):
            for run in state.items:
                self._score_item(state, run)

    def _score_item(self, state: RunState, run: ItemRun) -> None:
        """Filter and score one item's products on text and price. Safe to call twice."""
        if run.scored is not None:
            return
        if run.cached is not None:
            run.products = list(run.cached.products)
            run.image_scores = dict(run.cached.image_scores)
        run.scored = prefilter_and_score(run.item, run.products, state.budget, state.settings)

    def _rank(self, state: RunState) -> None:
        self._step(state, Step.RANK)
        with self._stage(state, Step.RANK.value):
            for run in state.items:
                scored = run.scored or []
                if state.query is not None and run.cached is None and scored:
                    run.candidates = select_candidates([entry.product for entry in scored])
                else:
                    self._final_rank(state, run)

    def _final_rank(self, state: RunState, run: ItemRun) -> None:
        run.ranked = apply_image_scores(run.scored or [], run.image_scores, state.settings)

    async def _image_rank(self, state: RunState) -> None:
        waiting = [run for run in state.items if run.ranked is None]
        query = state.query
        if not waiting or query is None:
            return

        self._step(state, Step.IMAGE_RANK)
        try:
            with self._stage(state, Step.IMAGE_RANK.value):
                for run in waiting:
                    await self._score_images(state, run, query)
        finally:
            query.image = None  # the embedding stays; the photo goes
        self._check_image_scores(state, waiting)

    async def _score_images(self, state: RunState, run: ItemRun, query: QueryImage) -> None:
        run.image_asked = True
        try:
            scores = await self._image_ranker.score(query, run.candidates)
        except Exception:  # a real ranker never raises; a broken one must not lose the search
            log.warning("the image ranker failed", exc_info=True)
            scores, run.image_failed = {}, True
        run.image_scores = dict(scores)
        self._final_rank(state, run)

    def _check_image_scores(self, state: RunState, asked: Sequence[ItemRun]) -> None:
        """Say so when the photo could not be used: the results are then ranked without it."""
        failed = any(run.image_failed for run in asked)
        scored = any(score is not None for run in asked for score in run.image_scores.values())
        expected = state.settings.image_ranker == "siglip"
        if failed or (expected and not scored):
            log.warning(
                "image similarity unavailable; ranking by text and price",
                extra={"ranker_failed": failed, "image_ranker": state.settings.image_ranker},
            )
            state.warn(messages.IMAGE_SIMILARITY_UNAVAILABLE)

    def _shape(self, state: RunState) -> None:
        self._step(state, Step.SHAPE)
        with self._stage(state, Step.SHAPE.value):
            for run in state.items:
                self._shape_item(state, run)

    def _shape_item(self, state: RunState, run: ItemRun) -> None:
        """Build one item's four price ranges. Safe to call twice."""
        if run.group is not None:
            return
        assert state.understood is not None  # noqa: S101 - planning always sets it
        built = build_group(
            run.ranked or [],
            state.settings,
            state.budget,
            run.stores,
            item_index=run.index,
            category=run.item.category,
            total=results_total(state.settings, state.understood.input_type),
        )
        run.group = built.group
        for note in built.warnings:
            state.warn(note)

    # ------------------------------------------------------------------------------------
    # The deadline
    # ------------------------------------------------------------------------------------

    def _deadline_reached(self, state: RunState, settings: Settings) -> None:
        if state.understood is None:
            log.warning("request deadline reached before the request was understood")
            raise RequestTimeoutError() from None
        state.timed_out = True
        log.warning(
            "request deadline reached; returning what has been ranked so far",
            extra={"deadline_s": settings.request_deadline_s},
        )
        state.warn(messages.deadline_warning(settings.request_deadline_s))

    def _finish_without_waiting(self, state: RunState) -> None:
        """Turn whatever the stages finished into groups, without waiting for anything.

        Items whose search did not finish have no products and get an empty group; items that
        have products are ranked on text and price, plus image scores if those were done.
        """
        for run in state.items:
            self._harvest(state, run)
            self._score_item(state, run)
            if run.ranked is None:
                self._final_rank(state, run)
            self._shape_item(state, run)

    def _harvest(self, state: RunState, run: ItemRun) -> None:
        """Take the result of a search that finished while another one was being waited for."""
        task = run.task
        if run.results is not None or task is None or not task.done() or task.cancelled():
            return
        if task.exception() is not None:
            self._search_crashed(state, run)
        else:
            self._record_results(state, run, task.result())

    async def _cancel_unfinished(self, state: RunState) -> None:
        tasks = [run.task for run in state.items if run.task is not None and not run.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for run in state.items:  # mark every outcome as seen so none is reported as never read
            if run.task is not None and run.task.done() and not run.task.cancelled():
                run.task.exception()

    # ------------------------------------------------------------------------------------
    # The response
    # ------------------------------------------------------------------------------------

    def _assemble(self, state: RunState) -> SearchResponse:
        assert state.understood is not None  # noqa: S101 - a run that gets here understood it
        self._step(state, Step.ASSEMBLE)
        with self._stage(state, Step.ASSEMBLE.value):
            summary = summarise(state.active_stores, state.items)
            self._note_store_outcomes(state, summary)
            self._insert_store_timings(state, summary)
            if state.settings.debug_dump:
                write_candidate_dump(state)
        groups = [run.group for run in state.items if run.group is not None]
        response = SearchResponse(
            request_id=state.req.request_id,
            understood=state.understood,
            groups=groups,
            stores_used=summary.used,
            stores_skipped=summary.skipped,
            timings=state.timings,
            usage=state.usage,
            warnings=state.warnings,
            duration_ms=round((self._clock.monotonic() - state.started) * 1000, 3),
            query_embedding=state.query.embedding if state.query is not None else None,
        )
        log.info(
            "search finished",
            extra={
                "results": response.result_count,
                "stores_used": len(summary.used),
                "stores_skipped": len(summary.skipped),
                "warnings": len(response.warnings),
                "duration_ms": response.duration_ms,
                "reused_understanding": state.reused_understanding,
            },
        )
        return response

    def _note_store_outcomes(self, state: RunState, summary: StoreSummary) -> None:
        """Log and tell the shopper about every store that failed and every item left empty."""
        names = {store.id: store.display_name for store in state.active_stores}
        for report in summary.failed:
            log.warning(
                "store skipped",
                extra={
                    "store": report.store_id,
                    "status": report.status.value,
                    "reason": report.reason,
                },
            )
            name = names.get(report.store_id, report.store_id)
            warning = messages.store_warning(name, report.status)
            if warning is not None:
                state.warn(warning)
        self._note_empty_items(state)

    def _note_empty_items(self, state: RunState) -> None:
        if not state.active_stores:
            return  # already said: no store is set up
        for run in state.items:
            gender = effective_gender(run.item)
            if not run.stores and gender is not None:
                state.warn(messages.no_store_for_gender(run.item.category, gender))
        searched = [run for run in state.items if run.stores]
        if state.timed_out or not searched:
            return  # the deadline warning, or the gender warning, already explains it
        found = sum(run.group.result_count for run in searched if run.group is not None)
        if found == 0:
            log.warning(
                "no store returned products that match", extra={"stores": len(state.active_stores)}
            )
            state.warn(messages.NO_RESULTS_ANYWHERE)
        elif len(state.items) > 1:
            for run in searched:
                if run.group is not None and run.group.result_count == 0:
                    state.warn(messages.nothing_found_for(run.item.category))

    def _insert_store_timings(self, state: RunState, summary: StoreSummary) -> None:
        """Per-store fetch times go just before the ``search`` step they are part of."""
        position = next(
            (i for i, t in enumerate(state.timings) if t.step == Step.SEARCH.value),
            len(state.timings),
        )
        state.timings[position:position] = summary.timings

    def _remember(self, state: RunState) -> None:
        """Keep what a re-run can reuse: the items whose search finished."""
        items: dict[int, CachedItem] = {}
        for run in state.items:
            if run.cached is not None:
                items[run.index] = run.cached
                continue
            results = run.results or []
            if not any(r.status in (StoreStatus.OK, StoreStatus.EMPTY) for r in results):
                continue  # nothing was learned from the stores, so a re-run must ask again
            outcomes = outcomes_for_item(run)
            items[run.index] = CachedItem(
                item=run.item,
                store_ids=tuple(store.id for store in run.stores),
                products=tuple(run.products),
                image_scores=dict(run.image_scores),
                reports=tuple(outcome.report for outcome in outcomes),
                searched_ids=frozenset(o.report.store_id for o in outcomes if o.searched),
                expires_at=run.fetched_expires_at or self._clock.monotonic(),
            )
        if not items:
            return
        embedding = state.query.embedding if state.query is not None else None
        self._cache.put(
            state.req.request_id,
            CachedRun(items=items, query_embedding=tuple(embedding) if embedding else None),
        )

    # ------------------------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------------------------

    def _step(self, state: RunState, step: Step) -> None:
        if state.on_step is None:
            return
        try:
            state.on_step(step)
        except Exception:  # a broken progress display must not lose the search
            log.warning("the progress callback failed", exc_info=True)

    @contextmanager
    def _stage(self, state: RunState, name: str) -> Iterator[TimedStep]:
        """Time a stage on the pipeline's clock and add it to the run's timings, even when the
        stage is cut short by the deadline."""
        handle: TimedStep | None = None
        try:
            with timed(name, clock=self._clock) as handle:
                try:
                    yield handle
                except asyncio.CancelledError:
                    handle.status = "timeout"
                    raise
        finally:
            if handle is not None:
                state.timings.append(handle.to_timing())

    def _log_no_store(self, state: RunState, run: ItemRun) -> None:
        if state.active_stores:
            log.warning(
                "no store sells for this item's gender; nothing was searched",
                extra={"item_index": run.index, "category": run.item.category.value},
            )


def merge_products(results: Sequence[StoreResult]) -> list[Product]:
    """Every store's products in one list, store by store; a link seen twice is kept once."""
    seen: set[str] = set()
    merged: list[Product] = []
    for result in results:
        for product in result.products:
            if product.key not in seen:
                seen.add(product.key)
                merged.append(product)
    return merged
