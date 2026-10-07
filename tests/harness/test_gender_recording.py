"""What a recording keeps so that the search after the "Who is this for?" answer can be replayed.

Two things only, beside the calls themselves: how long that second search took when it was live,
and the fact that the photo's embedding existed (never the embedding, BRD Rule 4). The replay
needs the fact because the pipeline scores images again only for a query that carries an embedding.
"""

import json
from pathlib import Path

from eval.harness.recording import MANIFEST_FILE, RecordingSession, ReplaySession
from eval.harness.wiring import Boundaries
from tests.factories import make_image_bytes, make_product
from tests.fakes import FakeImageRanker, FakeStoreSearcher, FakeUnderstander
from vga.models import Product, QueryImage

PHOTO = make_image_bytes()
EMBEDDING = (0.1111111, 0.2222222, 0.3333333)


def products() -> list[Product]:
    return [make_product(1), make_product(2)]


def finish(session: RecordingSession, *, confirm_ms: float | None = None) -> None:
    session.end_query("q01_photo", duration_ms=10.0, confirm_ms=confirm_ms)


def wrap(directory: Path, ranker: FakeImageRanker) -> tuple[RecordingSession, Boundaries]:
    session = RecordingSession(directory)
    live = Boundaries(FakeUnderstander(), FakeStoreSearcher(), ranker)
    return session, session.wrap(live)


class TestTheSecondSearchsLiveTime:
    def test_it_is_kept_in_the_manifest_beside_the_first_searchs(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec")
        session.begin_query("q01_photo")

        finish(session, confirm_ms=2500.0)

        entry = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text("utf-8"))["queries"]
        assert entry["q01_photo"] == {
            "file": "q01_photo.json",
            "live_duration_ms": 10.0,
            "live_confirm_ms": 2500.0,
        }

    def test_a_query_with_no_second_search_has_no_such_entry(self, tmp_path: Path) -> None:
        session = RecordingSession(tmp_path / "rec")
        session.begin_query("q01_photo")

        finish(session)

        entry = json.loads((tmp_path / "rec" / MANIFEST_FILE).read_text("utf-8"))["queries"]
        assert "live_confirm_ms" not in entry["q01_photo"]

    def test_the_replay_reads_it_back_and_says_none_when_there_was_no_second_search(
        self, tmp_path: Path
    ) -> None:
        session = RecordingSession(tmp_path / "rec")
        session.begin_query("q01_photo")
        finish(session, confirm_ms=2500.0)
        session.begin_query("q06_text")
        session.end_query("q06_text", duration_ms=5.0)

        replay = ReplaySession(tmp_path / "rec")

        assert replay.live_confirm_ms("q01_photo") == 2500.0
        assert replay.live_confirm_ms("q06_text") is None
        assert replay.live_confirm_ms("not-recorded") is None
        assert replay.live_duration_ms("q01_photo") == 10.0


class TestWhetherTheEmbeddingExisted:
    async def test_it_is_noted_as_a_fact_never_as_the_numbers(self, tmp_path: Path) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker(embedding=EMBEDDING))
        session.begin_query("q01_photo")

        await wrapped.image_ranker.score(QueryImage(image=PHOTO), products())
        finish(session)

        saved = (tmp_path / "rec" / "q01_photo.json").read_text(encoding="utf-8")
        assert json.loads(saved)["image_scores"][0]["embedded"] is True
        assert "0.1111111" not in saved
        assert "embedding" not in saved

    async def test_no_embedding_is_noted_as_false(self, tmp_path: Path) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker())
        session.begin_query("q01_photo")

        await wrapped.image_ranker.score(None, products())  # a text query has no photo
        finish(session)

        saved = json.loads((tmp_path / "rec" / "q01_photo.json").read_text(encoding="utf-8"))
        assert saved["image_scores"][0]["embedded"] is False

    async def test_a_replayed_score_leaves_a_stand_in_embedding_when_the_live_one_existed(
        self, tmp_path: Path
    ) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker(embedding=EMBEDDING))
        session.begin_query("q01_photo")
        await wrapped.image_ranker.score(QueryImage(image=PHOTO), products())
        finish(session)
        replay = ReplaySession(tmp_path / "rec")
        replay.begin_query("q01_photo")
        query = QueryImage(image=PHOTO)

        await replay.image_ranker.score(query, products())

        assert query.embedding == [0.0]  # "there was one"; the real numbers are never recorded
        assert query.embedding != list(EMBEDDING)

    async def test_a_replayed_score_leaves_a_real_embedding_alone(self, tmp_path: Path) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker(embedding=EMBEDDING))
        session.begin_query("q01_photo")
        await wrapped.image_ranker.score(QueryImage(image=PHOTO), products())
        finish(session)
        replay = ReplaySession(tmp_path / "rec")
        replay.begin_query("q01_photo")
        query = QueryImage(embedding=[0.5, 0.5])

        await replay.image_ranker.score(query, products())

        assert query.embedding == [0.5, 0.5]

    async def test_nothing_is_left_when_the_live_ranker_made_no_embedding(
        self, tmp_path: Path
    ) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker())
        session.begin_query("q01_photo")
        await wrapped.image_ranker.score(None, products())
        finish(session)
        replay = ReplaySession(tmp_path / "rec")
        replay.begin_query("q01_photo")
        query = QueryImage(image=PHOTO)

        await replay.image_ranker.score(query, products())

        assert query.embedding is None

    async def test_a_recording_made_before_the_note_existed_adds_no_embedding(
        self, tmp_path: Path
    ) -> None:
        session, wrapped = wrap(tmp_path / "rec", FakeImageRanker(embedding=EMBEDDING))
        session.begin_query("q01_photo")
        await wrapped.image_ranker.score(QueryImage(image=PHOTO), products())
        finish(session)
        saved = tmp_path / "rec" / "q01_photo.json"
        data = json.loads(saved.read_text(encoding="utf-8"))
        del data["image_scores"][0]["embedded"]
        saved.write_text(json.dumps(data), encoding="utf-8")
        replay = ReplaySession(tmp_path / "rec")
        replay.begin_query("q01_photo")
        query = QueryImage(image=PHOTO)

        await replay.image_ranker.score(query, products())

        assert query.embedding is None
