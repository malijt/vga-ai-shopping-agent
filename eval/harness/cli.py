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

from eval.harness.errors import RunFileError, WiringError
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
from eval.harness.queries import QUERIES_PATH, AcceptanceQuery, load_queries, read_query_image
from eval.harness.recording import RecordingSession, ReplaySession
from eval.harness.report import render_report
from eval.harness.runner import ImageLoader, QueryRun, QueryScope, run_queries
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
from eval.harness.wiring import Wiring, WiringFactory, load_wiring_factory
from vga.errors import VgaError
from vga.interfaces import Clock, Pipeline, SystemClock
from vga.settings import PROJECT_ROOT, Settings, load_settings

RESULTS_DIR = Path("eval") / "results"
_RUN_DIR = re.compile(r"^run-(\d+)$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.harness",
        description=(
            "Run the 10 acceptance queries headless, score them against the BRD pass rule, "
            "and leave only the good-match labels to a person."
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
        "eval/results/replay; for --rescore, the run's own folder)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="allow --out to be a folder that already has files"
    )
    parser.add_argument("--run", type=int, metavar="N", help="run number shown in the report")
    parser.add_argument("--labels", metavar="CSV", help="a filled labelling sheet to score")
    parser.add_argument(
        "--wiring",
        metavar="MODULE:FUNCTION",
        help="function that builds the real application parts: (Settings) -> Wiring",
    )
    parser.add_argument(
        "--queries", metavar="PATH", default=str(QUERIES_PATH), help="the queries file"
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


def _next_run_number(results_dir: Path) -> int:
    numbers = [
        int(match.group(1))
        for child in results_dir.glob("run-*")
        if (match := _RUN_DIR.match(child.name))
    ]
    return max(numbers, default=0) + 1


def _resolve_output(
    args: argparse.Namespace, mode: Mode, root: Path
) -> tuple[Path, int | None, bool]:
    """The output folder, the run number and whether the folder may already hold files."""
    results_dir = root / RESULTS_DIR
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
        number = args.run if args.run is not None else _next_run_number(results_dir)
        return results_dir / f"run-{number}", number, bool(args.overwrite)
    return results_dir / mode, args.run, True


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
    )


def _setup_record(
    args: argparse.Namespace,
    settings: Settings,
    factory: WiringFactory | None,
    links: LinksMode,
    root: Path,
) -> _Setup:
    wiring = _wiring(args, settings, factory)
    if wiring.build_boundaries is None:
        msg = "--record needs a wiring that can build the live boundaries (build_boundaries)."
        raise WiringError(msg)
    if links is not LinksMode.NONE and wiring.link_fetch is None:
        msg = "The wiring has no link_fetch, so links cannot be checked. Use --links none."
        raise WiringError(msg)
    session = RecordingSession(args.record)
    live = session.wrap(wiring.build_boundaries())
    return _Setup(
        mode="record",
        pipeline=wiring.pipeline_factory(live.understander, live.searcher, live.image_ranker),
        load_image=lambda query: read_query_image(query, root),
        scope=session,
        link_fetch=wiring.link_fetch,
        allowed_hosts=allowed_hosts_from_stores(wiring.stores),
        recording=session,
        close=wiring.aclose,
    )


async def _check_links(
    runs: Sequence[QueryRun],
    mode: LinksMode,
    fetch: LinkFetch,
    allowed: Mapping[str, Collection[str]],
) -> dict[str, list[LinkCheck]]:
    checker = LinkChecker(fetch, allowed)
    checks: dict[str, list[LinkCheck]] = {}
    for run in runs:
        if run.response is not None:
            checks[run.query.id] = await checker.check_all(products_to_check(run.response, mode))
    return checks


def _link_tools(
    setup: _Setup, runs: Sequence[QueryRun]
) -> tuple[LinkFetch, Mapping[str, Collection[str]]]:
    """The fetch function and allowed hosts to check links with."""
    if setup.mode == "mock":
        products = [s.product for r in runs if r.response for s in r.response.products]
        responses = [r.response for r in runs if r.response]
        return MockLinkFetch(products), allowed_hosts_from_responses(responses)
    if setup.link_fetch is None:
        msg = "The wiring has no link_fetch, so links cannot be checked."
        raise WiringError(msg)
    return setup.link_fetch, setup.allowed_hosts or {}


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


async def _run_and_check(
    setup: _Setup,
    queries: list[AcceptanceQuery],
    settings: Settings,
    links: LinksMode,
    progress: Callable[[QueryRun], None],
    checkpoint: Callable[[list[QueryRun]], None],
    on_warm_up: Callable[[WarmUp | None], None],
) -> tuple[list[QueryRun], dict[str, list[LinkCheck]]]:
    """Warm up, run the queries, save them, then check links. One event loop for all of it,
    because a fetch function or pipeline may keep an HTTP client that belongs to the loop it
    first ran in.

    ``checkpoint`` is called with the finished runs before the first link is fetched, so the
    expensive part of a live run is on disk even if the link phase is interrupted."""
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
        )
        if setup.replay is not None:
            runs = [_with_recorded_duration(run, setup.replay) for run in runs]
        checkpoint(runs)
        if links is LinksMode.NONE:
            return runs, {}
        fetch, allowed = _link_tools(setup, runs)
        return runs, await _check_links(runs, links, fetch, allowed)
    finally:
        if setup.close is not None:
            await setup.close()


