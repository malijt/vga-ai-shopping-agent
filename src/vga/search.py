"""Command line for the whole search: ``python -m vga.search`` (plan 13.3.1).

::

    uv run python -m vga.search --text "black oversized blazer for men under 400 AED"
    uv run python -m vga.search --image jacket.jpg --text "same but dark brown and cheaper"
    uv run python -m vga.search --text "white sneakers" --budget 300

It runs the real pipeline (real stores, real OpenAI, the local image model when configured) and
prints the ``SearchResponse`` as JSON on standard output. The structured log goes to
``<log_dir>/vga.jsonl``; ``--verbose`` also prints it to standard error. The photo is read into
memory for the request and never written anywhere.

When the search cannot be done, the plain message a shopper would see is printed to standard error
and the exit status is 1 (2 for a mistake in the command line). Without ``--verbose`` nothing else
is printed there, so no stack trace and no internals.
"""

import argparse
import asyncio
import io
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from vga.errors import GENERIC_USER_MESSAGE, InvalidInputError, VgaError
from vga.log import configure_logging, get_logger
from vga.models import (
    DEFAULT_CURRENCY,
    MAX_TEXT_CHARS,
    Budget,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    SettingsOverride,
)
from vga.pipeline import SearchPipeline, build_pipeline, messages
from vga.settings import Settings, load_settings

log = get_logger(__name__)

EXIT_FAILED = 1

PipelineBuilder = Callable[[Settings], SearchPipeline]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vga.search",
        description=(
            "Search the configured fashion stores from a photo, text, or both, and print the "
            "response as JSON. Needs OPENAI_API_KEY and openai_model (see .env.example)."
        ),
        epilog=(
            "The photo is sent to OpenAI to be understood and is not stored. "
            "Exit status: 0 done, 1 the search could not be done (the reason is printed), "
            "2 a mistake in the command line."
        ),
    )
    parser.add_argument(
        "--text",
        metavar="TEXT",
        help="what you are looking for, in English or Arabic (at most 2000 characters)",
    )
    parser.add_argument(
        "--image",
        metavar="PATH",
        help="a photo of a garment or an outfit: PNG, JPG or WebP",
    )
    parser.add_argument(
        "--budget",
        metavar="N",
        type=_positive_number,
        help="the most you want to pay; replaces a price found in the text",
    )
    parser.add_argument(
        "--currency",
        metavar="CODE",
        default=DEFAULT_CURRENCY,
        help="currency of --budget, a three-letter code (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also print the log lines to standard error (they always go to the log file)",
    )
    return parser


class _Discard(io.StringIO):
    """A text stream that throws everything away: the log handler for standard error when the
    command line is not verbose, so that only the error message shows there."""

    def write(self, text: str) -> int:
        return len(text)


def _positive_number(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not value > 0 or value == float("inf"):
        msg = f"{raw!r} is not a price above zero"
        raise argparse.ArgumentTypeError(msg)
    return value


def main(
    argv: Sequence[str] | None = None,
    *,
    build: PipelineBuilder = build_pipeline,
    settings: Settings | None = None,
) -> int:
    """Run the command line. ``build`` and ``settings`` are for tests; the defaults are real."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.text is None and args.image is None:
        parser.error("give --text, --image, or both")

    try:
        loaded = settings if settings is not None else load_settings()
        configure_logging(
            level=loaded.log_level,
            log_dir=loaded.log_dir,
            stream=sys.stderr if args.verbose else _Discard(),
        )
        request = _build_request(args.text, args.image, loaded.max_image_bytes)
        overrides = _build_overrides(args.budget, args.currency)
        response = asyncio.run(_search(build, loaded, request, overrides))
    except VgaError as error:
        print(error.user_message, file=sys.stderr)
        return EXIT_FAILED
    except Exception:  # a bug: log it, but show the shopper nothing but the generic message
        log.exception("search failed unexpectedly")
        print(GENERIC_USER_MESSAGE, file=sys.stderr)
        return EXIT_FAILED

    print(response.model_dump_json(indent=2))
    return 0


async def _search(
    build: PipelineBuilder,
    settings: Settings,
    request: SearchRequest,
    overrides: RunOverrides | None,
) -> SearchResponse:
    pipeline = build(settings)
    try:
        return await pipeline.run(request, settings, overrides)
    finally:
        await pipeline.aclose()


def _read_photo(image_path: str, max_bytes: int) -> bytes:
    """The photo file's bytes, but never more than one byte past the size limit: the pipeline
    refuses a photo over the limit, and there is no need to load a huge file to learn that."""
    try:
        with Path(image_path).open("rb") as source:
            return source.read(max_bytes + 1)
    except OSError as exc:
        raise InvalidInputError(
            f"We couldn't open the photo file {Path(image_path).name!r}. "
            "Check the path, or describe the item with --text.",
            detail=f"cannot read {image_path}: {type(exc).__name__}",
        ) from exc


def _build_request(text: str | None, image_path: str | None, max_image_bytes: int) -> SearchRequest:
    photo = _read_photo(image_path, max_image_bytes) if image_path is not None else None
    try:
        return SearchRequest(text=text, image=photo)
    except ValidationError as exc:
        if text is not None and len(text.strip()) > MAX_TEXT_CHARS:
            raise InvalidInputError(
                messages.text_too_long(MAX_TEXT_CHARS), detail="text over the limit"
            ) from exc
        raise InvalidInputError(detail=str(exc)) from exc


def _build_overrides(budget: float | None, currency: str) -> RunOverrides | None:
    if budget is None:
        return None
    try:
        parsed = Budget(max_price=budget, currency=currency)
    except ValidationError as exc:
        raise InvalidInputError(
            f"{currency!r} is not a currency code. Use three letters, for example AED.",
            detail=str(exc),
        ) from exc
    return RunOverrides(settings=SettingsOverride(budget=parsed))


if __name__ == "__main__":
    raise SystemExit(main())
