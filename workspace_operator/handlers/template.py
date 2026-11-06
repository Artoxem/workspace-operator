"""Composite tool: clone a Drive file as a template and fill placeholders.

Works for any native Google file:

* Docs and Slides — ``replaceAllText`` across the whole file;
* Sheets — ``findReplace`` across all sheets;
* anything else — the copy is made and the tool says placeholders were not filled.

The request builders are pure functions, so the per-type behaviour is unit-tested.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

DOC_TYPES = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.presentation": "presentation",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
}


def replacement_requests(kind: str, replacements: Dict[str, str]) -> List[Dict[str, Any]]:
    """Build API requests for the given native file type."""
    if kind in {"document", "presentation"}:
        return [
            {
                "replaceAllText": {
                    "containsText": {"text": key, "matchCase": False},
                    "replaceText": str(value),
                }
            }
            for key, value in replacements.items()
        ]
    if kind == "spreadsheet":
        return [
            {
                "findReplace": {
                    "find": key,
                    "replacement": str(value),
                    "matchCase": False,
                    "allSheets": True,
                }
            }
            for key, value in replacements.items()
        ]
    raise ValueError(f"unsupported template type: {kind}")


def count_occurrences(replies: Sequence[Dict[str, Any]]) -> int:
    """Sum occurrencesChanged across replaceAllText/findReplace replies."""
    total = 0
    for reply in replies:
        for key in ("replaceAllText", "findReplace"):
            payload = reply.get(key)
            if isinstance(payload, dict):
                total += int(payload.get("occurrencesChanged", 0))
    return total


def apply_replacements(creds, kind: str, file_id: str, replacements: Dict[str, str]) -> int:
    requests = replacement_requests(kind, replacements)
    if not requests:
        return 0

    if kind in {"document", "presentation"}:
        api = "docs" if kind == "document" else "slides"
        service = build(api, "v1", credentials=creds)
        if kind == "document":
            response = service.documents().batchUpdate(
                documentId=file_id, body={"requests": requests}
            ).execute()
        else:
            response = service.presentations().batchUpdate(
                presentationId=file_id, body={"requests": requests}
            ).execute()
        return count_occurrences(response.get("replies", []))

    service = build("sheets", "v4", credentials=creds)
    response = service.spreadsheets().batchUpdate(
        spreadsheetId=file_id, body={"requests": requests}
    ).execute()
    return count_occurrences(response.get("replies", []))


def clone_and_fill_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    replacements: Optional[Dict[str, str]] = None,
    name: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> str:
    try:
        if not file_id:
            return "Error: file_id is required."

        creds = get_creds(config)
        drive = build("drive", "v3", credentials=creds)

        meta = (
            drive.files()
            .get(fileId=file_id, fields="id,name,mimeType")
            .execute()
        )
        mime = meta.get("mimeType", "")
        kind = DOC_TYPES.get(mime)

        body: Dict[str, Any] = {"name": name or f"Copy of {meta.get('name', 'file')}"}
        if folder_id:
            body["parents"] = [folder_id]

        created = (
            drive.files()
            .copy(fileId=file_id, body=body, fields="id,name,mimeType,webViewLink")
            .execute()
        )
        new_id = created.get("id")

        replaced = 0
        note = ""
        if replacements:
            if kind is None:
                note = f"\nNote: {mime} has no placeholder support; the copy was not modified."
            else:
                replaced = apply_replacements(creds, kind, new_id, replacements)

        logger.info(
            "Template cloned: %s → %s kind=%s replaced=%s",
            file_id,
            new_id,
            kind or mime,
            replaced,
        )
        return (
            f"Created {created.get('name')} (ID: {new_id}) from template {file_id}\n"
            f"Type: {mime}\n"
            f"Replacements: {len(replacements or {})} key(s), {replaced} occurrence(s)\n"
            f"{created.get('webViewLink', '')}{note}"
        )
    except Exception as e:
        return f"Error cloning template: {str(e)}"
