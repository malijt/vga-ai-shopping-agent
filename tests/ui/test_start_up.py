"""Start-up of live mode: the pipeline is built and the image model loaded once, when the page
first opens, so the first photo search does not pay for the load (about 10 s cold, against a 30 s
limit for the whole search). Later page runs and searches never do it again.
"""

import pytest
from streamlit.testing.v1 import AppTest

from app import runner
from tests.ui.conftest import InstallLive
from tests.ui.helpers import search
from vga.models import MixPreset
from vga.pipeline import SearchPipeline
from vga.settings import Settings


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch, install_live: InstallLive) -> dict[str, int]:
    """The real ``get_pipeline`` (so Streamlit's resource cache is used) over the real pipeline
    on fake boundaries, with every build and every model load counted."""
    real_get_pipeline = runner.get_pipeline
    live = install_live()
    counts = {"builds": 0, "warm_ups": 0}

    def build(settings: Settings) -> SearchPipeline:
        counts["builds"] += 1
        return live.pipeline

    async def warm_up(self: SearchPipeline) -> bool:
        counts["warm_ups"] += 1
        return False  # no image model here: not an error for the page

    monkeypatch.setattr(runner, "get_pipeline", real_get_pipeline)
    monkeypatch.setattr(runner, "build_pipeline", build)
    monkeypatch.setattr(SearchPipeline, "warm_up", warm_up)
    return counts


class TestTheModelIsLoadedOnceWhenThePageFirstOpens:
    def test_opening_the_page_builds_the_pipeline_and_loads_the_model_before_any_search(
        self, at: AppTest, counted: dict[str, int]
    ) -> None:
        at.run()

        assert counted == {"builds": 1, "warm_ups": 1}
        assert not at.exception
        assert not at.error  # a model that is not there is not an error for the page

    def test_a_rerun_of_the_page_does_not_load_it_again(
        self, at: AppTest, counted: dict[str, int]
    ) -> None:
        at.run()

        at.run()
        at.run()

        assert counted == {"builds": 1, "warm_ups": 1}

    def test_typing_in_the_boxes_is_a_rerun_and_does_not_load_it_again(
        self, at: AppTest, counted: dict[str, int]
    ) -> None:
        at.run()

        at.text_input(key="query_text").set_value("black blazer").run()

        assert counted["warm_ups"] == 1

    def test_searches_a_mix_change_and_a_chip_edit_do_not_load_it_again(
        self, at: AppTest, counted: dict[str, int]
    ) -> None:
        at.run()
        search(at)
        search(at, "black oversized blazer for women")
        at.sidebar.radio(key="mix_preset").set_value(MixPreset.LUXURY_FIRST).run()
        at.text_input(key="chip_0_colour").set_value("navy").run()
        at.button(key="chips_apply").click().run()

        assert not at.exception
        assert counted == {"builds": 1, "warm_ups": 1}

    def test_a_new_browser_session_reuses_the_one_pipeline_of_the_process(
        self, counted: dict[str, int]
    ) -> None:
        first = AppTest.from_file(str(runner.PROJECT_ROOT / "app" / "main.py"), default_timeout=60)
        second = AppTest.from_file(str(runner.PROJECT_ROOT / "app" / "main.py"), default_timeout=60)

        first.run()
        search(first)
        second.run()
        search(second)

        assert counted == {"builds": 1, "warm_ups": 1}

    def test_the_re_run_cache_survives_between_searches_because_it_is_the_same_instance(
        self, at: AppTest, counted: dict[str, int]
    ) -> None:
        # A mix change costs nothing only if the pipeline that answers it is the pipeline that
        # answered the first search: its re-run cache lives on the instance.
        at.run()
        search(at)
        before = at.session_state["response"]

        at.sidebar.radio(key="mix_preset").set_value(MixPreset.VALUE_FIRST).run()

        after = at.session_state["response"]
        assert after.usage.llm_calls == 0
        assert after.stores_used == [
            report.model_copy(update={"from_cache": True, "duration_ms": 0.0})
            for report in before.stores_used
        ]


class TestNothingIsBuiltWhenThereIsNothingToBuildFor:
    def test_fixture_mode_builds_no_real_pipeline_and_loads_no_model(
        self, at: AppTest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def must_not_build(settings: Settings) -> SearchPipeline:
            raise AssertionError("fixture mode must not build the real pipeline")

        monkeypatch.setattr(runner, "build_pipeline", must_not_build)

        at.run()
        search(at)

        assert not at.exception
        assert at.subheader  # the sample results are there

    def test_a_missing_key_builds_nothing_and_the_page_says_what_to_do(
        self, at: AppTest, live_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def must_not_build(settings: Settings) -> SearchPipeline:
            raise AssertionError("no pipeline should be built without a key")

        monkeypatch.delenv("OPENAI_API_KEY")
        monkeypatch.setattr(runner, "build_pipeline", must_not_build)

        at.run()

        assert at.error
        assert not at.exception
