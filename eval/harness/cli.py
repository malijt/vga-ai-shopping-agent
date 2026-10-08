"""The command line: ``uv run python -m eval.harness``.

One of four modes is required:

``--mock``
    Run the 10 queries through ``FakePipeline``. No network, no OpenAI, no photos needed. Proves
    the harness and produces a full report and labelling sheet; it measures nothing about the app.
``--record DIR``
    A live run. Needs the real application wired in (``--wiring``, Phase 16). The three boundaries
    are recorded into ``DIR`` so tuning can be done offline afterwards. Needs the five private
    photos.
``--replay DIR``
    Run the real pipeline again on a recording: zero network and zero OpenAI calls. Needs
    ``--wiring`` for the pipeline factory, but not the photos.
``--rescore RUN_DIR``
    No pipeline at all. Rebuild the report of a saved run, for example after a person has filled
    the labelling sheet (``--labels``). Costs nothing.

Every run is saved to a folder under ``eval/results/`` (``run-N`` for a live run, ``mock`` and
``replay`` for the others): the raw responses, ``run.json``, ``results.md`` and a blank
``labels.csv``. A live run's folder is never overwritten.

A live run first warms the pipeline up (loads the image model) and reports how long that took,
apart from the queries: the 30 s limit is for a search on an app that is already running.

The queries run one at a time. Each is searched, saved, and has its links checked before the next
one starts (so a run that is stopped or interrupted keeps everything finished so far).

**Being gentle with the stores (a live run only).** The platform limits a client address across all
its shops, and a shopper never sends ten searches in a minute, so ``--record`` waits ``--pause``
seconds (default 30) between one query and the next and sends at most one link request every
``--link-interval`` seconds (default 2) across all stores. If a query finds every store blocked
or in cooldown it is *not run* (neither a pass nor a fail, no rows in the labelling sheet) and the
run stops there instead of asking the stores again; ``--keep-going`` sends the rest anyway. A run
with any query not run has the verdict INCOMPLETE. ``--record DIR --only q03,q07`` finishes such a
run later: it runs just those queries into the same run folder and recording (see ``resume.py``).
A mock or replay run contacts no store and never waits or stops.

A query may record the shopper's answer to the page's "Who is this for?" question
(``shopper_gender`` in the query file). When the app would ask (some garment's gender was not
stated), the harness gives that answer as the page does, with one re-search (see ``confirm.py``),
and the results of that second search are the ones scored, labelled and link-checked. The 30 s
limit is checked against the first search alone; the report shows both times and their sum.

``--queries`` names the queries file. The frozen ``eval/data/queries.yaml`` (the default) is the
acceptance set: it must have the PRD mix of 10 and it decides the demo. Any other file, such as
``eval/data/extra_queries.yaml`` (the 11 extra photos), is an *extra set*: no mix is required, the
report says plainly that it is not the acceptance result, no demo verdict is given, and its
results go to ``extras-N`` (``replay-extras`` for a replay) instead of ``run-N``.
"""

import argparse
import asyncio
import csv
import re
import sys
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import TextIO

from tests.fakes import FakePipeline

from eval.harness.confirm import describe_stated
from eval.harness.errors import ResumeError, RunFileError, WiringError
from eval.harness.followup import incomplete_lines
from eval.harness.labels import LabelSet, export_label_sheet, import_label_sheet
from eval.harness.links import (
    LinkCheck,
    LinkChecker,
    LinkFetch,
    LinksMode,
    allowed_hosts_from_stores,
    products_to_check,
)
from eval.harness.offline import MockLinkFetch, allowed_hosts_from_responses, placeholder_image
from eval.harness.queries import (
    QUERIES_PATH,
    AcceptanceQuery,
    QuerySet,
    load_queries,
    query_set_of,
    read_query_image,
)
from eval.harness.recording import RecordingSession, ReplaySession
from eval.harness.report import render_report
from eval.harness.resume import (
    Continuation,
    already_checked,
    links_to_keep,
    parse_only,
    plan_continuation,
)
from eval.harness.runner import (
    ImageLoader,
    Pacing,
    QueryRun,
    QueryScope,
    in_query_order,
    run_queries,
)
from eval.harness.runstore import (
    LABELS_FILE,
    REPORT_FILE,
    LoadedRun,
    Mode,
    RunMeta,
    WarmUp,
    load_run,
    save_run,
)
from eval.harness.scoring import ScoredRun, score_run
from eval.harness.session import Session, session_note
from eval.harness.spacing import DEFAULT_LINK_INTERVAL_S, SpacedLinkFetch
from eval.harness.wiring import Wiring, WiringFactory, load_wiring_factory
from vga.errors import VgaError
from vga.interfaces import Clock, Pipeline, SystemClock
from vga.models import SearchResponse, StoreConfig
from vga.settings import PROJECT_ROOT, Settings, load_settings

