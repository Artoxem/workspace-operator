"""Turn a bulk selector into a concrete, capped list of Drive items.

The selector is resolved exactly once. The plan then owns the snapshot, so a
concurrent upload or delete cannot change what the user reviewed.
"""

from __future__ import annotations

import fnmatch
import html
import logging
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import BulkError
from .move import FILE_FIELDS, FOLDER_MIME, read_folder

ITEM_FIELDS = "id,name,parents,size,mimeType,trashed"
MOVE_ITEM_FIELDS = f"{FILE_FIELDS},size"
MAX_FOLDERS = 500


def escape_query(value: str) -> str:
    """Escape a literal for a Drive query string."""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def build_query(selector: Dict[str, Any]) -> str:
    """Build the provider query from selector fields (folder scope excluded)."""
    parts: List[str] = []
    if not selector.get("include_trashed"):
        parts.append("trashed = false")

    query = selector.get("query")
    if isinstance(query, str) and query.strip():
        parts.append(f"({query.strip()})")

    mime_types = [str(item) for item in selector.get("mime_types") or [] if str(item).strip()]
    if mime_types:
        clauses = " or ".join(f"mimeType = '{escape_query(item)}'" for item in mime_types)
        parts.append(f"({clauses})")

    name_contains = selector.get("name_contains")
    if isinstance(name_contains, str) and name_contains.strip():
        parts.append(f"name contains '{escape_query(name_contains.strip())}'")

    modified = selector.get("modified") or {}
    if isinstance(modified, dict):
        after = modified.get("after")
        before = modified.get("before")
        if isinstance(after, str) and after.strip():
            parts.append(f"modifiedTime > '{escape_query(after.strip())}'")
        if isinstance(before, str) and before.strip():
            parts.append(f"modifiedTime < '{escape_query(before.strip())}'")

    if not parts:
        return ""
    return " and ".join(parts)


def _item_from(meta: Dict[str, Any], for_move: bool = False) -> Dict[str, Any]:
    size = meta.get("size")
    try:
        size_int = int(size) if size is not None else 0
    except (TypeError, ValueError):
        size_int = 0
    item = {
        "id": meta.get("id", ""),
        "name": meta.get("name", ""),
        "parents": meta.get("parents") if for_move else list(meta.get("parents") or []),
        "size": size_int,
        "mimeType": meta.get("mimeType", ""),
        "trashed": bool(meta.get("trashed", False)),
    }
    if for_move:
        item.update(driveId=meta.get("driveId"), capabilities=meta.get("capabilities"))
    return item


def _is_protected(item: Dict[str, Any], protected_ids: Set[str], patterns: Sequence[str]) -> bool:
    if item["id"] in protected_ids:
        return True
    name = item.get("name", "").casefold()
    return any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in patterns)


def _folder_tree(service, root_id: str, logger: logging.Logger, *, strict=False, **drive_scope) -> List[str]:
    """Breadth-first list of a folder and its descendants, capped."""
    seen = {root_id}
    queue = [root_id]
    while queue and len(seen) < MAX_FOLDERS:
        current = queue.pop(0)
        token = None
        while len(seen) < MAX_FOLDERS:
            response = (
                service.files()
                .list(
                    q=(
                        f"'{escape_query(current)}' in parents and "
                        f"mimeType = '{FOLDER_MIME}' and trashed = false"
                    ),
                    fields="nextPageToken,incompleteSearch,files(id)",
                    pageSize=1000,
                    pageToken=token,
                    **drive_scope,
                )
                .execute()
            )
            if strict and response.get("incompleteSearch"):
                raise BulkError("Drive returned incomplete folder results; narrow the move selector")
            for entry in response.get("files", []):
                folder_id = entry.get("id")
                if folder_id and folder_id not in seen:
                    seen.add(folder_id)
                    queue.append(folder_id)
            token = response.get("nextPageToken")
            if not token:
                break
    if len(seen) >= MAX_FOLDERS:
        if strict:
            raise BulkError("recursive move selector reached the folder cap; narrow the move selector")
        logger.warning("bulk selector: folder tree capped at %s folders", MAX_FOLDERS)
    return list(seen)


