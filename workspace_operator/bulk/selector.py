"""Turn a bulk selector into a concrete, capped list of Drive items.

The selector is resolved exactly once. The plan then owns the snapshot, so a
concurrent upload or delete cannot change what the user reviewed.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import BulkError

FOLDER_MIME = "application/vnd.google-apps.folder"
ITEM_FIELDS = "id,name,parents,size,mimeType,trashed"
LIST_FIELDS = f"nextPageToken, files({ITEM_FIELDS})"
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


def _item_from(meta: Dict[str, Any]) -> Dict[str, Any]:
    size = meta.get("size")
    try:
        size_int = int(size) if size is not None else 0
    except (TypeError, ValueError):
        size_int = 0
    return {
        "id": meta.get("id", ""),
        "name": meta.get("name", ""),
        "parents": list(meta.get("parents") or []),
        "size": size_int,
        "mimeType": meta.get("mimeType", ""),
        "trashed": bool(meta.get("trashed", False)),
    }


def _is_protected(item: Dict[str, Any], protected_ids: Set[str], patterns: Sequence[str]) -> bool:
    if item["id"] in protected_ids:
        return True
    name = item.get("name", "").casefold()
    return any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in patterns)


def _folder_tree(service, root_id: str, logger: logging.Logger) -> List[str]:
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
                    fields="nextPageToken, files(id)",
                    pageSize=1000,
                    pageToken=token,
                )
                .execute()
            )
            for entry in response.get("files", []):
                folder_id = entry.get("id")
                if folder_id and folder_id not in seen:
                    seen.add(folder_id)
                    queue.append(folder_id)
            token = response.get("nextPageToken")
            if not token:
                break
    if len(seen) >= MAX_FOLDERS:
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

    explicit = [str(value) for value in selector.get("ids") or [] if str(value).strip()]
    if explicit:
        for file_id in explicit[: max_items + 1]:
            try:
                meta = (
                    service.files()
                    .get(
                        fileId=file_id,
                        fields=ITEM_FIELDS,
                        supportsAllDrives=allow_shared_drives,
                    )
                    .execute()
                )
            except HttpError as exc:
                missing += 1
                logger.info("bulk selector: cannot read %s: %s", file_id, exc)
                continue
            keep(_item_from(meta))
            if len(items) > max_items:
                break
        if len(items) > max_items:
            truncated = True
    else:
        base_query = build_query(selector)
        folder_id = selector.get("folder_id")
        if isinstance(folder_id, str) and folder_id.strip():
            folders = (
                _folder_tree(service, folder_id.strip(), logger)
                if selector.get("recursive")
                else [folder_id.strip()]
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
            queries = [base_query or None]

        for query in queries:
            token = None
            while True:
                list_kwargs = {
                    "fields": LIST_FIELDS,
                    "pageSize": 1000,
                    "pageToken": token,
                    "supportsAllDrives": allow_shared_drives,
                    "includeItemsFromAllDrives": allow_shared_drives,
                }
                if query:
                    list_kwargs["q"] = query
                response = service.files().list(**list_kwargs).execute()
                for meta in response.get("files", []):
                    keep(_item_from(meta))
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