DEFAULT_PAUSE_S = 30.0
"""The rest between two queries of a live run. A shopper does not send ten searches in a minute;
the first recorded run did, and the platform turned every store away."""

RESULTS_DIR = Path("eval") / "results"
_RUN_DIR = re.compile(r"^(?:run|extras)-(\d+)$")
_FOLDER_PREFIX: dict[QuerySet, str] = {"acceptance": "run", "extra": "extras"}


def _seconds(text: str) -> float:
    """A number of seconds for an option: a number, not negative."""
    try:
        value = float(text)
    except ValueError:
        msg = f"{text!r} is not a number of seconds"
        raise argparse.ArgumentTypeError(msg) from None
    if value < 0 or value != value:
        msg = f"{text!r} is not a number of seconds (it must be 0 or more)"
        raise argparse.ArgumentTypeError(msg)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.harness",
        description=(
            "Run the 10 acceptance queries headless, score them against the BRD pass rule, "
            "and leave only the good-match labels to a person. Another --queries file is run "
            "as an extra set, which is reported but never scored against the pass rule."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="use FakePipeline: no network, no OpenAI")
    mode.add_argument(
        "--record",
        metavar="DIR",
        help="live run; record what the three boundaries return into DIR (needs --wiring)",
    )
    mode.add_argument(
        "--replay",
        metavar="DIR",
        help="re-run the real pipeline offline from the recording in DIR (needs --wiring)",
    )
    mode.add_argument(
        "--rescore",
        metavar="RUN_DIR",
        help="rebuild the report of a saved run (no pipeline); combine with --labels",
    )
    parser.add_argument(
        "--links",
        choices=[mode.value for mode in LinksMode],
        help="which links to check: the top 10 per garment group, all results, or none "
        "(default: all; a replay makes no network call, so it cannot check links)",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        help="output folder (default: eval/results/run-N for --record, eval/results/mock, "
        "eval/results/replay; extra sets use extras-N and replay-extras; for --rescore, "
        "the run's own folder)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --out to be a folder that already has files; with --only, also run a query "
        "again that already has a result, replacing it",
    )
    parser.add_argument("--run", type=int, metavar="N", help="run number shown in the report")
    parser.add_argument("--labels", metavar="CSV", help="a filled labelling sheet to score")
    parser.add_argument(
        "--wiring",
        metavar="MODULE:FUNCTION",
        help="function that builds the real application parts: (Settings) -> Wiring",
    )
    parser.add_argument(
        "--queries",
        metavar="PATH",
        default=str(QUERIES_PATH),
        help="the queries file (default: the frozen acceptance set; any other file is run as an "
        "extra set that does not count towards the pass rule, for example "
        "eval/data/extra_queries.yaml)",
    )
    parser.add_argument(
        "--pause",
        type=_seconds,
        default=DEFAULT_PAUSE_S,
        metavar="SECONDS",
        help="live run (--record) only: rest this long between one query and the next, so the "
        f"stores are not asked ten searches in a minute (default: {DEFAULT_PAUSE_S:g}; 0 turns it "
        "off). A mock or replay run never waits.",
    )
    parser.add_argument(
        "--link-interval",
        type=_seconds,
        default=DEFAULT_LINK_INTERVAL_S,
        metavar="SECONDS",
        help="live run (--record) only: send at most one link-check request every this many "
        f"seconds, across all stores together (default: {DEFAULT_LINK_INTERVAL_S:g}; 0 turns it "
        "off), on top of the fetch engine's own per-store limit",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="live run (--record) only: send the remaining queries even after one found every "
        "store blocked or in cooldown (by default the run stops there: asking stores that have "
        "just turned the search away only asks them again)",
    )
    parser.add_argument(
        "--only",
        metavar="IDS",
        help="finish a live run: with --record on the run's own recording folder, run just these "
        "queries (ids separated by commas, for example q03,q07) into the same run folder, next "
        "to the ones already there. The finished queries are not sent again; the report is "
        "rebuilt over all of them",
    )
    return parser


