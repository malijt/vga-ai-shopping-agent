"""The Markdown results report (plan 11.3.1), following ``eval/data/results-template.md``.

The sections and the column names are the template's: the field table, the results table with
``Query | Results | Stores | Seconds | Links ok | good@10 | Price ranges ok``, the verdict line, the
failures table and the notes. Between the failures and the notes the harness adds what the
template does not have room for: the fetch stage and the rank stage as separate tables (11.2.2),
and a per-step and per-store timing summary. The shopper-facing words apply here too: "price
range", never "tier".

Everything that came from a store (titles, URLs, reasons) is untrusted text. It is escaped before
it goes into a table cell, so a title cannot add columns, break a row or inject markup.
"""

import re
from collections import Counter

from eval.harness.criteria import (
    CriteriaConfig,
    Criterion,
    QueryEvaluation,
    Status,
    failure_rows,
)
from eval.harness.runstore import LoadedRun
from eval.harness.scoring import ScoredRun
from eval.harness.stages import (
    fetch_rows,
    format_dropped,
    rank_rows,
    step_summaries,
    store_summaries,
)
from vga.models import InputType, MixPreset

RESULT_COLUMNS = (
    "Query",
    "Results",
    "Stores",
    "Seconds",
    "Links ok",
    "good@10",
    "Price ranges ok",
)
FAILURE_COLUMNS = (
    "Query",
    "Criterion failed",
    "Cause (store / ranking / LLM / price range)",
    "Evidence",
)
FIELD_ROWS = (
    "Date",
    "Run",
    "Model snapshot",
    "Prompt version",
    "Stores working",
    "Price-range mix",
)

_MARKDOWN_SPECIALS = re.compile(r"([\\`*\[\]<>|])")


def escape(text: str) -> str:
    """Make untrusted text safe inside a Markdown table cell: one line, no markup."""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", " ".join(text.split()))


