"""Running a scenario under watch, and the checks on what the watch saw.

``run_case`` runs one ``Case`` through the real pipeline with every instrument on (``watch.py``) and
returns an ``Audited``: everything the checks need. A check is a plain function that returns a list
of problems, empty when the request left nothing behind. A test asserts the list is empty, so a
failure prints every problem, not only the first.
"""

import base64
import gc
import io
import json
import os
import platform
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

from tests.fakes import FakeClock
from tests.guards.privacy.photos import PrivatePhoto, make_private_photo
from tests.guards.privacy.reachable import (
    Held,
    module_state,
    photos_held,
    reachable,
)
from tests.guards.privacy.rig import BrokenWeights, Rig, build_rig, settings_for
from tests.guards.privacy.scenarios import Case
from tests.guards.privacy.traces import (
    Trace,
    find,
    is_an_image,
    signs_of_an_image,
    traces_of_photo,
)
from tests.guards.privacy.watch import Watch, without_pytest_log_capture
from tests.pipeline.builders import rerun
from tests.pipeline.world import StoreWorld
from vga.errors import VgaError
from vga.log import LOG_FILE_NAME, configure_logging
from vga.models import MixPreset, RunOverrides, SearchRequest, SearchResponse
from vga.pipeline.dump import dump_path


@dataclass(frozen=True)
class Workspace:
    """Folders for one test, all inside the test's own temporary folder, so that a write anywhere
    the app might choose (the working directory, the temp folder, the log folder) lands in a place
    the audit is watching."""

    root: Path
    cwd: Path
    temp: Path
    logs: Path


@dataclass(frozen=True)
class Failure:
    """What is left of an error once the code that caught it is done with it.

    The exception object is deliberately not kept. Its traceback holds every frame it passed
    through, and a frame holds its local variables, the photo among them. The app shows the
    shopper the message and lets the exception go; so does the audit, after taking down every text
    the exception could be turned into.
    """

    kind: type[VgaError]
    texts: str
    """The messages, the detail for the log and the full traceback text, of the error and of every
    error it was raised from."""


@dataclass
class Audited:
    case: Case
    photo: PrivatePhoto
    submitted: bytes
    """The bytes the shopper uploaded: the photo, or what the scenario made of it."""
    rig: Rig
    workspace: Workspace
    watch: Watch
    log_stream: io.StringIO
    traces: list[Trace]
    responses: list[SearchResponse] = field(default_factory=list)
    overrides: RunOverrides | None = None
    failure: Failure | None = None
    holders_added: list[str] = field(default_factory=list)
    """What started to refer to the uploaded bytes object during the request."""

    @property
    def log_file(self) -> Path:
        return self.workspace.logs / LOG_FILE_NAME

    @property
    def sent_images(self) -> list[bytes]:
        """The JPEG in each request that reached OpenAI, as OpenAI received it."""
        return _sent_images(self.rig)


def _sent_images(rig: Rig) -> list[bytes]:
    return [
        base64.b64decode(url.partition(",")[2])
        for request in rig.fake_openai.requests
        if (url := request.image_url) is not None
    ]


def _failure_of(error: VgaError) -> Failure:
    texts: list[str] = ["".join(traceback.format_exception(error))]
    link: BaseException | None = error
    while link is not None:
        texts.append(f"{link!s} {link!r} {getattr(link, 'detail', '')}")
        link = link.__cause__ or link.__context__
    return Failure(type(error), "\n".join(texts))


def _check_outcome(case: Case, failure: Failure | None, responses: list[SearchResponse]) -> None:
    expected = case.scenario.expect
    if expected is None:
        assert failure is None, f"the scenario should work but ended with {failure}"
        assert responses, "the scenario produced no answer"
    else:
        assert failure is not None, f"expected {expected.__name__}, but the request worked"
        assert issubclass(failure.kind, expected), (
            f"expected {expected.__name__}, got {failure.kind}"
        )


