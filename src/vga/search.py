"""Command line for the whole search: ``python -m vga.search`` (plan 13.3.1).

::

    uv run python -m vga.search --text "black oversized blazer for men under 400 AED"
    uv run python -m vga.search --image jacket.jpg --text "same but dark brown and cheaper"
    uv run python -m vga.search --text "white sneakers" --budget 300

It runs the real pipeline (real stores, real OpenAI, the local image model when configured) and
prints the ``SearchResponse`` as JSON on standard output. Logs go to standard error and to
``<log_dir>/vga.jsonl``. The photo is read into memory for the request and never written anywhere.

When the search cannot be done, the plain message a shopper would see is printed to standard error
and the exit status is 1 (2 for a mistake in the command line). Nothing else is printed there, so
no stack trace and no internals.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from vga.errors import GENERIC_USER_MESSAGE, InvalidInputError, VgaError
from vga.log import configure_logging, get_logger
from vga.models import (
    DEFAULT_CURRENCY,
    Budget,
    RunOverrides,
    SearchRequest,
    SearchResponse,
    SettingsOverride,
)
from vga.pipeline import SearchPipeline, build_pipeline
from vga.settings import Settings, load_settings

log = get_logger(__name__)

EXIT_FAILED = 1
EXIT_USAGE = 2

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
    return parser


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
        configure_logging(level=loaded.log_level, log_dir=loaded.log_dir)
        request = _build_request(args.text, args.image)
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


def _build_request(text: str | None, image_path: str | None) -> SearchRequest:
    photo: bytes | None = None
    if image_path is not None:
        try:
            photo = Path(image_path).read_bytes()
        except OSError as exc:
            raise InvalidInputError(
                f"We couldn't open the photo file {Path(image_path).name!r}. "
                "Check the path, or describe the item with --text.",
                detail=f"cannot read {image_path}: {type(exc).__name__}",
            ) from exc
    try:
        return SearchRequest(text=text, image=photo)
    except ValidationError as exc:
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
