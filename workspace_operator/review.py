"""Reviews for destructive single-target actions.

Move and upload already show what will happen. Deletion used to show only an id,
so the operator could not see the name, its location, or that a folder takes its
children with it. These helpers build the same review dict the approval page
already renders.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .config import Config
from .google_clients import api_client

FOLDER_MIME = "application/vnd.google-apps.folder"
TRASH_DESTINATION = {"id": "trash", "name": "Trash · recoverable 30 days"}
_CHILD_LIMIT = 1000


def _parent_entries(files, parents: List[str]) -> List[Dict[str, str]]:
    entries = []
    for parent_id in parents:
        try:
            parent = files.get(fileId=parent_id, fields="id,name").execute()
            entries.append({"id": parent.get("id", parent_id), "name": parent.get("name", parent_id)})
        except Exception:  # noqa: BLE001 - a missing parent must not block the review
            entries.append({"id": parent_id, "name": parent_id})
    return entries or [{"id": "root", "name": "My Drive"}]


def drive_trash_review(config: Config, file_id: str) -> Dict[str, Any]:
    """Describe what ``drive_trash`` will move to Trash, children included."""
    files = api_client(config, "drive", "v3").files()
    meta = files.get(
        fileId=file_id,
        fields="id,name,mimeType,size,parents,trashed",
    ).execute()
    if not meta.get("id"):
        raise ValueError("Drive did not return the requested file")
    if meta.get("trashed"):
        raise ValueError(f"'{meta.get('name')}' is already in Trash")
    item: Dict[str, Any] = {
        "id": meta["id"],
        "name": meta.get("name") or meta["id"],
        "mime_type": meta.get("mimeType"),
        "size": meta.get("size"),
        "sources": _parent_entries(files, meta.get("parents") or []),
    }
    if meta.get("mimeType") == FOLDER_MIME:
        children = files.list(
            q=f"'{meta['id']}' in parents and trashed = false",
            fields="files(id,name,mimeType),nextPageToken",
            pageSize=_CHILD_LIMIT,
        ).execute()
        found = children.get("files") or []
        item["children"] = len(found)
        item["children_sample"] = [child.get("name") for child in found[:10]]
        if children.get("nextPageToken"):
            item["children_at_least"] = True
    return {"operation": "trash", "destination": TRASH_DESTINATION, "items": [item]}


def gmail_trash_review(config: Config, message_id: str) -> Dict[str, Any]:
    """Describe the message that will move to Gmail Trash."""
    service = api_client(config, "gmail", "v1")
    message = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        )
        .execute()
    )
    headers = {
        header.get("name", "").lower(): header.get("value", "")
        for header in (message.get("payload") or {}).get("headers") or []
    }
    subject = headers.get("subject") or "(no subject)"
    sender = headers.get("from") or "unknown sender"
    item = {
        "id": message.get("id", message_id),
        "name": subject,
        "sources": [{"id": "inbox", "name": sender}],
        "mime_type": "message/rfc822",
    }
    if message.get("internalDate"):
        item["date_ms"] = message["internalDate"]
    return {"operation": "trash", "destination": TRASH_DESTINATION, "items": [item]}


def prepare_review(config: Config, legacy_name: str, arguments: Dict[str, Any], logger: logging.Logger):
    """Return ``(review, digest)`` for a deletion route, or ``(None, None)``.

    ``digest`` stays ``None``: the approved arguments already pin the exact id.
    """
    if legacy_name == "drive_delete_file" and arguments.get("file_id"):
        return drive_trash_review(config, str(arguments["file_id"])), None
    if legacy_name == "delete_email" and arguments.get("message_id"):
        return gmail_trash_review(config, str(arguments["message_id"])), None
    return None, None
