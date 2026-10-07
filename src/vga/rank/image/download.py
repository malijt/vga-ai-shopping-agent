"""Setup command: download the pinned FashionSigLIP weights ahead of time (plan 8.1.4).

    uv sync --group ml
    uv run --group ml python -m vga.rank.image.download

Downloads the snapshot named by ``siglip_revision`` in ``config/settings.yaml`` (about 816 MB) into
the default Hugging Face cache (``~/.cache/huggingface``, or ``HF_HOME``). It is safe to run
twice: files already in the cache are not fetched again, and a second run only reports where the
weights are. The ranker never downloads inside a request; without these weights it returns no
image scores and the search ranks by text and price only.
"""

import argparse
import sys
from collections.abc import Sequence

from vga.errors import ConfigError
from vga.rank.image.model import (
    DOWNLOAD_COMMAND,
    MODEL_REPO,
    ImageModelUnavailableError,
    resolve_snapshot,
)
from vga.settings import load_settings

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_SETTINGS = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m vga.rank.image.download",
        description=(
            f"Download the pinned {MODEL_REPO} weights (about 816 MB) into the Hugging Face cache. "
            "Safe to run twice."
        ),
    )
    parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"error: {exc.detail or exc}", file=sys.stderr)
        return EXIT_BAD_SETTINGS
    revision = settings.siglip_revision
    if not revision:
        print(
            "error: siglip_revision is not set in config/settings.yaml; "
            "refusing to download an unpinned model",
            file=sys.stderr,
        )
        return EXIT_BAD_SETTINGS

    try:
        folder = resolve_snapshot(revision, download=False)
    except ImageModelUnavailableError:
        pass  # not cached yet (or the packages are missing, which the download step reports)
    else:
        print(f"The weights for {MODEL_REPO}@{revision} are already downloaded: {folder}")
        return EXIT_OK

    print(f"Downloading {MODEL_REPO}@{revision} (about 816 MB); this can take several minutes ...")
    try:
        folder = resolve_snapshot(revision, download=True)
    except ImageModelUnavailableError as exc:
        print(f"error: {exc.detail or exc}", file=sys.stderr)
        print(f"Fix the problem above and run `{DOWNLOAD_COMMAND}` again.", file=sys.stderr)
        return EXIT_FAILED
    print(f"Done. The weights are in {folder}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
