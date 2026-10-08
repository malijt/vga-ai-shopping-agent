"""The harness answers "Who is this for?" the way a shopper would (BRD Rule 8, plan A3).

A query may record the shopper's answer. After its first search, if the app would ask (some
garment's gender was not stated), the runner gives the answer exactly as the page does: one more
search that reuses the first understanding and applies the answer to every garment whose gender
was not stated. That second response is what is scored. The 30 s limit is the first search's.
"""

from dataclasses import dataclass, field

import pytest

from eval.harness.queries import AcceptanceQuery
from eval.harness.runner import QueryRun, run_queries
from tests.factories import (
    make_image_bytes,
    make_item_intent,
    make_settings,
    make_understand_result,
)
from tests.fakes import FakeClock, PipelineCall
from tests.harness.helpers import make_query, make_response
from vga.errors import InvalidInputError
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    ItemIntent,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    StepTiming,
)
from vga.settings import Settings

EMBEDDING = [0.25, 0.5, 0.75]
PHOTO = make_image_bytes()


def garment(
    category: Category = Category.TOPS,
    gender: Gender | None = None,
    source: GenderSource = GenderSource.NONE,
    **overrides: object,
) -> ItemIntent:
    keywords = [f"{category.value} one", f"{category.value} two"]
    return make_item_intent(
        category=category,
        gender=gender,
        gender_source=source,
        search_keywords=keywords,
        **overrides,
    )


def understanding(*items: ItemIntent, kind: InputType = InputType.OUTFIT_PHOTO):
    return make_understand_result(input_type=kind, items=list(items))


def response_of(*items: ItemIntent, request_id: str, **overrides: object) -> SearchResponse:
    kind = InputType.OUTFIT_PHOTO if len(items) > 1 else InputType.PRODUCT_PHOTO
    return make_response(
        request_id=request_id, understood=understanding(*items, kind=kind), **overrides
    )


@dataclass
class TwoStepPipeline:
    """Answers the first search with ``first`` and a re-run with ``second`` (or raises it).

    It takes the fake time the test says each search takes, and keeps every call so a test can look
    at exactly what the runner sent."""

    clock: FakeClock
    first: SearchResponse | Exception
    second: SearchResponse | Exception | None = None
    first_seconds: float = 0.0
    second_seconds: float = 0.0
    calls: list[PipelineCall] = field(default_factory=list)

    async def run(
        self,
        req: SearchRequest,
        settings: Settings,
        overrides: RunOverrides | None = None,
        on_step: object = None,
    ) -> SearchResponse:
        self.calls.append(PipelineCall(req, settings, overrides))
        if req.rerun_of is None:
            self.clock.advance(self.first_seconds)
            if isinstance(self.first, Exception):
                raise self.first
            return self.first.model_copy(update={"request_id": req.request_id})
        self.clock.advance(self.second_seconds)
        if isinstance(self.second, Exception):
            raise self.second
        assert self.second is not None, "the runner asked for a second search nobody expected"
        return self.second.model_copy(update={"request_id": req.request_id})


async def run_one(query: AcceptanceQuery, pipeline: TwoStepPipeline) -> QueryRun:
    [run] = await run_queries(
        [query],
        pipeline,
        make_settings(),
        clock=pipeline.clock,
        load_image=lambda q: PHOTO if q.image else None,
    )
    return run


def photo_query(answer: str | None = "women", **overrides: object) -> AcceptanceQuery:
    return make_query("q01_photo", "product_photo", shopper_gender=answer, **overrides)


def make_pipeline(
    items: tuple[ItemIntent, ...],
    *,
    second_items: tuple[ItemIntent, ...] | None = None,
    first_seconds: float = 0.0,
    second_seconds: float = 0.0,
    **first_fields: object,
) -> TwoStepPipeline:
    first = response_of(*items, request_id="f" * 32, **{"duration_ms": 0.0, **first_fields})
    second = response_of(*(second_items or items), request_id="s" * 32, duration_ms=1.0)
    return TwoStepPipeline(FakeClock(), first, second, first_seconds, second_seconds)