@dataclass
class _Setup:
    """Everything one mode needs to run the queries."""

    mode: Mode
    pipeline: Pipeline
    load_image: ImageLoader
    scope: QueryScope | None = None
    source: str | None = None
    link_fetch: LinkFetch | None = None
    allowed_hosts: Mapping[str, Collection[str]] | None = None
    replay: ReplaySession | None = None
    recording: RecordingSession | None = None
    clock: Clock = field(default_factory=SystemClock)
    close: Callable[[], Awaitable[None]] | None = None
    """Releases what the real application holds open (its HTTP client). Called once, on the
    event loop the run used."""
    warm_up: WarmUp | None = None
    """Set by the run, before the first query."""
    stores: Sequence[StoreConfig] = ()
    """The stores the real application searches, to say so when a run starts."""
    session: Session | None = None
    """How this live session treats the stores (the pause, the link spacing), for the report."""
    earlier_session_notes: list[str] = field(default_factory=list)
    """The notes of the sessions that fed this run folder before this one (``--only``)."""
    known_links: list[LinkCheck] = field(default_factory=list)
    """Link checks an earlier session made, so those URLs are not asked again."""


def _next_run_number(results_dir: Path, prefix: str = "run") -> int:
    numbers = [
        int(match.group(1))
        for child in results_dir.glob(f"{prefix}-*")
        if (match := _RUN_DIR.match(child.name))
    ]
    return max(numbers, default=0) + 1


def _resolve_output(
    args: argparse.Namespace, mode: Mode, root: Path, query_set: QuerySet = "acceptance"
) -> tuple[Path, int | None, bool]:
    """The output folder, the run number and whether the folder may already hold files."""
    results_dir = root / RESULTS_DIR
    prefix = _FOLDER_PREFIX[query_set]
    if args.out:
        out = Path(args.out)
        match = _RUN_DIR.match(out.name)
        number = args.run if args.run is not None else (int(match.group(1)) if match else None)
        return out, number, bool(args.overwrite)
    if mode == "record":
        # `--record eval/results/run-1/recording` keeps the recording inside its run's folder
        # (plan 16.1.1), so that folder is where the results go too.
        beside = Path(args.record).parent
        match = _RUN_DIR.match(beside.name)
        if match:
            number = args.run if args.run is not None else int(match.group(1))
            return beside, number, bool(args.overwrite)
        number = args.run if args.run is not None else _next_run_number(results_dir, prefix)
        return results_dir / f"{prefix}-{number}", number, bool(args.overwrite)
    # A mock or replay folder is replaced each time, so an extra set gets its own: replaying the
    # extras must not wipe the replay of the acceptance run.
    return results_dir / (mode if query_set == "acceptance" else f"{mode}-extras"), args.run, True


def _ensure_output_is_free(out: Path, overwrite: bool) -> None:
    """Fail before a live run, not after it, if the results would have nowhere to go."""
    if out.exists() and any(out.iterdir()) and not overwrite:
        msg = (
            f"{out} already holds files. Choose another --out folder, "
            "or pass --overwrite if you mean to replace that run."
        )
        raise RunFileError(msg)


def _wiring(args: argparse.Namespace, settings: Settings, factory: WiringFactory | None) -> Wiring:
    chosen = factory or (load_wiring_factory(args.wiring) if args.wiring else None)
    if chosen is None:
        msg = (
            "This mode needs the real application wired in, with --wiring "
            "package.module:function (the function takes Settings and returns a Wiring; "
            "Phase 16 provides it). To try the harness without it, use --mock."
        )
        raise WiringError(msg)
    wiring: object = chosen(settings)
    if not isinstance(wiring, Wiring):
        msg = f"The wiring function must return a Wiring, got {type(wiring).__name__}."
        raise WiringError(msg)
    return wiring


def _setup_mock() -> _Setup:
    photo = placeholder_image()
    return _Setup(
        mode="mock",
        pipeline=FakePipeline(),
        load_image=lambda query: photo if query.image else None,
    )