async def run_case(
    case: Case, world: StoreWorld, clock: FakeClock, workspace: Workspace
) -> Audited:
    """Run ``case`` through the real pipeline, watched, and return everything the checks need."""
    scenario = case.scenario
    photo = make_private_photo(scenario.photo_format)
    submitted = scenario.upload(photo)

    stream = io.StringIO()
    settings = settings_for(
        str(workspace.logs),
        log_prompts=case.switches.log_prompts,
        debug_dump=case.switches.debug_dump,
    )
    configure_logging(level=settings.log_level, log_dir=settings.log_dir, stream=stream)
    rig = build_rig(
        world,
        clock,
        settings,
        scenario.steps(),
        store_status=scenario.store_status,
        embedder=BrokenWeights() if scenario.broken_weights else None,
        slow_model=scenario.slow_model,
        slow_thumbnails=scenario.slow_thumbnails,
        leak=scenario.leak,
    )

    # The OpenAI library asks the operating system for its name the first time it is used in a
    # process, which on macOS starts a short helper program (``uname``). It carries no data. Doing
    # it now, before the watch opens, keeps the audit's "no other program is started" check exact.
    platform.platform()

    request = SearchRequest(text=scenario.text, image=submitted)
    holders_before = {id(holder) for holder in gc.get_referrers(submitted)}
    responses: list[SearchResponse] = []
    overrides: RunOverrides | None = None
    failure: Failure | None = None

    with without_pytest_log_capture(), Watch([workspace.root]) as watch:
        try:
            first = await rig.pipeline.run(request, settings)
            responses.append(first)
            if scenario.rerun:
                followup, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
                responses.append(await rig.pipeline.run(followup, settings, overrides))
        except VgaError as raised:
            failure = _failure_of(raised)
    _check_outcome(case, failure, responses)

    gc.collect()  # unreachable leftovers (cycles) do not count; what the collector keeps does
    holders_added = [
        _describe_holder(holder)
        for holder in gc.get_referrers(submitted)
        if id(holder) not in holders_before and not isinstance(holder, FrameType | list)
    ]
    sent = next(iter(_sent_images(rig)), None)
    return Audited(
        case=case,
        photo=photo,
        submitted=submitted,
        rig=rig,
        workspace=workspace,
        watch=watch,
        log_stream=stream,
        traces=traces_of_photo(submitted, photo.marker, sent=sent),
        responses=responses,
        overrides=overrides,
        failure=failure,
        holders_added=holders_added,
    )


def _describe_holder(holder: object) -> str:
    """A ``bytes`` holder and who holds that in turn, so a failure says where to look."""
    owners = sorted({type(owner).__qualname__ for owner in gc.get_referrers(holder)})
    return f"{type(holder).__qualname__} (held by {', '.join(owners) or 'nothing else'})"


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _problems_in(content: bytes | str, traces: list[Trace], where: str) -> list[str]:
    """What is wrong with ``content`` (a file, a log line, a request): traces of this photo and
    signs of any image."""
    problems = [f"{where} holds {label}" for label in find(content, traces)]
    problems += [f"{where} has {sign}" for sign in signs_of_an_image(content)]
    return problems


def allowed_files(audited: Audited) -> set[Path]:
    """The files a request is allowed to write: the log, and the candidate dump if it is switched
    on. Nothing else."""
    allowed = {_real(audited.log_file)}
    if audited.case.switches.debug_dump:
        logs = audited.workspace.logs
        allowed |= {_real(dump_path(logs, response.request_id)) for response in audited.responses}
    return allowed


def content_problems(path: Path, traces: list[Trace]) -> list[str]:
    """What is wrong with the content of one file: traces of the photo, signs of any image, and
    whether Pillow can open it as a picture (which sees a shrunk or re-encoded copy)."""
    content = path.read_bytes()
    problems = _problems_in(content, traces, path.name)
    if is_an_image(content):
        problems.append(f"{path.name} can be opened as a picture")
    return problems


