"""Human approval queue for destructive tool calls.

The MCP agent can still call a destructive tool, but the server does not execute
it until a human approves the exact call locally via the CLI. Approvals are
one-time, short-lived and bound to a hash of the tool, action and arguments.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional, Sequence

from .config import Config, _default_path
from .secure_files import file_lock, restrict_to_owner, write_private

DEFAULT_TTL_SECONDS = 900
_STATUSES = ("pending", "approved", "denied", "used")


class ApprovalError(ValueError):
    """A request cannot be approved or consumed."""


def approval_root(config: Config) -> Path:
    configured = getattr(config, "approval_dir", None) or os.environ.get("MCP_APPROVAL_DIR")
    if configured:
        root = Path(configured).expanduser()
    else:
        # The default is the per-user credentials folder that also holds the token:
        # it does not depend on the working directory, and the container reaches it
        # through the credentials mount.
        root = Path(_default_path(".google", "approvals"))
    return root.resolve()


KEY_FILE_NAME = "approval.key"
_SIGNED_FIELDS = (
    "id",
    "tool",
    "action",
    "arguments_hash",
    "created_at",
    "expires_at",
    "status",
    "approved_at",
    "denied_at",
    "used_at",
    "secret_hash",
)


def _load_or_create_key(root: Path) -> bytes:
    """Per-install HMAC key used to seal approval records against tampering."""
    path = root / KEY_FILE_NAME
    if path.exists():
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(32)
    write_private(path, key.hex() + "\n")
    return key


def _seal(key: bytes, record: Dict[str, Any]) -> str:
    signed = {field: record.get(field) for field in _SIGNED_FIELDS}
    if "review" in record:
        signed["review"] = record["review"]
        signed["summary"] = record.get("summary")
    message = json.dumps(
        signed,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def arguments_hash(
    tool: str, action: Optional[str], arguments: Dict[str, Any], *,
    review: Optional[Dict[str, Any]] = None, snapshot_digest: Optional[str] = None,
) -> str:
    """Bind an approval to the exact call, excluding approval/confirm fields."""
    clean = {
        key: value
        for key, value in arguments.items()
        if key not in ("approval_id", "confirm")
    }
    data = {"tool": tool, "action": action, "arguments": clean}
    if review is not None:
        data["review"] = review
    if snapshot_digest is not None:
        data["snapshot_digest"] = snapshot_digest
    payload = json.dumps(
        data,
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
    if not re.fullmatch(r"apr_[A-Za-z0-9_-]{1,64}", approval_id):
        raise ApprovalError(f"Unknown approval id '{approval_id}'.")
    return root / f"{approval_id}.json"


def _write(root: Path, data: Dict[str, Any], key: bytes) -> None:
    new_root = not root.exists()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if new_root:
        restrict_to_owner(root)
    data = dict(data)
    data["seal"] = _seal(key, data)
    write_private(
        _record_path(root, data["id"]),
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _read(root: Path, approval_id: str, key: bytes) -> Dict[str, Any]:
    path = _record_path(root, approval_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ApprovalError(f"Unknown approval id '{approval_id}'.") from None
    except (OSError, ValueError) as exc:
        raise ApprovalError(f"Cannot read approval '{approval_id}': {exc}") from None
    # A record edited outside the server (status, expiry, arguments) fails here.
    if (
        not isinstance(record, dict) or record.get("id") != approval_id
        or not hmac.compare_digest(str(record.get("seal", "")).encode("utf-8"), _seal(key, record).encode("ascii"))
    ):
        raise ApprovalError(f"Approval '{approval_id}' failed its integrity check.")
    return record


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
        self._key: Optional[bytes] = None

    @contextmanager
    def _locked(self) -> Iterator[None]:
        # The browser, MCP profiles and operator CLI may have separate stores.
        try:
            try:
                self.root.mkdir(mode=0o700, parents=True)
            except FileExistsError:
                pass
            else:
                restrict_to_owner(self.root)
            with file_lock(self.root / "queue"):
                yield
        except OSError as exc:
            raise ApprovalError("The approval store is unavailable.") from exc

    @property
    def key(self) -> bytes:
        if self._key is None:
            self._key = _load_or_create_key(self.root)
        return self._key

    def _read(self, approval_id: str) -> Dict[str, Any]:
        return _read(self.root, approval_id, self.key)

    def _write(self, record: Dict[str, Any]) -> None:
        _write(self.root, record, self.key)

    def _iter_records(self) -> list[Dict[str, Any]]:
        """Records with a valid seal only; tampered files are silently ignored."""
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("apr_*.json"):
            try:
                record = _read(self.root, path.stem, self.key)
            except ApprovalError:
                continue
            records.append(record)
        return sorted(records, key=lambda item: item.get("created_at", ""))

    def request(
        self,
        tool: str,
        action: Optional[str],
        arguments: Dict[str, Any],
        *, review: Optional[Dict[str, Any]] = None, snapshot_digest: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return an existing pending request or create a new one.

        No human secret is created here: the link secret is issued only when a
        human asks for the link (``human_link``), so the agent never holds it.
        """
        digest = arguments_hash(tool, action, arguments, review=review, snapshot_digest=snapshot_digest)
        with self._locked():
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
            if review is not None:
                record["review"] = review
                # Agent-facing status stays compact; the full list is operator-only.
                verb = {"move": "Move", "upload": "Upload", "trash": "Delete"}.get(
                    str(review.get("operation")), "Review"
                )
                noun = "item(s)" if review.get("operation") == "trash" else "file(s)"
                record["summary"] = f"{verb} {len(review['items'])} {noun}"
            self._write(record)
            return record

    def get(self, approval_id: str) -> Dict[str, Any]:
        return self._read(approval_id)

    def verify_secret(self, approval_id: str, candidate: Optional[str]) -> bool:
        """Constant-time check of the human-only secret (stored as a hash)."""
        try:
            record = self._read(approval_id)
        except ApprovalError:
            return False
        if not candidate or _expired(record):
            return False
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        expected = record.get("secret_hash")
        return (
            bool(expected and hmac.compare_digest(str(expected), digest))
            or hmac.compare_digest(candidate.encode("utf-8"), self._browser_secret(record))
        )

    def _browser_secret(self, record: Dict[str, Any]) -> bytes:
        # A separate purpose from the record seal; the helper needs read-only
        # access to the queue and doesn't rotate a link while a page is open.
        payload = f"browser-v1:{record['id']}:{record['arguments_hash']}:{record['expires_at']}"
        return hmac.new(self.key, payload.encode("utf-8"), hashlib.sha256).hexdigest().encode("ascii")

    def browser_link(self, record: Dict[str, Any], base_url: str) -> str:
        secret = self._browser_secret(record).decode("ascii")
        return f"{base_url.rstrip('/')}/approvals/{record['id']}?k={secret}"

    def rotate_secret(self, approval_id: str) -> str:
        """Issue a fresh human secret for a pending approval (invalidates the old link)."""
        with self._locked():
            record = self._read(approval_id)
            if record.get("status") != "pending":
                raise ApprovalError(
                    f"Approval '{approval_id}' is {record.get('status')}, not pending."
                )
            secret = secrets.token_urlsafe(24)
            record["secret_hash"] = hashlib.sha256(secret.encode("utf-8")).hexdigest()
            self._write(record)
            return secret

    def human_link(self, approval_id: str, base_url: Optional[str]) -> Optional[str]:
        """Browser link for the human. Rotates the secret, so the old link dies."""
        base = (base_url or "").rstrip("/")
        if not base:
            return None
        secret = self.rotate_secret(approval_id)
        return f"{base}/approvals/{approval_id}?k={secret}"

    def list_pending(self) -> list[Dict[str, Any]]:
        return [
            record
            for record in self._iter_records()
            if record.get("status") == "pending" and not _expired(record)
        ]

    def list_all(self) -> list[Dict[str, Any]]:
        return self._iter_records()

    def approve(self, approval_id: str, actor: str = "cli") -> Dict[str, Any]:
        with self._locked():
            record = self._read(approval_id)
            if record.get("status") != "pending":
                raise ApprovalError(
                    f"Approval '{approval_id}' is {record.get('status')}, not pending."
                )
            if _expired(record):
                raise ApprovalError(f"Approval '{approval_id}' has expired.")
            record["status"] = "approved"
            record["approved_at"] = _iso(_now())
            record["approved_by"] = actor
            self._write(record)
            return record

    def deny(self, approval_id: str, actor: str = "cli") -> Dict[str, Any]:
        with self._locked():
            record = self._read(approval_id)
            if record.get("status") != "pending":
                raise ApprovalError(
                    f"Approval '{approval_id}' is {record.get('status')}, not pending."
                )
            record["status"] = "denied"
            record["denied_at"] = _iso(_now())
            record["denied_by"] = actor
            self._write(record)
            return record

    def consume(
        self,
        approval_id: str,
        tool: str,
        action: Optional[str],
        arguments: Dict[str, Any],
        *, review: Optional[Dict[str, Any]] = None, snapshot_digest: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Validate and mark one approval as used. Returns (ok, reason)."""
        digest = arguments_hash(tool, action, arguments, review=review, snapshot_digest=snapshot_digest)
        with self._locked():
            try:
                record = self._read(approval_id)
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
            self._write(record)
            return True, ""


def challenge_text(record: Dict[str, Any], approve_url: str | None = None) -> str:
    """Text returned to the agent. ``approve_url`` must not contain the secret."""
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
    # The agent is told that a human must decide, and nothing about how. No CLI
    # commands, no links, no secret: the decision happens on the operator's side.
    return (
        "⚠️ APPROVAL REQUIRED — the action has NOT run.\n\n"
        f"{payload}\n\n"
        "A human operator must review and decide this request. Tell the user that "
        "an approval is pending and what it is for. Do not attempt to approve it "
        "yourself. When the user confirms it is approved, repeat the same tool call "
        "with this `approval_id`; if it was denied or has expired, do not retry."
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
