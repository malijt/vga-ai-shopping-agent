"""The labelling sheet: export it blank, import it filled, compute good@10 (plan 11.3.2).

The harness scores everything it can by itself. The one thing only a person can judge is whether
a product is a "good match" (``rubric.md``). The sheet is a CSV with one row per result in the
top 10 of each garment group, with everything the person needs to judge it::

    query_id, photo, group, rank, title, price, store, price_range, url, label

``photo`` is the file name of the query's photo (empty for a text-only query), so the person knows
which photo to open; the file is in ``eval/data/assets/private/``. ``group`` is the garment: an
outfit photo has one block of rows per garment (assumption A20). ``price_range`` is the range the
app showed the product in (Budget, Mid-range, Premium or Luxury); price is not part of the label.
The rows of a group are in rank order, best match first.

``label`` is left blank on export. The person fills it with ``1`` (good) or ``0`` (not good),
nothing else. On import every row is checked against the run that produced the sheet: a label
for a result that is not in this run's top 10, a different URL at that rank (a sheet from another
run), a blank label, or any value but ``1`` and ``0`` is an error that names the row. Every
problem is reported together, so one pass through the sheet fixes them all.

``good@10`` counts the ``1`` labels in a group's top 10 out of 10. A group with fewer than 10
results has fewer rows; the missing places count as "not good" (``rubric.md``, step 4), which is
why the denominator stays 10.

Titles and store names come from store pages and are untrusted. A spreadsheet would run a cell
that starts with ``=``, ``+``, ``-`` or ``@`` as a formula, so the export prefixes such a cell
with an apostrophe. The import never reads the title back, so labels are unaffected.
"""

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from eval.harness.errors import LabelSheetError
from eval.harness.groups import TOP_N, format_price, group_names, price_range_labels, top_results
from eval.harness.runner import QueryRun

LABEL_COLUMNS = (
    "query_id",
    "photo",
    "group",
    "rank",
    "title",
    "price",
    "store",
    "price_range",
    "url",
    "label",
)
_MAX_ERRORS_SHOWN = 15
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class LabelRow:
    query_id: str
    group: str
    rank: int
    title: str
    store: str
    url: str
    photo: str = ""
    """File name of the query's photo; empty for a text-only query."""
    price: str = ""
    """The price as the shopper sees it, for example ``349 AED``."""
    price_range: str = ""
    label: int | None = None


@dataclass(frozen=True)
class GroupGood:
    """good@10 for one garment group."""

    group: str
    good: int
    """Results in the top 10 labelled ``1``."""
    rows: int
    """Results that are in the top 10 (fewer than 10 when the group has fewer results)."""
    top_n: int = TOP_N

    @property
    def cell(self) -> str:
        return f"{self.good}/{self.top_n}"


@dataclass(frozen=True)
class LabelSet:
    """The labels of a whole run, checked against that run."""

    rows: tuple[LabelRow, ...]

    def for_group(self, query_id: str, group: str) -> list[LabelRow]:
        return [row for row in self.rows if row.query_id == query_id and row.group == group]


def label_rows(runs: Sequence[QueryRun]) -> list[LabelRow]:
    """The blank rows of the sheet: the top 10 of every group of every answered query."""
    rows: list[LabelRow] = []
    for run in runs:
        if run.response is None:
            continue
        photo = PurePosixPath(run.query.image).name if run.query.image else ""
        for name, group in zip(group_names(run.response), run.response.groups, strict=True):
            ranges = price_range_labels(group)
            for rank, scored in enumerate(top_results(group), start=1):
                product = scored.product
                rows.append(
                    LabelRow(
                        query_id=run.query.id,
                        group=name,
                        rank=rank,
                        title=product.title,
                        store=product.store,
                        url=product.product_url,
                        photo=photo,
                        price=format_price(product),
                        price_range=ranges.get(product.key, ""),
                    )
                )
    return rows


def _safe_cell(value: str) -> str:
    one_line = " ".join(value.split())
    return f"'{one_line}" if one_line.startswith(_FORMULA_STARTS) else one_line


