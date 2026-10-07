"""What the report and ``run.json`` show for a query whose "Who is this for?" question was answered.

Time is reported honestly: the first search (the wait before the shopper sees anything), the search
after the answer, and their sum. The 30 s limit is applied to the first search alone.
"""

import json
from datetime import date
from pathlib import Path

from eval.harness.cli import _gender_notes
from eval.harness.confirm import GarmentGender, GenderAnswer
from eval.harness.criteria import Criterion, Status
from eval.harness.links import LinksMode
from eval.harness.report import SECONDS_SENTENCE, render_report
from eval.harness.runner import QueryRun
from eval.harness.runstore import RUN_FILE, LoadedRun, RunMeta, load_run, save_run
from eval.harness.scoring import score_run
from eval.harness.stages import gender_rows, step_summaries
from tests.harness.helpers import make_query, make_response
from vga.models import Category, Gender, StepTiming

TOPS_GUESSED_MEN = GarmentGender(index=0, category=Category.TOPS, gender=Gender.MEN)
SHOES_NO_GUESS = GarmentGender(index=1, category=Category.SHOES, gender=None)


def answered(
    *,
    first_s: float = 7.0,
    after_s: float | None = 4.0,
    first_timings: list[StepTiming] | None = None,
    source: str = "measured",
    query_id: str = "q01_photo",
    answer: Gender = Gender.WOMEN,
) -> QueryRun:
    """A photo query whose question was asked (``after_s``) or not (``None``)."""
    asked = after_s is not None
    gender = GenderAnswer(
        answer=answer,
        asked=asked,
        garments=[TOPS_GUESSED_MEN, SHOES_NO_GUESS] if asked else [],
        first_timings=first_timings or [],
        wall_ms=after_s * 1000 if asked else None,
        duration_ms=after_s * 1000 if asked else None,
    )
    return QueryRun(
        make_query(query_id, "product_photo", shopper_gender=answer.value),
        make_response(duration_ms=0.0),
        None,
        first_s * 1000,
        first_s * 1000,
        duration_source=source,  # type: ignore[arg-type]
        gender=gender,
    )


def plain(query_id: str = "q06_text", seconds: float = 5.0) -> QueryRun:
    return QueryRun(
        make_query(query_id, "text"), make_response(), None, seconds * 1000, seconds * 1000
    )


def loaded(*runs: QueryRun, mode: str = "record") -> LoadedRun:
    meta = RunMeta(
        number=1,
        mode=mode,  # type: ignore[arg-type]
        date=date(2026, 10, 8),
        links=LinksMode.NONE,
        price_range_mix=[25, 25, 25, 25],
    )
    return LoadedRun(meta, list(runs))


def report_of(*runs: QueryRun, mode: str = "record") -> str:
    return render_report(score_run(loaded(*runs, mode=mode)))


def row_of(text: str, query_id: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"| {query_id} |"))


class TestTheResultsTable:
    def test_the_seconds_cell_shows_the_first_search_then_the_search_after_the_answer_and_the_sum(
        self,
    ) -> None:
        text = report_of(answered(first_s=7.0, after_s=4.0))

        assert "| 7.0 (+4.0 after the answer = 11.0) |" in row_of(text, "q01_photo")

    def test_a_query_with_no_second_search_keeps_the_plain_cell(self) -> None:
        text = report_of(answered(after_s=None), plain())

        assert "| 7.0 |" in row_of(text, "q01_photo")
        assert "| 5.0 |" in row_of(text, "q06_text")

    def test_a_replayed_figure_says_it_was_recorded(self) -> None:
        text = report_of(answered(first_s=7.0, after_s=4.0, source="recorded"), mode="replay")

        assert "| 7.0 (recorded; +4.0 after the answer = 11.0) |" in row_of(text, "q01_photo")

    def test_one_plain_sentence_says_which_time_the_limit_is_checked_against(self) -> None:
        text = report_of(answered())

        assert text.count(SECONDS_SENTENCE) == 1
        assert "the 30 s limit applies to it alone" in SECONDS_SENTENCE
        assert "first search" in SECONDS_SENTENCE
        results = text.split("## Results", 1)[1].split("## Failures", 1)[0]
        assert SECONDS_SENTENCE in results

    def test_the_sentence_is_left_out_when_no_question_was_asked(self) -> None:
        text = report_of(answered(after_s=None), plain())

        results = text.split("## Results", 1)[1].split("## Failures", 1)[0]
        assert SECONDS_SENTENCE not in text
        assert "Who is this for?" not in results


