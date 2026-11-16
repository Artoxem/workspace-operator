"""Human approval queue for destructive tool calls.

The MCP agent can still call a destructive tool, but the server does not execute
it until a human approves the exact call locally via the CLI. Approvals are
one-time, short-lived and bound to a hash of the tool, action and arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from .config import Config

DEFAULT_TTL_SECONDS = 900
_STATUSES = ("pending", "approved", "denied", "used")


class ApprovalError(ValueError):
    """A request cannot be approved or consumed."""


def approval_root(config: Config) -> Path:
    configured = getattr(config, "approval_dir", None) or os.environ.get("MCP_APPROVAL_DIR")
    root = Path(configured).expanduser() if configured else Path("data") / "approvals"
    return root.resolve()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def arguments_hash(tool: str, action: Optional[str], arguments: Dict[str, Any]) -> str:
    """Bind an approval to the exact call, excluding approval/confirm fields."""
    clean = {
        key: value
        for key, value in arguments.items()
        if key not in ("approval_id", "confirm")
    }
    payload = json.dumps(
        {"tool": tool, "action": action, "arguments": clean},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize(tool: str, action: Optional[str], arguments: Dict[str, Any]) -> str:
    """A short human-readable summary without dumping mail bodies."""
    keys: Sequence[str] = (
        "plan_id",
        "job_id",
        "file_id",
        "document_id",
        "spreadsheet_id",
        "event_id",
        "message_id",
        "message_ids",
        "range",
        "name",
        "to",
        "subject",
        "domain",
        "script_id",
        "function_name",
    )
    parts = []
    for key in keys:
        if key not in arguments:
            continue
        value = arguments[key]
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value[:3])
            if len(arguments[key]) > 3:
                value += f" … (+{len(arguments[key]) - 3})"
        text = str(value).replace("\n", " ")
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(f"{key}={text}")
    if not parts:
        parts = [f"{key}=…" for key in list(arguments)[:4] if key not in ("confirm", "approval_id")]
    target = tool + (f":{action}" if action else "")
    return f"{target} ({', '.join(parts)})" if parts else target


def _record_path(root: Path, approval_id: str) -> Path:
    return root / f"{approval_id}.json"


def _write(root: Path, data: Dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = _record_path(root, data["id"])
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def _read(root: Path, approval_id: str) -> Dict[str, Any]:
    path = _record_path(root, approval_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ApprovalError(f"Unknown approval id '{approval_id}'.") from None
    except (OSError, ValueError) as exc:
        raise ApprovalError(f"Cannot read approval '{approval_id}': {exc}") from None


def _expired(record: Dict[str, Any]) -> bool:
    try:
        return _now() >= _parse(record["expires_at"])
    except (KeyError, ValueError):
        return True


class ApprovalStore:
    """Small JSON-backed approval queue, safe for one server process + CLI."""

    def __init__(self, config: Config) -> None:
        self.root = approval_root(config)
        self.ttl_seconds = max(
            30, int(getattr(config, "approval_ttl", DEFAULT_TTL_SECONDS) or DEFAULT_TTL_SECONDS)
        )
        self._lock = threading.Lock()

    def request(
        self,
        tool: str,
        action: Optional[str],
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return an existing pending request or create a new one."""
        digest = arguments_hash(tool, action, arguments)
        with self._lock:
            for record in self.list_pending():
                if (
                    record.get("tool") == tool
                    and record.get("action") == action
                    and record.get("arguments_hash") == digest
                    and not _expired(record)
                ):
                    return record
            now = _now()
            record = {
                "id": "apr_" + secrets.token_hex(8),
                "tool": tool,
                "action": action,
                "arguments_hash": digest,
                "summary": summarize(tool, action, arguments),
                "created_at": _iso(now),
                "expires_at": _iso(now + timedelta(seconds=self.ttl_seconds)),
                "status": "pending",
            }
            _write(self.root, record)
            return record

    def get(self, approval_id: str) -> Dict[str, Any]:
        return _read(self.root, approval_id)

    def list_pending(self) -> list[Dict[str, Any]]:
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("apr_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if record.get("status") == "pending" and not _expired(record):
                records.append(record)
        return sorted(records, key=lambda item: item.get("created_at", ""))

    def list_all(self) -> list[Dict[str, Any]]:
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("apr_*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda item: item.get("created_at", ""))

    def approve(self, approval_id: str, actor: str = "cli") -> Dict[str, Any]:
        with self._lock:
            record = self.get(approval_id)
            if record.get("status") != "pending":
                raise ApprovalError(
                    f"Approval '{approval_id}' is {record.get('status')}, not pending."
                )
            if _expired(record):
                raise ApprovalError(f"Approval '{approval_id}' has expired.")
            record["status"] = "approved"
            record["approved_at"] = _iso(_now())
            record["approved_by"] = actor
            _write(self.root, record)
            return record

    def deny(self, approval_id: str, actor: str = "cli") -> Dict[str, Any]:
        with self._lock:
            record = self.get(approval_id)
            if record.get("status") != "pending":
                raise ApprovalError(
                    f"Approval '{approval_id}' is {record.get('status')}, not pending."
                )
            record["status"] = "denied"
            record["denied_at"] = _iso(_now())
            record["denied_by"] = actor
            _write(self.root, record)
            return record

    def consume(
        self,
        approval_id: str,
        tool: str,
        action: Optional[str],
        arguments: Dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate and mark one approval as used. Returns (ok, reason)."""
        digest = arguments_hash(tool, action, arguments)
        with self._lock:
            try:
                record = self.get(approval_id)
            except ApprovalError as exc:
                return False, str(exc)
            if record.get("status") == "pending":
                return False, "The approval is still pending. Ask the user to approve it."
            if record.get("status") == "denied":
                return False, "The user denied this approval."
            if record.get("status") == "used":
                return False, "This approval was already used. Request a new one."
            if record.get("status") != "approved":
                return False, f"Approval status is {record.get('status')!r}."
            if _expired(record):
                return False, "The approval has expired. Request a new one."
            if record.get("tool") != tool or record.get("action") != action:
                return False, "The approval belongs to a different tool or action."
            if record.get("arguments_hash") != digest:
                return False, "The arguments changed after approval. Request a new approval."
            record["status"] = "used"
            record["used_at"] = _iso(_now())
            _write(self.root, record)
            return True, ""


def challenge_text(record: Dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "status": "approval_required",
            "approval_id": record["id"],
            "tool": record.get("tool"),
            "action": record.get("action"),
            "expires_at": record.get("expires_at"),
            "summary": record.get("summary"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        "⚠️ APPROVAL REQUIRED — the action has NOT run.\n\n"
        f"{payload}\n\n"
        "Ask the user to approve exactly this call locally:\n\n"
        f"    workspace-operator approvals approve {record['id']}\n\n"
        "Then repeat the same tool call with this `approval_id`. "
        "Do not fabricate an id: approval is one-time and bound to the arguments. "
        "If the user denies it, use `workspace-operator approvals deny "
        f"{record['id']}` and do not retry."
    )


def render_records(records: Iterable[Dict[str, Any]], *, show_status: bool = True) -> str:
    rows = []
    for record in records:
        status = record.get("status", "?")
        expired = " EXPIRED" if status == "pending" and _expired(record) else ""
        rows.append(
            f"{record.get('id')}  {status + expired:<14}  "
            f"{record.get('summary', '')}  (expires {record.get('expires_at')})"
        )
    return "\n".join(rows) if rows else "(no approvals)"
