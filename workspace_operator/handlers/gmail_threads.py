"""Gmail threads, attachments and threaded replies.

The base Gmail handlers cover single messages. This module adds the parts that
make mail usable in practice:

* ``gmail_get_thread`` — read a whole conversation, not one message;
* ``gmail_get_attachment`` — save an attachment to disk;
* ``gmail_reply`` — answer inside the thread with proper ``In-Reply-To`` /
  ``References`` headers.

Pure helpers (recipient selection, subject prefixing, attachment matching) are
kept separate from the API calls so they can be unit-tested.
"""

import base64
import logging
from email.mime.text import MIMEText
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text, parse_email_date
from .files import conflict_message, ensure_parent, resolve_target
from .gmail import _attachment_names, _header_map, _message_body

BODY_PREVIEW = 900
THREAD_BODY_LIMIT = 1200


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def reply_subject(subject: Optional[str]) -> str:
    clean = clean_text(subject, single_line=True)
    if not clean:
        return "Re:"
    return clean if clean.lower().startswith("re:") else f"Re: {clean}"


def _addresses(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [address for _, address in getaddresses([value]) if address]


def reply_recipients(
    headers: Dict[str, str], self_email: str, reply_all: bool = False
) -> str:
    """Pick reply recipients: sender only, or sender + To/Cc without yourself."""
    self_address = (self_email or "").strip().lower()
    candidates: List[str] = _addresses(headers.get("From"))
    if reply_all:
        candidates += _addresses(headers.get("To"))
        candidates += _addresses(headers.get("Cc"))

    seen: List[str] = []
    for address in candidates:
        lowered = address.lower()
        if lowered == self_address or lowered in {item.lower() for item in seen}:
            continue
        seen.append(address)
    return ", ".join(seen)


def reply_reference(headers: Dict[str, str]) -> str:
    """Build the References chain: existing References + original Message-ID."""
    existing = clean_text(headers.get("References"))
    message_id = clean_text(headers.get("Message-ID"))
    parts = [part for part in (existing, message_id) if part]
    return " ".join(parts)


def match_attachment(
    attachments: List[Dict[str, Any]], filename: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Find an attachment by exact name, case-insensitively, then by substring."""
    if not attachments:
        return None
    if not filename:
        return attachments[0] if len(attachments) == 1 else None

    wanted = str(filename).strip().lower()
    for item in attachments:
        if item["filename"].lower() == wanted:
            return item
    for item in attachments:
        if wanted in item["filename"].lower():
            return item
    return None


def attachment_catalog(attachments: List[Dict[str, Any]]) -> str:
    return ", ".join(item["filename"] for item in attachments)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _service(config: Config):
    return build("gmail", "v1", credentials=get_creds(config))


def gmail_get_attachment_handler(
    config: Config,
    logger: logging.Logger,
    message_id: str,
    attachment_id: Optional[str] = None,
    filename: Optional[str] = None,
    save_to: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    try:
        service = _service(config)
        message = (
            service.users().messages().get(userId="me", id=message_id, format="full").execute()
        )
        attachments = _attachments(message.get("payload", {}))

        if not attachments:
            return f"Error: message {message_id} has no attachments."

        selected = None
        if attachment_id:
            selected = next(
                (item for item in attachments if item["attachment_id"] == attachment_id), None
            )
        else:
            selected = match_attachment(attachments, filename)

        if selected is None:
            return (
                f"Error: attachment not found. Available: {attachment_catalog(attachments)}. "
                "Pass filename= or attachment_id=."
            )

        data = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=selected["attachment_id"])
            .execute()
        )
        raw = data.get("data", "")
        payload = base64.urlsafe_b64decode(raw.encode("ascii")) if raw else b""

        target = resolve_target(save_to, selected["filename"])
        if target.exists() and not overwrite:
            return conflict_message(target)
        ensure_parent(target)
        target.write_bytes(payload)

        logger.info("Attachment saved: %s → %s", selected["filename"], target)
        return (
            f"Saved {target} ({len(payload):,} bytes) from '{selected['filename']}' "
            f"({selected['mime_type']})."
        )
    except Exception as e:
        return f"Error downloading attachment: {str(e)}"


def gmail_get_thread_handler(
    config: Config,
    logger: logging.Logger,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
    include_body: bool = False,
) -> str:
    try:
        if not thread_id and not message_id:
            return "Error: pass thread_id or message_id."

        service = _service(config)
        if not thread_id:
            stub = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="minimal")
                .execute()
            )
            thread_id = stub.get("threadId")

        thread = service.users().threads().get(userId="me", id=thread_id).execute()
        messages = thread.get("messages", [])
        if not messages:
            return f"Thread {thread_id} has no messages."

        first_headers = _header_map(messages[0].get("payload", {}))
        subject = clean_text(first_headers.get("Subject"), single_line=True) or "(no subject)"
        lines = [
            f"Thread: {subject}",
            f"ID: {thread_id} | messages: {len(messages)}",
            "",
        ]

        for index, message in enumerate(messages, start=1):
            headers = _header_map(message.get("payload", {}))
            labels = [label for label in message.get("labelIds", []) if label != "UNREAD"]
            attachments = _attachment_names(message.get("payload", {}))
            snippet = clean_text(message.get("snippet", ""), limit=200)

            lines.append(
                f"{index}. {parse_email_date(headers.get('Date'))} | "
                f"{clean_text(headers.get('From'), single_line=True)} | "
                f"ID: {message.get('id')}"
            )
            if labels:
                lines.append(f"   labels: {', '.join(labels)}")
            if attachments:
                lines.append(f"   attachments: {', '.join(attachments)}")
            if include_body:
                body = _message_body(message.get("payload", {}))[:THREAD_BODY_LIMIT]
                if body:
                    lines.append("   ---")
                    lines.extend(f"   {line}" for line in body.splitlines())
            elif snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        return "\n".join(lines).rstrip()
    except Exception as e:
        return f"Error reading thread: {str(e)}"


def gmail_reply_handler(
    config: Config,
    logger: logging.Logger,
    message_id: str,
    body_text: str,
    reply_all: bool = False,
    draft_mode: bool = True,
) -> str:
    try:
        if not body_text or not body_text.strip():
            return "Error: body_text is required."

        service = _service(config)
        original = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=[
                    "From",
                    "To",
                    "Cc",
                    "Subject",
                    "Date",
                    "Message-ID",
                    "References",
                ],
            )
            .execute()
        )
        headers = _header_map(original.get("payload", {}))
        thread_id = original.get("threadId")

        self_email = service.users().getProfile(userId="me").execute().get("emailAddress", "")
        recipients = reply_recipients(headers, self_email, reply_all=reply_all)
        if not recipients:
            return "Error: could not determine the reply recipients."

        message = MIMEText(body_text, "plain", "utf-8")
        message["To"] = recipients
        message["Subject"] = reply_subject(headers.get("Subject"))
        if headers.get("Message-ID"):
            message["In-Reply-To"] = headers["Message-ID"]
        references = reply_reference(headers)
        if references:
            message["References"] = references

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload: Dict[str, Any] = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id

        if draft_mode:
            draft = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": payload})
                .execute()
            )
            logger.info("Reply draft created: %s (thread %s)", draft.get("id"), thread_id)
            return (
                f"Draft reply created (Draft ID: {draft.get('id')}, thread: {thread_id}).\n"
                f"To: {recipients}\n"
                f"Subject: {message['Subject']}\n\n"
                "Saved as a draft — nothing was sent."
            )

        sent = service.users().messages().send(userId="me", body=payload).execute()
        logger.info("Reply sent: %s (thread %s)", sent.get("id"), sent.get("threadId"))
        return (
            f"Reply sent (Message ID: {sent.get('id')}, thread: {sent.get('threadId')}).\n"
            f"To: {recipients}\nSubject: {message['Subject']}"
        )
    except Exception as e:
        return f"Error replying to message: {str(e)}"


def _attachments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    def walk(part: Dict[str, Any]) -> None:
        body = part.get("body") or {}
        filename = part.get("filename")
        if filename and body.get("attachmentId"):
            found.append(
                {
                    "filename": clean_text(filename, single_line=True),
                    "attachment_id": body["attachmentId"],
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": body.get("size"),
                }
            )
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    return found
