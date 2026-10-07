"""BRD Rule 4: a recording, and everything else a run saves, never holds the shopper's photo.

Recordings may be committed so that tuning can be replayed offline, so a photo (or its base64, or an
embedding made from it) in one would be a privacy leak. These tests record a run whose photos are
noise pictures with a unique marker, then search every file the run wrote for any trace of them.
The scan is checked against files that do hold a photo first, so a clean result means something.
"""

import base64
import json
from pathlib import Path

import pytest

from eval.harness.queries import QUERIES_PATH, load_queries
from tests.fakes import FakeClock
from tests.harness.cli_support import Cli, SlowToLoadRanker, wiring_over
from tests.harness.live_parts import LiveParts
from tests.harness.photos import (
    MARKER_PREFIX,
    make_marked_photo,
    marker_of,
    put_marked_photos,
    traces_of_photos,
)

EMBEDDING = (0.3141592653, 0.2718281828, 0.1618033988)
"""What the fake image model stores on the photo query. Odd digits, so no score matches them."""


class TestTheScanItselfCanFindAPhoto:
    """A scan that finds nothing proves nothing until it is shown to find something."""

    @pytest.fixture
    def photo(self) -> bytes:
        return make_marked_photo("dress_burgundy_gown.png")

    def test_a_clean_folder_has_no_traces(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "run.json").write_text('{"scores": {"https://a.example/p": 0.8}}')

        assert traces_of_photos(tmp_path, [photo]) == []

    def test_the_photo_as_it_is_is_found(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.bin").write_bytes(b"header" + photo)

        assert traces_of_photos(tmp_path, [photo])

    def test_the_photo_as_base64_is_found(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.json").write_text(json.dumps({"x": base64.b64encode(photo).decode()}))

        assert any("base64" in problem for problem in traces_of_photos(tmp_path, [photo]))

    def test_the_photo_as_url_safe_base64_is_found(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.txt").write_text(base64.urlsafe_b64encode(photo).decode())

        assert any("url-safe" in problem for problem in traces_of_photos(tmp_path, [photo]))

    def test_a_slice_of_the_photo_is_enough(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.bin").write_bytes(photo[len(photo) // 2 : len(photo) // 2 + 200])

        assert traces_of_photos(tmp_path, [photo])

    def test_the_marker_alone_is_found(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.txt").write_text(f"saw {marker_of(photo)} and {MARKER_PREFIX}:")

        assert any("marker" in problem for problem in traces_of_photos(tmp_path, [photo]))

    def test_an_embedding_number_is_found(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "leak.json").write_text(json.dumps({"query_embedding": list(EMBEDDING)}))

        problems = traces_of_photos(tmp_path, [photo], EMBEDDING)

        assert any("0.3141592653" in problem for problem in problems)

    def test_it_looks_in_sub_folders(self, tmp_path: Path, photo: bytes) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "leak.bin").write_bytes(photo)

        assert any(
            problem.startswith("a/b/leak.bin") for problem in traces_of_photos(tmp_path, [photo])
        )

    def test_the_marker_names_the_photo_it_came_from(self, photo: bytes) -> None:
        assert marker_of(photo) == "dress_burgundy_gown.png"


class TestARecordedRunHoldsNoPhoto:
    def record(self, cli: Cli) -> tuple[dict[str, bytes], LiveParts]:
        queries = load_queries(QUERIES_PATH, require_images=False)
        photos = put_marked_photos(cli.root, queries)
        live = LiveParts()
        live.ranker = SlowToLoadRanker(FakeClock(), embedding=EMBEDDING)
        code = cli.run(
            "--record",
            str(cli.root / "eval" / "results" / "run-1" / "recording"),
            wiring=wiring_over(live),
        )
        assert code == 0, cli.errors
        return photos, live

    def test_nothing_the_run_saved_holds_a_trace_of_a_photo(self, cli: Cli) -> None:
        photos, live = self.record(cli)

        assert live.understander.calls, "the run did not use the photos at all"
        assert any(call.image for call in live.understander.calls)
        problems = traces_of_photos(cli.root / "eval" / "results", photos.values(), EMBEDDING)
        assert problems == []

    def test_the_fake_image_model_really_did_hold_the_embedding_while_it_ran(
        self, cli: Cli
    ) -> None:
        # Without this the test above could pass because the embedding was never made.
        _, live = self.record(cli)

        assert isinstance(live.ranker, SlowToLoadRanker)
        assert live.ranker.calls

    def test_the_recording_files_are_text_with_no_binary_field(self, cli: Cli) -> None:
        self.record(cli)

        recording = cli.root / "eval" / "results" / "run-1" / "recording"
        for file in recording.glob("*.json"):
            file.read_bytes().decode("utf-8")  # text, not an image
            data = json.loads(file.read_text(encoding="utf-8"))
            assert "image" not in json.dumps(data).replace("image_url", "").replace(
                "image_scores", ""
            )

    def test_the_labelling_sheet_names_the_photo_file_but_holds_none_of_it(self, cli: Cli) -> None:
        photos, _ = self.record(cli)

        sheet = (cli.root / "eval" / "results" / "run-1" / "labels.csv").read_text(
            encoding="utf-8-sig"
        )

        assert "dress_burgundy_gown.png" in sheet
        assert traces_of_photos(cli.root / "eval" / "results" / "run-1", photos.values()) == []

    def test_a_replay_leaves_no_photo_either_and_needs_none(self, cli: Cli) -> None:
        photos, live = self.record(cli)
        for path in (cli.root / "eval" / "data").rglob("*.png"):
            path.unlink()

        code = cli.run(
            "--replay",
            str(cli.root / "eval" / "results" / "run-1" / "recording"),
            wiring=wiring_over(live),
        )

        assert code == 0, cli.errors
        replayed = cli.root / "eval" / "results" / "replay"
        assert traces_of_photos(replayed, photos.values(), EMBEDDING) == []
