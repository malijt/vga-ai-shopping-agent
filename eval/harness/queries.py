"""Load and validate the frozen acceptance queries (plan 11.1.1).

``eval/data/queries.yaml`` holds the 10 inputs. Each entry has ``id``, ``type``, ``text``,
``image`` and ``notes``, and may have ``shopper_gender`` (the header of that file is the contract).
This module rejects anything else with a message that names the query and the field, so a typo in
a frozen file is found before a paid live run, not after.

Two sets are read by this module. ``queries.yaml`` is the frozen acceptance set: it must have the
PRD mix and its result decides the demo. Any other file, such as ``extra_queries.yaml`` (the 11
extra photos), is an *extra set*: it has no required mix, its results are reported beside the
acceptance table, and it never counts towards the pass rule (``query_set_of`` tells them apart).

A photo is only needed for a live run. ``require_images=False`` (used by ``--mock`` and
``--replay``) skips the existence check, because the five private photos are supplied by the user
and are not in the repository (see ``eval/data/ASSETS.md``).
"""

from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from eval.harness.errors import MissingImageError, QueryFileError
from vga.models import Gender, InputType, VgaModel
from vga.settings import PROJECT_ROOT

QUERIES_PATH = PROJECT_ROOT / "eval" / "data" / "queries.yaml"
EXTRA_QUERIES_PATH = PROJECT_ROOT / "eval" / "data" / "extra_queries.yaml"
ASSETS_PREFIX = "eval/data/assets/"
"""Every image path starts here (relative to the repository root)."""
ASSETS_GUIDE = "eval/data/ASSETS.md"

EXPECTED_MIX: dict[InputType, int] = {
    InputType.PRODUCT_PHOTO: 3,
    InputType.OUTFIT_PHOTO: 2,
    InputType.TEXT: 3,
    InputType.PHOTO_TEXT: 2,
}
"""The mix the PRD "Acceptance test (10 queries)" requires."""

QuerySet = Literal["acceptance", "extra"]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_ID_RE = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class AcceptanceQuery(VgaModel):
    """One acceptance query, exactly as ``queries.yaml`` describes it."""

    id: str = Field(pattern=_ID_RE)
    type: InputType
    text: str | None
    image: str | None
    shopper_gender: Gender | None = None
    """What the shopper answers if the app asks "Who is this for?": ``women`` or ``men``. The app
    asks when a garment's gender was not stated in the request (BRD Rule 8: a gender the model only
    guessed is shown, not applied, until the shopper confirms it). Absent means the shopper gives no
    answer, which is what "Show both" comes to; the harness then never applies a guessed gender."""
    notes: str = Field(min_length=1)

    @field_validator("shopper_gender")
    @classmethod
    def _answer_is_women_or_men(cls, value: Gender | None) -> Gender | None:
        if value is Gender.UNISEX:
            msg = "shopper_gender must be 'women' or 'men'; leave it out for 'show both'"
            raise ValueError(msg)
        return value

    @field_validator("text")
    @classmethod
    def _text_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            msg = "text must be null (no text) or the shopper's words, not an empty string"
            raise ValueError(msg)
        return value

    @field_validator("image")
    @classmethod
    def _image_path_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            msg = (
                f"image must be a path relative to the repository root without '..', got {value!r}"
            )
            raise ValueError(msg)
        if not value.startswith(ASSETS_PREFIX):
            msg = f"image must be under {ASSETS_PREFIX}, got {value!r}"
            raise ValueError(msg)
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            msg = f"image must be one of {', '.join(_IMAGE_SUFFIXES)}, got {value!r}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _type_matches_inputs(self) -> Self:
        has_text, has_image = self.text is not None, self.image is not None
        expected = {
            InputType.PRODUCT_PHOTO: (False, True),
            InputType.OUTFIT_PHOTO: (False, True),
            InputType.TEXT: (True, False),
            InputType.PHOTO_TEXT: (True, True),
        }[self.type]
        if (has_text, has_image) != expected:
            wants_text = "text" if expected[0] else "text: null"
            wants_image = "an image" if expected[1] else "image: null"
            msg = f"type {self.type.value!r} needs {wants_text} and {wants_image}"
            raise ValueError(msg)
        return self


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "entry"
        message = str(error["msg"]).removeprefix("Value error, ")
        parts.append(f"field '{field}': {message}")
    return "; ".join(parts)


def _describe(index: int, raw: Any) -> str:
    query_id = raw.get("id") if isinstance(raw, dict) else None
    return f"query #{index}" + (f" ({query_id})" if isinstance(query_id, str) else "")