class TestTheQuestionIsAskedWhenAGarmentsGenderWasNotStated:
    async def test_a_guessed_gender_is_asked_about_and_the_answer_is_sent_as_the_page_sends_it(
        self,
    ) -> None:
        pipeline = make_pipeline(
            (garment(Category.TOPS, Gender.MEN, GenderSource.INFERRED),),
            query_embedding=EMBEDDING,
        )

        await run_one(photo_query("women"), pipeline)

        first_call, second_call = pipeline.calls
        assert first_call.req.rerun_of is None
        assert first_call.overrides is None  # the first search is exactly today's
        previous = pipeline.first
        assert isinstance(previous, SearchResponse)
        assert second_call.req.rerun_of == first_call.req.request_id
        assert (second_call.req.text, second_call.req.image) == (None, None)  # no photo again
        overrides = second_call.overrides
        assert overrides is not None
        assert overrides.understood == previous.understood  # no second model call is needed
        assert overrides.query_embedding == EMBEDDING
        assert overrides.chips is not None
        assert overrides.chips.items == [ItemEdit(index=0, gender=Gender.WOMEN)]
        assert (overrides.chips.budget, overrides.chips.clear_budget) == (None, False)

    async def test_a_garment_the_model_said_nothing_about_is_asked_about_too(self) -> None:
        pipeline = make_pipeline((garment(Category.SHOES),))

        run = await run_one(photo_query("men"), pipeline)

        assert len(pipeline.calls) == 2
        assert pipeline.calls[1].overrides.chips.items == [  # type: ignore[union-attr]
            ItemEdit(index=0, gender=Gender.MEN)
        ]
        assert run.gender is not None
        assert [(g.category, g.gender) for g in run.gender.garments] == [(Category.SHOES, None)]

    async def test_the_answer_goes_to_every_garment_whose_gender_was_not_stated_and_to_no_other(
        self,
    ) -> None:
        pipeline = make_pipeline(
            (
                garment(Category.TOPS, Gender.MEN, GenderSource.INFERRED),
                garment(Category.BOTTOMS, Gender.WOMEN, GenderSource.EXPLICIT),
                garment(Category.SHOES),
                garment(Category.OUTERWEAR, Gender.UNISEX, GenderSource.EXPLICIT),
            )
        )

        run = await run_one(photo_query("women"), pipeline)

        chips = pipeline.calls[1].overrides.chips  # type: ignore[union-attr]
        assert [(e.index, e.gender) for e in chips.items] == [
            (0, Gender.WOMEN),
            (2, Gender.WOMEN),
        ]
        assert run.gender is not None
        assert [g.category for g in run.gender.garments] == [Category.TOPS, Category.SHOES]

    async def test_it_works_for_a_text_query_whose_words_left_the_gender_out(self) -> None:
        pipeline = make_pipeline((garment(Category.BOTTOMS),))
        query = make_query("q08_text", "text", shopper_gender="women")

        await run_one(query, pipeline)

        assert len(pipeline.calls) == 2


class TestTheSecondResponseIsTheOneThatIsScored:
    async def test_the_response_kept_is_the_search_after_the_answer(self) -> None:
        pipeline = make_pipeline((garment(Category.TOPS, Gender.MEN, GenderSource.INFERRED),))

        run = await run_one(photo_query("women"), pipeline)

        assert run.failure is None
        assert run.response is not None
        assert run.response.request_id == pipeline.calls[1].req.request_id
        assert run.response.request_id != pipeline.calls[0].req.request_id

    async def test_the_search_after_the_answer_is_one_extra_search_not_two(self) -> None:
        pipeline = make_pipeline((garment(),))

        await run_one(photo_query("women"), pipeline)

        assert len(pipeline.calls) == 2

    async def test_the_shoppers_photo_is_sent_with_the_first_search_only(self) -> None:
        pipeline = make_pipeline((garment(),))

        await run_one(photo_query("women"), pipeline)

        assert pipeline.calls[0].req.image == PHOTO
        assert pipeline.calls[1].req.image is None