def _table(header: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines.extend("| " + " | ".join(cells) + " |" for cells in rows)
    return lines


def _mix_label(mix: list[int]) -> str:
    for preset in MixPreset:
        if list(preset.mix.as_tuple()) == mix:
            return preset.value.replace("_", " ")
    return "custom"


def _run_label(loaded: LoadedRun) -> str:
    meta = loaded.meta
    number = f"{meta.number} " if meta.number is not None else ""
    if meta.mode == "mock":
        return f"{number}mock (FakePipeline's canned response; not a real run)"
    if meta.mode == "replay":
        what = f"replay of {escape(meta.source or 'a recording')}"
        return f"{number}({what})" if number else what
    return f"{number}(live, recorded)" if number else "live, recorded"


def _fields(loaded: LoadedRun) -> list[list[str]]:
    responses = loaded.responses
    models = sorted({response.understood.model for response in responses})
    prompts = sorted({response.understood.prompt_version for response in responses})
    working = sorted({report.store_id for r in responses for report in r.stores_used})
    skipped = sorted(
        {report.store_id for r in responses for report in r.stores_skipped} - set(working)
    )
    stores = f"{len(working)}: {', '.join(working)}" if working else "0"
    if skipped:
        stores += f" (never worked: {', '.join(skipped)})"
    mix = loaded.meta.price_range_mix
    values = [
        loaded.meta.date.isoformat(),
        _run_label(loaded),
        escape(", ".join(models) or "unknown"),
        escape(", ".join(prompts) or "unknown"),
        escape(stores),
        f"{' / '.join(str(share) for share in mix)} ({_mix_label(mix)})",
    ]
    return [[name, value] for name, value in zip(FIELD_ROWS, values, strict=True)]


def _results_rows(scored: ScoredRun) -> list[list[str]]:
    return [
        [evaluation.query_id, *(escape(result.cell) for result in evaluation.criteria)]
        for evaluation in scored.evaluations
    ]


def _verdict_lines(scored: ScoredRun) -> list[str]:
    verdict = scored.verdict
    total = verdict.total
    lines = [
        "A query passes only if every column meets the pass rule. "
        f"**Overall verdict:** {verdict.headline}. "
        f"The demo passes if at least {verdict.required} of {total} pass "
        "(the rule in `rubric.md`).",
        "",
    ]
    if verdict.status is Status.PENDING:
        lines.append(
            f"Verdict: PENDING (not final: {len(verdict.pending)} of {total} queries are still "
            f"undecided ({_pending_reasons(scored.evaluations)}); {len(verdict.failed)} have "
            f"failed so far, and the demo can still reach {verdict.required})"
        )
    else:
        lines.append(f"Verdict: {verdict.label}")
    return lines


def _pending_reasons(evaluations: tuple[QueryEvaluation, ...]) -> str:
    counts: Counter[Criterion] = Counter()
    for evaluation in evaluations:
        for result in evaluation.criteria:
            if result.status is Status.PENDING:
                counts[result.criterion] += 1
    parts = [f"{criterion.value} for {count}" for criterion, count in counts.items()]
    return "; ".join(parts) or "nothing"


def _failures(scored: ScoredRun) -> list[str]:
    rows = [
        [
            row.query_id,
            row.criterion.value,
            row.cause.value,
            escape(row.evidence),
        ]
        for row in failure_rows(scored.evaluations)
    ]
    return _table(FAILURE_COLUMNS, rows or [["none", "", "", ""]])


def _fetch_stage(scored: ScoredRun) -> list[str]:
    runs = scored.loaded.runs
    detail = [
        [
            row.query_id,
            escape(row.store_id),
            row.status.value,
            str(row.valid_products),
            escape(row.strategy or "-"),
            escape(format_dropped(row.dropped)),
            "yes" if row.from_cache else "no",
            f"{row.duration_ms:.0f}",
        ]
        for row in fetch_rows(runs)
    ]
    header = (
        "Query",
        "Store",
        "Status",
        "Valid products",
        "Strategy",
        "Dropped records (reason: count)",
        "Cache hit",
        "ms",
    )
    return _table(header, detail or [["none", "", "", "", "", "", "", ""]])


def _rank_stage(scored: ScoredRun) -> list[str]:
    rows = [
        [row.query_id, escape(row.group), str(row.results), escape(row.good), row.reaches_bar]
        for row in rank_rows(scored.evaluations, scored.config)
    ]
    header = (
        "Query",
        "Garment group",
        "Results in group",
        "good@10",
        f"Reaches {scored.config.min_good}",
    )
    return _table(header, rows or [["none", "", "", "", ""]])


def _warm_up_lines(scored: ScoredRun) -> list[str]:
    """The warm-up, apart from the queries: loading the image model is not part of any search."""
    warm_up = scored.loaded.meta.warm_up
    if warm_up is None:
        return []
    state = "ready" if warm_up.ready else "NOT available (photo queries ranked on text and price)"
    return [
        f"Warm-up before the first query: {warm_up.duration_ms / 1000:.1f} s; image scoring "
        f"{state}. This time is not inside any query's seconds above: the 30 s limit is for a "
        "search on an app that is already running.",
        "",
    ]


def _timings(scored: ScoredRun) -> list[str]:
    runs = scored.loaded.runs
    steps = [
        [escape(s.step), str(s.runs), f"{s.mean_ms / 1000:.2f}", f"{s.max_ms / 1000:.2f}"]
        for s in step_summaries(runs)
    ]
    stores = [
        [
            escape(s.store_id),
            f"{s.queries_ok}/{s.queries_total}",
            str(s.valid_products),
            escape(", ".join(s.strategies) or "-"),
            escape(format_dropped(s.dropped)),
            str(s.cache_hits),
            f"{s.mean_ms / 1000:.2f}",
            f"{s.max_ms / 1000:.2f}",
        ]
        for s in store_summaries(runs)
    ]
    lines = _warm_up_lines(scored)
    lines += ["Per step, across all queries (seconds):", ""]
    lines += _table(("Step", "Runs", "Mean s", "Max s"), steps or [["none", "", "", ""]])
    lines += ["", "Per store, across all queries:", ""]
    lines += _table(
        (
            "Store",
            "Queries ok",
            "Valid products",
            "Strategies",
            "Dropped records (reason: count)",
            "Cache hits",
            "Mean s",
            "Max s",
        ),
        stores or [["none", "", "", "", "", "", "", ""]],
    )
    return lines


def _notes(scored: ScoredRun) -> list[str]:
    loaded, meta = scored.loaded, scored.loaded.meta
    outfit_ids = [r.query.id for r in loaded.runs if r.query.type is InputType.OUTFIT_PHOTO]
    config: CriteriaConfig = scored.config
    notes: list[str] = []
    if meta.mode == "mock":
        notes.append(
            "Mock run: every query received the same canned response from `FakePipeline`, and "
            "links were answered by a mock. Nothing here measures the real app."
        )
    if meta.mode == "replay":
        notes.append(
            "Replay: the real pipeline ran again on a recording, with no network call and no "
            "OpenAI call. Seconds are the recorded live figures, not the replay's own."
        )
    if outfit_ids:
        notes.append(
            f"Outfit photos ({', '.join(outfit_ids)}): the price-range check and good@10 are "
            "applied per garment group, and the Results cell shows one figure per garment. The "
            f"{config.min_results}-result floor is applied to the total over all garments, because "
            "an outfit returns 12 results per garment (assumption A2); each garment must also "
            "have at least one result. The query counts as its lowest good@10."
        )
    notes.append(
        "Price-range targets are read from each response, so a query whose request changes the "
        'mix (for example "cheaper" without a budget, assumption A7) is judged against its own '
        "targets."
    )
    notes.append(_link_note(scored))
    notes.append(
        "good@10 comes from the labelling sheet you imported."
        if scored.labelled
        else "good@10 is not labelled yet: fill `labels.csv` using `rubric.md`, then run the "
        "harness again with `--rescore <this folder> --labels labels.csv`."
    )
    notes.extend(escape(note) for note in meta.notes)
    notes.append(
        "Changes since the previous run (model, prompt version, store set, settings) and any "
        "change to the queries or rubric, with the reason: add by hand."
    )
    return [f"- {note}" for note in notes]


def _link_note(scored: ScoredRun) -> str:
    mode = scored.loaded.meta.links.value
    base = (
        'Links ok covers points 1 to 3 of "A working link" in `rubric.md` (opens, on the '
        "store's own host, a product page). Point 4, that the page shows the same product as "
        "the card, is checked by the person labelling."
    )
    if mode == "none":
        return base + " Links were not checked in this run."
    if mode == "top10":
        return base + (
            " This run checked the top 10 of each garment group only (`--links top10`); a "
            "query's links stay undecided until every result is checked (`--links all`)."
        )
    return base + " This run checked every result (`--links all`)."


def render_report(scored: ScoredRun) -> str:
    """The whole report as Markdown text."""
    loaded = scored.loaded
    config = scored.config
    number = loaded.meta.number if loaded.meta.number is not None else loaded.meta.mode
    lines: list[str] = [f"# Acceptance results: run {number}", ""]
    if loaded.meta.mode == "mock":
        lines += ["> Mock run: a canned response, not a real result.", ""]
    elif loaded.meta.mode == "replay":
        lines += ["> Replay of a recording: no live data was fetched in this run.", ""]
    lines += _table(("Field", "Value"), _fields(loaded))
    lines += [
        "",
        "## Results",
        "",
        f"Pass rule (PRD): at least {config.min_results} results, from at least "
        f"{config.min_stores} stores, {config.max_seconds:g} s or less, all links open the "
        "right product page, at "
        f"least {config.min_good} of the top {config.top_n} good, and each price range within "
        f'{config.price_range_tolerance} result of its target count or flagged "few options".',
        "",
    ]
    lines += _table(RESULT_COLUMNS, _results_rows(scored))
    lines += [""]
    lines += _verdict_lines(scored)
    lines += ["", "## Failures", "", *_failures(scored)]
    lines += ["", "## Fetch stage", "", "What each store returned, per query.", ""]
    lines += _fetch_stage(scored)
    lines += ["", "## Rank stage", "", "How well the ranked results match, per garment group.", ""]
    lines += _rank_stage(scored)
    lines += ["", "## Timings", "", *_timings(scored)]
    lines += ["", "## Notes", "", *_notes(scored)]
    return "\n".join(lines) + "\n"
