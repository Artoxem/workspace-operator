"""Runtime concerns: retry, dry-run and audit logging.

These are deliberately separate from handlers:

* ``call_with_retry`` retries transient Google API failures (429/5xx) with an
  exponential backoff, so a single rate-limit does not fail a tool call;
* ``AuditLog`` records one JSON line per tool call — tool, profile, status,
  duration and the *names* of the arguments (never the values);
* dry-run is implemented in the server: when enabled, any non-read-only tool is
  turned into a preview.

Everything here is pure Python and unit-tested.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar

T = TypeVar("T")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.4


def status_code(error: BaseException) -> Optional[int]:
    """Best-effort HTTP status extraction across googleapiclient and httplib2."""
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status

    code = getattr(error, "status_code", None)
    if isinstance(code, int):
        return code

    return None


def is_transient(error: BaseException) -> bool:
    return status_code(error) in TRANSIENT_STATUS


def call_with_retry(
    func: Callable[[], T],
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    logger: Optional[logging.Logger] = None,
) -> T:
    """Call ``func`` and retry transient failures with exponential backoff."""
    total = max(1, int(attempts))
    for attempt in range(1, total + 1):
        try:
            return func()
        except Exception as error:  # noqa: BLE001 - re-raised below
            if attempt >= total or not is_transient(error):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            if logger:
                logger.warning(
                    "Transient Google API error (status %s), retry %s/%s in %.1fs",
                    status_code(error),
                    attempt,
                    total,
                    delay,
                )
            time.sleep(delay)

    raise RuntimeError("unreachable")  # pragma: no cover


class AuditLog:
    """Append-only JSONL log of tool calls."""

    def __init__(self, path: Optional[str]):
        self.path = Path(path).expanduser() if path else None

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def record(
        self,
        tool: str,
        profile: str,
        status: str,
        duration_ms: int,
        argument_names: Iterable[str] = (),
        error: Optional[str] = None,
    ) -> None:
        if not self.path:
            return

        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "profile": profile,
            "status": status,
            "duration_ms": duration_ms,
            "arguments": sorted(argument_names),
        }
        if error:
            entry["error"] = error[:300]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}
