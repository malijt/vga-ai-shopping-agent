"""The command line (``python -m vga.search --image ...``) is the way into the pipeline today, so
the audit follows a photo through it too: what it prints, what it writes, and what it leaves of the
photo file the shopper pointed it at.

Plain (not ``async``) tests: the command starts its own event loop, as it does for a user.
"""

import base64
from pathlib import Path

import pytest

from tests.fakes import FakeClock
from tests.guards.privacy.audit import Workspace, content_problems, problems_in
from tests.guards.privacy.photos import make_private_photo
from tests.guards.privacy.rig import (
    Rig,
    blazer_reading,
    build_rig,
    look_up_the_platform_once,
    settings_for,
)
from tests.guards.privacy.scenarios import SHOPPER_TEXT
from tests.guards.privacy.traces import traces_of_photo
from tests.guards.privacy.watch import Watch, without_pytest_log_capture
from tests.pipeline.world import StoreWorld
from tests.understand.fake_openai import answer, http_error
from vga.log import LOG_FILE_NAME
from vga.models import InputType, SearchResponse
from vga.pipeline import SearchPipeline
from vga.pipeline.dump import dump_path
from vga.search import main
from vga.settings import Settings


class Command:
    """The command line, run against the fake world, with the photo in a file of its own."""

    def __init__(self, world: StoreWorld, clock: FakeClock, workspace: Workspace) -> None:
        self.world, self.clock, self.workspace = world, clock, workspace
        self.photo = make_private_photo()
        self.photo_file = workspace.root / "input" / "my-photo.jpg"
        self.photo_file.parent.mkdir()
        self.photo_file.write_bytes(self.photo.data)
        self.settings = settings_for(str(workspace.logs), log_prompts=True, debug_dump=True)
        self.rigs: list[Rig] = []
        look_up_the_platform_once()

    def run(self, steps: list, *flags: str) -> tuple[int, Watch]:
        def build(settings: Settings) -> SearchPipeline:
            rig = build_rig(self.world, self.clock, settings, steps)
            self.rigs.append(rig)
            return rig.pipeline

        arguments = ["--image", str(self.photo_file), *flags]
        with without_pytest_log_capture(), Watch([self.workspace.root]) as watch:
            code = main(arguments, build=build, settings=self.settings)
        return code, watch

    def traces(self):
        sent = [r.image_url for rig in self.rigs for r in rig.fake_openai.requests if r.image_url]
        jpeg = base64.b64decode(sent[0].partition(",")[2]) if sent else None
        return traces_of_photo(self.photo.data, self.photo.marker, sent=jpeg)


@pytest.fixture
def command(world: StoreWorld, clock: FakeClock, workspace: Workspace) -> Command:
    return Command(world, clock, workspace)


def run_command(
    command: Command, capsys: pytest.CaptureFixture[str], steps: list, *flags: str
) -> tuple[int, str, str, Watch]:
    code, watch = command.run(steps, *flags)
    captured = capsys.readouterr()
    return code, captured.out, captured.err, watch


def test_a_search_prints_no_photo_writes_no_photo_and_leaves_the_photo_file_alone(
    command: Command, capsys: pytest.CaptureFixture[str]
) -> None:
    steps = [answer(blazer_reading(InputType.PHOTO_TEXT))]

    code, out, err, watch = run_command(command, capsys, steps, "--text", SHOPPER_TEXT, "--verbose")

    assert code == 0
    response = SearchResponse.model_validate_json(out)
    traces = command.traces()
    assert err, "--verbose printed no log lines: the test is not testing anything"
    assert problems_in(out, traces, "what the command printed") == []
    assert problems_in(err, traces, "what the command logged to the screen") == []

    logs = command.workspace.logs
    allowed = {logs / LOG_FILE_NAME, dump_path(logs, response.request_id)}
    written = {opened.path.resolve() for opened in watch.activity.file_writes}
    changed = {path.resolve() for path in watch.changed}
    assert (written | changed) <= {path.resolve() for path in allowed}
    for path in sorted(changed):
        assert content_problems(path, traces) == []
    assert watch.activity.network == []
    assert command.photo_file.read_bytes() == command.photo.data  # the shopper's own file


def test_a_search_that_fails_prints_only_the_plain_message(
    command: Command, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err, watch = run_command(
        command, capsys, [http_error(500), http_error(500)], "--verbose"
    )

    assert code == 1
    assert out == ""
    assert "We couldn't read your photo right now." in err
    assert problems_in(err, command.traces(), "what the command printed") == []
    assert watch.activity.network == []


def test_a_file_that_is_not_a_photo_is_refused_without_quoting_it(
    command: Command, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    command.photo_file.write_bytes(b"secret notes: " + command.photo.marker)

    code, out, err, _ = run_command(command, capsys, [])

    assert code == 1
    assert out == ""
    assert command.photo.marker.decode() not in err
    assert command.rigs[0].fake_openai.requests == []