class TestThirtySecondsIsTheFirstSearchAlone:
    def evaluation(self, run: QueryRun):  # type: ignore[no-untyped-def]
        return score_run(loaded(run)).evaluations[0]

    def test_a_slow_second_search_does_not_fail_the_limit(self) -> None:
        run = answered(first_s=25.0, after_s=14.0)  # 39 s in all

        result = self.evaluation(run).result(Criterion.SECONDS)

        assert result.status is Status.PASS
        assert result.cell == "25.0 (+14.0 after the answer = 39.0)"

    def test_a_slow_first_search_fails_it_even_if_the_second_is_quick(self) -> None:
        run = answered(first_s=31.0, after_s=1.0)

        result = self.evaluation(run).result(Criterion.SECONDS)

        assert result.status is Status.FAIL
        assert result.evidence.startswith("took 31.0 s, at most 30 s allowed")

    def test_the_cause_comes_from_the_first_searchs_steps_not_the_second(self) -> None:
        steps = [
            StepTiming(step="understand", duration_ms=24_000.0),
            StepTiming(step="search", duration_ms=5_000.0),
            StepTiming(step="rank", duration_ms=1_000.0),
        ]
        run = answered(first_s=31.0, after_s=2.0, first_timings=steps)

        result = self.evaluation(run).result(Criterion.SECONDS)

        assert result.cause is not None
        assert result.cause.value == "LLM"
        assert "understand 24.0 s, search 5.0 s" in result.evidence


class TestTheTimingsSection:
    def test_the_per_step_table_counts_the_first_searches(self) -> None:
        first = [StepTiming(step="understand", duration_ms=1800.0)]
        run = answered(first_timings=first)
        reused = [StepTiming(step="understand", duration_ms=0.0, status="reused")]
        run = QueryRun(
            run.query,
            make_response(timings=reused),
            None,
            run.wall_ms,
            run.duration_ms,
            gender=run.gender,
        )

        [understand] = step_summaries([run])

        assert (understand.step, understand.mean_ms) == ("understand", 1800.0)

    def test_each_answered_query_has_a_row_with_the_first_the_second_and_the_sum(self) -> None:
        text = report_of(answered(first_s=7.0, after_s=4.0), plain())

        timings = text.split("## Timings", 1)[1].split("## Notes", 1)[0]
        assert "| Query | Answer | Asked | Garments answered" in timings
        assert (
            "| q01_photo | women | yes | tops (guessed men), shoes (no guess) | 7.0 | 4.0 | 11.0 |"
            in timings
        )
        assert "q06_text |" not in timings.split("Who is this for?", 1)[1]  # no answer recorded

    def test_a_question_that_was_not_needed_says_so_and_adds_nothing_to_the_time(self) -> None:
        rows = gender_rows([answered(first_s=7.0, after_s=None)])

        assert [(r.asked, r.after_ms, r.total_ms, r.garments) for r in rows] == [
            (False, None, 7_000.0, "-")
        ]
        text = report_of(answered(after_s=None))
        assert "no (every garment's gender was stated)" in text

    def test_the_fetch_stage_says_it_is_the_search_after_the_answer(self) -> None:
        text = report_of(answered())

        fetch = text.split("## Fetch stage", 1)[1].split("## Rank stage", 1)[0]
        assert "this is the search after the answer" in fetch

    def test_the_fetch_stage_is_unchanged_when_nothing_was_asked(self) -> None:
        text = report_of(answered(after_s=None))

        fetch = text.split("## Fetch stage", 1)[1].split("## Rank stage", 1)[0]
        assert "search after the answer" not in fetch


