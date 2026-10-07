"""The acceptance harness builds the pipeline from the three boundaries
(``Wiring.pipeline_factory``) and records or replays a run at those boundaries. This proves the
real pipeline fits that:

- it is built by ``pipeline_factory(stores)`` from recorders around the real store engine,
- a replay of the recording runs the same pipeline with no network call and no model call,
- the replay gives the same answer, the calls were made in a deterministic order (an outfit's
  garments are searched side by side), and the replay finds nothing to complain about.

The second half goes through ``eval.harness.real`` (the wiring that ``--wiring
eval.harness.real:real_wiring`` names), over the same fakes, as far as it can go without a network:
the whole command line, the real pipeline, the real store engine, the recorder, the link check
through the fetch engine, the report and the labelling sheet.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import httpx
import pytest
import respx

from eval.harness import real
from eval.harness.errors import WiringError
from eval.harness.groups import top_results
from eval.harness.labels import LABEL_COLUMNS
from eval.harness.links import LinksMode, products_to_check
from eval.harness.queries import QUERIES_PATH, AcceptanceQuery, load_queries
from eval.harness.real import build_real_wiring
from eval.harness.recording import RecordingSession, ReplaySession
from eval.harness.runner import QueryRun, run_queries
from eval.harness.runstore import LABELS_FILE, REPORT_FILE, load_run
from eval.harness.wiring import Boundaries, Wiring, load_wiring_factory
from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.harness.cli_support import Cli, SlowToLoadRanker, read_rows, write_rows
from tests.harness.helpers import make_query
from tests.harness.photos import marker_of, put_marked_photos, traces_of_photos
from tests.pipeline.builders import BLAZER, OUTFIT, SHIRT
from tests.pipeline.world import TITLES, StoreWorld, store_for
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    SearchRequest,
    SearchResponse,
    UnderstandResult,
)
from vga.pipeline import pipeline_factory
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine

OUTFIT_TEXT = "an outfit: blazer and shirt"


def understand_for(req: SearchRequest) -> UnderstandResult:
    if req.text == OUTFIT_TEXT:
        return make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=OUTFIT[:2])
    item = make_item_intent(search_keywords=["black oversized blazer", "oversized blazer"])
    kind = InputType.TEXT if req.image is None else InputType.PHOTO_TEXT
    return make_understand_result(input_type=kind, items=[item])


def queries() -> list[AcceptanceQuery]:
    return [
        make_query("q01_text", "text", text="black oversized blazer"),
        make_query("q02_outfit", "text", text=OUTFIT_TEXT),
    ]


def comparable(response: SearchResponse | None) -> dict:
    """The answer, without what differs between two runs: the id and the clock."""
    assert response is not None
    return response.model_dump(exclude={"request_id", "timings", "duration_ms"})


async def run_through(
    boundaries: Boundaries, scope: RecordingSession | ReplaySession, stores: list
) -> list[QueryRun]:
    pipeline = pipeline_factory(stores)(
        boundaries.understander, boundaries.searcher, boundaries.image_ranker
    )
    return await run_queries(
        queries(),
        pipeline,
        make_settings(),
        clock=FakeClock(),
        load_image=lambda query: None,
        scope=scope,
    )


async def test_a_recorded_run_of_the_real_pipeline_replays_with_no_network_and_no_model_call(
    world: StoreWorld, tmp_path: Path, clock: FakeClock
) -> None:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    settings = make_settings()
    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    understander = FakeUnderstander(understand_for)
    ranker = FakeImageRanker()

    session = RecordingSession(tmp_path / "recording")
    live = Boundaries(understander, engine, ranker)
    recorded = await run_through(session.wrap(live), session, stores)
    await engine.aclose()
    requests_after_recording = world.all_requests()

    replaying = ReplaySession(tmp_path / "recording")
    replayed = await run_through(replaying.boundaries(), replaying, stores)

    assert [run.failure for run in recorded] == [None, None]
    assert [run.failure for run in replayed] == [None, None]
    assert requests_after_recording > 0  # the recording really used the fake network
    assert world.all_requests() == requests_after_recording  # the replay used none
    assert len(understander.calls) == 2  # ... and no model call
    assert [comparable(a.response) for a in recorded] == [comparable(b.response) for b in replayed]
    assert all(run.response and run.response.result_count > 0 for run in replayed)
    assert replaying.mismatches == []
    assert replaying.final_notes() == []  # every recorded call was used, none was missing


async def test_the_calls_of_an_outfit_are_recorded_in_item_order_then_store_order(
    world: StoreWorld, tmp_path: Path, clock: FakeClock
) -> None:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    settings = make_settings()
    engine = StoreSearchEngine(settings, StoreRegistry(stores), clock=clock)
    session = RecordingSession(tmp_path / "recording")
    live = Boundaries(FakeUnderstander(understand_for), engine, FakeImageRanker())

    await run_through(session.wrap(live), session, stores)
    await engine.aclose()

    outfit = json.loads((tmp_path / "recording" / "q02_outfit.json").read_text(encoding="utf-8"))
    searched = [(call["item"]["category"], call["stores"]) for call in outfit["search"]]
    assert searched == [
        ("outerwear", ["alpha"]),
        ("outerwear", ["beta"]),
        ("tops", ["alpha"]),
        ("tops", ["beta"]),
    ]


# ============================================================================================
# The real wiring (eval.harness.real): the acceptance run's own code path, over fakes
# ============================================================================================
#
# `build_real_wiring` is what `--wiring eval.harness.real:real_wiring` builds, with the stores,
# the clock, the OpenAI call and the image model handed in. Everything else is the real code: the
# real pipeline, the real store engine and extractor, the real recorder, the real link check
# through the fetch engine, the real report and labelling sheet. Only the network (respx), time
# (FakeClock), OpenAI (FakeUnderstander) and the image model (a fake that charges 10 s to load)
# are fake. These tests are plain functions: the command line starts its own event loop.

EMBEDDING = (0.3141592653, 0.2718281828, 0.1618033988)
JEANS = make_item_intent(
    category=Category.BOTTOMS,
    colour="blue",
    style="jeans",
    search_keywords=["blue jeans", "wide-leg jeans"],
)
SNEAKERS = make_item_intent(
    category=Category.SHOES,
    colour="white",
    style="sneakers",
    search_keywords=["white sneakers", "leather sneakers"],
)
PAGE_URL = re.compile(r"https://(?P<host>[a-z]+\.example)/products/(?P<handle>[^?#]+)")


def acceptance_understanding(req: SearchRequest) -> UnderstandResult:
    """What a good model would make of each of the 10 acceptance queries, in the four kinds of
    garment the fake stores sell. The photo says which query it is (see ``put_marked_photos``)."""
    name = marker_of(req.image) if req.image else ""
    if req.image is None:
        text = req.text or ""
        items = [JEANS] if "jeans" in text else [BLAZER] if "blazer" in text else [SHIRT]
        return make_understand_result(input_type=InputType.TEXT, items=items)
    if name.startswith("outfit_navy"):
        items, kind = [SHIRT, JEANS], InputType.OUTFIT_PHOTO
    elif name.startswith("outfit_black"):
        items, kind = [BLAZER, SNEAKERS], InputType.OUTFIT_PHOTO
    else:
        items = [JEANS] if name.startswith("bottoms") else [BLAZER]
        kind = InputType.PHOTO_TEXT if req.text else InputType.PRODUCT_PHOTO
    return make_understand_result(input_type=kind, items=items)


@dataclass
class RealRun:
    """One acceptance run over the fake world, and what it asked of the fake network."""

    world: StoreWorld
    router: respx.MockRouter
    clock: FakeClock
    root: Path
    stores: list
    understander: FakeUnderstander
    ranker: SlowToLoadRanker
    photos: dict[str, bytes] = field(default_factory=dict)
    page_requests: list[tuple[str, str, float, str]] = field(default_factory=list)
    """(host, url, fake-clock time, user agent) of every product page that was opened."""

    def wiring(self) -> Callable[[Settings], Wiring]:
        return lambda settings: build_real_wiring(
            settings,
            registry=StoreRegistry(self.stores),
            clock=self.clock,
            understander=self.understander,
            image_ranker=self.ranker,
        )

    def settings(self) -> Settings:
        return make_settings(log_dir=str(self.root / "logs"))

    def run(self, cli: Cli, *argv: str) -> int:
        return cli.run(*argv, wiring=self.wiring(), clock=self.clock, settings=self.settings())

    @property
    def recording(self) -> Path:
        return self.root / "eval" / "results" / "run-1" / "recording"

    @property
    def results(self) -> Path:
        return self.root / "eval" / "results"

    @property
    def first_run(self) -> Path:
        return self.results / "run-1"


@pytest.fixture
def real_run(
    world: StoreWorld, router: respx.MockRouter, clock: FakeClock, tmp_path: Path
) -> RealRun:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    state = RealRun(
        world,
        router,
        clock,
        tmp_path / "repo",
        stores,
        FakeUnderstander(acceptance_understanding),
        SlowToLoadRanker(clock, embedding=EMBEDDING),
    )
    state.photos = put_marked_photos(state.root, load_queries(QUERIES_PATH, require_images=False))

    def product_page(request: httpx.Request, **_captured: str) -> httpx.Response:
        # respx passes the pattern's named groups on as keyword arguments; the URL is enough here.
        found = PAGE_URL.match(str(request.url))
        assert found is not None
        kind, tag, number = found["handle"].rsplit("-", 2)
        title = TITLES[kind].format(colour="Black", tag=tag.upper(), n=int(number))
        state.page_requests.append(
            (found["host"], str(request.url), clock.monotonic(), request.headers["user-agent"])
        )
        page = f"<html><head><title>{title} | Demo</title></head><body>{title}</body></html>"
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    router.get(url__regex=PAGE_URL.pattern).mock(side_effect=product_page)
    return state


def distinct_links(run_dir: Path, mode: LinksMode) -> dict[str, str]:
    """URL -> store of every link ``mode`` asks for, over the whole run (each URL once)."""
    wanted: dict[str, str] = {}
    for query_run in load_run(run_dir).runs:
        if query_run.response is not None:
            for product in products_to_check(query_run.response, mode):
                wanted.setdefault(product.product_url, product.store)
    return wanted


class TestARealWiredRunIsRecordedAndReplaysOffline:
    def test_a_live_run_answers_all_ten_queries_and_a_replay_reproduces_it(
        self, real_run: RealRun
    ) -> None:
        cli = Cli(real_run.root)
        assert real_run.run(cli, "--record", str(real_run.recording), "--links", "top10") == 0
        assert "10 of 10 queries answered" in cli.printed
        network_after_record = real_run.world.all_requests()
        model_calls = len(real_run.understander.calls)
        warm_ups = real_run.ranker.warm_ups
        assert network_after_record > 0
        assert model_calls == 10

        assert real_run.run(Cli(real_run.root), "--replay", str(real_run.recording)) == 0

        assert real_run.world.all_requests() == network_after_record  # no network call
        assert len(real_run.understander.calls) == model_calls  # no model call
        assert real_run.ranker.warm_ups == warm_ups  # nothing loaded
        recorded = load_run(real_run.first_run)
        replayed = load_run(real_run.results / "replay")
        assert [r.failure for r in replayed.runs] == [None] * 10
        assert [comparable(r.response) for r in replayed.runs] == [
            comparable(r.response) for r in recorded.runs
        ]
        assert all(r.response and r.response.result_count > 0 for r in replayed.runs)

    def test_the_replay_report_finds_nothing_to_complain_about(self, real_run: RealRun) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        real_run.run(Cli(real_run.root), "--replay", str(real_run.recording))

        text = (real_run.results / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert "Replay diverged" not in text
        assert "could not serve" not in text

    def test_the_stores_of_the_run_are_listed_when_it_starts(self, real_run: RealRun) -> None:
        cli = Cli(real_run.root)

        real_run.run(cli, "--record", str(real_run.recording), "--links", "none")

        assert "Stores in this run (2): alpha, beta" in cli.printed

    def test_the_model_is_warmed_up_once_before_the_first_query(self, real_run: RealRun) -> None:
        cli = Cli(real_run.root)

        real_run.run(cli, "--record", str(real_run.recording), "--links", "none")

        assert (real_run.ranker.warm_ups, real_run.ranker.loads) == (1, 1)
        warm_line = next(x for x in cli.printed.splitlines() if x.startswith("Warm-up:"))
        assert "done in 10.0 s" in warm_line
        assert cli.printed.index(warm_line) < cli.printed.index("q01_product_gown")
        run = load_run(real_run.first_run)
        assert all(q.wall_ms < 10_000 for q in run.runs)  # the load is in no query's time


class TestNoPhotoIsKept:
    def test_nothing_a_real_wired_run_saves_holds_any_trace_of_a_photo_or_its_embedding(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "top10")
        real_run.run(Cli(real_run.root), "--replay", str(real_run.recording))

        # The photos really reached the model and the image ranker, so a clean scan means
        # something: the run had every chance to write them down.
        assert sum(1 for call in real_run.understander.calls if call.image) == 7
        assert real_run.ranker.calls
        assert len(list(real_run.recording.glob("q*.json"))) == 10  # a file per query
        assert traces_of_photos(real_run.results, real_run.photos.values(), EMBEDDING) == []

    def test_the_recording_keeps_the_models_answer_which_is_what_replay_needs(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        gown = json.loads((real_run.recording / "q01_product_gown.json").read_text("utf-8"))

        assert gown["understand"][0]["result"]["items"][0]["category"] == "outerwear"
        assert gown["search"]
        assert gown["image_scores"]


class TestTheLinkCheckUsesTheFetchEngine:
    @pytest.mark.parametrize("mode", ["top10", "all"])
    def test_each_link_is_opened_once_and_only_the_ones_asked_for(
        self, real_run: RealRun, mode: str
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", mode)

        wanted = distinct_links(real_run.first_run, LinksMode(mode))
        opened = [url for _host, url, _moment, _agent in real_run.page_requests]

        assert sorted(opened) == sorted(wanted)  # each link once, none more, none fewer
        assert len(wanted) > 10

    def test_all_covers_more_links_than_the_top_ten(self, real_run: RealRun) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "top10")

        top10 = distinct_links(real_run.first_run, LinksMode.TOP10)
        everything = distinct_links(real_run.first_run, LinksMode.ALL)

        assert set(top10) < set(everything)

    def test_every_page_request_is_honest_and_at_most_one_per_second_per_store(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "top10")

        assert {agent for *_rest, agent in real_run.page_requests} == {
            real_run.settings().user_agent
        }
        by_host: dict[str, list[float]] = {}
        for host, _url, moment, _agent in real_run.page_requests:
            by_host.setdefault(host, []).append(moment)
        assert set(by_host) == {"alpha.example", "beta.example"}
        for host, moments in by_host.items():
            gaps = [later - earlier for earlier, later in pairwise(moments)]
            assert all(gap >= 0.99 for gap in gaps), (host, gaps)

    def test_robots_txt_of_every_store_was_read_and_the_links_are_in_the_report(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "top10")

        robots = [c for c in real_run.router.calls if c.request.url.path == "/robots.txt"]
        assert {c.request.url.host for c in robots} >= {"alpha.example", "beta.example"}
        report = (real_run.first_run / REPORT_FILE).read_text(encoding="utf-8")
        assert "Links ok" in report
        assert "no page opened" not in report  # every fake product page opened


class TestTheLabellingSheetOfARealShapedRun:
    def test_it_has_a_row_per_top_ten_result_per_garment_with_everything_to_judge_it(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        rows = read_rows(real_run.first_run / LABELS_FILE)

        assert list(rows[0]) == list(LABEL_COLUMNS)
        expected = sum(
            min(10, group.result_count)
            for r in load_run(real_run.first_run).runs
            if r.response
            for group in r.response.groups
        )
        assert len(rows) == expected
        assert {row["label"] for row in rows} == {""}
        assert {row["price_range"] for row in rows} <= {"Budget", "Mid-range", "Premium", "Luxury"}
        assert all(re.fullmatch(r"[\d,]+(\.\d\d)? AED", row["price"]) for row in rows)
        assert {row["store"] for row in rows} <= {"Alpha", "Beta"}
        assert all(row["url"].startswith("https://") for row in rows)

    def test_rows_name_the_photo_to_open_and_an_outfit_has_a_block_per_garment(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        rows = read_rows(real_run.first_run / LABELS_FILE)

        photo_of = {row["query_id"]: row["photo"] for row in rows}
        assert photo_of["q01_product_gown"] == "dress_burgundy_gown.png"
        assert photo_of["q09_photo_text_gown_green"] == "dress_burgundy_gown.png"
        assert photo_of["q06_text_blazer_budget"] == ""
        outfit = [r for r in rows if r["query_id"] == "q04_outfit_palazzo_top"]
        groups = [row["group"] for row in outfit]
        assert set(groups) == {"tops", "bottoms"}
        assert groups == sorted(groups, key=["tops", "bottoms"].index)  # a block per garment
        saved = next(
            r for r in load_run(real_run.first_run).runs if r.query.id == "q04_outfit_palazzo_top"
        )
        assert saved.response is not None
        tops = top_results(saved.response.groups[0])
        assert [row["url"] for row in outfit][: len(tops)] == [s.product.product_url for s in tops]

    def test_a_filled_sheet_is_scored_against_the_same_run(self, real_run: RealRun) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "top10")
        sheet = real_run.first_run / LABELS_FILE
        rows = read_rows(sheet)
        for row in rows:
            row["label"] = "1"
        write_rows(sheet, rows)
        scoring = Cli(real_run.root)

        code = scoring.run("--rescore", str(real_run.first_run), "--labels", str(sheet))

        assert code == 0, scoring.errors
        assert "Verdict:" in scoring.printed


class TestTheWiringFailsEarlyAndPlainly:
    def test_a_missing_openai_key_is_found_before_anything_is_made_or_spent(
        self, real_run: RealRun
    ) -> None:
        # No understander is handed in, and the tests run without OPENAI_API_KEY.
        cli = Cli(real_run.root)

        def without_a_key(settings: Settings) -> Wiring:
            return build_real_wiring(
                settings, registry=StoreRegistry(real_run.stores), clock=real_run.clock
            )

        code = cli.run(
            "--record",
            str(real_run.recording),
            wiring=without_a_key,
            settings=make_settings(openai_model="gpt-6-luna"),
        )

        assert code == 2
        assert "OPENAI_API_KEY" in cli.errors
        assert not real_run.recording.exists()
        assert not real_run.first_run.exists()
        assert real_run.world.all_requests() == 0

    def test_no_enabled_store_is_a_plain_error(self) -> None:
        with pytest.raises(WiringError, match="No store is enabled"):
            build_real_wiring(make_settings(), registry=StoreRegistry([]))

    def test_the_production_wiring_reads_config_stores_and_touches_nothing(
        self, router: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logged: list[dict] = []
        monkeypatch.setattr(real, "configure_logging", lambda **kwargs: logged.append(kwargs))
        settings = make_settings(log_dir=str(tmp_path / "logs"))

        wiring = real.real_wiring(settings)

        assert router.calls.call_count == 0  # not one request (the router refuses strangers)
        assert wiring.stores
        assert all(store.enabled for store in wiring.stores)
        assert {store.country for store in wiring.stores} == {settings.country}
        assert wiring.build_boundaries is not None
        assert wiring.link_fetch is not None
        assert wiring.aclose is not None
        assert logged[0]["log_dir"] == str(tmp_path / "logs")  # the run's log goes to a file ...
        assert logged[0]["stream"].write("x") == 1  # ... and the screen gets none of it

    def test_the_command_line_name_resolves_to_the_production_wiring(self) -> None:
        assert load_wiring_factory("eval.harness.real:real_wiring") is real.real_wiring


# ============================================================================================
# The shopper's answer to "Who is this for?": recorded and replayed
# ============================================================================================
#
# A query that records the shopper's answer is searched twice: the first search, then the search
# the page runs after the answer (the first understanding reused, the gender applied, no photo, no
# model call). Both belong to one query, so one recording holds both, in order, and a replay serves
# both offline.

GUESSED_MEN_BLAZER = make_item_intent(
    search_keywords=["black oversized blazer", "oversized blazer"],
    gender=Gender.MEN,
    gender_source=GenderSource.INFERRED,
)
SHOPPER_PHOTO = make_image_bytes("JPEG", (64, 64), (10, 120, 200))


def guessed_men(req: SearchRequest) -> UnderstandResult:
    """The model looks at a women's blazer and guesses men: shown to the shopper, never applied."""
    return make_understand_result(input_type=InputType.PRODUCT_PHOTO, items=[GUESSED_MEN_BLAZER])