def resolve_drive(
    creds,
    selector: Dict[str, Any],
    max_items: int,
    allow_shared_drives: bool,
    protected_ids: Optional[Iterable[str]] = None,
    protected_patterns: Optional[Sequence[str]] = None,
    logger: Optional[logging.Logger] = None,
    for_move: bool = False,
) -> Dict[str, Any]:
    """Resolve a Drive selector into a capped item snapshot."""
    logger = logger or logging.getLogger(__name__)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    protected = {str(value) for value in (protected_ids or []) if str(value).strip()}
    patterns = [str(value) for value in (protected_patterns or []) if str(value).strip()]
    exclude_ids = {str(value) for value in selector.get("exclude_ids") or [] if str(value).strip()}

    items: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    warnings: List[str] = []
    missing = 0
    protected_skipped = 0
    truncated = False

    def keep(item: Dict[str, Any]) -> None:
        nonlocal protected_skipped
        if item["id"] in seen or item["id"] in exclude_ids:
            return
        if not selector.get("include_trashed") and item["trashed"]:
            return
        if _is_protected(item, protected, patterns):
            protected_skipped += 1
            return
        seen.add(item["id"])
        items.append(item)

    item_fields = MOVE_ITEM_FIELDS if for_move else ITEM_FIELDS
    explicit = [str(value) for value in selector.get("ids") or [] if str(value).strip()]
    if explicit:
        if for_move:
            explicit = [file_id for file_id in dict.fromkeys(explicit) if file_id not in exclude_ids]
        for file_id in explicit[: max_items + 1]:
            try:
                meta = (
                    service.files()
                    .get(
                        fileId=file_id,
                        fields=item_fields,
                        supportsAllDrives=allow_shared_drives,
                    )
                    .execute()
                )
            except HttpError as exc:
                if for_move:
                    raise BulkError(f"file '{file_id}' cannot be read for the move: {exc}") from exc
                missing += 1
                logger.info("bulk selector: cannot read %s: %s", file_id, exc)
                continue
            if for_move and meta.get("id") != file_id:
                raise BulkError(f"Drive did not return the requested file '{file_id}'")
            keep(_item_from(meta, for_move))
            if len(items) > max_items:
                break
        if len(items) > max_items or (for_move and len(explicit) > max_items + 1):
            truncated = True
    else:
        base_query = build_query(selector)
        folder_id = selector.get("folder_id")
        drive_scope: dict[str, Any] = {
            "supportsAllDrives": allow_shared_drives,
            "includeItemsFromAllDrives": allow_shared_drives,
        }
        if for_move:
            file_filter = f"mimeType != '{FOLDER_MIME}'"
            base_query = f"({base_query}) and {file_filter}" if base_query else file_filter
        if isinstance(folder_id, str) and folder_id.strip():
            folder_id = folder_id.strip()
            if for_move:
                folder = read_folder(service.files(), folder_id, allow_shared_drives)
                folder_id = folder["id"]
                if folder["driveId"] is not None:
                    drive_scope.update(corpora="drive", driveId=folder["driveId"])
            folders = (
                _folder_tree(service, folder_id, logger, strict=for_move, **drive_scope)
                if selector.get("recursive")
                else [folder_id]
            )
        else:
            folders = []

        if folders:
            chunks = [folders[index : index + 40] for index in range(0, len(folders), 40)]
            queries = []
            for chunk in chunks:
                parents = " or ".join(f"'{escape_query(item)}' in parents" for item in chunk)
                if base_query:
                    queries.append(f"({parents}) and ({base_query})")
                else:
                    queries.append(f"({parents})")
        else:
            queries = [base_query or ""]

        for query in queries:
            token = None
            while True:
                list_kwargs = {
                    "fields": f"nextPageToken,incompleteSearch,files({item_fields})",
                    "pageSize": 1000,
                    "pageToken": token,
                    **drive_scope,
                }
                if query:
                    list_kwargs["q"] = query
                response = service.files().list(**list_kwargs).execute()
                if for_move and response.get("incompleteSearch"):
                    raise BulkError("Drive returned incomplete results; narrow the move selector")
                for meta in response.get("files", []):
                    keep(_item_from(meta, for_move))
                    if len(items) > max_items:
                        truncated = True
                        break
                if truncated:
                    break
                token = response.get("nextPageToken")
                if not token:
                    break
            if truncated:
                break

        if not items and not truncated and not explicit:
            warnings.append("No files matched the selector.")

    if truncated:
        items = items[:max_items]
        warnings.append(
            f"More than {max_items} files matched; the plan keeps the first {max_items}. "
            "Narrow the selector or raise the cap."
        )
    else:
        items = items[:max_items]

    if missing:
        warnings.append(f"{missing} id(s) could not be read and were skipped.")
    if protected_skipped:
        warnings.append(f"{protected_skipped} file(s) are protected and were skipped.")

    return {
        "items": items,
        "truncated": truncated,
        "warnings": warnings,
    }


