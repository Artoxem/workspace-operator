"""Local ↔ Google Drive file transfer.

Two tools cover the gap between the machine the MCP server runs on and Drive:

* ``drive_upload`` — local file → Drive (optional conversion to Docs or Sheets)
* ``drive_export`` — Google-native file (Doc/Sheet/Slide) → local file in a chosen format

File names that originate from remote data are sanitised (``safe_filename``) and
uploads refuse OAuth secrets and anything outside the optional ``upload_roots``.

Paths are always expanded and reported as absolute; nothing is overwritten
unless the caller explicitly asks for it.
"""

import hashlib
import logging
import mimetypes
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Callable, Optional

from googleapiclient.http import MediaIoBaseUpload

from ..config import Config
from ..google_clients import api_client
from ..secure_files import is_protected

MAX_TRANSFER_BYTES = 100 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_RESUMABLE_UPLOAD_ABOVE_BYTES = 5 * 1024 * 1024
_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"

CONVERT_TARGETS = {
    "google-docs": "application/vnd.google-apps.document",
    "google-sheets": "application/vnd.google-apps.spreadsheet",
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
}

EXPORT_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
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


_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def safe_filename(name: Optional[str], fallback: str = "download") -> str:
    """Reduce an untrusted file name (mail attachment, Drive title) to a leaf name.

    Directory components, drive letters, control characters and Windows-invalid
    characters are removed, so the result can never escape the target directory.
    """
    leaf = re.split(r"[\\/]", str(name or ""))[-1]
    leaf = _INVALID_NAME_CHARS.sub("_", leaf).strip().strip(".")
    leaf = leaf[:200].rstrip(" .")
    if not leaf or leaf.split(".")[0].upper() in _RESERVED_WINDOWS_NAMES:
        leaf = f"{fallback}_{leaf}" if leaf else fallback
    return leaf


def resolve_target(save_to: Optional[str], filename: str) -> Path:
    """Interpret ``save_to`` as a directory or a full file path.

    ``filename`` comes from untrusted data (attachment or Drive name), so it is
    always reduced to a leaf name. An explicit ``save_to`` file path chosen by
    the caller is respected.
    """
    leaf = safe_filename(filename)
    if not save_to:
        return default_download_dir() / leaf

    candidate = expand_path(save_to)
    looks_like_dir = (
        candidate.is_dir()
        or str(save_to).endswith(("/", "\\"))
        or candidate.suffix == ""
    )
    if not looks_like_dir:
        return candidate
    target = candidate / leaf
    if not target.resolve().is_relative_to(candidate.resolve()):  # pragma: no cover
        raise ValueError(f"Refusing to write outside {candidate}")
    return target


def check_upload_allowed(source: Path, config: Optional[Config] = None) -> Optional[str]:
    """Return an error message when ``source`` must not be uploaded, else None."""
    try:
        resolved = source.resolve()
    except OSError as exc:
        return f"Error: cannot resolve {source}: {exc}"

    if is_protected(resolved, config):
        return (
            f"Error: {source.name} is a secrets file or inside a protected "
            "location (OAuth tokens, keys, approvals, logs) and cannot be uploaded."
        )

    roots = getattr(config, "upload_roots", None) if config is not None else None
    if roots:
        allowed = [Path(root).expanduser().resolve() for root in roots]
        if not any(resolved.is_relative_to(root) for root in allowed):
            return (
                f"Error: {source.name} is outside the allowed upload_roots "
                f"({', '.join(str(root) for root in allowed)})."
            )
    return None


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


def _resolve_upload_source(source: Path) -> Path:
    try:
        return source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"local file not found or inaccessible: {source}") from exc


def _upload_fingerprint(
    source: Path,
    config: Config,
    *,
    write_snapshot: Optional[Callable[[bytes], int]] = None,
    expected_size: Optional[int] = None,
) -> tuple[int, str]:
    """Hash a permitted regular file; optionally copy the very same bytes."""
    changed = f"local file changed: {source}. Request a new upload approval."
    if not source.is_absolute() or _resolve_upload_source(source) != source:
        raise ValueError(changed)
    denied = check_upload_allowed(source, config)
    if denied:
        raise ValueError(denied.removeprefix("Error: "))

    def check_size(size: int) -> None:
        if expected_size is not None and size != expected_size:
            raise ValueError(changed)
        if size > MAX_TRANSFER_BYTES:
            raise ValueError(
                f"{source.name} is {_human_size(size)}; "
                f"the limit for this tool is {_human_size(MAX_TRANSFER_BYTES)}."
            )

    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"not a regular local file: {source}")
    check_size(before.st_size)
    # NOFOLLOW protects the leaf where available. NONBLOCK avoids hanging if
    # a regular file is replaced by a FIFO between stat and open on POSIX.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_BINARY", 0)
    with open(source, "rb", opener=lambda path, _: os.open(path, flags)) as handle:
        opened = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or not os.path.samestat(before, opened)
            or _resolve_upload_source(source) != source
        ):
            raise ValueError(changed)
        check_size(opened.st_size)

        digest = hashlib.sha256()
        size = 0
        limit = min(MAX_TRANSFER_BYTES, expected_size) if expected_size is not None else MAX_TRANSFER_BYTES
        while chunk := handle.read(min(_UPLOAD_CHUNK_BYTES, limit - size + 1)):
            size += len(chunk)
            if size > limit:
                check_size(size)
            digest.update(chunk)
            if write_snapshot is not None:
                write_snapshot(chunk)

        after = os.fstat(handle.fileno())
        if (
            size != opened.st_size
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or after.st_ctime_ns != opened.st_ctime_ns
            or _resolve_upload_source(source) != source
            or not os.path.samestat(after, source.stat())
        ):
            raise ValueError(changed)
        check_size(size)
        return size, digest.hexdigest()