def photo_query(answer: str | None) -> AcceptanceQuery:
    return make_query("q01_photo", "product_photo", shopper_gender=answer)


@dataclass
class AnsweredWorld:
    """Two stores for everyone and one for men only, a model that guesses men, and a recorder."""

    world: StoreWorld
    clock: FakeClock
    directory: Path
    stores: list
    understander: FakeUnderstander
    ranker: FakeImageRanker

    async def record(self, answer: str | None) -> tuple[QueryRun, RecordingSession]:
        engine = StoreSearchEngine(make_settings(), StoreRegistry(self.stores), clock=self.clock)
        session = RecordingSession(self.directory)
        live = session.wrap(Boundaries(self.understander, engine, self.ranker))
        [run] = await self.run(live, session, answer)
        await engine.aclose()
        return run, session

    async def replay(self, answer: str | None) -> tuple[QueryRun, ReplaySession]:
        session = ReplaySession(self.directory)
        [run] = await self.run(session.boundaries(), session, answer)
        return run, session

    async def run(
        self, boundaries: Boundaries, scope: RecordingSession | ReplaySession, answer: str | None
    ) -> list[QueryRun]:
        pipeline = pipeline_factory(self.stores)(
            boundaries.understander, boundaries.searcher, boundaries.image_ranker
        )
        return await run_queries(
            [photo_query(answer)],
            pipeline,
            make_settings(),
            clock=FakeClock(),
            load_image=lambda query: SHOPPER_PHOTO,
            scope=scope,
        )

    def recording(self) -> dict:
        return json.loads((self.directory / "q01_photo.json").read_text(encoding="utf-8"))

    def manifest(self) -> dict:
        return json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture
def answered_world(world: StoreWorld, clock: FakeClock, tmp_path: Path) -> AnsweredWorld:
    stores = [store_for("alpha"), store_for("beta"), store_for("mens", genders=[Gender.MEN])]
    for store in stores:
        world.add(store)
    return AnsweredWorld(
        world,
        clock,
        tmp_path / "recording",
        stores,
        FakeUnderstander(guessed_men),
        FakeImageRanker(embedding=EMBEDDING),
    )


def stores_of(run: QueryRun) -> set[str]:
    assert run.response is not None
    return {scored.product.store for scored in run.response.products}


class TestTheAnswerIsAppliedByTheRealPipeline:
    async def test_without_an_answer_a_guessed_gender_excludes_no_store(
        self, answered_world: AnsweredWorld
    ) -> None:
        run, _session = await answered_world.record(None)

        assert stores_of(run) == {"Alpha", "Beta", "Mens"}  # today's behaviour, Rule 8
        assert run.gender is None
        assert len(answered_world.recording()["search"]) == 3  # one search, three stores

    async def test_with_the_answer_the_results_scored_are_the_ones_after_it(
        self, answered_world: AnsweredWorld
    ) -> None:
        run, _session = await answered_world.record("women")

        assert stores_of(run) == {"Alpha", "Beta"}  # the men-only store is out of the results
        assert run.response is not None
        [skipped] = run.response.stores_skipped
        assert skipped.store_id == "mens"
        [item] = run.response.understood.items
        assert (item.gender, item.gender_source) == (Gender.WOMEN, GenderSource.EXPLICIT)
        assert run.gender is not None
        assert run.gender.asked is True

    async def test_the_search_after_the_answer_asks_only_the_stores_that_sell_for_it(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record("women")

        searched = [call["stores"] for call in answered_world.recording()["search"]]
        assert searched == [["alpha"], ["beta"], ["mens"], ["alpha"], ["beta"]]

    async def test_a_garment_whose_gender_was_stated_is_not_searched_again_and_still_replays(
        self, answered_world: AnsweredWorld
    ) -> None:
        tops = make_item_intent(
            category=Category.TOPS,
            colour="white",
            style="shirt",
            search_keywords=["white shirt", "cotton shirt"],
            gender=Gender.MEN,
            gender_source=GenderSource.INFERRED,
        )
        shoes = make_item_intent(
            category=Category.SHOES,
            colour="white",
            style="sneakers",
            search_keywords=["white sneakers", "leather sneakers"],
            gender=Gender.WOMEN,
            gender_source=GenderSource.EXPLICIT,
        )
        answered_world.understander = FakeUnderstander(
            make_understand_result(input_type=InputType.OUTFIT_PHOTO, items=[tops, shoes])
        )

        recorded, _session = await answered_world.record("women")

        searched = [
            (call["item"]["category"], call["stores"])
            for call in answered_world.recording()["search"]
        ]
        assert searched == [  # the first search, then only the garment that was asked about
            ("tops", ["alpha"]),
            ("tops", ["beta"]),
            ("tops", ["mens"]),
            ("shoes", ["alpha"]),
            ("shoes", ["beta"]),
            ("tops", ["alpha"]),
            ("tops", ["beta"]),
        ]
        assert recorded.response is not None
        assert [g.result_count > 0 for g in recorded.response.groups] == [True, True]
        replayed, session = await answered_world.replay("women")
        assert comparable(replayed.response) == comparable(recorded.response)
        assert session.final_notes() == []

    async def test_the_search_after_the_answer_makes_no_model_call(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record("women")

        assert len(answered_world.understander.calls) == 1
        assert answered_world.understander.calls[0].rerun_of is None
        assert len(answered_world.recording()["understand"]) == 1

    async def test_the_photo_reaches_the_model_once_and_the_ranker_scores_both_searches(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record("women")

        assert [bool(call.image) for call in answered_world.understander.calls] == [True]
        scores = answered_world.recording()["image_scores"]
        assert len(scores) == 2  # the first search, and the search after the answer
        assert [entry["embedded"] for entry in scores] == [True, True]

    async def test_the_recording_never_holds_the_embedding_itself(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record("women")

        assert traces_of_photos(answered_world.directory, [SHOPPER_PHOTO], EMBEDDING) == []

    async def test_the_manifest_keeps_both_live_times_for_the_replay(
        self, answered_world: AnsweredWorld
    ) -> None:
        run, _session = await answered_world.record("women")

        entry = answered_world.manifest()["queries"]["q01_photo"]
        assert run.confirm_ms is not None
        assert entry["live_duration_ms"] == run.duration_ms
        assert entry["live_confirm_ms"] == run.confirm_ms

    async def test_a_query_with_no_answer_records_no_second_time(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record(None)

        assert "live_confirm_ms" not in answered_world.manifest()["queries"]["q01_photo"]


class TestAnAnsweredRunReplaysOffline:
    async def test_the_replay_gives_identical_scored_results_with_no_network_and_no_model(
        self, answered_world: AnsweredWorld
    ) -> None:
        recorded, _session = await answered_world.record("women")
        requests = answered_world.world.all_requests()
        assert requests > 0
        model_calls = len(answered_world.understander.calls)
        scoring_calls = len(answered_world.ranker.calls)

        replayed, session = await answered_world.replay("women")

        assert replayed.failure is None
        assert comparable(replayed.response) == comparable(recorded.response)
        assert stores_of(replayed) == {"Alpha", "Beta"}
        assert answered_world.world.all_requests() == requests  # not one request
        assert len(answered_world.understander.calls) == model_calls  # not one model call
        assert len(answered_world.ranker.calls) == scoring_calls  # the model is not run again
        assert session.mismatches == []

    async def test_every_recorded_call_is_used_in_order_including_the_second_image_scores(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record("women")

        _replayed, session = await answered_world.replay("women")

        # "the pipeline made N call(s), the recording holds M" would name a call left unused.
        assert session.final_notes() == []

    async def test_the_answer_and_the_garments_it_was_given_for_are_the_same_in_the_replay(
        self, answered_world: AnsweredWorld
    ) -> None:
        recorded, _session = await answered_world.record("women")

        replayed, _replay = await answered_world.replay("women")

        assert recorded.gender is not None
        assert replayed.gender is not None
        assert replayed.gender.answer == recorded.gender.answer
        assert replayed.gender.asked is True
        assert replayed.gender.garments == recorded.gender.garments

    async def test_a_replay_of_a_run_with_no_answer_is_unchanged(
        self, answered_world: AnsweredWorld
    ) -> None:
        recorded, _session = await answered_world.record(None)

        replayed, session = await answered_world.replay(None)

        assert comparable(replayed.response) == comparable(recorded.response)
        assert replayed.gender is None
        assert session.final_notes() == []

    async def test_asking_a_question_the_recording_never_asked_is_a_plain_mismatch(
        self, answered_world: AnsweredWorld
    ) -> None:
        await answered_world.record(None)  # recorded without the answer

        replayed, session = await answered_world.replay("women")  # replayed with one

        assert session.mismatches  # the extra search is not in the recording
        assert "record again" in session.mismatches[0]
        assert stores_of(replayed) == set()  # nothing was invented to fill the gap


class TestTheCommandLineKeepsBothSearches:
    def test_the_recorded_run_answers_the_seven_photo_queries_and_only_those(
        self, real_run: RealRun
    ) -> None:
        cli = Cli(real_run.root)
        real_run.run(cli, "--record", str(real_run.recording), "--links", "none")

        run = load_run(real_run.first_run)

        asked = {r.query.id for r in run.runs if r.gender is not None and r.gender.asked}
        text_only = {r.query.id for r in run.runs if r.query.image is None}
        assert len(asked) == 7
        assert len(text_only) == 3
        assert asked.isdisjoint(text_only)
        assert all(r.gender is None for r in run.runs if r.query.id in text_only)
        assert "after the shopper answered women" in cli.printed

    def test_the_run_makes_one_model_call_per_query_and_none_for_an_answer(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        assert len(real_run.understander.calls) == 10
        assert all(call.rerun_of is None for call in real_run.understander.calls)
        gown = json.loads((real_run.recording / "q01_product_gown.json").read_text("utf-8"))
        assert len(gown["understand"]) == 1
        assert len(gown["search"]) > 2  # the first search and the search after the answer

    def test_the_notes_and_the_times_are_in_the_report_and_run_json(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")

        report = (real_run.first_run / REPORT_FILE).read_text(encoding="utf-8")
        assert "was answered, as the page does, for" in report
        assert "q01_product_gown (women)" in report
        assert "the 30 s limit applies to it alone" in report
        saved = json.loads((real_run.first_run / "run.json").read_text(encoding="utf-8"))
        gown = next(q for q in saved["queries"] if q["query"]["id"] == "q01_product_gown")
        assert gown["gender"]["asked"] is True
        both = gown["duration_ms"] + gown["gender"]["duration_ms"]
        assert gown["total_ms"] == pytest.approx(both)

    def test_the_replay_reports_the_recorded_times_of_both_searches(
        self, real_run: RealRun
    ) -> None:
        real_run.run(Cli(real_run.root), "--record", str(real_run.recording), "--links", "none")
        manifest = json.loads((real_run.recording / "manifest.json").read_text("utf-8"))

        real_run.run(Cli(real_run.root), "--replay", str(real_run.recording))

        replayed = load_run(real_run.results / "replay")
        gown = next(r for r in replayed.runs if r.query.id == "q01_product_gown")
        recorded = manifest["queries"]["q01_product_gown"]
        assert gown.duration_source == "recorded"
        assert gown.duration_ms == recorded["live_duration_ms"]
        assert gown.confirm_ms == recorded["live_confirm_ms"]
        text = (real_run.results / "replay" / REPORT_FILE).read_text(encoding="utf-8")
        assert "(recorded; +" in text
        assert "the recording holds" not in text  # every recorded call was used, the second too
