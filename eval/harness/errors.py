"""Errors the acceptance harness raises on purpose.

They extend ``VgaError`` so the command line prints one plain ``user_message`` and exits with a
non-zero status, with no stack trace. The harness is a developer tool, but it follows the same
rule as the app: say what went wrong and what to do next.
"""

from vga.errors import VgaError


class HarnessError(VgaError):
    """Base class: the harness cannot continue, and the message says why."""

    default_code = "harness"
    default_message = "The acceptance harness could not continue."


class QueryFileError(HarnessError):
    """``queries.yaml`` is malformed, or a query does not follow its contract."""

    default_code = "query_file"


class MissingImageError(QueryFileError):
    """A query points to a photo that is not on disk."""

    default_code = "missing_image"


class RecordingError(HarnessError):
    """A recording is missing, unreadable, or was made by a different version of the harness."""

    default_code = "recording"


class RecordingMismatchError(RecordingError):
    """The pipeline asked a replayed boundary for something the recording does not hold."""

    default_code = "recording_mismatch"


class RunFileError(HarnessError):
    """A saved run (``run.json`` and its responses) is missing or unreadable."""

    default_code = "run_file"


class LabelSheetError(HarnessError):
    """The labelling sheet does not follow the format, or does not match this run."""

    default_code = "label_sheet"


class WiringError(HarnessError):
    """The live wiring (real pipeline, stores, link fetch) is missing or unusable."""

    default_code = "wiring"