def _setup_replay(
    args: argparse.Namespace, settings: Settings, factory: WiringFactory | None
) -> _Setup:
    session = ReplaySession(args.replay)
    wiring = _wiring(args, settings, factory)
    photo = placeholder_image()
    return _Setup(
        mode="replay",
        pipeline=wiring.pipeline_factory(
            session.understander, session.searcher, session.image_ranker
        ),
        load_image=lambda query: photo if query.image else None,
        scope=session,
        source=str(args.replay),
        replay=session,
        stores=wiring.stores,
    )


def _setup_record(
    args: argparse.Namespace,
    settings: Settings,
    factory: WiringFactory | None,
    links: LinksMode,
    root: Path,
    planned: Sequence[str],
    *,
    resume: bool,
) -> _Setup:
    wiring = _wiring(args, settings, factory)
    if wiring.build_boundaries is None:
        msg = "--record needs a wiring that can build the live boundaries (build_boundaries)."
        raise WiringError(msg)
    if links is not LinksMode.NONE and wiring.link_fetch is None:
        msg = "The wiring has no link_fetch, so links cannot be checked. Use --links none."
        raise WiringError(msg)
    # Build the live parts before the recording folder exists: a missing key or model is found
    # here, in plain words, and leaves nothing behind.
    boundaries = wiring.build_boundaries()
    session = RecordingSession(args.record, planned=planned, resume=resume)
    live = session.wrap(boundaries)
    return _Setup(
        mode="record",
        pipeline=wiring.pipeline_factory(live.understander, live.searcher, live.image_ranker),
        load_image=lambda query: read_query_image(query, root),
        scope=session,
        link_fetch=wiring.link_fetch,
        allowed_hosts=allowed_hosts_from_stores(wiring.stores),
        recording=session,
        close=wiring.aclose,
        stores=wiring.stores,
    )


class _LinkPhase:
    """Checks the links of one query at a time.

    A live run shares one checker across the whole run, so a product that turns up in two queries
    is opened once. A mock run has no network and no state to share: each query gets a checker
    over its own products."""

    def __init__(self, setup: _Setup, mode: LinksMode) -> None:
        self._setup = setup
        self._mode = mode
        self._checker: LinkChecker | None = None

    async def check(self, response: SearchResponse) -> list[LinkCheck]:
        products = products_to_check(response, self._mode)
        if self._setup.mode == "mock":
            mock = LinkChecker(
                MockLinkFetch([s.product for s in response.products]),
                allowed_hosts_from_responses([response]),
            )
            return await mock.check_all(products)
        if self._checker is None:
            if self._setup.link_fetch is None:
                msg = "The wiring has no link_fetch, so links cannot be checked."
                raise WiringError(msg)
            self._checker = LinkChecker(
                self._setup.link_fetch,
                self._setup.allowed_hosts or {},
                known=self._setup.known_links,
            )
        return await self._checker.check_all(products)


async def _warm_up(setup: _Setup) -> WarmUp | None:
    """Load the image model before the first timed query, and say how long that took.

    The 30 s limit is about a search on an app that is already running (plan 16.1.1), so the
    model's load time must not land inside the first photo query. Only a live run loads anything:
    a replay serves the recorded scores and a mock has no model. A pipeline with no ``warm_up``
    has nothing to load either."""
    if setup.mode != "record":
        return None
    warm = getattr(setup.pipeline, "warm_up", None)
    if warm is None:
        return None
    started = setup.clock.monotonic()
    ready = False
    detail: str | None = None
    try:
        ready = bool(await warm())
    except Exception as exc:  # a warm-up that raises must not stop the run; it is reported
        detail = f"{type(exc).__name__}: {exc}"
    elapsed_ms = max(setup.clock.monotonic() - started, 0.0) * 1000.0
    return WarmUp(duration_ms=elapsed_ms, ready=ready, detail=detail)


Snapshot = Callable[[Sequence[QueryRun], Mapping[str, list[LinkCheck]]], None]
"""Saves the run as it stands: the finished queries and the link checks made so far."""