def _with_recorded_duration(run: QueryRun, replay: ReplaySession) -> QueryRun:
    """A replay's own time is meaningless; the 30 s rule uses the recorded live figure."""
    if run.failure is not None:
        return run
    recorded = replay.live_duration_ms(run.query.id)
    if recorded is None:
        return replace(run, duration_source="unavailable")
    return replace(run, duration_ms=recorded, duration_source="recorded")


def _run_notes(setup: _Setup, runs: Sequence[QueryRun]) -> list[str]:
    notes: list[str] = []
    if setup.replay is not None:
        notes.extend(setup.replay.final_notes())
    unservable = [r.query.id for r in runs if r.failure and r.failure.code.startswith("recording")]
    if unservable:
        notes.append(
            "The replay could not serve " + ", ".join(unservable) + " from the recording (not "
            "recorded, incomplete, or the pipeline asked for something else). Those queries "
            "count as failed; the others ran. This is a limit of the recording, not a store fault."
        )
    warm_up = setup.warm_up
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
    print(f"Verdict: {verdict.label}. {verdict.headline}.", file=out)
    if verdict.pending:
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
    if mode == "replay" and args.links not in (None, "none"):
        msg = (
            "--replay makes no network call, so it cannot check links. "
            "Drop --links, or use --links none."
        )
        raise WiringError(msg)
    links = (
        LinksMode(args.links)
        if args.links
        else (LinksMode.NONE if mode == "replay" else LinksMode.ALL)
    )
    out, number, overwrite = _resolve_output(args, mode, root)
    _ensure_output_is_free(out, overwrite)

    queries: list[AcceptanceQuery] = load_queries(
        args.queries, repo_root=root, require_images=mode == "record"
    )
    if mode == "mock":
        setup = _setup_mock()
    elif mode == "replay":
        setup = _setup_replay(args, settings, wiring_factory)
    else:
        setup = _setup_record(args, settings, wiring_factory, links, root)
    if clock is not None:
        setup.clock = clock

    def progress(run: QueryRun) -> None:
        if run.response is not None:
            print(
                f"{run.query.id}: {run.response.result_count} results in "
                f"{run.duration_ms / 1000:.1f} s",
                file=out_stream,
            )
        else:
            failure = run.failure.message if run.failure else "no response"
            print(f"{run.query.id}: FAILED ({failure})", file=out_stream)

    def persist(
        runs: list[QueryRun], link_checks: dict[str, list[LinkCheck]], *, use_labels: bool
    ) -> tuple[ScoredRun, Path, int]:
        meta = RunMeta(
            number=number,
            mode=mode,
            date=today,
            links=links,
            price_range_mix=list(settings.tier_mix.as_tuple()),
            source=setup.source,
            notes=_run_notes(setup, runs),
            warm_up=setup.warm_up,
        )
        loaded = LoadedRun(meta, runs, link_checks)
        # The folder was checked before the run (`_ensure_output_is_free`). By now it may hold
        # the recording, written there on purpose, so this save must not call that a collision.
        save_run(out, loaded, overwrite=True)
        sheet, rows = (out / LABELS_FILE, 0) if args.labels else _export_sheet(runs, out)
        labels = _load_labels(args.labels, runs) if use_labels else None
        scored = score_run(loaded, labels=labels)
        _write_report(scored, out)
        return scored, sheet, rows

    def checkpoint(runs: list[QueryRun]) -> None:
        persist(runs, {}, use_labels=False)

    def warmed_up(warm_up: WarmUp | None) -> None:
        setup.warm_up = warm_up
        if warm_up is not None:
            print(_warm_up_line(warm_up), file=out_stream)

    runs, link_checks = asyncio.run(
        _run_and_check(setup, queries, settings, links, progress, checkpoint, warmed_up)
    )
    scored, sheet, rows = persist(runs, link_checks, use_labels=True)

    answered = sum(1 for run in runs if run.response is not None)
    print(
        f"{answered} of {len(runs)} queries answered; responses saved in {out / 'responses'}",
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