class TestRunJson:
    def raw(self, tmp_path: Path, *runs: QueryRun) -> dict:
        save_run(tmp_path, loaded(*runs))
        return json.loads((tmp_path / RUN_FILE).read_text(encoding="utf-8"))

    def test_it_shows_per_query_the_first_search_the_search_after_the_answer_and_the_sum(
        self, tmp_path: Path
    ) -> None:
        data = self.raw(tmp_path, answered(first_s=7.0, after_s=4.0), plain())

        photo, text = data["queries"]
        assert photo["duration_ms"] == 7_000.0  # the first search: what 30 s is checked against
        assert photo["gender"]["duration_ms"] == 4_000.0  # the search after the answer
        assert photo["total_ms"] == 11_000.0
        assert photo["gender"]["answer"] == "women"
        assert photo["gender"]["asked"] is True
        assert [g["category"] for g in photo["gender"]["garments"]] == ["tops", "shoes"]
        assert text["gender"] is None
        assert text["total_ms"] == text["duration_ms"] == 5_000.0

    def test_the_query_file_entry_keeps_the_recorded_answer(self, tmp_path: Path) -> None:
        data = self.raw(tmp_path, answered())

        assert data["queries"][0]["query"]["shopper_gender"] == "women"

    def test_a_saved_run_loads_back_with_the_answer_and_the_times(self, tmp_path: Path) -> None:
        original = answered(first_s=7.0, after_s=4.0)
        save_run(tmp_path, loaded(original))

        [again] = load_run(tmp_path).runs

        assert again.gender == original.gender
        assert (again.duration_ms, again.confirm_ms, again.total_ms) == (7_000.0, 4_000.0, 11_000.0)
        assert again.query.shopper_gender is Gender.WOMEN

    def test_a_run_saved_before_the_question_existed_still_loads(self, tmp_path: Path) -> None:
        save_run(tmp_path, loaded(plain()))
        data = json.loads((tmp_path / RUN_FILE).read_text(encoding="utf-8"))
        for entry in data["queries"]:
            del entry["gender"], entry["total_ms"]
            del entry["query"]["shopper_gender"]
        (tmp_path / RUN_FILE).write_text(json.dumps(data), encoding="utf-8")

        [again] = load_run(tmp_path).runs

        assert again.gender is None
        assert again.total_ms == again.duration_ms


class TestTheRunsNotes:
    def test_they_say_which_queries_were_answered_and_with_what(self) -> None:
        notes = _gender_notes(
            [
                answered(query_id="q01_photo", answer=Gender.WOMEN),
                answered(query_id="q02_photo", answer=Gender.MEN),
                plain(),
            ]
        )

        [note] = notes
        assert 'The "Who is this for?" question was answered' in note
        assert "q01_photo (women), q02_photo (men)" in note
        assert "no photo was sent and no model was called" in note
        assert "the ones shown after the answer" in note

    def test_a_query_whose_gender_was_stated_is_listed_as_not_asked(self) -> None:
        notes = _gender_notes([answered(query_id="q03_photo", after_s=None)])

        [note] = notes
        assert "q03_photo (women)" in note
        assert "no second search ran" in note

    def test_a_stated_gender_that_differs_from_the_answer_is_reported_and_stands(self) -> None:
        run = answered(query_id="q04_photo", after_s=None)
        assert run.gender is not None
        stated = GarmentGender(index=0, category=Category.TOPS, gender=Gender.MEN)
        run = QueryRun(
            run.query,
            run.response,
            None,
            run.wall_ms,
            run.duration_ms,
            gender=run.gender.model_copy(update={"typed_differently": [stated]}),
        )

        notes = _gender_notes([run])

        assert any(
            "q04_photo: the recorded answer is women, but the request stated tops (stated men)."
            " The stated gender stands." in note
            for note in notes
        )

    def test_no_recorded_answer_means_no_note(self) -> None:
        assert _gender_notes([plain(), plain("q07_text")]) == []

    def test_the_notes_reach_the_report(self) -> None:
        run = answered()
        meta = loaded(run).meta.model_copy(update={"notes": _gender_notes([run])})

        text = render_report(score_run(LoadedRun(meta, [run])))

        notes = text.split("## Notes", 1)[1]
        assert "q01\\_photo" in notes or "q01_photo (women)" in notes.replace("\\", "")
