"""What a live run that did not run every query tells the person at the keyboard.

A run that stopped (or kept going past) a query whose stores were blocked is incomplete. Before the
report and the verdict, the console says which queries ran, which did not and why, how long to wait
and the exact command that finishes the run later. The same facts are in the report's "Queries not
run" section (``report.py``); this is the version for the terminal, with the command in it.
"""

import argparse
import shlex
from collections.abc import Sequence

from eval.harness.notrun import STORES_UNAVAILABLE_WHY, describe_wait
from eval.harness.queries import QUERIES_PATH
from eval.harness.runner import QueryRun


def repeat_command(args: argparse.Namespace, only: Sequence[str]) -> list[str]:
    """The command line that runs the queries ``only`` again into the same run: the same recording
    folder, wiring, queries file and output folder."""
    words = ["uv", "run", "--group", "ml", "python", "-m", "eval.harness"]
    words += ["--record", args.record, "--only", ",".join(only)]
    if args.wiring:
        words += ["--wiring", args.wiring]
    if args.queries != str(QUERIES_PATH):
        words += ["--queries", args.queries]
    if args.out:
        words += ["--out", args.out]
    return words


def _segments(runs: Sequence[QueryRun]) -> list[str]:
    """``q04 (the stores were blocked or in cooldown), q05, q06 (not sent)``: consecutive queries
    that did not run for the same reason share it."""
    groups: list[tuple[str, list[str]]] = []
    for run in runs:
        if run.not_run is None:
            continue
        why = STORES_UNAVAILABLE_WHY if run.not_run.kind == "stores_unavailable" else "not sent"
        if groups and groups[-1][0] == why:
            groups[-1][1].append(run.query.id)
        else:
            groups.append((why, [run.query.id]))
    return [f"{', '.join(ids)} ({why})" for why, ids in groups]


def _stopped_after(runs: Sequence[QueryRun]) -> QueryRun | None:
    """The query that stopped the run: the last throttled query before the first one not sent."""
    stopper: QueryRun | None = None
    for run in runs:
        if run.not_run is None:
            continue
        if run.not_run.kind == "stores_unavailable":
            stopper = run
        elif stopper is not None:
            return stopper
    return None


def incomplete_lines(runs: Sequence[QueryRun], args: argparse.Namespace) -> list[str]:
    """The console lines for a live run with queries that did not run; none when all of them did."""
    skipped = [run for run in runs if run.not_run is not None]
    if not skipped:
        return []
    ran = [run.query.id for run in runs if run.not_run is None]
    unsent = [run for run in skipped if run.not_run is not None and run.not_run.kind == "not_sent"]
    lines: list[str] = []
    stopper = _stopped_after(runs)
    if stopper is not None:
        lines.append(
            f"Stopped after {stopper.query.id}: every store that could be asked was blocked or "
            f"in cooldown, so the other {len(unsent)} queries were not sent "
            "(--keep-going sends them anyway)."
        )
    lines.append(f"Ran ({len(ran)}): {', '.join(ran) or 'none'}.")
    lines.append(f"Did not run ({len(skipped)}): {', '.join(_segments(runs))}.")
    cooldowns = [
        run.not_run.cooldown_s
        for run in skipped
        if run.not_run is not None and run.not_run.cooldown_s is not None
    ]
    if cooldowns:
        lines.append(
            f"A store that turns a search away is left alone for {describe_wait(max(cooldowns))} "
            "(the store_cooldown_s setting). The responses do not say how much of that is left, "
            "and a new run does not remember it, so wait at least that long."
        )
    again = repeat_command(args, [run.query.id for run in skipped])
    lines.append(
        "This run is incomplete and must be repeated later for the queries that did not run:"
    )
    lines.append("  " + shlex.join(again))
    return lines
