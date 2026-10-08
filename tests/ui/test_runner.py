"""The runner is the one place that produces a ``SearchResponse`` for the page: it builds the real
pipeline once per process, calls it with one event loop per search, and says up front when live
mode cannot work yet."""

import asyncio
import inspect

import pytest

from app import runner
from tests.factories import load_sample_response, make_search_request
from tests.fakes import FakePipeline
from vga.errors import ConfigError, LlmError
from vga.models import RunOverrides, SearchResponse, SettingsOverride, Step
from vga.pipeline import SearchPipeline
from vga.settings import Settings
from vga.understand.understander import API_KEY_MISSING_MESSAGE, MODEL_NOT_SET_MESSAGE


def test_run_search_keeps_the_signature_the_page_relies_on() -> None:
    parameters = inspect.signature(runner.run_search).parameters

    assert list(parameters) == ["request", "overrides", "on_step"]
    assert parameters["overrides"].default is None
    assert parameters["on_step"].default is None


class TestFixtureMode:
    def test_it_returns_the_sample_response_for_the_request(self) -> None:
        request = make_search_request()

        response = runner.run_search(request)

        assert response.request_id == request.request_id
        assert response.groups == load_sample_response().groups

    def test_it_reports_every_step_in_order(self) -> None:
        seen: list[Step] = []

        runner.run_search(make_search_request(), None, seen.append)

        assert seen == list(Step)

    def test_it_needs_no_api_key_and_builds_no_real_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(runner, "build_pipeline", _must_not_be_called)

        response = runner.run_search(make_search_request())

        assert response.result_count > 0

    def test_it_announces_that_the_results_are_a_fixed_example(self) -> None:
        assert runner.mode_notice(Settings(ui_fixture=True)) == runner.FIXTURE_NOTICE

    def test_nothing_is_missing_whatever_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert runner.setup_problem(Settings(ui_fixture=True, openai_model=None)) is None


def _must_not_be_called(*args: object, **kwargs: object) -> SearchPipeline:
    raise AssertionError("fixture mode must not build the real pipeline")


class TestOverridesReachThePipeline:
    def test_the_overrides_and_the_request_are_passed_on_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakePipeline()
        monkeypatch.setattr(runner, "get_pipeline", lambda settings: fake)
        overrides = RunOverrides(settings=SettingsOverride())
        request = make_search_request()

        runner.run_search(request, overrides)

        assert fake.calls[0].overrides == overrides
        assert fake.calls[0].req == request