def export_label_sheet(runs: Sequence[QueryRun], path: Path | str) -> int:
    """Write the blank sheet and return the number of rows. UTF-8 with a byte-order mark, so
    Excel shows Arabic titles correctly; the import reads it with or without."""
    rows = label_rows(runs)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(LABEL_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.query_id,
                    row.photo,
                    row.group,
                    row.rank,
                    _safe_cell(row.title),
                    row.price,
                    _safe_cell(row.store),
                    row.price_range,
                    row.url,
                    "",
                ]
            )
    return len(rows)


def _summarise(errors: list[str]) -> str:
    shown = errors[:_MAX_ERRORS_SHOWN]
    more = len(errors) - len(shown)
    lines = [f"- {error}" for error in shown]
    if more > 0:
        lines.append(f"- ... and {more} more")
    return "\n".join(lines)


def _check_record(
    record: dict[str | None, str | list[str] | None],
    line: int,
    expected: dict[tuple[str, str, int], LabelRow],
    answered: set[tuple[str, str, int]],
) -> tuple[LabelRow | None, str | None]:
    """Check one sheet row. Returns the labelled row, or the problem with it."""
    if None in record:
        return None, f"row {line}: has more columns than the header"

    def cell(name: str) -> str:
        value = record.get(name)
        return value.strip() if isinstance(value, str) else ""

    where = f"{cell('query_id')}, {cell('group')}, rank {cell('rank')}"
    try:
        rank = int(cell("rank"))
    except ValueError:
        return None, f"row {line} ({where}): rank must be a whole number"
    key = (cell("query_id"), cell("group"), rank)
    row = expected.get(key)
    if row is None:
        return None, (
            f"row {line} ({where}): this run has no result there. The sheet may come from "
            "another run, or the row's query, group or rank was edited"
        )
    if cell("url") != row.url:
        return None, (
            f"row {line} ({where}): the url is not this run's result at that rank. "
            "The sheet may come from another run"
        )
    if key in answered:
        return None, f"row {line} ({where}): appears twice"
    answered.add(key)
    label = cell("label")
    if label not in {"0", "1"}:
        shown = "blank" if not label else repr(label)
        return None, f"row {line} ({where}): label must be 1 or 0, got {shown}"
    return replace(row, label=int(label)), None


def import_label_sheet(path: Path | str, runs: Sequence[QueryRun]) -> LabelSet:
    """Read a filled sheet and check it against ``runs``. Raises ``LabelSheetError`` naming every
    bad row."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"The labelling sheet {path} could not be read. Check the path."
        raise LabelSheetError(msg, detail=str(exc)) from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [(name or "").strip() for name in (reader.fieldnames or [])]
    if header != list(LABEL_COLUMNS):
        msg = (
            f"The labelling sheet must have exactly these columns, in this order: "
            f"{', '.join(LABEL_COLUMNS)}. Found: {', '.join(header) or 'none'}."
        )
        raise LabelSheetError(msg)

    expected = {(row.query_id, row.group, row.rank): row for row in label_rows(runs)}
    answered: set[tuple[str, str, int]] = set()  # rows with a line in the sheet, good or bad
    labelled: dict[tuple[str, str, int], LabelRow] = {}
    errors: list[str] = []
    for record in reader:
        row, problem = _check_record(record, reader.line_num, expected, answered)
        if problem is not None:
            errors.append(problem)
        elif row is not None:
            labelled[(row.query_id, row.group, row.rank)] = row
    errors.extend(
        f"missing row for {row.query_id}, {row.group}, rank {row.rank} "
        "(every result in the top 10 needs a label)"
        for key, row in expected.items()
        if key not in answered
    )

    if errors:
        msg = f"The labelling sheet {Path(path).name} has problems:\n{_summarise(errors)}"
        raise LabelSheetError(msg, detail=f"{len(errors)} problem(s)")
    return LabelSet(tuple(labelled[key] for key in expected))


def good_at_10(query_id: str, run: QueryRun, labels: LabelSet) -> list[GroupGood]:
    """good@10 per garment group of one query, from the imported labels."""
    if run.response is None:
        return []
    figures: list[GroupGood] = []
    for name in group_names(run.response):
        rows = labels.for_group(query_id, name)
        figures.append(GroupGood(name, sum(1 for row in rows if row.label == 1), len(rows)))
    return figures
