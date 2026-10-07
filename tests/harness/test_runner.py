"""11.1.2: the runner runs queries one after another and keeps each response and timing."""

import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from eval.harness.errors import RunFileError
from eval.harness.links import LinkCheck, LinksMode
from eval.harness.queries import AcceptanceQuery
from eval.harness.runner import PipelineFailure, QueryRun, QueryScope, run_queries
from eval.harness.runstore import (
    RESPONSES_DIR,
    RUN_FILE,
    LoadedRun,
    RunMeta,
    load_run,
    save_run,
)

from tests.factories import make_image_bytes, make_settings
from tests.fakes import FakeClock, FakePipeline
from tests.harness.helpers import make_query, make_response
from vga.errors import InvalidInputError
from vga.interfaces import Pipeline
from vga.models import SearchRequest, SearchResponse
from vga.settings import Settings

PHOTO = make_image_bytes()


def queries() -> list[AcceptanceQuery]:
    return [
        make_query("q01_photo", "product_photo"),
        make_query("q06_text", "text"),
        make_query("q09_photo_text", "photo_text"),
    ]


def photo_loader(query: AcceptanceQuery) -> bytes | None:
    return PHOTO if query.image else None


class RecordingScope:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, float | None]] = []

    def begin_query(self, query_id: str) -> None:
        self.events.append(("begin", query_id, None))

    def end_query(self, query_id: str, *, duration_ms: float) -> None:
        self.events.append(("end", query_id, duration_ms))


