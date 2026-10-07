"""Record a live run and replay it offline (plan 11.1.3).

How it works, and what it deliberately is not
---------------------------------------------
Recording happens at the **contract boundary**, not at the HTTP layer. Three thin recorders wrap
the real ``Understander``, ``StoreSearcher`` and ``ImageRanker`` and save what each returned:

- the ``UnderstandResult`` of each call (or the ``VgaError`` it raised),
- the ``StoreResult`` list of each ``search`` call, with the item and store ids that were asked,
- the image score map of each ``score`` call.

Replay provides stand-ins for the same three protocols that return exactly those saved values.
The real pipeline, the real ranking and the real price-range logic then run again on them: **zero
network calls and zero OpenAI calls**. That is what makes tuning the weights (plan 16.3.1) free
of store traffic.

This is **not raw HTTP capture** (no response bodies, headers or cookies are saved). A replay
therefore cannot test a change to the fetch or extraction code: for that, use the recorded store
responses under ``tests/`` with ``StoreHttpFixtures``. A replay also cannot judge a changed search
keyword: the stand-in refuses a search for an item or a store list that differs from the recording
(``RecordingMismatchError``) rather than return results for something else.

Never saved: the photo, any image bytes, any embedding. Only text, URLs and numbers are written,
and ``_refuse_image_data`` checks every payload before it is written.

Layout of a recording directory
-------------------------------
::

    <dir>/manifest.json     format, the query ids in order, model and prompt version, and each
                            query's live duration in milliseconds
    <dir>/<query_id>.json   {"understand": [...], "search": [...], "image_scores": [...]}, one
                            entry per call in the order the calls were made

Calls are keyed by query id and call order. The order is fixed when a call *starts*, so
concurrent calls (an outfit searched garment by garment) replay in the order they began.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.harness.errors import RecordingError, RecordingMismatchError
from eval.harness.wiring import Boundaries
from vga.errors import (
    CallBudgetExceededError,
    ConfigError,
    InvalidInputError,
    LlmError,
    StoreBlockedError,
    VgaError,
)
from vga.interfaces import ImageRanker, StoreSearcher, Understander
from vga.models import (
    ItemIntent,
    Product,
    QueryImage,
    SearchRequest,
    StoreConfig,
    StoreResult,
    UnderstandResult,
)

RECORDING_FORMAT = 1
MANIFEST_FILE = "manifest.json"

_FORBIDDEN_KEYS = frozenset(
    {"image", "image_bytes", "photo", "embedding", "query_embedding", "bytes"}
)
"""Keys that would mean a photo or something derived from it is about to be saved. ``image_url``
(a link to a product thumbnail) is fine and is not on the list."""

_ERROR_TYPES: dict[str, type[VgaError]] = {
    "invalid_input": InvalidInputError,
    "llm_failure": LlmError,
    "store_blocked": StoreBlockedError,
    "call_budget_exceeded": CallBudgetExceededError,
    "config": ConfigError,
}


_FREE_FORM = frozenset({"dropped", "scores"})
"""Fields whose keys are data, not field names: drop reasons (``{"image": 3}`` could mean "no image
URL") and image scores (keyed by URL). Their keys are not checked; their values still are."""


def _refuse_image_data(value: Any, where: str = "recording", *, check_keys: bool = True) -> None:
    """Raise if a payload holds bytes or a field that names a photo or an embedding."""
    if isinstance(value, bytes | bytearray):
        msg = f"refusing to save binary data at {where}: photos are never recorded"
        raise RecordingError(msg)
    if isinstance(value, dict):
        for key, item in value.items():
            if check_keys and key in _FORBIDDEN_KEYS:
                msg = (
                    f"refusing to save a {key!r} field at {where}: "
                    "photos and embeddings are never recorded"
                )
                raise RecordingError(msg)
            _refuse_image_data(item, f"{where}.{key}", check_keys=key not in _FREE_FORM)
    elif isinstance(value, list):
        for position, item in enumerate(value):
            _refuse_image_data(item, f"{where}[{position}]", check_keys=check_keys)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _refuse_image_data(payload, path.name)
    # Write beside the target and swap it in, so an interrupt cannot leave half a file where a
    # complete recording used to be.
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    partial.replace(path)


def _read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"{what} {path} could not be read. Record the run first with --record."
        raise RecordingError(msg, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        msg = f"{what} {path} is not valid JSON. Record the run again."
        raise RecordingError(msg, detail=str(exc)) from exc
    if not isinstance(data, dict):
        msg = f"{what} {path} must hold a JSON object. Record the run again."
        raise RecordingError(msg)
    return data


# --------------------------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------------------------


@dataclass
class _Bucket:
    """Everything recorded for the query that is running now."""

    understand: list[dict[str, Any] | None] = field(default_factory=list)
    search: list[dict[str, Any] | None] = field(default_factory=list)
    image_scores: list[dict[str, Any] | None] = field(default_factory=list)


class RecordingSession:
    """Collects what the three boundaries return, query by query, and writes it to a directory.

    Refuses a directory that already holds a recording: a live recording is expensive to make
    and is never overwritten silently.
    """

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        if (self._dir / MANIFEST_FILE).exists():
            msg = (
                f"{self._dir} already holds a recording. Choose a new folder for --record, "
                "or remove the old one on purpose: a live recording is never overwritten."
            )
            raise RecordingError(msg)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._bucket: _Bucket | None = None
        self._queries: dict[str, dict[str, Any]] = {}
        self._models: list[str] = []
        self._prompt_versions: list[str] = []
        self.incomplete: list[str] = []
        """Query ids whose recording lacks a call because a boundary raised mid-call."""

    def wrap(self, boundaries: Boundaries) -> Boundaries:
        """Recorders around the live boundaries; hand these to the pipeline factory."""
        return Boundaries(
            understander=_RecordingUnderstander(boundaries.understander, self),
            searcher=_RecordingSearcher(boundaries.searcher, self),
            image_ranker=_RecordingImageRanker(boundaries.image_ranker, self),
        )

    def bucket(self) -> _Bucket:
        if self._bucket is None:
            msg = "a boundary was called outside a query; the runner must call begin_query first"
            raise RecordingError(msg)
        return self._bucket

    def note_understanding(self, result: UnderstandResult) -> None:
        if result.model not in self._models:
            self._models.append(result.model)
        if result.prompt_version not in self._prompt_versions:
            self._prompt_versions.append(result.prompt_version)

    def begin_query(self, query_id: str) -> None:
        self._bucket = _Bucket()

    def end_query(self, query_id: str, *, duration_ms: float) -> None:
        bucket = self.bucket()
        calls = (bucket.understand, bucket.search, bucket.image_scores)
        incomplete = any(entry is None for entries in calls for entry in entries)
        if incomplete:
            self.incomplete.append(query_id)
        _write_json(
            self._dir / f"{query_id}.json",
            {
                "format": RECORDING_FORMAT,
                "query_id": query_id,
                "incomplete": incomplete,
                "understand": bucket.understand,
                "search": bucket.search,
                "image_scores": bucket.image_scores,
            },
        )
        self._queries[query_id] = {"file": f"{query_id}.json", "live_duration_ms": duration_ms}
        self._bucket = None
        _write_json(
            self._dir / MANIFEST_FILE,
            {
                "format": RECORDING_FORMAT,
                "queries": self._queries,
                "models": self._models,
                "prompt_versions": self._prompt_versions,
            },
        )


class _RecordingUnderstander:
    def __init__(self, inner: Understander, session: RecordingSession) -> None:
        self._inner = inner
        self._session = session

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        bucket = self._session.bucket()
        slot = len(bucket.understand)
        bucket.understand.append(None)
        try:
            result = await self._inner.understand(req)
        except VgaError as exc:
            bucket.understand[slot] = {
                "error": {"code": exc.code, "user_message": exc.user_message}
            }
            raise
        self._session.note_understanding(result)
        bucket.understand[slot] = {"result": result.model_dump(mode="json")}
        return result


class _RecordingSearcher:
    def __init__(self, inner: StoreSearcher, session: RecordingSession) -> None:
        self._inner = inner
        self._session = session

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        bucket = self._session.bucket()
        slot = len(bucket.search)
        bucket.search.append(None)
        results = await self._inner.search(item, stores)
        bucket.search[slot] = {
            "item": item.model_dump(mode="json"),
            "stores": [store.id for store in stores],
            "results": [result.model_dump(mode="json") for result in results],
        }
        return results


class _RecordingImageRanker:
    def __init__(self, inner: ImageRanker, session: RecordingSession) -> None:
        self._inner = inner
        self._session = session

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        bucket = self._session.bucket()
        slot = len(bucket.image_scores)
        bucket.image_scores.append(None)
        scores = await self._inner.score(query, products)
        bucket.image_scores[slot] = {"scores": dict(scores)}
        return scores


# --------------------------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------------------------


@dataclass
class _Replay:
    """The recorded calls of the query that is running now, and how many were used."""

    query_id: str
    understand: list[dict[str, Any] | None]
    search: list[dict[str, Any] | None]
    image_scores: list[dict[str, Any] | None]
    used_understand: int = 0
    used_search: int = 0
    used_image_scores: int = 0


def _next_entry(
    session: "ReplaySession",
    replay: _Replay,
    entries: list[dict[str, Any] | None],
    used: int,
    kind: str,
) -> dict[str, Any]:
    entry = entries[used] if used < len(entries) else None
    if entry is None:
        msg = (
            f"{replay.query_id}: the pipeline made {kind} call number {used + 1}, but the "
            f"recording holds {len(entries)}. The pipeline now behaves differently from the "
            "recorded run (for example it asks for another search); record again to test that."
        )
        raise session.mismatch(msg)
    return entry


class ReplaySession:
    """Serves a recording back through stand-ins for the three boundaries."""

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        manifest = _read_json(self._dir / MANIFEST_FILE, "The recording manifest")
        if manifest.get("format") != RECORDING_FORMAT:
            msg = (
                f"The recording in {self._dir} has format {manifest.get('format')!r}, but this "
                f"harness reads format {RECORDING_FORMAT}. Record the run again."
            )
            raise RecordingError(msg)
        queries = manifest.get("queries")
        if not isinstance(queries, dict):
            msg = f"The recording manifest in {self._dir} has no 'queries'. Record the run again."
            raise RecordingError(msg)
        self._manifest = manifest
        self._queries: dict[str, dict[str, Any]] = queries
        self._current: _Replay | None = None
        self.notes: list[str] = []
        """Plain notes for the report: calls the pipeline did not use, scores that were missing."""
        self.mismatches: list[str] = []
        """Every time the pipeline asked for something the recording does not hold."""
        self._missing_scores = 0

    def live_duration_ms(self, query_id: str) -> float | None:
        """How long the recorded live run of this query took, if the recording says."""
        value = self._queries.get(query_id, {}).get("live_duration_ms")
        return float(value) if isinstance(value, int | float) else None

    @property
    def understander(self) -> "_ReplayUnderstander":
        return _ReplayUnderstander(self)

    @property
    def searcher(self) -> "_ReplaySearcher":
        return _ReplaySearcher(self)

    @property
    def image_ranker(self) -> "_ReplayImageRanker":
        return _ReplayImageRanker(self)

    def boundaries(self) -> Boundaries:
        return Boundaries(self.understander, self.searcher, self.image_ranker)

    def current(self) -> _Replay:
        if self._current is None:
            msg = "a replayed boundary was called outside a query; call begin_query first"
            raise RecordingError(msg)
        return self._current

    def mismatch(self, message: str) -> RecordingMismatchError:
        """Remember that the replay diverged from the recording, and return the error to raise.

        The error alone is not enough: a pipeline that catches it and degrades would look clean.
        The report lists every mismatch in its notes either way."""
        if message not in self.mismatches:
            self.mismatches.append(message)
        return RecordingMismatchError(message)

    def note_missing_scores(self, count: int) -> None:
        self._missing_scores += count

    def begin_query(self, query_id: str) -> None:
        if query_id not in self._queries:
            msg = (
                f"The recording in {self._dir} has no query {query_id!r}. It holds: "
                f"{', '.join(self._queries) or 'nothing'}. Record the run again."
            )
            raise RecordingError(msg)
        data = _read_json(self._dir / f"{query_id}.json", f"The recording of {query_id}")
        if data.get("incomplete"):
            msg = (
                f"The recording of {query_id} is incomplete: a boundary failed while it was "
                "recorded. Record the run again."
            )
            raise RecordingError(msg)
        self._current = _Replay(
            query_id,
            list(data.get("understand", [])),
            list(data.get("search", [])),
            list(data.get("image_scores", [])),
        )

    def end_query(self, query_id: str, *, duration_ms: float) -> None:
        replay = self.current()
        for kind, used, total in (
            ("understand", replay.used_understand, len(replay.understand)),
            ("search", replay.used_search, len(replay.search)),
            ("image score", replay.used_image_scores, len(replay.image_scores)),
        ):
            if used < total:
                self.notes.append(
                    f"{query_id}: the pipeline made {used} {kind} call(s), "
                    f"the recording holds {total}."
                )
        self._current = None

    def final_notes(self) -> list[str]:
        """Notes collected so far, plus a count of products that had no recorded image score."""
        notes = [f"Replay diverged from the recording: {message}" for message in self.mismatches]
        notes += self.notes
        if self._missing_scores:
            notes.append(
                f"{self._missing_scores} product(s) had no recorded image score and were scored "
                "as 'no image score'."
            )
        return notes


class _ReplayUnderstander:
    def __init__(self, session: ReplaySession) -> None:
        self._session = session

    async def understand(self, req: SearchRequest) -> UnderstandResult:
        replay = self._session.current()
        entry = _next_entry(
            self._session, replay, replay.understand, replay.used_understand, "understand"
        )
        replay.used_understand += 1
        error = entry.get("error")
        if error is not None:
            error_type = _ERROR_TYPES.get(str(error.get("code")), VgaError)
            raise error_type(str(error.get("user_message")), code=str(error.get("code")))
        return UnderstandResult.model_validate(entry["result"])


class _ReplaySearcher:
    def __init__(self, session: ReplaySession) -> None:
        self._session = session

    async def search(self, item: ItemIntent, stores: Sequence[StoreConfig]) -> list[StoreResult]:
        replay = self._session.current()
        entry = _next_entry(self._session, replay, replay.search, replay.used_search, "search")
        replay.used_search += 1
        asked = [store.id for store in stores]
        if entry["stores"] != asked:
            msg = (
                f"{replay.query_id}: search call {replay.used_search} asked for stores {asked}, "
                f"but the recording searched {entry['stores']}. Record again to test a changed "
                "store list."
            )
            raise self._session.mismatch(msg)
        if ItemIntent.model_validate(entry["item"]) != item:
            msg = (
                f"{replay.query_id}: search call {replay.used_search} asked for a different item "
                "(category, attributes or keywords) than the recording holds. A replay cannot "
                "judge changed keywords: record again to test that."
            )
            raise self._session.mismatch(msg)
        return [StoreResult.model_validate(result) for result in entry["results"]]


class _ReplayImageRanker:
    def __init__(self, session: ReplaySession) -> None:
        self._session = session

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        replay = self._session.current()
        entry = _next_entry(
            self._session, replay, replay.image_scores, replay.used_image_scores, "image score"
        )
        replay.used_image_scores += 1
        recorded: dict[str, float | None] = entry["scores"]
        scores: dict[str, float | None] = {}
        missing = 0
        for product in products:
            key = product.key
            if key in recorded:
                scores[key] = recorded[key]
            else:
                scores[key] = None
                missing += 1
        self._session.note_missing_scores(missing)
        return scores
