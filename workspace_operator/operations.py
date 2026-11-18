"""Staged (two-step) operations and local backups.

An Apps Script update is prepared first and executed later by a second tool call.
That state used to live in a module-level dict: it vanished on restart, was
invisible to a second process (the HTTP transport can run several profile
servers) and could not survive a container recreate.

``OperationStore`` keeps one JSON file per operation under ``operation_dir``
(default ``data/operations``). Files are written atomically with owner-only
permissions (they contain script source), carry their own expiry, and ``claim()``
removes one atomically so an operation cannot be executed twice, even by two
processes racing on the same id.
"""

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .secure_files import file_lock, restrict_to_owner, write_private

OPERATION_ID_RE = re.compile(r"^op_[0-9a-f]{8,32}$")
DEFAULT_TTL_SECONDS = 600


@dataclass
class BinaryResult:
    """Wraps binary data for tool results that produce non-text content (e.g. PDF exports)."""

    uri: str
    mime_type: str
    data: bytes
    description: str = field(default="")


def create_backup(
    data: Any, backup_type: str, identifier: str, backup_dir: str, logger
) -> str:
    """Create a backup file and return its path."""
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{backup_type}_{identifier}_{timestamp}.json"
    filepath = os.path.join(backup_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Backup created: %s", filepath)
    return filepath


def new_operation_id() -> str:
    """A fresh operation id."""
    return "op_" + uuid.uuid4().hex[:12]


def operation_root(config: Optional[Config] = None) -> Path:
    configured = getattr(config, "operation_dir", None) if config else None
    configured = configured or os.environ.get("MCP_OPERATION_DIR")
    root = Path(configured).expanduser() if configured else Path("data") / "operations"
    return root.resolve()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OperationStore:
    """One JSON file per staged operation, with expiry and atomic claim."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.root = operation_root(config)
        ttl = getattr(config, "operation_ttl", None) if config else None
        try:
            self.ttl_seconds = max(30, int(ttl or DEFAULT_TTL_SECONDS))
        except (TypeError, ValueError):
            self.ttl_seconds = DEFAULT_TTL_SECONDS

    # ---------------------------------------------------------------- helpers

    def _path(self, operation_id: str) -> Path:
        if not OPERATION_ID_RE.match(str(operation_id or "")):
            raise ValueError(f"Invalid operation id: {operation_id!r}")
        return self.root / f"{operation_id}.json"

    def _ensure_root(self) -> None:
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            restrict_to_owner(self.root)

    def _write(self, operation_id: str, record: Dict[str, Any]) -> None:
        self._ensure_root()
        write_private(
            self._path(operation_id),
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
        )

    @staticmethod
    def _expired(record: Dict[str, Any]) -> bool:
        try:
            return _now() >= datetime.fromisoformat(record["expires_at"])
        except (KeyError, TypeError, ValueError):
            return True

    def _read(self, operation_id: str) -> Optional[Dict[str, Any]]:
        try:
            record = json.loads(self._path(operation_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if self._expired(record):
            self.delete(operation_id)
            return None
        return record

    # ------------------------------------------------------------------- api

    def create(self, payload: Dict[str, Any], operation_id: Optional[str] = None) -> str:
        """Store ``payload`` and return its id (TTL starts now)."""
        self._ensure_root()
        op_id = operation_id or new_operation_id()
        now = _now()
        record = dict(payload)
        record["operation_id"] = op_id
        record["created_at"] = now.isoformat(timespec="seconds")
        record["expires_at"] = (now + timedelta(seconds=self.ttl_seconds)).isoformat(
            timespec="seconds"
        )
        self._write(op_id, record)
        return op_id

    def get(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Return a stored operation without consuming it."""
        try:
            return self._read(operation_id)
        except ValueError:
            return None

    def claim(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Atomically take an operation: the first caller gets it, others get None."""
        try:
            path = self._path(operation_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            with file_lock(path):
                record = self._read(operation_id)
                if record is None:
                    return None
                path.unlink(missing_ok=True)
                return record
        except (OSError, TimeoutError):
            return None

    def restore(self, record: Dict[str, Any]) -> str:
        """Put a claimed operation back (its execution failed); TTL restarts."""
        payload = {k: v for k, v in record.items() if k not in ("created_at", "expires_at")}
        return self.create(payload, operation_id=record.get("operation_id"))

    def delete(self, operation_id: str) -> bool:
        try:
            self._path(operation_id).unlink(missing_ok=True)
            return True
        except (OSError, ValueError):
            return False

    def cleanup(self) -> int:
        """Delete expired operations; returns how many were removed."""
        if not self.root.exists():
            return 0
        removed = 0
        for path in self.root.glob("op_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if self._expired(record):
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
        return removed

    def list_ids(self) -> List[str]:
        """Pending operation ids, oldest first."""
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("op_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not self._expired(record):
                records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""))
        return [str(record.get("operation_id", "")) for record in records]


def cleanup_expired_operations(store: Optional[Dict[str, Any]] = None, ttl_minutes: int = 10) -> int:
    """Backwards-compatible cleanup of the on-disk store."""
    del store, ttl_minutes  # the dict-era arguments are ignored
    return OperationStore().cleanup()
