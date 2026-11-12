"""Shared types for the bulk engine.

A bulk change is a two-step protocol:

1. :func:`workspace_operator.bulk.service.plan_bulk` resolves a selector into an
   immutable snapshot and stores it as a *plan*.
2. :func:`workspace_operator.bulk.service.run_bulk` executes that snapshot as a
   background *job*, with progress, cancellation and a result artifact.

This module only holds the small dataclasses that cross module boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DOMAINS = ("drive", "gmail", "docs", "slides", "sheets")
DRIVE_ACTIONS = ("move", "trash", "restore", "rename", "share", "revoke_public")
GMAIL_ACTIONS = (
    "archive",
    "label",
    "trash",
    "restore",
    "mark_read",
    "mark_unread",
)
DOCS_ACTIONS = ("replace_text",)
SLIDES_ACTIONS = ("replace_text",)
SHEETS_ACTIONS = ("find_replace",)
ACTIONS = DRIVE_ACTIONS + GMAIL_ACTIONS + DOCS_ACTIONS + SLIDES_ACTIONS + SHEETS_ACTIONS
DESTRUCTIVE_ACTIONS = ("trash", "revoke_public")

DOMAIN_MIME = {
    "docs": "application/vnd.google-apps.document",
    "slides": "application/vnd.google-apps.presentation",
    "sheets": "application/vnd.google-apps.spreadsheet",
}


class BulkError(ValueError):
    """Raised when a plan or run request is invalid."""


@dataclass
class Plan:
    """An immutable snapshot of the objects a bulk action will touch."""

    id: str
    domain: str
    action: str
    options: Dict[str, Any]
    selector: Dict[str, Any]
    created_at: str
    expires_at: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "action": self.action,
            "options": self.options,
            "selector": self.selector,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "items": self.items,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        return cls(
            id=data["id"],
            domain=data["domain"],
            action=data["action"],
            options=data.get("options") or {},
            selector=data.get("selector") or {},
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            items=data.get("items") or [],
            warnings=data.get("warnings") or [],
        )


@dataclass
class Job:
    """A running or finished bulk execution."""

    id: str
    plan_id: str
    domain: str
    action: str
    state: str = "running"
    total: int = 0
    done: int = 0
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    started_at: str = ""
    updated_at: str = ""
    finished_at: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "domain": self.domain,
            "action": self.action,
            "state": self.state,
            "total": self.total,
            "done": self.done,
            "ok": self.ok,
            "skipped": self.skipped,
            "failed": self.failed,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "result_file": self.result_file,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        return cls(
            id=data["id"],
            plan_id=data.get("plan_id", ""),
            domain=data.get("domain", "drive"),
            action=data.get("action", ""),
            state=data.get("state", "running"),
            total=int(data.get("total") or 0),
            done=int(data.get("done") or 0),
            ok=int(data.get("ok") or 0),
            skipped=int(data.get("skipped") or 0),
            failed=int(data.get("failed") or 0),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            finished_at=data.get("finished_at"),
            result_file=data.get("result_file"),
            error=data.get("error"),
        )

    def summary(self) -> Dict[str, Any]:
        """Compact progress payload; never includes per-item data."""
        return {
            "job_id": self.id,
            "plan_id": self.plan_id,
            "action": self.action,
            "state": self.state,
            "total": self.total,
            "done": self.done,
            "succeeded": self.ok,
            "skipped": self.skipped,
            "failed": self.failed,
            "percent": round((self.done / self.total) * 100, 1) if self.total else 0.0,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "result_file": self.result_file,
            "error": self.error,
        }