async def _run_and_check(
    setup: _Setup,
    queries: list[AcceptanceQuery],
    settings: Settings,
    links: LinksMode,
    progress: Callable[[QueryRun], None],
    snapshot: Snapshot,
    on_warm_up: Callable[[WarmUp | None], None],
    pacing: Pacing | None = None,
) -> tuple[list[QueryRun], dict[str, list[LinkCheck]]]:
    """Warm up, then run the queries one by one: search, save, check that query's links, save
    again. One event loop for all of it, because a fetch function or pipeline may keep an HTTP
    client that belongs to the loop it first ran in.

    A live run is saved after every query's search, before its first link is fetched, so the
    expensive part is on disk even if the link phase or a later query is interrupted. Checking a
    query's links right away (not after all ten queries) spreads the traffic out over the run
    and lets the next query's pause cover the links too."""
    link_checks: dict[str, list[LinkCheck]] = {}
    phase = _LinkPhase(setup, links)

    async def after_query(runs: Sequence[QueryRun]) -> None:
        live = setup.mode == "record"
        if live:
            snapshot(runs, link_checks)
        run = runs[-1]
        if links is LinksMode.NONE or run.response is None:
            return
        link_checks[run.query.id] = await phase.check(run.response)
        if live:
            snapshot(runs, link_checks)

    try:
        on_warm_up(await _warm_up(setup))
        runs = await run_queries(
            queries,
            setup.pipeline,
            settings,
            clock=setup.clock,
            load_image=setup.load_image,
            scope=setup.scope,
            progress=progress,
            after_query=after_query,
            pacing=pacing,
        )
        if setup.replay is not None:
            runs = [_with_recorded_duration(run, setup.replay) for run in runs]
        return runs, link_checks
    finally:
        if setup.close is not None:
            await setup.close()


def _with_recorded_duration(run: QueryRun, replay: ReplaySession) -> QueryRun:
    """A replay's own time is meaningless; the 30 s rule uses the recorded live figure. The same
    goes for the search after the gender question was answered: its recorded time replaces it."""
    if run.failure is not None or (run.not_run is not None and run.response is None):
        return run  # nothing was replayed: a failure, or a query the recording does not reach
    gender = run.gender
    if gender is not None and gender.asked:
        gender = gender.model_copy(update={"duration_ms": replay.live_confirm_ms(run.query.id)})
    recorded = replay.live_duration_ms(run.query.id)
    if recorded is None:
        return replace(run, duration_source="unavailable", gender=gender)
    return replace(run, duration_ms=recorded, duration_source="recorded", gender=gender)


def _gender_notes(runs: Sequence[QueryRun]) -> list[str]:
    """Which queries had the "Who is this for?" question answered, with what, and what was not."""
    answered = [(r.query.id, r.gender.answer.value) for r in runs if r.gender and r.gender.asked]
    unused = [(r.query.id, r.gender.answer.value) for r in runs if r.gender and not r.gender.asked]
    notes: list[str] = []
    if answered:
        listing = ", ".join(f"{query_id} ({answer})" for query_id, answer in answered)
        notes.append(
            f'The "Who is this for?" question was answered, as the page does, for {listing}. '
            "After a query's first search the harness ran one re-search with the recorded answer "
            "applied to every garment whose gender the request had not stated; no photo was sent "
            "and no model was called. The results scored, labelled and link-checked are the ones "
            "shown after the answer."
        )
    if unused:
        listing = ", ".join(f"{query_id} ({answer})" for query_id, answer in unused)
        notes.append(
            f"The recorded answer was not needed for {listing}: the request already stated the "
            "gender of every garment, so the page would not ask and no second search ran."
        )
    for run in runs:
        if run.gender is not None and run.gender.typed_differently:
            stated = describe_stated(run.gender.typed_differently)
            notes.append(
                f"{run.query.id}: the recorded answer is {run.gender.answer.value}, but the "
                f"request stated {stated}. The stated gender stands."
            )
    return notes


def _session_notes(setup: _Setup) -> list[str]:
    """One note for every live session that fed this run folder, this one last."""
    if setup.session is None:
        return []
    return [*setup.earlier_session_notes, session_note(setup.session, setup.warm_up)]