GMAIL_SYSTEM_LABELS = {
    "INBOX",
    "UNREAD",
    "TRASH",
    "SPAM",
    "STARRED",
    "IMPORTANT",
    "SENT",
    "DRAFT",
}


def clean_snippet(text: str, limit: int = 200) -> str:
    """Gmail snippets carry zero-width and variation marks; keep the words."""
    kept = "".join(
        char
        for char in (text or "")
        if unicodedata.category(char) != "Cf" and not 0xFE00 <= ord(char) <= 0xFE0F
    )
    return " ".join(html.unescape(kept).split())[:limit].rstrip()


def resolve_gmail_labels(creds, names: Iterable[str], logger: logging.Logger) -> List[str]:
    """Map label names (or ids) to Gmail label ids."""
    wanted = [str(name).strip() for name in names if str(name).strip()]
    if not wanted:
        return []
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    labels = (
        service.users()
        .labels()
        .list(userId="me")
        .execute()
        .get("labels", [])
    )
    by_name = {label.get("name", "").casefold(): label.get("id") for label in labels}
    by_id = {label.get("id"): label.get("name") for label in labels}
    resolved: List[str] = []
    unknown: List[str] = []
    for name in wanted:
        upper = name.upper()
        if upper in GMAIL_SYSTEM_LABELS:
            resolved.append(upper)
            continue
        if name in by_id:
            resolved.append(name)
            continue
        match = by_name.get(name.casefold())
        if match:
            resolved.append(match)
        else:
            unknown.append(name)
    if unknown:
        raise BulkError(f"unknown Gmail label(s): {', '.join(sorted(unknown))}")
    return resolved


def resolve_gmail(
    creds,
    selector: Dict[str, Any],
    max_items: int,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Resolve a Gmail selector into a capped message-id snapshot."""
    logger = logger or logging.getLogger(__name__)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    explicit = [str(value) for value in selector.get("ids") or [] if str(value).strip()]
    exclude_ids = {
        str(value) for value in selector.get("exclude_ids") or [] if str(value).strip()
    }
    ids: List[str] = []
    seen: Set[str] = set()
    warnings: List[str] = []
    truncated = False

    def keep(message_id: str) -> None:
        if message_id in seen or message_id in exclude_ids:
            return
        seen.add(message_id)
        ids.append(message_id)

    if explicit:
        for message_id in explicit:
            keep(message_id)
            if len(ids) > max_items:
                truncated = True
                break
    else:
        query = selector.get("query")
        if not isinstance(query, str):
            query = ""
        token = None
        while True:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query.strip() or None,
                    maxResults=500,
                    pageToken=token,
                    includeSpamTrash=bool(selector.get("include_spam_trash")),
                )
                .execute()
            )
            for entry in response.get("messages", []):
                keep(entry.get("id", ""))
                if len(ids) > max_items:
                    truncated = True
                    break
            if truncated:
                break
            token = response.get("nextPageToken")
            if not token:
                break
        if not ids:
            warnings.append("No messages matched the selector.")

    if truncated:
        ids = ids[:max_items]
        warnings.append(
            f"More than {max_items} messages matched; the plan keeps the first {max_items}."
        )
    else:
        ids = ids[:max_items]

    sample = []
    for message_id in ids[:5]:
        try:
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
                header.get("name", ""): header.get("value", "")
                for header in message.get("payload", {}).get("headers", [])
            }
            sample.append(
                {
                    "id": message_id,
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "snippet": clean_snippet(message.get("snippet", "")),
                }
            )
        except HttpError:
            sample.append({"id": message_id, "subject": "", "from": "", "date": "", "snippet": ""})

    items = [{"id": message_id, "name": "", "size": 0, "mimeType": "message/rfc822"} for message_id in ids]
    return {
        "items": items,
        "sample": sample,
        "truncated": truncated,
        "warnings": warnings,
    }