class TestNoAnswerMeansNoSecondSearch:
    async def test_a_query_with_no_recorded_answer_runs_as_it_always_did(self) -> None:
        pipeline = make_pipeline((garment(Category.TOPS, Gender.MEN, GenderSource.INFERRED),))

        run = await run_one(photo_query(None), pipeline)

        assert len(pipeline.calls) == 1  # a guess is never applied by the harness on its own
        assert run.gender is None
        assert run.response is not None
        assert run.response.request_id == pipeline.calls[0].req.request_id

    async def test_the_answer_is_ignored_when_every_garments_gender_was_stated(self) -> None:
        pipeline = make_pipeline(
            (
                garment(Category.TOPS, Gender.WOMEN, GenderSource.EXPLICIT),
                garment(Category.SHOES, Gender.WOMEN, GenderSource.EXPLICIT),
            )
        )

        run = await run_one(photo_query("women"), pipeline)

        assert len(pipeline.calls) == 1  # the page would not ask, so no second search
        assert run.gender is not None
        assert (run.gender.answer, run.gender.asked) == (Gender.WOMEN, False)
        assert run.gender.typed_differently == []
        assert run.confirm_ms is None
        assert run.total_ms == run.duration_ms

    async def test_a_failed_first_search_is_not_followed_by_a_second(self) -> None:
        failing = TwoStepPipeline(FakeClock(), InvalidInputError("Please add a photo."))

        run = await run_one(photo_query("women"), failing)

        assert len(failing.calls) == 1
        assert run.response is None
        assert run.failure is not None
        assert run.failure.code == "invalid_input"
        assert run.gender is None


class TestAStatedGenderStands:
    async def test_a_stated_gender_that_differs_from_the_answer_stands_and_is_reported(
        self,
    ) -> None:
        pipeline = make_pipeline(
            (
                garment(Category.TOPS, Gender.MEN, GenderSource.EXPLICIT),
                garment(Category.SHOES, Gender.MEN, GenderSource.INFERRED),
            )
        )

        run = await run_one(photo_query("women"), pipeline)

        chips = pipeline.calls[1].overrides.chips  # type: ignore[union-attr]
        assert [e.index for e in chips.items] == [1]  # the stated men is not overwritten
        assert run.gender is not None
        assert [(g.category, g.gender) for g in run.gender.typed_differently] == [
            (Category.TOPS, Gender.MEN)
        ]

    async def test_when_every_garment_is_stated_and_differs_there_is_no_search_and_a_report(
        self,
    ) -> None:
        pipeline = make_pipeline((garment(Category.TOPS, Gender.MEN, GenderSource.EXPLICIT),))

        run = await run_one(photo_query("women"), pipeline)

        assert len(pipeline.calls) == 1
        assert run.gender is not None
        assert run.gender.asked is False
        assert [(g.category, g.gender) for g in run.gender.typed_differently] == [
            (Category.TOPS, Gender.MEN)
        ]

    async def test_a_stated_unisex_also_stands_against_a_women_answer(self) -> None:
        pipeline = make_pipeline((garment(Category.TOPS, Gender.UNISEX, GenderSource.EXPLICIT),))

        run = await run_one(photo_query("women"), pipeline)

        assert len(pipeline.calls) == 1
        assert run.gender is not None
        assert [g.gender for g in run.gender.typed_differently] == [Gender.UNISEX]

    async def test_a_stated_gender_that_agrees_with_the_answer_is_not_a_mismatch(self) -> None:
        pipeline = make_pipeline(
            (
                garment(Category.TOPS, Gender.WOMEN, GenderSource.EXPLICIT),
                garment(Category.SHOES),
            )
        )

        run = await run_one(photo_query("women"), pipeline)

        assert run.gender is not None
        assert run.gender.typed_differently == []
        assert run.gender.asked is True


