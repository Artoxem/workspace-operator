"""Resolve and validate the Drive context of a reviewed file move."""

from __future__ import annotations

from googleapiclient.errors import HttpError

from .models import BulkError, Plan

FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,parents,trashed,driveId,capabilities(canMoveItemWithinDrive)"
FOLDER_FIELDS = "id,name,mimeType,trashed,driveId,capabilities(canAddChildren)"


def drive_id(metadata):
    """Drive v3 omits driveId for My Drive items."""
    value = metadata.get("driveId")
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise BulkError("Drive returned an invalid Shared drive ID")
    return value


def _capability(metadata, name, *, shared):
    capabilities = metadata.get("capabilities") or {}
    value = capabilities.get(name) if isinstance(capabilities, dict) else None
    return value is True or (value is None and not shared)


def _label(metadata):
    if not isinstance(metadata, dict) or any(
        not isinstance(metadata.get(key), str) or not metadata[key].strip()
        for key in ("id", "name")
    ):
        raise BulkError("Drive did not provide a complete item or folder name and ID")
    return {key: metadata[key] for key in ("id", "name")}


def read_folder(files, folder_id, allow_shared, *, destination=False):
    role = "target" if destination else "source"
    try:
        folder = files.get(
            fileId=folder_id, fields=FOLDER_FIELDS, supportsAllDrives=allow_shared
        ).execute()
    except HttpError as exc:
        raise BulkError(f"{role} folder '{folder_id}' cannot be read: {exc}") from exc
    label = _label(folder)
    if folder.get("mimeType") != FOLDER_MIME or folder.get("trashed"):
        raise BulkError(f"{role} '{folder_id}' must be an active Drive folder")
    if folder_id != "root" and label["id"] != folder_id:
        raise BulkError(f"{role} folder ID did not match the requested folder")
    shared_drive = drive_id(folder)
    if shared_drive is not None and not allow_shared:
        raise BulkError("Shared drive moves require bulk_allow_shared_drives to be enabled")
    if destination and not _capability(folder, "canAddChildren", shared=shared_drive is not None):
        raise BulkError(f"Drive does not allow adding files to target folder '{label['name']}'")
    return {**label, "driveId": shared_drive}


def source_parents(metadata):
    parents = metadata.get("parents")
    if not isinstance(parents, list) or not parents or any(
        not isinstance(parent, str) or not parent.strip() for parent in parents
    ) or len(set(parents)) != len(parents):
        raise BulkError("cannot verify every source parent folder for this file")
    return parents


def check_item(item, destination, allow_shared):
    _label(item)
    if not item.get("mimeType") or item.get("mimeType") == FOLDER_MIME or item.get("trashed"):
        raise BulkError("bulk move only supports active files, not folders")
    drive = drive_id(item)
    if (drive is not None or drive_id(destination) is not None) and not allow_shared:
        raise BulkError("Shared drive moves require bulk_allow_shared_drives to be enabled")
    if drive != drive_id(destination):
        raise BulkError("bulk move does not support moves between different Drive locations")
    if not _capability(item, "canMoveItemWithinDrive", shared=drive is not None):
        raise BulkError(f"Drive does not allow moving file '{item['name']}' within its drive")
    parents = source_parents(item)
    if drive is not None and len(parents) != 1:
        raise BulkError("Shared drive files must have exactly one source parent folder")
    return parents


def snapshot(files, target, items, allow_shared):
    """Capture the target and each distinct source folder from live metadata."""
    destination = read_folder(files, target, allow_shared, destination=True)
    folders = {destination["id"]: destination}
    reviewed = []
    for item in items:
        parents = check_item(item, destination, allow_shared)
        sources = []
        for parent in parents:
            if parent not in folders:
                folders[parent] = read_folder(files, parent, allow_shared)
            folder = folders[parent]
            if drive_id(folder) != drive_id(item):
                raise BulkError("source folder is not in the same drive as its file")
            sources.append(_label(folder))
        reviewed.append({**item, "driveId": drive_id(item), "sources": sources})
    return destination, reviewed


def move_review(plan: Plan):
    """Return the complete human review, exclusively from the stored snapshot."""
    if (plan.domain, plan.action) != ("drive", "move"):
        raise BulkError("not a Drive move plan")
    try:
        destination = plan.options.get("move_destination")
        destination_label = _label(destination)
        if not isinstance(destination, dict) or "driveId" not in destination or plan.options.get("target_folder_id") != destination["id"]:
            raise BulkError("destination does not match the move snapshot")
        items = []
        seen = set()
        for item in plan.items:
            label = _label(item)
            if item["id"] in seen or "driveId" not in item:
                raise BulkError("incomplete move item metadata")
            parents = check_item(item, destination, allow_shared=True)
            sources = [_label(folder) for folder in item["sources"]]
            if [source["id"] for source in sources] != parents:
                raise BulkError("source folders do not match the move snapshot")
            items.append({**label, "sources": sources})
            seen.add(item["id"])
        if not items:
            raise BulkError("the move plan is empty")
    except (BulkError, KeyError, TypeError, AttributeError) as exc:
        raise BulkError(f"move plan has no valid complete review; run bulk_plan again: {exc}") from exc
    if destination["driveId"]:
        destination_label["drive_id"] = destination["driveId"]
    review = {"operation": "move", "destination": destination_label, "items": items}
    if plan.warnings:
        review["warnings"] = plan.warnings
    return review


def apply(files, item, options, allow_shared):
    """Recheck the approved context immediately before one update attempt."""
    expected = options.get("move_destination")
    if not isinstance(expected, dict) or not expected.get("id") or expected["id"] != options.get("target_folder_id"):
        raise BulkError("move needs a reviewed destination snapshot")
    parents = check_item(item, expected, allow_shared)
    target = expected["id"]
    destination = read_folder(files, target, allow_shared, destination=True)
    if destination != expected:
        raise BulkError("destination folder changed after planning; create a fresh move plan")

    file_id = item["id"]
    request = files.get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=allow_shared)
    # Drive v3 does not expose an etag property. Use the HTTP precondition if
    # the provider returns an ETag on the metadata read.
    response_headers = {}
    add_callback = getattr(request, "add_response_callback", None)
    if add_callback is not None:
        add_callback(response_headers.update)
    current = request.execute()
    if not isinstance(current, dict) or current.get("id") != file_id:
        raise BulkError("Drive did not return the requested file")
    try:
        current_parents = source_parents(current)
    except BulkError as exc:
        raise BulkError("source parent folders changed or cannot be verified; create a fresh move plan") from exc
    if set(current_parents) != set(parents):
        raise BulkError("source parent folders changed after planning; create a fresh move plan")
    if current.get("name") != item["name"] or current.get("mimeType") != item["mimeType"]:
        raise BulkError("file metadata changed after planning; create a fresh move plan")
    check_item(current, destination, allow_shared)

    record = {"id": file_id, "name": item["name"]}
    if target in parents:
        return {**record, "status": "skipped"}
    update = files.update(
        fileId=file_id,
        addParents=target,
        removeParents=",".join(parents),
        supportsAllDrives=allow_shared,
        fields="id,parents",
    )
    etag = response_headers.get("etag") or response_headers.get("ETag")
    if etag:
        update.headers["If-Match"] = etag
    update.execute()
    return {**record, "previous_parents": list(parents), "status": "ok"}