def _upload_destination(files, folder_id: str, *, allow_shared: bool) -> dict:
    folder = files.get(
        fileId=folder_id,
        fields="id,name,mimeType,trashed,driveId,capabilities(canAddChildren)",
        supportsAllDrives=allow_shared,
    ).execute()
    if folder.get("mimeType") != _DRIVE_FOLDER_MIME or folder.get("trashed"):
        raise ValueError(f"Drive destination must be a non-trashed folder: {folder_id}")
    shared_drive_id = folder.get("driveId")
    if shared_drive_id and not allow_shared:
        raise ValueError("Shared drive uploads require bulk_allow_shared_drives to be enabled")
    can_add = (folder.get("capabilities") or {}).get("canAddChildren")
    if can_add is False or (shared_drive_id and can_add is not True):
        raise ValueError(f"you do not have permission to upload to Drive folder: {folder_id}")
    if not folder.get("id") or not folder.get("name"):
        raise ValueError(f"could not identify Drive destination folder: {folder_id}")
    destination = {"id": folder["id"], "name": folder["name"]}
    if shared_drive_id:
        destination["drive_id"] = shared_drive_id
    return destination


def prepare_drive_upload(
    config: Config,
    local_path: str,
    name: Optional[str] = None,
    parent_id: Optional[str] = None,
    mime_type: Optional[str] = None,
    convert_to: Optional[str] = None,
) -> dict:
    """Resolve and fingerprint a local upload without starting a Drive write."""
    if not local_path or not str(local_path).strip():
        raise ValueError("upload requires local_path")
    requested = expand_path(local_path)
    source = _resolve_upload_source(requested)
    conversion_mime = None
    if convert_to:
        conversion_mime = CONVERT_TARGETS.get(convert_to.strip().lower())
        if conversion_mime is None and convert_to.startswith("application/vnd.google-apps."):
            conversion_mime = convert_to
        if conversion_mime is None:
            raise ValueError(
                f"unsupported convert_to '{convert_to}'. "
                f"Valid values: {', '.join(sorted(CONVERT_TARGETS))}."
            )
    media_mime = mime_type or mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
    try:
        size, digest = _upload_fingerprint(source, config)
    except OSError as exc:
        raise ValueError(f"could not read local file: {source}: {exc}") from exc
    files = api_client(config, "drive", "v3").files()
    destination = _upload_destination(
        files, (parent_id or "").strip() or "root", allow_shared=bool(getattr(config, "bulk_allow_shared_drives", False)),
    )
    return {
        "operation": "upload",
        "destination": destination,
        "items": [{
            "id": str(source),
            "name": name or requested.name,
            "sources": [{"id": str(source), "name": source.name}],
            "size_bytes": size,
            "sha256": digest,
            "mime_type": media_mime,
            "conversion_mime_type": conversion_mime,
        }],
    }


def execute_prepared_drive_upload(config: Config, logger: logging.Logger, prepared: dict) -> str:
    """Upload only the bytes, metadata and canonical folder approved by the user."""
    try:
        if prepared["operation"] != "upload" or len(prepared["items"]) != 1:
            raise ValueError("invalid prepared upload")
        item = prepared["items"][0]
        source = Path(item["id"])
        destination = prepared["destination"]
        expected_size = item["size_bytes"]
        if type(expected_size) is not int or not 0 <= expected_size <= MAX_TRANSFER_BYTES:
            raise ValueError("invalid prepared upload size")
        allow_shared = bool(getattr(config, "bulk_allow_shared_drives", False))
        if destination.get("drive_id") and not allow_shared:
            raise ValueError("Shared drive uploads require bulk_allow_shared_drives to be enabled")

        # The source path is never passed to Drive's upload client. A temporary
        # snapshot avoids a second-open race even if the file changes after hashing.
        with tempfile.SpooledTemporaryFile(max_size=_RESUMABLE_UPLOAD_ABOVE_BYTES) as snapshot:
            size, digest = _upload_fingerprint(
                source, config, write_snapshot=snapshot.write, expected_size=expected_size,
            )
            if digest != item["sha256"]:
                raise ValueError(f"local file changed: {source}. Request a new upload approval.")

            files = api_client(config, "drive", "v3").files()
            if _upload_destination(files, destination["id"], allow_shared=allow_shared) != destination:
                raise ValueError("Drive destination changed. Request a new upload approval.")
            metadata = {"name": item["name"], "parents": [destination["id"]]}
            if item["conversion_mime_type"]:
                metadata["mimeType"] = item["conversion_mime_type"]
            media = MediaIoBaseUpload(
                snapshot, item["mime_type"], chunksize=_RESUMABLE_UPLOAD_ABOVE_BYTES,
                resumable=size > _RESUMABLE_UPLOAD_ABOVE_BYTES,
            )
            created = files.create(
                body=metadata,
                media_body=media,
                fields="id,name,mimeType,size,webViewLink",
                supportsAllDrives=allow_shared,
            ).execute()

        logger.info("Uploaded %s → %s", source, created.get("id"))
        return (
            f"Uploaded {created.get('name')} (ID: {created.get('id')}) "
            f"[{created.get('mimeType')}]\n"
            f"Size: {_human_size(size)} · {created.get('webViewLink', 'no link')}"
        )
    except Exception as exc:
        return f"Error uploading file: {exc}"


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

        service = api_client(config, 'drive', 'v3')

        meta = (
            service.files()
            .get(fileId=file_id, fields="id,name,mimeType")
            .execute()
        )
        native = meta.get("mimeType", "")
        if not native.startswith("application/vnd.google-apps."):
            return (
                f"Error: '{meta.get('name')}' is a binary file ({native}); "
                "use drive_read(action='export') instead."
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
