"""Local ↔ Google Drive file transfer.

Three tools cover the gap between the machine the MCP server runs on and Drive:

* ``drive_upload``   — local file → Drive (optional conversion to Docs/Sheets/Slides)
* ``drive_download`` — binary Drive file → local path
* ``drive_export``   — Google-native file (Doc/Sheet/Slide) → local file in a chosen format

Paths are always expanded and reported as absolute; nothing is overwritten
unless the caller explicitly asks for it.
"""

import io
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from ..auth import get_creds
from ..config import Config

MAX_TRANSFER_BYTES = 100 * 1024 * 1024

CONVERT_TARGETS = {
    "google-docs": "application/vnd.google-apps.document",
    "google-sheets": "application/vnd.google-apps.spreadsheet",
    "google-slides": "application/vnd.google-apps.presentation",
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
}

EXPORT_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
    "rtf": "application/rtf",
    "epub": "application/epub+zip",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "zip": "application/zip",
    "json": "application/json",
}

EXPORT_FORMATS_BY_TYPE = {
    "application/vnd.google-apps.document": {
        "pdf", "docx", "odt", "txt", "md", "html", "rtf", "epub", "zip",
    },
    "application/vnd.google-apps.spreadsheet": {
        "pdf", "xlsx", "ods", "csv", "tsv", "zip",
    },
    "application/vnd.google-apps.presentation": {
        "pdf", "pptx", "odp", "txt",
    },
    "application/vnd.google-apps.drawing": {
        "pdf", "png", "jpeg", "svg",
    },
    "application/vnd.google-apps.script": {"json"},
}


def expand_path(value: str) -> Path:
    """Expand ``~``/env vars and make the path absolute against the cwd."""
    expanded = os.path.expandvars(os.path.expanduser(str(value).strip()))
    path = Path(expanded)
    return path if path.is_absolute() else Path.cwd() / path


def default_download_dir() -> Path:
    return Path.home() / "Downloads"


def resolve_target(save_to: Optional[str], filename: str) -> Path:
    """Interpret ``save_to`` as a directory or a full file path."""
    if not save_to:
        return default_download_dir() / filename

    candidate = expand_path(save_to)
    looks_like_dir = (
        candidate.is_dir()
        or str(save_to).endswith(("/", "\\"))
        or candidate.suffix == ""
    )
    return candidate / filename if looks_like_dir else candidate


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def conflict_message(path: Path) -> str:
    return (
        f"Error: {path} already exists. Pass overwrite=true to replace it, "
        "or choose another save_to path."
    )


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def drive_upload_handler(
    config: Config,
    logger: logging.Logger,
    local_path: str,
    name: Optional[str] = None,
    parent_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    convert_to: Optional[str] = None,
) -> str:
    try:
        source = expand_path(local_path)
        if not source.exists() or not source.is_file():
            return f"Error: local file not found: {source}"

        size = source.stat().st_size
        if size > MAX_TRANSFER_BYTES:
            return (
                f"Error: {source.name} is {_human_size(size)}; "
                f"the limit for this tool is {_human_size(MAX_TRANSFER_BYTES)}."
            )

        metadata: dict = {"name": name or source.name}
        if parent_id:
            metadata["parents"] = [parent_id]

        if convert_to:
            key = str(convert_to).strip().lower()
            target = CONVERT_TARGETS.get(key)
            if target is None and str(convert_to).startswith("application/vnd.google-apps"):
                target = str(convert_to)
            if target is None:
                return (
                    f"Error: unsupported convert_to '{convert_to}'. "
                    f"Valid values: {', '.join(sorted(CONVERT_TARGETS))}."
                )
            metadata["mimeType"] = target

        media_mime = (
            mime_type
            or mimetypes.guess_type(str(source))[0]
            or "application/octet-stream"
        )

        creds = get_creds(config)
        service = build("drive", "v3", credentials=creds)
        created = (
            service.files()
            .create(
                body=metadata,
                media_body=MediaFileUpload(str(source), mimetype=media_mime, resumable=False),
                fields="id,name,mimeType,size,webViewLink",
            )
            .execute()
        )

        logger.info("Uploaded %s → %s", source, created.get("id"))
        return (
            f"Uploaded {created.get('name')} (ID: {created.get('id')}) "
            f"[{created.get('mimeType')}]\n"
            f"Size: {_human_size(size)} · {created.get('webViewLink', 'no link')}"
        )
    except Exception as e:
        return f"Error uploading file: {str(e)}"


def drive_download_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    save_to: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    try:
        creds = get_creds(config)
        service = build("drive", "v3", credentials=creds)

        meta = (
            service.files()
            .get(fileId=file_id, fields="id,name,mimeType,size")
            .execute()
        )
        mime = meta.get("mimeType", "")

        if mime.startswith("application/vnd.google-apps."):
            formats = EXPORT_FORMATS_BY_TYPE.get(mime)
            hint = (
                f"Valid formats for this type: {', '.join(sorted(formats))}."
                if formats
                else "Use drive_export with a supported format."
            )
            return (
                f"Error: '{meta.get('name')}' is a Google-native file ({mime}) "
                f"and cannot be downloaded as bytes. {hint}"
            )

        target = resolve_target(save_to, meta.get("name") or file_id)
        if target.exists() and not overwrite:
            return conflict_message(target)
        ensure_parent(target)

        request = service.files().get_media(fileId=file_id)
        with io.FileIO(target, "wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        size = target.stat().st_size
        logger.info("Downloaded %s → %s", file_id, target)
        return f"Saved {target} ({_human_size(size)}) from '{meta.get('name')}'."
    except Exception as e:
        return f"Error downloading file: {str(e)}"


def drive_export_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    export_format: str,
    save_to: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    try:
        fmt = str(export_format).strip().lower().lstrip(".")
        export_mime = EXPORT_MIME.get(fmt)
        if not export_mime:
            return (
                f"Error: unsupported format '{export_format}'. "
                f"Valid formats: {', '.join(sorted(EXPORT_MIME))}."
            )

        creds = get_creds(config)
        service = build("drive", "v3", credentials=creds)

        meta = (
            service.files()
            .get(fileId=file_id, fields="id,name,mimeType")
            .execute()
        )
        native = meta.get("mimeType", "")
        if not native.startswith("application/vnd.google-apps."):
            return (
                f"Error: '{meta.get('name')}' is a binary file ({native}); "
                "use drive_download instead."
            )

        allowed = EXPORT_FORMATS_BY_TYPE.get(native)
        if allowed and fmt not in allowed:
            return (
                f"Error: {native} cannot be exported as {fmt}. "
                f"Valid formats: {', '.join(sorted(allowed))}."
            )

        data = service.files().export(fileId=file_id, mimeType=export_mime).execute()
        if len(data) > MAX_TRANSFER_BYTES:
            return (
                f"Error: export would be {_human_size(len(data))}; "
                f"the limit for this tool is {_human_size(MAX_TRANSFER_BYTES)}."
            )

        stem = Path(meta.get("name") or file_id).stem
        target = resolve_target(save_to, f"{stem}.{fmt}")
        if target.exists() and not overwrite:
            return conflict_message(target)
        ensure_parent(target)
        target.write_bytes(data)

        logger.info("Exported %s as %s → %s", file_id, fmt, target)
        return (
            f"Exported '{meta.get('name')}' as {fmt} → {target} "
            f"({_human_size(len(data))})."
        )
    except Exception as e:
        return f"Error exporting file: {str(e)}"