class TestLiveModeNeedsAKeyAndAModel:
    @pytest.fixture(autouse=True)
    def _live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VGA_UI_FIXTURE", "0")
        monkeypatch.setenv("OPENAI_API_KEY", "placeholder-not-a-real-key")

    def test_a_configured_machine_has_nothing_to_fix(self) -> None:
        settings = runner.load_ui_settings()

        assert runner.setup_problem(settings) is None
        assert runner.mode_notice(settings) is None

    def test_a_missing_key_is_named_with_what_to_do(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY")

        assert runner.setup_problem(runner.load_ui_settings()) == API_KEY_MISSING_MESSAGE
        assert "OPENAI_API_KEY" in API_KEY_MISSING_MESSAGE

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_an_empty_key_counts_as_missing(
        self, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", blank)

        assert runner.setup_problem(runner.load_ui_settings()) == API_KEY_MISSING_MESSAGE

    def test_a_missing_model_is_named_with_what_to_do(self) -> None:
        settings = runner.load_ui_settings().model_copy(update={"openai_model": None})

        assert runner.setup_problem(settings) == MODEL_NOT_SET_MESSAGE
        assert "openai_model" in MODEL_NOT_SET_MESSAGE

    def test_the_key_is_never_part_of_what_the_runner_returns(self) -> None:
        settings = runner.load_ui_settings()

        assert "placeholder-not-a-real-key" not in settings.model_dump_json()


class TestTheRealPipelineIsBuiltOncePerProcess:
    """The re-run cache lives on the pipeline instance, so a second instance would make every
    search again after a mix or chip change cost what a new search costs."""

    @pytest.fixture
    def builds(self, monkeypatch: pytest.MonkeyPatch) -> list[SearchPipeline]:
        built: list[SearchPipeline] = []

        def build(settings: Settings) -> SearchPipeline:
            from tests.fakes import FakeImageRanker, FakeStoreSearcher, FakeUnderstander

            pipeline = SearchPipeline(
                FakeUnderstander(), FakeStoreSearcher(), FakeImageRanker(), []
            )
            built.append(pipeline)
            return pipeline

        monkeypatch.setattr(runner, "build_pipeline", build)
        return built

    def test_two_searches_use_the_same_instance(self, builds: list[SearchPipeline]) -> None:
        settings = Settings(ui_fixture=False)

        first = runner.get_pipeline(settings)
        second = runner.get_pipeline(settings)

        assert first is second
        assert len(builds) == 1

    def test_the_image_model_is_loaded_at_start_up_not_on_the_first_photo(
        self, monkeypatch: pytest.MonkeyPatch, builds: list[SearchPipeline]
    ) -> None:
        warmed: list[bool] = []

        async def warm_up(self: SearchPipeline) -> bool:
            warmed.append(True)
            return False  # no image model on this machine: the pipeline copes, so must the page

        monkeypatch.setattr(SearchPipeline, "warm_up", warm_up)

        runner.get_pipeline(Settings(ui_fixture=False))
        runner.get_pipeline(Settings(ui_fixture=False))

        assert warmed == [True]

    def test_the_connections_opened_at_start_up_are_closed_in_the_same_loop(
        self, monkeypatch: pytest.MonkeyPatch, builds: list[SearchPipeline]
    ) -> None:
        # Start-up reads the stores' robots.txt files, and its event loop ends right after.
        events: list[tuple[str, asyncio.AbstractEventLoop]] = []

        async def warm_up(self: SearchPipeline) -> bool:
            events.append(("warm_up", asyncio.get_running_loop()))
            return True

        async def aclose(self: SearchPipeline) -> None:
            events.append(("aclose", asyncio.get_running_loop()))

        monkeypatch.setattr(SearchPipeline, "warm_up", warm_up)
        monkeypatch.setattr(SearchPipeline, "aclose", aclose)

        runner.get_pipeline(Settings(ui_fixture=False))

        assert [name for name, _ in events] == ["warm_up", "aclose"]
        assert events[0][1] is events[1][1]


class ClosingPipeline(FakePipeline):
    """A pipeline that counts how often it is asked to release its connections."""

    def __init__(self, *, error: LlmError | None = None) -> None:
        super().__init__(error=error)
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class TestEverySearchEndsWithItsConnectionsClosed:
    """The page runs each search in a fresh event loop, and the store engine's HTTP client belongs
    to the loop it was made in."""

    @staticmethod
    def install(
        monkeypatch: pytest.MonkeyPatch, *, error: LlmError | None = None
    ) -> ClosingPipeline:
        fake = ClosingPipeline(error=error)
        monkeypatch.setattr(runner, "get_pipeline", lambda settings: fake)
        return fake

    def test_the_pool_is_closed_after_a_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self.install(monkeypatch)

        runner.run_search(make_search_request())

        assert fake.closed == 1

    def test_the_pool_is_closed_after_a_search_that_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = self.install(monkeypatch, error=LlmError())

        with pytest.raises(LlmError):
            runner.run_search(make_search_request())

        assert fake.closed == 1

    def test_a_pipeline_with_nothing_to_close_is_fine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner, "get_pipeline", lambda settings: FakePipeline())

        response: SearchResponse = runner.run_search(make_search_request())

        assert response.result_count > 0


def test_a_search_started_without_a_key_gets_the_same_plain_words_from_the_real_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt and braces for the notice: if a search is started anyway, the real pipeline answers
    with the plain message, not a stack trace."""
    monkeypatch.setenv("VGA_UI_FIXTURE", "0")
    monkeypatch.setenv("VGA_IMAGE_RANKER", "off")  # nothing to load, nothing to warm up
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigError) as raised:
        runner.run_search(make_search_request())

    assert raised.value.user_message == API_KEY_MISSING_MESSAGE