class OverlapProbe:
    """A pipeline that notices if two queries are ever in flight at the same time."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: object = None,
        on_step: object = None,
    ) -> SearchResponse:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.active -= 1
        return make_response()


class ClockedPipeline:
    """A pipeline that takes ``seconds`` of fake time and reports its own, shorter, figure."""

    def __init__(self, clock: FakeClock, seconds: float, own_ms: float = 0.0) -> None:
        self._clock, self._seconds, self._own_ms = clock, seconds, own_ms

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: object = None,
        on_step: object = None,
    ) -> SearchResponse:
        self._clock.advance(self._seconds)
        return make_response(duration_ms=self._own_ms)


class FailingOn:
    """Raises for the chosen query texts, returns a response for the rest."""

    def __init__(self, bad_text: str, error: Exception) -> None:
        self._bad_text, self._error = bad_text, error

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: object = None,
        on_step: object = None,
    ) -> SearchResponse:
        if req.text == self._bad_text:
            raise self._error
        return make_response()


async def run_all(
    pipeline: Pipeline,
    *,
    clock: FakeClock | None = None,
    scope: QueryScope | None = None,
    progress: Callable[[QueryRun], None] | None = None,
) -> list[QueryRun]:
    return await run_queries(
        queries(),
        pipeline,
        make_settings(),
        clock=clock or FakeClock(),
        load_image=photo_loader,
        scope=scope,
        progress=progress,
    )


class TestRunning:
    async def test_runs_every_query_in_order_and_keeps_each_response(self) -> None:
        pipeline = FakePipeline()

        runs = await run_all(pipeline)

        assert [run.query.id for run in runs] == ["q01_photo", "q06_text", "q09_photo_text"]
        assert all(run.response is not None and run.failure is None for run in runs)
        assert len(pipeline.calls) == 3

    async def test_gives_each_query_its_own_request_carrying_the_right_inputs(self) -> None:
        pipeline = FakePipeline()

        await run_all(pipeline)

        photo, text, both = (call.req for call in pipeline.calls)
        assert photo.text is None
        assert photo.image == PHOTO
        assert text.text == "black oversized blazer"
        assert text.image is None
        assert both.text == "black oversized blazer"
        assert both.image == PHOTO
        assert len({call.req.request_id for call in pipeline.calls}) == 3

    async def test_never_runs_two_queries_at_once(self) -> None:
        probe = OverlapProbe()

        await run_all(probe)

        assert probe.max_active == 1

    async def test_tells_the_scope_when_each_query_starts_and_ends(self) -> None:
        scope = RecordingScope()

        await run_all(FakePipeline(), scope=scope)

        assert [(kind, qid) for kind, qid, _ in scope.events] == [
            ("begin", "q01_photo"),
            ("end", "q01_photo"),
            ("begin", "q06_text"),
            ("end", "q06_text"),
            ("begin", "q09_photo_text"),
            ("end", "q09_photo_text"),
        ]

    async def test_reports_progress_after_each_query(self) -> None:
        seen: list[str] = []

        await run_all(FakePipeline(), progress=lambda run: seen.append(run.query.id))

        assert seen == ["q01_photo", "q06_text", "q09_photo_text"]


class TestTiming:
    async def test_measures_wall_time_with_the_injected_clock(self) -> None:
        clock = FakeClock()

        runs = await run_all(ClockedPipeline(clock, seconds=7.5), clock=clock)

        assert [run.wall_ms for run in runs] == [7500.0, 7500.0, 7500.0]

    async def test_the_checked_duration_is_the_slower_of_wall_time_and_the_pipelines_own_figure(
        self,
    ) -> None:
        clock = FakeClock()

        wall_is_longer = await run_all(ClockedPipeline(clock, 7.0, own_ms=2000.0), clock=clock)
        own_is_longer = await run_all(ClockedPipeline(clock, 1.0, own_ms=9000.0), clock=clock)

        assert wall_is_longer[0].duration_ms == 7000.0
        assert own_is_longer[0].duration_ms == 9000.0
        assert own_is_longer[0].duration_source == "measured"


class TestAFailingQuery:
    async def test_a_vga_error_is_kept_with_its_code_and_plain_message(self) -> None:
        error = InvalidInputError("Please add a photo.", detail="secret internals")

        runs = await run_all(FailingOn("black oversized blazer", error))

        failed = runs[1]
        assert failed.response is None
        assert failed.failure == PipelineFailure(
            "invalid_input", "Please add a photo.", "InvalidInputError"
        )
        assert "secret internals" not in repr(failed.failure)

    async def test_an_unexpected_exception_is_kept_and_does_not_stop_the_other_queries(
        self,
    ) -> None:
        runs = await run_all(FailingOn("black oversized blazer", RuntimeError("boom")))

        assert [run.response is not None for run in runs] == [True, False, False]
        assert runs[1].failure is not None
        assert runs[1].failure.code == "unexpected"
        assert "RuntimeError: boom" in runs[1].failure.message
        assert len(runs) == 3

    async def test_a_failed_query_still_tells_the_scope_it_ended(self) -> None:
        scope = RecordingScope()

        await run_all(FailingOn("black oversized blazer", RuntimeError("boom")), scope=scope)

        assert ("end", "q06_text") in [(kind, qid) for kind, qid, _ in scope.events]


def loaded_run(tmp_path: Path | None = None) -> LoadedRun:
    meta = RunMeta(
        number=1,
        mode="record",
        date=date(2026, 10, 7),
        links=LinksMode.ALL,
        price_range_mix=[25, 25, 25, 25],
    )
    ok = make_response()
    runs = [
        QueryRun(make_query("q01_photo", "product_photo"), ok, None, 5100.0, 5100.0),
        QueryRun(
            make_query("q06_text", "text"),
            None,
            PipelineFailure("llm_failure", "We could not understand that.", "LlmError"),
            300.0,
            300.0,
        ),
    ]
    link = LinkCheck(url="https://x.example/p/1", store="Alpha Store", product_title="T", ok=True)
    return LoadedRun(meta, runs, {"q01_photo": [link]})


class TestSavingARun:
    def test_saves_one_response_file_per_answered_query_and_a_run_file(
        self, tmp_path: Path
    ) -> None:
        save_run(tmp_path / "run-1", loaded_run())

        saved = sorted(p.name for p in (tmp_path / "run-1" / RESPONSES_DIR).iterdir())
        assert saved == ["q01_photo.json"]
        assert (tmp_path / "run-1" / RUN_FILE).is_file()

    def test_a_saved_run_loads_back_with_responses_failures_timings_and_links(
        self, tmp_path: Path
    ) -> None:
        original = loaded_run()
        save_run(tmp_path, loaded_run())

        again = load_run(tmp_path)

        assert again.meta == original.meta
        assert [run.query for run in again.runs] == [run.query for run in original.runs]
        assert again.runs[0].response == original.runs[0].response
        assert again.runs[1].response is None
        assert again.runs[1].failure == original.runs[1].failure
        assert [run.duration_ms for run in again.runs] == [5100.0, 300.0]
        assert again.links == original.links

    def test_the_saved_response_carries_no_photo_and_no_embedding(self, tmp_path: Path) -> None:
        run = loaded_run()
        leaky = run.runs[0].response.model_copy(  # type: ignore[union-attr]
            update={"query_embedding": [0.123456, 0.654321]}
        )
        run.runs[0] = QueryRun(run.runs[0].query, leaky, None, 1.0, 1.0)

        save_run(tmp_path, run)

        text = (tmp_path / RESPONSES_DIR / "q01_photo.json").read_text(encoding="utf-8")
        assert "0.123456" not in text
        assert "embedding" not in text

    def test_refuses_a_folder_that_already_holds_files(self, tmp_path: Path) -> None:
        (tmp_path / "old.txt").write_text("earlier run", encoding="utf-8")

        with pytest.raises(RunFileError, match="already holds files"):
            save_run(tmp_path, loaded_run())

    def test_overwrite_replaces_the_previous_responses(self, tmp_path: Path) -> None:
        save_run(tmp_path, loaded_run())
        later = loaded_run()
        later.runs = later.runs[1:]

        save_run(tmp_path, later, overwrite=True)

        assert list((tmp_path / RESPONSES_DIR).iterdir()) == []

    def test_a_missing_run_has_a_plain_message(self, tmp_path: Path) -> None:
        with pytest.raises(RunFileError, match="No saved run"):
            load_run(tmp_path / "nothing-here")

    def test_a_broken_run_file_has_a_plain_message(self, tmp_path: Path) -> None:
        (tmp_path / RUN_FILE).write_text("{not json", encoding="utf-8")

        with pytest.raises(RunFileError, match="could not be read"):
            load_run(tmp_path)

    def test_a_missing_response_file_has_a_plain_message(self, tmp_path: Path) -> None:
        save_run(tmp_path, loaded_run())
        (tmp_path / RESPONSES_DIR / "q01_photo.json").unlink()

        with pytest.raises(RunFileError, match="saved response"):
            load_run(tmp_path)