def file_problems(audited: Audited) -> list[str]:
    """Files written during the request: anything outside the allowed ones, and anything that
    holds the photo or looks like an image."""
    allowed = allowed_files(audited)
    problems: list[str] = []
    callers: dict[Path, str] = {}
    for opened in audited.watch.activity.file_writes:
        callers.setdefault(_real(opened.path), opened.caller)
    appeared = {_real(path) for path in audited.watch.changed}
    for path in sorted(callers.keys() | appeared):
        if path not in allowed:
            how = f"opened for writing by {callers[path]}" if path in callers else "created"
            problems.append(f"{path} was {how}; only the log and the dump may be written")
    for path in sorted(appeared & allowed - {_real(audited.log_file)}):
        problems += content_problems(path, audited.traces)
    return problems


def log_problems(audited: Audited) -> list[str]:
    """Every place a log line ends up: the call itself (before the logger redacts it), the
    stream and the file."""
    problems: list[str] = []
    for line in audited.watch.raw_logs.lines:
        problems += _problems_in(line, audited.traces, f"the log call {line[:60]!r}")
    stream = audited.log_stream.getvalue()
    problems += _problems_in(stream, audited.traces, "the log stream")
    file_text = audited.log_file.read_bytes() if audited.log_file.exists() else b""
    problems += _problems_in(file_text, audited.traces, "the log file")
    for where, text in (("the log stream", stream), ("the log file", file_text.decode())):
        if "REDACTED" in text:
            problems.append(f"{where} has a redaction marker: the code tried to log image data")
    return problems


def memory_problems(audited: Audited) -> list[str]:
    """What is reachable after the request, from everything the pipeline owns and keeps."""
    rig = audited.rig
    roots = [rig.pipeline, rig.understander, rig.engine, *audited.responses, audited.overrides]
    roots += module_state()
    skip = [rig.fake_openai, rig.world, rig.clock, rig.embedder, audited.log_stream]
    held: list[Held] = photos_held(roots, audited.traces, skip=skip)
    problems = [f"{item.what}, in a {item.where}" for item in held]
    problems += [
        f"the uploaded bytes are now referred to by a {who}" for who in audited.holders_added
    ]
    return problems


def outbound_problems(audited: Audited) -> list[str]:
    """What left the machine: every request to a store or an image host, and anything else the
    interpreter reported (a network attempt, another program, a database)."""
    problems: list[str] = []
    for call in audited.rig.world.router.calls:
        request = call.request
        where = f"the request {request.method} {request.url.host}{request.url.path}"
        for part, content in (
            ("URL", str(request.url)),
            ("headers", json.dumps(dict(request.headers))),
            ("body", request.content),
        ):
            problems += _problems_in(content, audited.traces, f"{where}, {part}")
        if request.method != "GET" or request.content:
            problems.append(f"{where} sent a body or used a method other than GET")
    activity = audited.watch.activity
    problems += [f"network attempt: {what}" for what in activity.network]
    problems += [f"another program was started: {what}" for what in activity.programs]
    problems += [f"a database was opened: {what}" for what in activity.databases]
    return problems


def caller_problems(audited: Audited) -> list[str]:
    """What the code that called the pipeline is handed: the answers, the re-run settings and the
    error, in every form they can be printed or saved."""
    problems: list[str] = []
    for index, response in enumerate(audited.responses):
        for form, text in (("JSON", response.model_dump_json()), ("repr", repr(response))):
            problems += _problems_in(text, audited.traces, f"answer {index + 1} as {form}")
    if audited.overrides is not None:
        problems += _problems_in(
            audited.overrides.model_dump_json(), audited.traces, "the re-run settings"
        )
    if audited.failure is not None:
        problems += _problems_in(audited.failure.texts, audited.traces, "the error")
    return problems


def reachable_from(audited: Audited, *roots: object) -> list[object]:
    return list(
        reachable(roots, skip=[audited.rig.fake_openai, audited.rig.world, audited.rig.clock])
    )