def parse_queries(
    raw: Any, *, source: str = "queries.yaml", check_mix: bool = True
) -> list[AcceptanceQuery]:
    """Validate already-parsed YAML. Raises ``QueryFileError`` naming every problem found."""
    if not isinstance(raw, dict) or set(raw) != {"queries"}:
        msg = f"{source} must hold one top-level key, 'queries', with a list of queries"
        raise QueryFileError(msg, detail=f"top level was {type(raw).__name__}")
    entries = raw["queries"]
    if not isinstance(entries, list) or not entries:
        msg = f"{source}: 'queries' must be a non-empty list"
        raise QueryFileError(msg)

    problems: list[str] = []
    queries: list[AcceptanceQuery] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            problems.append(f"{_describe(index, entry)}: must be a mapping of fields")
            continue
        try:
            queries.append(AcceptanceQuery.model_validate(entry))
        except ValidationError as exc:
            problems.append(f"{_describe(index, entry)}: {_format_validation_error(exc)}")

    duplicates = sorted(qid for qid, n in Counter(q.id for q in queries).items() if n > 1)
    if duplicates:
        problems.append(f"query ids must be unique; repeated: {', '.join(duplicates)}")

    if check_mix and not problems:
        counts = Counter(q.type for q in queries)
        if dict(counts) != EXPECTED_MIX:
            found = ", ".join(f"{kind.value} {counts.get(kind, 0)}" for kind in EXPECTED_MIX)
            wanted = ", ".join(f"{kind.value} {n}" for kind, n in EXPECTED_MIX.items())
            problems.append(f"the mix must be {wanted} (PRD acceptance test); found {found}")

    if problems:
        raise QueryFileError(f"{source} is not valid:\n- " + "\n- ".join(problems))
    return queries


def query_set_of(path: Path | str) -> QuerySet:
    """``acceptance`` for the frozen ``queries.yaml`` and nothing else, ``extra`` for any other
    file. Deciding by the file, not by what it holds, means a copy of the acceptance queries with
    a typo cannot pass itself off as the acceptance run."""
    return "acceptance" if Path(path).resolve() == QUERIES_PATH.resolve() else "extra"


def image_path(query: AcceptanceQuery, repo_root: Path = PROJECT_ROOT) -> Path | None:
    """The photo's location on disk, or ``None`` for a text-only query."""
    return None if query.image is None else repo_root / query.image


def _missing_images_error(missing: Sequence[tuple[str, list[str]]]) -> MissingImageError:
    lines = [f"- {path} (used by {', '.join(ids)})" for path, ids in missing]
    message = (
        "Missing photo file(s) for the acceptance queries:\n"
        + "\n".join(lines)
        + f"\nThese photos are private and not in the repository. See {ASSETS_GUIDE} for what "
        "each file must show and where to save it. `--mock` and `--replay` run without them."
    )
    return MissingImageError(message, detail=f"missing: {[path for path, _ in missing]}")


def check_images_exist(queries: Sequence[AcceptanceQuery], repo_root: Path = PROJECT_ROOT) -> None:
    """Raise ``MissingImageError`` listing each absent photo once, with the queries using it."""
    users: dict[str, list[str]] = {}
    for query in queries:
        path = image_path(query, repo_root)
        if path is not None and not path.is_file():
            users.setdefault(str(query.image), []).append(query.id)
    if users:
        raise _missing_images_error(sorted(users.items()))


def load_queries(
    path: Path | str = QUERIES_PATH,
    *,
    repo_root: Path = PROJECT_ROOT,
    require_images: bool = True,
    check_mix: bool = True,
) -> list[AcceptanceQuery]:
    """Read and validate the acceptance queries.

    ``require_images`` makes a missing photo an error (live runs). ``check_mix`` insists on the
    PRD mix of 3 product photos, 2 outfit photos, 3 text and 2 photo + text queries.
    """
    file = Path(path)
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"The query file {file} could not be read. Check the path."
        raise QueryFileError(msg, detail=str(exc)) from exc
    except yaml.YAMLError as exc:
        msg = f"The query file {file} is not valid YAML. Fix it and run again."
        raise QueryFileError(msg, detail=str(exc)) from exc
    queries = parse_queries(raw, source=file.name, check_mix=check_mix)
    if require_images:
        check_images_exist(queries, repo_root)
    return queries


def read_query_image(query: AcceptanceQuery, repo_root: Path = PROJECT_ROOT) -> bytes | None:
    """The photo's bytes for a live run, or ``None`` for a text-only query."""
    path = image_path(query, repo_root)
    if path is None:
        return None
    if not path.is_file():
        raise _missing_images_error([(str(query.image), [query.id])])
    return path.read_bytes()
