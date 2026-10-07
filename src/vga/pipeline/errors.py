"""Errors only the pipeline raises. They are ``VgaError``s: a plain message, a code for the logs."""

from vga.errors import VgaError
from vga.pipeline.messages import REQUEST_TIMED_OUT


class RequestTimeoutError(VgaError):
    """The 30 s request deadline passed before the request was even understood, so there is
    nothing to show. Once the request is understood the pipeline returns what it has instead."""

    default_code = "request_timeout"
    default_message = REQUEST_TIMED_OUT
