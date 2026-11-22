"""Human review for every bulk action, not only Drive moves.

The page needs to show what a plan will touch. Drive moves get a richer review
from :mod:`workspace_operator.bulk.move`; the other actions use this module.
Gmail plans keep subjects only for a small sample, so their review says how many
messages in total the plan covers.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import BulkError, Plan

TRASH = {"id": "trash", "name": "Trash · recoverable 30 days"}
GMAIL_TRASH = {"id": "trash", "name": "Gmail Trash · recoverable 30 days"}
GMAIL_ARCHIVE = {"id": "archive", "name": "Archive · Inbox label removed"}
GMAIL_INBOX = {"id": "inbox", "name": "Inbox"}
GMAIL_FLAGS = {"id": "flags", "name": "Read state"}
ORIGINAL_LOCATION = {"id": "restore", "name": "Original location"}
IN_PLACE = {"id": "in-place", "name": "Changed in place"}

_GMAIL_DESTINATIONS = {
    "trash": GMAIL_TRASH,
    "archive": GMAIL_ARCHIVE,
    "restore": GMAIL_INBOX,
    "mark_read": GMAIL_FLAGS,
    "mark_unread": GMAIL_FLAGS,
}

_DRIVE_DESTINATIONS = {
    "trash": TRASH,
    "restore": ORIGINAL_LOCATION,
    "rename": IN_PLACE,
    "share": IN_PLACE,
    "revoke_public": IN_PLACE,
}


def _label_destination(plan: Plan) -> Dict[str, str]:
    add = plan.options.get("add_labels") or []
    remove = plan.options.get("remove_labels") or []
    parts = []
    if add:
        parts.append("+" + ", ".join(str(name) for name in add))
    if remove:
        parts.append("−" + ", ".join(str(name) for name in remove))
    return {"id": "labels", "name": "Labels " + " ".join(parts) if parts else "Labels"}


def _describe_selector(plan: Plan) -> str:
    selector = plan.selector or {}
    pieces: List[str] = []
    query = selector.get("query")
    if isinstance(query, str) and query.strip():
        pieces.append(f"query: {query.strip()}")
    ids = selector.get("ids") or []
    if ids:
        pieces.append(f"{len(ids)} explicit id(s)")
    if selector.get("folder_id"):
        pieces.append(f"folder: {selector['folder_id']}")
    if selector.get("include_spam_trash"):
        pieces.append("including spam and trash")
    return "; ".join(pieces)


def _gmail_review(plan: Plan) -> Dict[str, Any]:
    sample = getattr(plan, "sample", None) or []
    items = [
        {
            "id": entry.get("id", ""),
            "name": entry.get("subject") or "(no subject)",
            "snippet": (entry.get("snippet") or "")[:140],
            "sources": [{"id": "gmail", "name": entry.get("from") or "unknown sender"}],
            "mime_type": "message/rfc822",
        }
        for entry in sample
    ]
    destination = _label_destination(plan) if plan.action == "label" else _GMAIL_DESTINATIONS[plan.action]
    review: Dict[str, Any] = {
        "operation": plan.action,
        "destination": destination,
        "items": items,
        "total": len(plan.items),
        "sampled": True,
    }
    described = _describe_selector(plan)
    if described:
        review["note"] = f"matched by {described}"
    if plan.warnings:
        review["warnings"] = plan.warnings
    return review


def _item_review(plan: Plan, destination: Dict[str, str]) -> Dict[str, Any]:
    items = [
        {
            "id": item.get("id", ""),
            "name": item.get("name") or "(unnamed)",
            "sources": [{"id": "drive", "name": "Drive"}],
            "mime_type": item.get("mimeType"),
            "size": item.get("size"),
        }
        for item in plan.items
    ]
    review: Dict[str, Any] = {"operation": plan.action, "destination": destination, "items": items}
    if plan.warnings:
        review["warnings"] = plan.warnings
    return review


def review_for(plan: Plan) -> Dict[str, Any]:
    """Return the review dict for a plan; raises :class:`BulkError` when unclear."""
    if plan.domain == "gmail":
        if plan.action not in _GMAIL_DESTINATIONS and plan.action != "label":
            raise BulkError(f"no review for Gmail action '{plan.action}'")
        if not plan.items:
            raise BulkError("the plan is empty")
        return _gmail_review(plan)
    if plan.domain == "drive":
        if plan.action not in _DRIVE_DESTINATIONS:
            raise BulkError(f"no review for Drive action '{plan.action}'")
        if not plan.items:
            raise BulkError("the plan is empty")
        return _item_review(plan, _DRIVE_DESTINATIONS[plan.action])
    if not plan.items:
        raise BulkError("the plan is empty")
    return _item_review(plan, IN_PLACE)
