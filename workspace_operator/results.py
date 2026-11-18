"""Tool results and tool errors.

Handlers used to report a recoverable failure by returning a string that starts
with "Error", and the router treated *any* reply starting with "Error" as a
failure — so a legitimate answer such as "Errors found: 0" was reported as an
error to the client.

Two explicit signals replace the guesswork:

* raise ToolError("...") — the message becomes the tool output, isError is set;
* return ToolResult(text, is_error=True) — same, for code that builds a result
  instead of raising.

A handler that returns a plain string keeps working: it is treated as a failure
only when it starts with the word "Error" followed by ":", whitespace or the end
of the text (the shape every legacy handler uses). "Errors found: 0" no longer
matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A legacy handler error string: "Error", "Error: ...", "Error writing file: ...".
ERROR_PREFIX = re.compile(r"^Error(?=:|\s|$)")


@dataclass(frozen=True)
class ToolResult:
    """A finished tool result. is_error is authoritative: no guessing."""

    text: str
    is_error: bool = False


class ToolError(Exception):
    """A user-facing failure: the message is shown as the tool result."""


def is_error_text(text: str) -> bool:
    """True for the legacy "Error ..." convention used by existing handlers."""
    return bool(ERROR_PREFIX.match(text.lstrip()))