class TestTimeIsReportedHonestly:
    async def test_the_first_search_is_what_the_thirty_seconds_is_checked_on(self) -> None:
        pipeline = make_pipeline((garment(),), first_seconds=25.0, second_seconds=12.0)

        run = await run_one(photo_query("women"), pipeline)

        assert run.wall_ms == 25_000.0
        assert run.duration_ms == 25_000.0  # not 37 s
        assert run.confirm_ms == 12_000.0
        assert run.total_ms == 37_000.0

    async def test_the_slower_of_the_pipelines_own_figure_and_the_wall_time_counts_for_each(
        self,
    ) -> None:
        pipeline = make_pipeline(
            (garment(),), first_seconds=2.0, second_seconds=1.0, duration_ms=9_000.0
        )
        pipeline.second = pipeline.second.model_copy(update={"duration_ms": 4_000.0})  # type: ignore[union-attr]

        run = await run_one(photo_query("women"), pipeline)

        assert run.duration_ms == 9_000.0
        assert run.confirm_ms == 4_000.0
        assert run.total_ms == 13_000.0

    async def test_the_first_searchs_step_timings_are_kept_because_the_response_is_the_second(
        self,
    ) -> None:
        first_steps = [StepTiming(step="understand", duration_ms=1800.0)]
        pipeline = make_pipeline((garment(),), timings=first_steps)
        pipeline.second = pipeline.second.model_copy(  # type: ignore[union-attr]
            update={"timings": [StepTiming(step="understand", duration_ms=0.0, status="reused")]}
        )

        run = await run_one(photo_query("women"), pipeline)

        assert run.first_timings == first_steps
        assert run.response is not None
        assert run.response.timings[0].status == "reused"

    async def test_a_query_with_no_second_search_has_only_its_own_time(self) -> None:
        pipeline = make_pipeline((garment(),), first_seconds=3.0)

        run = await run_one(photo_query(None), pipeline)

        assert (run.confirm_ms, run.total_ms) == (None, 3_000.0)


class TestAFailedSecondSearch:
    async def test_the_query_fails_in_plain_words_that_say_where_it_happened(self) -> None:
        pipeline = make_pipeline((garment(),), first_seconds=4.0, second_seconds=2.0)
        pipeline.second = InvalidInputError("We could not search again.")

        run = await run_one(photo_query("women"), pipeline)

        assert run.response is None  # the first response is NOT scored in its place
        assert run.failure is not None
        assert run.failure.code == "invalid_input"
        assert "answered 'women'" in run.failure.message
        assert "We could not search again." in run.failure.message
        assert run.duration_ms == 4_000.0  # the first search still counts as the wait
        assert run.gender is not None
        assert run.gender.asked is True

    async def test_an_unexpected_error_is_kept_without_the_photo(self) -> None:
        pipeline = make_pipeline((garment(),))
        pipeline.second = RuntimeError(f"boom {PHOTO!r}")

        run = await run_one(photo_query("women"), pipeline)

        assert run.failure is not None
        assert run.failure.code == "unexpected"
        assert "<bytes omitted>" in run.failure.message


class TestTheScopeIsToldBothTimes:
    async def test_the_scope_hears_the_first_search_and_the_search_after_the_answer(self) -> None:
        pipeline = make_pipeline((garment(),), first_seconds=6.0, second_seconds=2.5)
        told: list[tuple[str, float, float | None]] = []

        class Scope:
            def begin_query(self, query_id: str) -> None:
                told.append((query_id, -1.0, None))

            def end_query(
                self, query_id: str, *, duration_ms: float, confirm_ms: float | None = None
            ) -> None:
                told.append((query_id, duration_ms, confirm_ms))

        await run_queries(
            [photo_query("women"), make_query("q06_text", "text")],
            pipeline,
            make_settings(),
            clock=pipeline.clock,
            load_image=lambda q: PHOTO if q.image else None,
            scope=Scope(),
        )

        assert told[1] == ("q01_photo", 6_000.0, 2_500.0)
        assert told[3][2] is None  # a query with no recorded answer has no second search


@pytest.mark.parametrize("answer", ["women", "men"])
async def test_the_answer_is_the_one_the_query_records(answer: str) -> None:
    pipeline = make_pipeline((garment(),))

    await run_one(photo_query(answer), pipeline)

    chips = pipeline.calls[1].overrides.chips  # type: ignore[union-attr]
    assert chips.items[0].gender is Gender(answer)
