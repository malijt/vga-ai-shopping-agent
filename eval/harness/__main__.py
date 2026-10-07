"""Entry point: ``uv run python -m eval.harness``."""

import sys

from eval.harness.cli import main

if __name__ == "__main__":
    sys.exit(main())
