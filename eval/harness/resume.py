"""Finish a live run later: ``--only q03,q07`` (plan 16.1.1).

A run that stopped at a throttled query, or was interrupted, has some queries done and some not.
``--only`` runs just the named queries into the same run folder and the same recording, next to the
ones already there. The finished queries are not sent again: their responses, link checks and
recordings stay as they are, the report is rebuilt over all of them, and the recording replays as
one run.

This module only decides what ``--only`` may do. It reads the folder and the queries file and
returns what to run; it sends nothing.

What it deliberately cannot do (the simplest sound version):

- It runs a named query *whole* (search, answer to "Who is this for?", links). It cannot redo only
  a query's links, or its second search.
- A query that already has a result is not run again unless ``--overwrite`` says so; the result and
  the recording of that query are then replaced.
- The run keeps one ``--links`` setting, the one it was started with.
- The sessions share one folder and one report, so they must use the same queries file.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from eval.harness.errors import ResumeError
from eval.harness.links import LinkCheck, LinksMode
from eval.harness.queries import AcceptanceQuery, QuerySet
from eval.harness.runner import QueryRun
from eval.harness.runstore import RUN_FILE, LoadedRun, load_run


@dataclass(frozen=True)
class Continuation:
    """An earlier session of a run folder, and the queries this session runs."""

    earlier: LoadedRun
    selected: tuple[AcceptanceQuery, ...]
    """The queries to run now, in the order of the queries file."""
    links: LinksMode
    """The run's own link setting: a run is finished the way it was started."""
    replaced: tuple[str, ...]
    """The selected queries that already had a result, which ``--overwrite`` allows to replace."""


def parse_only(text: str) -> list[str]:
    """The query ids in ``--only``, without repeats."""
    ids = [part.strip() for part in text.split(",")]
    if not all(ids):
        msg = "--only needs query ids separated by commas, for example --only q03,q07."
        raise ResumeError(msg)
    return list(dict.fromkeys(ids))


def has_a_result(run: QueryRun) -> bool:
    """True when the query was sent: it answered, or failed with a reason of its own. A query
    that was not run (its stores were unavailable, or it was never sent) has no result."""
    return run.not_run is None


def plan_continuation(
    folder: Path,
    queries: Sequence[AcceptanceQuery],
    only: Sequence[str],
    *,
    query_set: QuerySet,
    links_asked: LinksMode | None,
    overwrite: bool,
) -> Continuation:
    """Check that ``folder`` is a live run that ``only`` can finish, and say what to run."""
    if not (folder / RUN_FILE).is_file():
        msg = (
            f"{folder} holds no saved run, so there is nothing to continue with --only. Name the "
            "run's folder with --out (or keep the recording inside it, as run-N/recording), or "
            "start the run without --only."
        )
        raise ResumeError(msg)
    earlier = load_run(folder)
    meta = earlier.meta
    if meta.mode != "record":
        msg = f"{folder} is a {meta.mode} result, not a live run, so --only cannot finish it."
        raise ResumeError(msg)
    if meta.query_set != query_set:
        msg = (
            f"{folder} was run on the {meta.query_set} queries, not the {query_set} set named "
            "now. Use the same --queries file to finish it."
        )
        raise ResumeError(msg)
    if links_asked is not None and links_asked is not meta.links:
        msg = (
            f"{folder} was run with --links {meta.links.value}; a run is finished the way it was "
            f"started. Leave --links out, or use --links {meta.links.value}."
        )
        raise ResumeError(msg)

    wanted = {query.id for query in queries}
    strangers = [run.query.id for run in earlier.runs if run.query.id not in wanted]
    if strangers:
        msg = (
            f"{folder} holds {', '.join(strangers)}, which the queries file does not have. "
            "Use the same --queries file the run started with."
        )
        raise ResumeError(msg)
    unknown = [item for item in only if item not in wanted]
    if unknown:
        msg = (
            f"--only names {', '.join(unknown)}, which the queries file does not have. "
            f"The queries are: {', '.join(query.id for query in queries)}."
        )
        raise ResumeError(msg)

    done = {run.query.id for run in earlier.runs if has_a_result(run)}
    replaced = tuple(item for item in only if item in done)
    if replaced and not overwrite:
        msg = (
            f"These queries already have a result in {folder}: {', '.join(replaced)}. Running "
            "them again would ask the stores again. Leave them out of --only, or pass "
            "--overwrite to run them again and replace the result."
        )
        raise ResumeError(msg)
    selected = tuple(query for query in queries if query.id in set(only))
    return Continuation(earlier, selected, meta.links, replaced)


def links_to_keep(earlier: LoadedRun, running: Collection[str]) -> dict[str, list[LinkCheck]]:
    """The link checks of the queries this session does not run again."""
    return {
        query_id: list(checks)
        for query_id, checks in earlier.links.items()
        if query_id not in running
    }


def already_checked(earlier: LoadedRun) -> list[LinkCheck]:
    """Link checks worth keeping when new ones are made: a URL that was answered is not asked
    again. A link a store turned away was never looked at, so it is asked again."""
    return [check for checks in earlier.links.values() for check in checks if not check.not_checked]
