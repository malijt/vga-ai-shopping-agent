"""Save a run to a directory and load it back (plan 11.1.2, 11.3.2).

A run directory holds everything the report needs, so a person can label the sheet days later and
the report can be rebuilt (``--rescore``) **without running the pipeline again**, which would cost
OpenAI calls and store traffic::

    <dir>/run.json              metadata, per-query timings and failures, link checks
    <dir>/responses/<id>.json   the raw ``SearchResponse`` of each query
    <dir>/results.md            the report (written by the CLI)
    <dir>/labels.csv            the labelling sheet (written by the CLI)

``SearchResponse`` already leaves the photo and the query embedding out of its JSON, so nothing
derived from a photo is saved here either (BRD Rule 4).
"""

import json
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from eval.harness.errors import RunFileError
from eval.harness.links import LinkCheck, LinksMode
from eval.harness.queries import AcceptanceQuery
from eval.harness.runner import DurationSource, PipelineFailure, QueryRun
from vga.models import SearchResponse, VgaModel

RUN_FORMAT = 1
RUN_FILE = "run.json"
RESPONSES_DIR = "responses"
REPORT_FILE = "results.md"
LABELS_FILE = "labels.csv"

Mode = Literal["mock", "record", "replay"]


class RunMeta(VgaModel):
    """What kind of run this was."""

    number: int | None = None
    """The run number (``run-1``), or ``None`` for a mock or replay run."""
    mode: Mode
    date: date
    links: LinksMode
    price_range_mix: list[int] = Field(min_length=4, max_length=4)
    """Target price-range mix in percent: budget, mid-range, premium, luxury."""
    source: str | None = None
    """Where a replay's recording came from."""
    notes: list[str] = Field(default_factory=list)
    """Plain notes from the run itself, copied into the report."""


class FailureRecord(VgaModel):
    code: str
    message: str
    kind: str


class QueryRecord(VgaModel):
    query: AcceptanceQuery
    response_file: str | None
    failure: FailureRecord | None
    wall_ms: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    duration_source: DurationSource = "measured"
    link_checks: list[LinkCheck] = Field(default_factory=list)


class RunRecord(VgaModel):
    format: int = RUN_FORMAT
    meta: RunMeta
    queries: list[QueryRecord]


@dataclass
class LoadedRun:
    """A run in memory: what ``save_run`` writes and ``load_run`` returns."""

    meta: RunMeta
    runs: list[QueryRun]
    links: dict[str, list[LinkCheck]] = field(default_factory=dict)
    """Link checks by query id. A query missing here was not checked."""

    @property
    def responses(self) -> list[SearchResponse]:
        return [run.response for run in self.runs if run.response is not None]


def save_run(directory: Path | str, loaded: LoadedRun, *, overwrite: bool = False) -> Path:
    """Write ``run.json`` and one response file per query. Returns the run directory.

    Refuses a directory that already holds files unless ``overwrite`` is set, so a live run's
    results cannot be replaced by accident.
    """
    target = Path(directory)
    if target.exists() and any(target.iterdir()) and not overwrite:
        msg = (
            f"{target} already holds files. Choose another --out folder, "
            "or pass --overwrite if you mean to replace this run."
        )
        raise RunFileError(msg)
    responses_dir = target / RESPONSES_DIR
    if responses_dir.exists():
        shutil.rmtree(responses_dir)
    responses_dir.mkdir(parents=True)

    records: list[QueryRecord] = []
    for run in loaded.runs:
        response_file: str | None = None
        if run.response is not None:
            response_file = f"{RESPONSES_DIR}/{run.query.id}.json"
            (target / response_file).write_text(
                run.response.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        failure = None
        if run.failure is not None:
            failure = FailureRecord(
                code=run.failure.code, message=run.failure.message, kind=run.failure.kind
            )
        records.append(
            QueryRecord(
                query=run.query,
                response_file=response_file,
                failure=failure,
                wall_ms=run.wall_ms,
                duration_ms=run.duration_ms,
                duration_source=run.duration_source,
                link_checks=loaded.links.get(run.query.id, []),
            )
        )
    record = RunRecord(meta=loaded.meta, queries=records)
    (target / RUN_FILE).write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def load_run(directory: Path | str) -> LoadedRun:
    """Read a run saved by ``save_run``. Raises ``RunFileError`` with a plain message."""
    source = Path(directory)
    run_file = source / RUN_FILE
    try:
        record = RunRecord.model_validate(json.loads(run_file.read_text(encoding="utf-8")))
    except OSError as exc:
        msg = f"No saved run was found in {source} (missing {RUN_FILE}). Check the folder."
        raise RunFileError(msg, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        msg = f"{run_file} could not be read as a saved run. Run the harness again."
        raise RunFileError(msg, detail=str(exc)) from exc
    if record.format != RUN_FORMAT:
        msg = f"{run_file} has format {record.format}, but this harness reads format {RUN_FORMAT}."
        raise RunFileError(msg)

    runs: list[QueryRun] = []
    links: dict[str, list[LinkCheck]] = {}
    for item in record.queries:
        response: SearchResponse | None = None
        if item.response_file is not None:
            path = source / item.response_file
            try:
                response = SearchResponse.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as exc:
                msg = f"The saved response {path} could not be read. Run the harness again."
                raise RunFileError(msg, detail=str(exc)) from exc
        failure = None
        if item.failure is not None:
            failure = PipelineFailure(item.failure.code, item.failure.message, item.failure.kind)
        runs.append(
            QueryRun(
                query=item.query,
                response=response,
                failure=failure,
                wall_ms=item.wall_ms,
                duration_ms=item.duration_ms,
                duration_source=item.duration_source,
            )
        )
        if item.link_checks:
            links[item.query.id] = list(item.link_checks)
    return LoadedRun(record.meta, runs, links)