def _run_notes(setup: _Setup, runs: Sequence[QueryRun], warm_up: WarmUp | None) -> list[str]:
    """The notes for the report. ``warm_up`` is the run's own (the first session's)."""
    notes: list[str] = []
    if setup.replay is not None:
        notes.extend(setup.replay.final_notes())
    notes.extend(_session_notes(setup))
    notes.extend(_gender_notes(runs))
    unservable = [r.query.id for r in runs if r.failure and r.failure.code.startswith("recording")]
    if unservable:
        notes.append(
            "The replay could not serve " + ", ".join(unservable) + " from the recording (not "
            "recorded, incomplete, or the pipeline asked for something else). Those queries "
            "count as failed; the others ran. This is a limit of the recording, not a store fault."
        )
    if warm_up is not None and not warm_up.ready:
        notes.append(
            "Image scoring was not available when the run started"
            + (f" ({warm_up.detail})" if warm_up.detail else "")
            + ": photo queries were ranked on text and price only, so this run does not show what "
            "the finished app does with a photo. The reason is in the log."
        )
    if setup.recording is not None and setup.recording.incomplete:
        notes.append(
            "The recording of "
            + ", ".join(setup.recording.incomplete)
            + " is incomplete (a boundary failed mid-call); it cannot be replayed."
        )
    return notes


def _back_up(path: Path) -> Path:
    """Move ``path`` aside to the first free ``<name>.bak-N`` and return where it went."""
    number = 1
    while (backup := path.with_name(f"{path.stem}.bak-{number}{path.suffix}")).exists():
        number += 1
    path.replace(backup)
    return backup


def _write_report(
    scored: ScoredRun, out: Path, *, keep_previous: bool = False
) -> tuple[Path, Path | None]:
    """Write ``results.md``. With ``keep_previous``, an existing different report (a person may
    have added notes to it) is moved aside first rather than overwritten. Returns the report and
    the backup, if one was made."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / REPORT_FILE
    text = render_report(scored)
    backup = None
    if keep_previous and path.exists() and path.read_text(encoding="utf-8") != text:
        backup = _back_up(path)
    path.write_text(text, encoding="utf-8")
    return path, backup


def _sheet_has_labels(path: Path) -> bool:
    """True when a labelling sheet already holds at least one label: a person's work."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return any((row.get("label") or "").strip() for row in csv.DictReader(handle))
    except (OSError, UnicodeDecodeError):
        return False


def _export_sheet(runs: Sequence[QueryRun], out: Path) -> tuple[Path, int]:
    """Write the blank labelling sheet, but never over one that already holds labels."""
    sheet = out / LABELS_FILE
    if sheet.exists() and _sheet_has_labels(sheet):
        sheet = out / "labels.new.csv"
    return sheet, export_label_sheet(runs, sheet)


def _load_labels(path: str | None, runs: Sequence[QueryRun]) -> LabelSet | None:
    return import_label_sheet(path, runs) if path else None


def _warm_up_line(warm_up: WarmUp) -> str:
    took = f"{warm_up.duration_ms / 1000:.1f} s"
    if warm_up.ready:
        return (
            f"Warm-up: done in {took}, before the first query and outside every query's time. "
            "Image scoring is ready."
        )
    return (
        f"Warm-up: done in {took}, but image scoring is NOT available, so photo queries will be "
        "ranked on text and price only. The reason is in the log. The image model needs "
        "`uv sync --group ml` and `uv run --group ml python -m vga.rank.image.download`."
    )


def _print_verdict(scored: ScoredRun, out: TextIO) -> None:
    verdict = scored.verdict
    if scored.loaded.meta.mode == "mock":
        print("Mock run: the verdict below says nothing about the real app.", file=out)
    if verdict.required is None:
        print(f"Extra set, not the acceptance result: {verdict.headline}.", file=out)
        print("  It has no demo verdict and does not count towards the 7 of 10 rule.", file=out)
    else:
        print(f"Verdict: {verdict.label}. {verdict.headline}.", file=out)
    if verdict.not_run:
        decided = len(verdict.passed) + len(verdict.failed) + len(verdict.pending)
        print(
            f"  Of the {decided} that ran: {len(verdict.passed)} pass, {len(verdict.failed)} fail, "
            f"{len(verdict.pending)} undecided. A query that did not run is neither a pass nor "
            "a fail; repeat the run for it (see the report).",
            file=out,
        )
    elif verdict.pending:
        print(
            f"  {len(verdict.pending)} query(ies) still undecided (labels or links missing).",
            file=out,
        )
    if verdict.failed:
        print(f"  Failed: {', '.join(verdict.failed)}.", file=out)


