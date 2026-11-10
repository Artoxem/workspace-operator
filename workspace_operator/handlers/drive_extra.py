"""Drive extras: metadata, rename, trash/restore and permission removal."""

import logging
from typing import Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import format_timestamp

FILE_FIELDS = (
    "id,name,mimeType,size,createdTime,modifiedTime,parents,webViewLink,"
    "trashed,shared,owners(displayName,emailAddress)"
)


def _drive(config: Config):
    return build("drive", "v3", credentials=get_creds(config))


def get_metadata_handler(
    config: Config, logger: logging.Logger, file_id: str
) -> str:
    try:
        if not file_id:
            return "Error: file_id is required."
        meta = _drive(config).files().get(fileId=file_id, fields=FILE_FIELDS).execute()

        owners = ", ".join(
            f"{owner.get('displayName') or '?'} <{owner.get('emailAddress') or '?'}>"
            for owner in meta.get("owners", [])
        )
        size = meta.get("size")
        lines = [
            f"Name: {meta.get('name')}",
            f"ID: {meta.get('id')}",
            f"Type: {meta.get('mimeType')}",
            f"Size: {int(size):,} bytes" if size else "Size: — (Google-native file)",
            f"Created: {format_timestamp(meta.get('createdTime'))}",
            f"Modified: {format_timestamp(meta.get('modifiedTime'))}",
            f"Owner: {owners or '—'}",
            f"Parents: {', '.join(meta.get('parents', [])) or '—'}",
            f"Trashed: {meta.get('trashed')}",
            f"Shared: {meta.get('shared')}",
            f"Link: {meta.get('webViewLink')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading file metadata: {str(e)}"


def rename_file_handler(
    config: Config, logger: logging.Logger, file_id: str, name: str
) -> str:
    try:
        if not file_id or not name:
            return "Error: file_id and name are required."
        updated = (
            _drive(config)
            .files()
            .update(fileId=file_id, body={"name": name}, fields="id,name,webViewLink")
            .execute()
        )
        return (
            f"Renamed to '{updated.get('name')}' (ID: {updated.get('id')})\n"
            f"URL: {updated.get('webViewLink')}"
        )
    except Exception as e:
        return f"Error renaming file: {str(e)}"


def delete_file_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    confirm: bool = False,
) -> str:
    """Move a file to the trash. Permanent deletion is not exposed on purpose."""
    try:
        if not file_id:
            return "Error: file_id is required."
        drive = _drive(config)
        meta = drive.files().get(fileId=file_id, fields="id,name,mimeType").execute()

        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Move to trash: {meta.get('name')} ({meta.get('mimeType')})\n"
                f"ID: {file_id}\n\n"
                "The file stays recoverable for 30 days.\n"
                "Call again with confirm=true to proceed."
            )

        drive.files().update(fileId=file_id, body={"trashed": True}).execute()
        logger.info("Trashed file %s (%s)", meta.get("name"), file_id)
        return (
            f"Moved to trash: {meta.get('name')}\n"
            "Restore with drive_restore_file while it is still in the trash."
        )
    except Exception as e:
        return f"Error deleting file: {str(e)}"


def restore_file_handler(
    config: Config, logger: logging.Logger, file_id: str
) -> str:
    try:
        if not file_id:
            return "Error: file_id is required."
        updated = (
            _drive(config)
            .files()
            .update(fileId=file_id, body={"trashed": False}, fields="id,name,webViewLink")
            .execute()
        )
        return (
            f"Restored: {updated.get('name')} (ID: {updated.get('id')})\n"
            f"URL: {updated.get('webViewLink')}"
        )
    except Exception as e:
        return f"Error restoring file: {str(e)}"


def remove_permission_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    permission_id: str,
    confirm: bool = False,
) -> str:
    try:
        if not file_id or not permission_id:
            return "Error: file_id and permission_id are required."
        drive = _drive(config)
        meta = drive.files().get(fileId=file_id, fields="id,name").execute()

        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Remove permission {permission_id} from: {meta.get('name')}\n"
                "The person or group will lose access immediately.\n"
                "Call again with confirm=true to proceed."
            )

        drive.permissions().delete(fileId=file_id, permissionId=permission_id).execute()
        logger.info("Removed permission %s from %s", permission_id, file_id)
        return f"Permission {permission_id} removed from '{meta.get('name')}'."
    except Exception as e:
        return f"Error removing permission: {str(e)}"


def empty_trash_handler(
    config: Config, logger: logging.Logger, confirm: bool = False
) -> str:
    """Permanently delete everything in the trash. Irreversible."""
    try:
        drive = _drive(config)
        if not confirm:
            listing = (
                drive.files()
                .list(
                    q="trashed = true",
                    pageSize=10,
                    fields="files(id,name,mimeType)",
                )
                .execute()
            )
            files = listing.get("files", [])
            sample = "\n".join(f"- {item.get('name')}" for item in files[:10])
            return (
                "CONFIRMATION REQUIRED\n\n"
                "Emptying the trash permanently deletes every trashed file in this "
                "account. This cannot be undone.\n"
                + (f"First items:\n{sample}\n" if sample else "")
                + "\nCall again with confirm=true to proceed."
            )

        drive.files().emptyTrash().execute()
        logger.warning("Trash emptied")
        return "Trash emptied. Every trashed file is permanently gone."
    except Exception as e:
        return f"Error emptying trash: {str(e)}"
