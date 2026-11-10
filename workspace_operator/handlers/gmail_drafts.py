"""Gmail drafts: list and delete."""

import logging

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text


def _gmail(config: Config):
    return build("gmail", "v1", credentials=get_creds(config))


def _headers(message: dict) -> dict:
    payload = message.get("payload") or {}
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in payload.get("headers", [])
    }


def list_drafts_handler(
    config: Config, logger: logging.Logger, limit: int = 10
) -> str:
    try:
        service = _gmail(config)
        result = (
            service.users()
            .drafts()
            .list(userId="me", maxResults=max(1, min(limit, 50)))
            .execute()
        )
        drafts = result.get("drafts", [])
        if not drafts:
            return "No drafts."

        lines = [f"Drafts ({len(drafts)}):"]
        for draft in drafts:
            message_id = (draft.get("message") or {}).get("id")
            if not message_id:
                lines.append(f"- {draft.get('id')} (empty draft)")
                continue
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["To", "Subject"],
                )
                .execute()
            )
            headers = _headers(message)
            lines.append(
                f"- {draft.get('id')} · to: {headers.get('to', '—')} · "
                f"subject: {clean_text(headers.get('subject', '—'))}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing drafts: {str(e)}"


def delete_draft_handler(
    config: Config, logger: logging.Logger, draft_id: str, confirm: bool = False
) -> str:
    try:
        if not draft_id:
            return "Error: draft_id is required."
        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Delete draft {draft_id}. The message is discarded, not sent.\n"
                "Call again with confirm=true to proceed."
            )
        _gmail(config).users().drafts().delete(userId="me", id=draft_id).execute()
        logger.info("Draft deleted: %s", draft_id)
        return f"Draft {draft_id} deleted."
    except Exception as e:
        return f"Error deleting draft: {str(e)}"
