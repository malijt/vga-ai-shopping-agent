"""Each shared fake passes the same contract suite the real implementation must pass (1.2.7)."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_products,
    make_search_request,
    make_settings,
    make_store_config,
    make_store_result,
    make_understand_result,
)
from tests.fakes import (
    FakeClock,
    FakeImageRanker,
    FakePipeline,
    FakeStoreSearcher,
    FakeUnderstander,
    StoreHttpFixtures,
    UnexpectedRequestError,
    load_recorded_response,
)
from tests.foundation.contracts import (
    ClockContract,
    ImageRankerContract,
    PipelineContract,
    StoreSearcherContract,
    UnderstanderContract,
)
from vga.errors import InvalidInputError
from vga.interfaces import Clock, ImageRanker, Pipeline, StoreSearcher, SystemClock, Understander
from vga.models import QueryImage, SearchResponse, Step, StoreStatus


class TestFakeClockContract(ClockContract):
    @pytest.fixture
    def clock(self) -> Clock:
        return FakeClock()


class TestSystemClockContract(ClockContract):
    @pytest.fixture
    def clock(self) -> Clock:
        return SystemClock()


class TestFakeUnderstanderContract(UnderstanderContract):
    @pytest.fixture
    def understander(self) -> Understander:
        return FakeUnderstander()


class TestFakeStoreSearcherContract(StoreSearcherContract):
    @pytest.fixture
    def searcher(self) -> StoreSearcher:
        return FakeStoreSearcher()


class TestFakeImageRankerContract(ImageRankerContract):
    @pytest.fixture
    def ranker(self) -> ImageRanker:
        return FakeImageRanker()


class TestFakePipelineContract(PipelineContract):
    @pytest.fixture
    def pipeline(self) -> Pipeline:
        return FakePipeline()


class TestFakeClock:
    async def test_sleep_advances_virtual_time_without_waiting(self) -> None:
        clock = FakeClock(start=100.0)

        await asyncio.wait_for(clock.sleep(3600), timeout=1)

        assert clock.monotonic() == 3700.0

    async def test_sequential_sleeps_add_up(self) -> None:
        clock = FakeClock(start=0.0)

        await clock.sleep(1)
        await clock.sleep(2)

        assert clock.monotonic() == 3.0

    async def test_concurrent_sleeps_overlap_like_real_time(self) -> None:
        clock = FakeClock(start=0.0)

        await asyncio.gather(clock.sleep(1), clock.sleep(2), clock.sleep(2))

        assert clock.monotonic() == 2.0

    async def test_a_task_that_wakes_early_sees_the_earlier_time(self) -> None:
        clock = FakeClock(start=0.0)
        woke_at: dict[str, float] = {}

        async def sleeper(name: str, seconds: float) -> None:
            await clock.sleep(seconds)
            woke_at[name] = clock.monotonic()

        await asyncio.gather(sleeper("short", 1), sleeper("long", 5))

        assert woke_at == {"short": 1.0, "long": 5.0}

    async def test_rate_limited_requests_take_at_least_n_minus_one_over_rps(self) -> None:
        # The shape P6's limiter will have: reserve a slot, then sleep until it is due.
        clock = FakeClock(start=0.0)
        rps = 2.0
        next_free = 0.0

        async def acquire() -> None:
            nonlocal next_free
            start = max(clock.monotonic(), next_free)
            next_free = start + 1 / rps
            await clock.sleep(start - clock.monotonic())

        await asyncio.gather(*(acquire() for _ in range(5)))

        assert clock.monotonic() >= (5 - 1) / rps

    async def test_work_that_races_a_deadline_is_cancelled_in_virtual_time(self) -> None:
        clock = FakeClock(start=0.0)

        async def slow_store() -> str:
            await clock.sleep(40)
            return "late"

        slow = asyncio.ensure_future(slow_store())
        deadline = asyncio.ensure_future(clock.sleep(30))
        await asyncio.wait({slow, deadline}, return_when=asyncio.FIRST_COMPLETED)
        slow.cancel()

        assert deadline.done()
        assert clock.monotonic() == 30.0

    async def test_a_cancelled_sleeper_does_not_move_time(self) -> None:
        clock = FakeClock(start=0.0)
        task = asyncio.ensure_future(clock.sleep(100))
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        await clock.sleep(1)

        assert clock.monotonic() == 1.0

    def test_advance_moves_time_at_once(self) -> None:
        clock = FakeClock(start=0.0)

        clock.advance(601)

        assert clock.monotonic() == 601.0

    async def test_advance_wakes_due_sleepers(self) -> None:
        clock = FakeClock(start=0.0)
        task = asyncio.ensure_future(clock.sleep(10))
        await asyncio.sleep(0)

        clock.advance(10)
        await asyncio.wait_for(task, timeout=1)

        assert task.done()

    async def test_sleeps_records_requested_durations_in_order(self) -> None:
        clock = FakeClock()

        for seconds in (0.5, 1.0, 2.0):
            await clock.sleep(seconds)

        assert clock.sleeps == [0.5, 1.0, 2.0]


class TestFakeUnderstander:
    async def test_returns_the_configured_result_and_records_the_call(self) -> None:
        canned = make_understand_result(language="ar")
        fake = FakeUnderstander(canned)
        request = make_search_request()

        assert await fake.understand(request) is canned
        assert fake.calls == [request]

    async def test_can_compute_the_result_from_the_request(self) -> None:
        fake = FakeUnderstander(lambda req: make_understand_result(edits=[req.text or ""]))

        result = await fake.understand(make_search_request(text="red dress"))

        assert result.edits == ["red dress"]

    async def test_can_raise(self) -> None:
        fake = FakeUnderstander(error=InvalidInputError())

        with pytest.raises(InvalidInputError):
            await fake.understand(make_search_request())

    async def test_default_result_follows_the_input_type(self) -> None:
        fake = FakeUnderstander()

        photo = await fake.understand(make_search_request(image=make_image_bytes(), text=None))
        both = await fake.understand(make_search_request(image=make_image_bytes(), text="darker"))
        text = await fake.understand(make_search_request(text="black blazer"))

        assert [r.input_type.value for r in (photo, both, text)] == [
            "product_photo",
            "photo_text",
            "text",
        ]


class TestFakeImageRanker:
    async def test_uses_configured_scores_then_the_default(self) -> None:
        products = make_products(2)
        ranker = FakeImageRanker({products[0].key: 0.9}, default=0.1)

        scores = await ranker.score(QueryImage(image=make_image_bytes()), products)

        assert scores == {products[0].key: 0.9, products[1].key: 0.1}

    async def test_fills_the_query_embedding_so_the_photo_can_be_dropped(self) -> None:
        query = QueryImage(image=make_image_bytes())

        await FakeImageRanker(embedding=[1.0, 2.0]).score(query, make_products(1))

        assert query.embedding == [1.0, 2.0]

    async def test_can_raise_to_test_the_fallback(self) -> None:
        with pytest.raises(RuntimeError):
            await FakeImageRanker(error=RuntimeError("model failed")).score(
                QueryImage(image=b"x"), make_products(1)
            )


class TestFakeStoreSearcher:
    async def test_canned_result_is_returned_for_its_store(self) -> None:
        canned = make_store_result(StoreStatus.BLOCKED, store_id="store-b")
        fake = FakeStoreSearcher({"store-b": canned})
        stores = [make_store_config(id="store-a"), make_store_config(id="store-b")]

        results = await fake.search(make_item_intent(), stores)

        assert results[1] is canned
        assert results[0].status is StoreStatus.OK
        assert fake.calls == [(make_item_intent(), ["store-a", "store-b"])]

    async def test_zero_products_gives_an_empty_status(self) -> None:
        fake = FakeStoreSearcher(product_count=0)

        (result,) = await fake.search(make_item_intent(), [make_store_config()])

        assert result.status is StoreStatus.EMPTY


class TestFakePipeline:
    async def test_returns_the_sample_response_for_the_request(self) -> None:
        request = make_search_request()

        response = await FakePipeline().run(request, make_settings())

        assert isinstance(response, SearchResponse)
        assert response.request_id == request.request_id
        assert response.result_count > 20

    async def test_reports_every_step_in_order(self) -> None:
        seen: list[Step] = []

        await FakePipeline().run(make_search_request(), make_settings(), on_step=seen.append)

        assert seen == list(Step)

    async def test_records_calls_and_can_raise(self) -> None:
        pipeline = FakePipeline(error=InvalidInputError())
        request = make_search_request()

        with pytest.raises(InvalidInputError):
            await pipeline.run(request, make_settings())

        assert [call.req for call in pipeline.calls] == [request]


class TestStoreHttpFixtures:
    @pytest.fixture
    def body_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "search.json"
        path.write_text('{"products": []}', encoding="utf-8")
        return path

    def test_loads_a_recorded_response_with_defaults_from_the_extension(
        self, body_file: Path
    ) -> None:
        recorded = load_recorded_response(body_file)

        assert recorded.status == 200
        assert recorded.headers["content-type"] == "application/json"
        assert recorded.text == '{"products": []}'

    def test_sidecar_file_overrides_url_status_and_headers(self, body_file: Path) -> None:
        sidecar = body_file.with_name("search.json.meta.json")
        sidecar.write_text(
            json.dumps(
                {"url": "https://www.demo-store.example/s", "status": 403, "headers": {"X-A": "1"}}
            ),
            encoding="utf-8",
        )

        recorded = load_recorded_response(body_file)

        assert (recorded.url, recorded.status, recorded.headers["x-a"]) == (
            "https://www.demo-store.example/s",
            403,
            "1",
        )

    def test_arguments_beat_the_sidecar(self, body_file: Path) -> None:
        recorded = load_recorded_response(body_file, status=429, headers={"Retry-After": "60"})

        assert (recorded.status, recorded.headers["retry-after"]) == (429, "60")

    async def test_serves_recorded_responses_and_counts_requests(self, body_file: Path) -> None:
        fixtures = StoreHttpFixtures().add_file("https://www.demo-store.example/search", body_file)

        async with httpx.AsyncClient(transport=fixtures.transport()) as client:
            first = await client.get("https://www.demo-store.example/search?q=blazer")
            await client.get("https://www.demo-store.example/search?q=jacket")

        assert first.json() == {"products": []}
        assert fixtures.request_count() == 2
        assert fixtures.request_count("www.demo-store.example") == 2
        assert fixtures.request_count("other.example") == 0
        assert fixtures.urls()[0].endswith("q=blazer")

    async def test_longest_matching_prefix_wins(self, body_file: Path) -> None:
        fixtures = StoreHttpFixtures()
        fixtures.add("https://x.example/", load_recorded_response(body_file, status=404))
        fixtures.add("https://x.example/search", load_recorded_response(body_file, status=200))

        async with httpx.AsyncClient(transport=fixtures.transport()) as client:
            response = await client.get("https://x.example/search?q=a")

        assert response.status_code == 200

    async def test_unexpected_request_is_remembered_even_if_the_caller_swallows_the_error(
        self,
    ) -> None:
        fixtures = StoreHttpFixtures()

        async with httpx.AsyncClient(transport=fixtures.transport()) as client:
            with pytest.raises(UnexpectedRequestError):
                await client.get("https://elsewhere.example/a")

        with pytest.raises(UnexpectedRequestError, match=r"elsewhere\.example"):
            fixtures.assert_no_unexpected_requests()