def _rescore(args: argparse.Namespace, out_stream: TextIO) -> int:
    loaded = load_run(args.rescore)
    scored = score_run(loaded, labels=_load_labels(args.labels, loaded.runs))
    target = Path(args.out) if args.out else Path(args.rescore)
    report, backup = _write_report(scored, target, keep_previous=True)
    print(f"Rescored {args.rescore} -> {report}", file=out_stream)
    if backup is not None:
        print(f"The previous report was kept as {backup}.", file=out_stream)
    _print_verdict(scored, out_stream)
    return 0


def _execute(
    args: argparse.Namespace,
    out_stream: TextIO,
    wiring_factory: WiringFactory | None,
    today: date,
    root: Path,
    settings: Settings,
    clock: Clock | None,
) -> int:
    mode: Mode = "mock" if args.mock else "record" if args.record else "replay"
    only = parse_only(args.only) if args.only is not None else None
    if only is not None and mode != "record":
        msg = "--only finishes a live run: use it with --record, on the run's own recording."
        raise ResumeError(msg)
    if mode == "replay" and args.links not in (None, "none"):
        msg = (
            "--replay makes no network call, so it cannot check links. "
            "Drop --links, or use --links none."
        )
        raise WiringError(msg)
    links_asked = LinksMode(args.links) if args.links else None
    links = links_asked or (LinksMode.NONE if mode == "replay" else LinksMode.ALL)
    query_set = query_set_of(args.queries)
    out, number, overwrite = _resolve_output(args, mode, root, query_set)
    if only is None:
        _ensure_output_is_free(out, overwrite)

    # Only the frozen acceptance set must have the PRD mix; an extra set has none to check.
    queries: list[AcceptanceQuery] = load_queries(
        args.queries,
        repo_root=root,
        require_images=mode == "record",
        check_mix=query_set == "acceptance",
    )
    # Finishing a run: the folder's earlier sessions are kept, and this one runs the named queries.
    continuation: Continuation | None = None
    if only is not None:
        continuation = plan_continuation(
            out,
            queries,
            only,
            query_set=query_set,
            links_asked=links_asked,
            overwrite=bool(args.overwrite),
        )
        links = continuation.links
    earlier = continuation.earlier if continuation else None
    to_run = list(continuation.selected) if continuation else queries
    earlier_runs = earlier.runs if earlier else []
    earlier_links = links_to_keep(earlier, {query.id for query in to_run}) if earlier else {}

    if mode == "mock":
        setup = _setup_mock()
    elif mode == "replay":
        setup = _setup_replay(args, settings, wiring_factory)
    else:
        setup = _setup_record(
            args,
            settings,
            wiring_factory,
            links,
            root,
            [query.id for query in queries],
            resume=continuation is not None,
        )
    if clock is not None:
        setup.clock = clock
    if setup.stores:
        names = ", ".join(store.id for store in setup.stores)
        print(f"Stores in this run ({len(setup.stores)}): {names}", file=out_stream)
    if earlier is not None and continuation is not None:
        setup.earlier_session_notes = list(earlier.meta.session_notes)
        setup.known_links = already_checked(earlier)
        print(
            f"Continuing {out.name}: this session runs "
            f"{', '.join(query.id for query in to_run)}; the other "
            f"{len(queries) - len(to_run)} queries are left as they are and not sent again.",
            file=out_stream,
        )

    def progress(run: QueryRun) -> None:
        if run.not_run is not None:
            print(f"{run.query.id}: NOT RUN ({run.not_run.reason})", file=out_stream)
        elif run.response is not None:
            line = f"{run.query.id}: {run.response.result_count} results in "
            line += f"{run.duration_ms / 1000:.1f} s"
            if run.gender is not None and run.confirm_ms is not None:
                line += (
                    f" (first search), then {run.confirm_ms / 1000:.1f} s after the shopper "
                    f"answered {run.gender.answer.value}"
                )
            print(line, file=out_stream)
        else:
            failure = run.failure.message if run.failure else "no response"
            print(f"{run.query.id}: FAILED ({failure})", file=out_stream)

    def whole_run(new_runs: Sequence[QueryRun]) -> list[QueryRun]:
        """Every query of the run folder, in the order of the queries file: this session's where
        it ran, the earlier session's where it did not, and "not sent yet" for the rest. What is
        saved after every query is this view, so an interrupted or stopped run can be finished."""
        return in_query_order(queries, earlier_runs, new_runs)

    def persist(
        new_runs: Sequence[QueryRun],
        new_links: Mapping[str, list[LinkCheck]],
        *,
        use_labels: bool,
    ) -> tuple[ScoredRun, Path, int]:
        runs = whole_run(new_runs)
        # The first session's own figures stay the run's: the date, the mix and the warm-up.
        first = earlier.meta if earlier is not None else None
        warm_up = first.warm_up if first is not None else setup.warm_up
        meta = RunMeta(
            number=number,
            query_set=query_set,
            mode=mode,
            date=first.date if first is not None else today,
            links=links,
            price_range_mix=first.price_range_mix
            if first is not None
            else list(settings.tier_mix.as_tuple()),
            source=setup.source,
            notes=_run_notes(setup, runs, warm_up),
            session_notes=_session_notes(setup),
            warm_up=warm_up,
        )
        loaded = LoadedRun(meta, runs, {**earlier_links, **new_links})
        # The folder was checked before the run (`_ensure_output_is_free`). By now it may hold
        # the recording, written there on purpose, so this save must not call that a collision.
        save_run(out, loaded, overwrite=True)
        sheet, rows = (out / LABELS_FILE, 0) if args.labels else _export_sheet(runs, out)
        labels = _load_labels(args.labels, runs) if use_labels else None
        scored = score_run(loaded, labels=labels)
        _write_report(scored, out)
        return scored, sheet, rows

    def snapshot(runs: Sequence[QueryRun], checks: Mapping[str, list[LinkCheck]]) -> None:
        persist(runs, checks, use_labels=False)

    def warmed_up(warm_up: WarmUp | None) -> None:
        setup.warm_up = warm_up
        if warm_up is not None:
            print(_warm_up_line(warm_up), file=out_stream)

    pacing: Pacing | None = None
    if mode == "record":
        pacing = Pacing(
            pause_s=args.pause,
            say=lambda text: print(text, file=out_stream),
            stop_when_throttled=not args.keep_going,
        )
        setup.session = Session(
            number=len(setup.earlier_session_notes) + 1,
            day=today,
            ran=tuple(query.id for query in to_run) if continuation else None,
            pause_s=args.pause,
            link_interval_s=args.link_interval,
            links=links,
        )
        if setup.link_fetch is not None and links is not LinksMode.NONE:
            setup.link_fetch = SpacedLinkFetch(setup.link_fetch, args.link_interval, setup.clock)

    new_runs, new_links = asyncio.run(
        _run_and_check(setup, to_run, settings, links, progress, snapshot, warmed_up, pacing)
    )
    runs = whole_run(new_runs)
    if mode == "record":
        for line in incomplete_lines(runs, args):
            print(line, file=out_stream)
    scored, sheet, rows = persist(new_runs, new_links, use_labels=True)

    answered = sum(1 for run in runs if run.response is not None and run.not_run is None)
    not_run = sum(1 for run in runs if run.not_run is not None)
    print(
        f"{answered} of {len(runs)} queries answered"
        + (f" ({not_run} not run)" if not_run else "")
        + f"; responses saved in {out / 'responses'}",
        file=out_stream,
    )
    print(f"Report: {out / REPORT_FILE}", file=out_stream)
    if not args.labels:
        print(f"Labelling sheet: {sheet} ({rows} rows to label)", file=out_stream)
    _print_verdict(scored, out_stream)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    wiring_factory: WiringFactory | None = None,
    settings: Settings | None = None,
    clock: Clock | None = None,
    today: Callable[[], date] = date.today,
    root: Path = PROJECT_ROOT,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the harness. Returns 0 when the run completed (whatever the verdict), 2 on a problem
    with the inputs or the setup.

    ``wiring_factory`` is the programmatic form of ``--wiring``; ``settings`` replaces loading
    ``config/settings.yaml`` and ``clock`` replaces the real clock (both for tests); ``root`` is
    the repository root.
    """
    out_stream = stdout or sys.stdout
    err_stream = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        if args.rescore:
            return _rescore(args, out_stream)
        return _execute(
            args, out_stream, wiring_factory, today(), root, settings or load_settings(), clock
        )
    except VgaError as exc:
        print(f"error: {exc}", file=err_stream)
        return 2
