import base64
import logging
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..security import validate_email
from ..text import clean_text, html_to_text, parse_email_date, shorten_links

BODY_LIMIT = 2500


def _header_map(payload: dict) -> dict:
    return {header["name"]: header["value"] for header in payload.get("headers", [])}


def _find_part_data(payload: dict, mime_type: str) -> str | None:
    """Depth-first search for the first non-empty body part of ``mime_type``."""
    if payload.get("mimeType") == mime_type and payload.get("body", {}).get("data"):
        return payload["body"]["data"]
    for part in payload.get("parts") or []:
        found = _find_part_data(part, mime_type)
        if found:
            return found
    return None


def _decode_part(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", "replace")
    except (ValueError, UnicodeDecodeError):
        return ""


def _message_body(payload: dict) -> str:
    """Return readable text: text/plain if present, else text/html stripped."""
    plain = _find_part_data(payload, "text/plain")
    text = clean_text(_decode_part(plain)) if plain else ""
    if not text:
        markup = _find_part_data(payload, "text/html")
        text = html_to_text(_decode_part(markup)) if markup else ""

    text = shorten_links(text)
    if len(text) > BODY_LIMIT:
        return text[:BODY_LIMIT].rstrip() + f"\n… (truncated, {len(text):,} characters total)"
    return text


def _attachment_names(payload: dict) -> list[str]:
    names: list[str] = []

    def walk(part: dict) -> None:
        filename = part.get("filename")
        body = part.get("body", {})
        if filename and (body.get("attachmentId") or body.get("size")):
            names.append(clean_text(filename))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    return names


def _create_message(to: str, subject: str, message_text: str) -> dict:
    message = MIMEText(message_text)
    message["to"] = to
    message["from"] = "me"
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw_message}


def send_email_handler(
    config: Config,
    logger: logging.Logger,
    to: str,
    subject: str,
    body_text: str,
    draft_mode: bool = True,
) -> str:
    """Send email with draft mode by default for safety."""
    try:
        if not validate_email(to):
            return f"Error: Invalid email format: {to}"

        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)
        message = _create_message(to, subject, body_text)

        # Safe by default: create draft unless explicitly disabled
        if draft_mode:
            draft = {"message": message}
            created_draft = (
                service.users().drafts().create(userId="me", body=draft).execute()
            )
            draft_id = created_draft["id"]

            logger.info("Email draft created: %s to %s", draft_id, to)
            return (
                f"📝 EMAIL DRAFT CREATED (ID: {draft_id})\n\n"
                f"To: {to}\n"
                f"Subject: {subject}\n"
                f"Body: {body_text[:100]}{'...' if len(body_text) > 100 else ''}\n\n"
                "⚠️ Email saved as DRAFT, not sent yet.\n\n"
                "To send: send_email(..., draft_mode=False)\n"
                f"Or send draft: send_draft(draft_id='{draft_id}')"
            )

        sent_message = (
            service.users().messages().send(userId="me", body=message).execute()
        )
        logger.info("Email sent: %s to %s", sent_message["id"], to)
        return f"✅ Email sent. Message Id: {sent_message['id']}"

    except Exception as e:
        logger.error("Error sending email to %s: %s", to, str(e))
        return f"Error sending email: {str(e)}"


def send_draft_handler(config: Config, logger: logging.Logger, draft_id: str) -> str:
    """Send an existing draft."""
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        sent_message = (
            service.users()
            .drafts()
            .send(userId="me", body={"id": draft_id})
            .execute()
        )

        logger.info("Draft sent: %s", draft_id)
        return f"✅ Draft sent successfully. Message Id: {sent_message['id']}"

    except Exception as e:
        logger.error("Error sending draft %s: %s", draft_id, str(e))
        return f"Error sending draft: {str(e)}"


def get_gmail_profile_handler(config: Config, logger: logging.Logger) -> str:
    """Get the authenticated Gmail address (profile)."""
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "Unknown")
        logger.info("Gmail profile accessed: %s", email_address)
        return f"✅ Authenticated Gmail address: {email_address}"
    except Exception as e:
        logger.error("Error getting Gmail profile: %s", str(e))
        return f"Error getting Gmail profile: {str(e)}"


def create_draft_handler(
    config: Config, logger: logging.Logger, to: str, subject: str, body_text: str
) -> str:
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        message = _create_message(to, subject, body_text)
        draft = {"message": message}
        created_draft = (
            service.users().drafts().create(userId="me", body=draft).execute()
        )

        return f"Draft created. Draft Id: {created_draft['id']}"
    except Exception as e:
        return f"Error creating draft: {str(e)}"


def list_emails_handler(
    config: Config, logger: logging.Logger, max_results: int = 10, query: Optional[str] = None
) -> str:
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        q = query if query else ""
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=q)
            .execute()
        )
        messages = results.get("messages", [])

        if not messages:
            return "No messages found."

        output = f"Messages ({len(messages)}):\n"
        for index, msg in enumerate(messages, start=1):
            full = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = _header_map(full.get("payload", {}))
            snippet = clean_text(full.get("snippet", ""), limit=120)
            output += (
                f"{index}. {parse_email_date(headers.get('Date'))} | "
                f"{clean_text(headers.get('From'), single_line=True)} | "
                f"{clean_text(headers.get('Subject'), single_line=True) or '(no subject)'}\n"
                f"   ID: {msg['id']}"
                + (f" | {snippet}" if snippet else "")
                + "\n"
            )

        return output
    except Exception as e:
        return f"Error listing emails: {str(e)}"


def read_email_handler(config: Config, logger: logging.Logger, message_id: str) -> str:
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        payload = message.get("payload", {})
        headers = _header_map(payload)
        labels = [label for label in message.get("labelIds", []) if label != "UNREAD"]
        unread = "UNREAD" in message.get("labelIds", [])
        attachments = _attachment_names(payload)
        body = _message_body(payload)

        lines = [
            f"From: {clean_text(headers.get('From'), single_line=True)}",
            f"To: {clean_text(headers.get('To'), single_line=True)}",
            f"Date: {clean_text(headers.get('Date'), single_line=True)}",
            f"Subject: {clean_text(headers.get('Subject'), single_line=True) or '(no subject)'}",
            f"Status: {'unread' if unread else 'read'}"
            + (f" | labels: {', '.join(labels)}" if labels else ""),
            f"Attachments: {', '.join(attachments) if attachments else 'none'}",
            "",
            body or "(no readable text body)",
        ]

        return "\n".join(lines)
    except Exception as e:
        return f"Error reading email: {str(e)}"


def delete_email_handler(
    config: Config, logger: logging.Logger, message_id: str, confirm: bool = False
) -> str:
    """Delete email with confirmation requirement."""
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        # Provide a preview before destructive action
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="minimal")
                .execute()
            )
            snippet = clean_text(msg.get("snippet", "No preview available"), limit=120)
        except Exception:
            snippet = "Unable to load preview"

        if not confirm:
            logger.warning("Delete email attempted without confirm: %s", message_id)
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will permanently delete email {message_id}.\n\n"
                f"Email preview:\n{snippet}\n\n"
                "⚠️ To proceed, call this tool again with confirm=True"
            )

        service.users().messages().delete(userId="me", id=message_id).execute()
        logger.info("Email deleted: %s", message_id)
        return f"✅ Email {message_id} deleted successfully."

    except Exception as e:
        logger.error("Error deleting email %s: %s", message_id, str(e))
        return f"Error deleting email: {str(e)}"


def batch_delete_emails_handler(
    config: Config, logger: logging.Logger, message_ids: List[str], dry_run: bool = True
) -> str:
    """Batch delete emails with dry-run mode."""
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        if dry_run:
            preview = "🔍 DRY RUN MODE - No emails will be deleted\n\n"
            preview += f"Would delete {len(message_ids)} email(s):\n\n"

            previews_to_show = min(10, len(message_ids))
            for msg_id in message_ids[:previews_to_show]:
                try:
                    msg = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg_id, format="minimal")
                        .execute()
                    )
                    snippet = clean_text(msg.get("snippet", "No preview"), limit=100)
                    preview += f"  • {msg_id}: {snippet}\n"
                except Exception:
                    preview += f"  • {msg_id}: (unable to load preview)\n"

            if len(message_ids) > previews_to_show:
                preview += f"\n... and {len(message_ids) - previews_to_show} more\n"

            preview += "\n⚠️ To actually delete these emails, call with dry_run=False"
            logger.info("Batch delete dry-run: %s emails", len(message_ids))
            return preview

        body = {"ids": message_ids}
        service.users().messages().batchDelete(userId="me", body=body).execute()
        logger.info("Batch deleted %s emails", len(message_ids))
        return f"✅ Successfully deleted {len(message_ids)} email(s)."

    except Exception as e:
        logger.error("Error batch deleting emails: %s", str(e))
        return f"Error: batch deleting emails: {str(e)}"


def gmail_search_and_summarize_handler(
    config: Config, logger: logging.Logger, query: str, max_results: int = 50
) -> str:
    """Search Gmail and return a brief summary."""
    try:
        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        if not query:
            return "Error: Query is required."

        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=min(max_results, 100), q=query)
            .execute()
        )
        messages = results.get("messages", [])

        if not messages:
            return "No messages found."

        summary_lines = []
        for msg in messages[: min(len(messages), 20)]:
            full = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {
                h["name"]: h["value"]
                for h in full.get("payload", {}).get("headers", [])
            }
            summary_lines.append(
                f"- {parse_email_date(headers.get('Date'))} | "
                f"{clean_text(headers.get('From'))} | "
                f"{clean_text(headers.get('Subject'))}"
            )

        logger.info("Gmail search: query='%s' results=%s", query, len(messages))
        output = f"Found {len(messages)} message(s) for query: {query}\n"
        output += "Top results:\n" + "\n".join(summary_lines)
        return output
    except Exception as e:
        logger.error("Error searching Gmail: %s", str(e))
        return f"Error searching Gmail: {str(e)}"


def gmail_archive_handler(
    config: Config, logger: logging.Logger, message_id: str, confirm: bool = False
) -> str:
    """Archive a Gmail message (remove INBOX label)."""
    try:
        if not confirm:
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will archive message {message_id} (remove from INBOX).\n"
                "To proceed, call again with confirm=True."
            )

        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)

        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
        ).execute()

        logger.info("Gmail archived: %s", message_id)
        return f"✅ Message archived: {message_id}"
    except Exception as e:
        logger.error("Error archiving message: %s", str(e))
        return f"Error archiving message: {str(e)}"


def _get_or_create_label_id(service, label_name: str, create_if_missing: bool = True):
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for lbl in labels:
        if lbl.get("name") == label_name:
            return lbl.get("id")
    if not create_if_missing:
        return None
    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return created.get("id")


def gmail_label_apply_handler(
    config: Config,
    logger: logging.Logger,
    message_ids: List[str],
    label_name: str,
    dry_run: bool = True,
    create_if_missing: bool = True,
) -> str:
    """Apply a label to messages with dry-run preview."""
    try:
        if not message_ids:
            return "Error: message_ids is required."
        if not label_name:
            return "Error: label_name is required."

        creds = get_creds(config)
        service = build("gmail", "v1", credentials=creds)
        label_id = _get_or_create_label_id(service, label_name, create_if_missing)
        if not label_id:
            return f"Error: Label not found: {label_name}"

        if dry_run:
            preview_ids = message_ids[:10]
            logger.info(
                "Gmail label dry-run: %s count=%s", label_name, len(message_ids)
            )
            return (
                f"🔍 DRY RUN: Would apply label '{label_name}' to "
                f"{len(message_ids)} message(s).\n"
                f"Sample IDs: {', '.join(preview_ids)}\n"
                "To apply, call again with dry_run=False."
            )

        for mid in message_ids:
            service.users().messages().modify(
                userId="me", id=mid, body={"addLabelIds": [label_id]}
            ).execute()

        logger.info("Gmail label applied: %s count=%s", label_name, len(message_ids))
        return f"✅ Label '{label_name}' applied to {len(message_ids)} message(s)."
    except Exception as e:
        logger.error("Error applying label: %s", str(e))
        return f"Error applying label: {str(e)}"


def _create_message_with_attachments(
    to: str, subject: str, body_text: str, attachments: List[str]
) -> dict:
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body_text, "plain", "utf-8"))

    total = 0
    for item in attachments:
        path = Path(item).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"attachment not found: {item}")
        total += path.stat().st_size
        if total > 20 * 1024 * 1024:
            raise ValueError("attachments exceed the 20 MB limit")
        part = MIMEBase("application", "octet-stream")
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", f'attachment; filename="{path.name}"'
        )
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def send_with_attachments_handler(
    config: Config,
    logger: logging.Logger,
    to: str,
    subject: str,
    body_text: str,
    attachments: List[str],
    draft_mode: bool = True,
) -> str:
    """Send or draft an email with local file attachments (20 MB cap)."""
    try:
        if not validate_email(to):
            return f"Error: Invalid email format: {to}"
        if not attachments:
            return "Error: attachments must list at least one local file."

        message = _create_message_with_attachments(to, subject, body_text, attachments)
        service = build("gmail", "v1", credentials=get_creds(config))
        names = ", ".join(Path(item).name for item in attachments)

        if draft_mode:
            draft = service.users().drafts().create(
                userId="me", body={"message": message}
            ).execute()
            return (
                f"EMAIL DRAFT CREATED (ID: {draft['id']})\n\n"
                f"To: {to}\nSubject: {subject}\nAttachments: {names}\n\n"
                "Saved as a draft, not sent."
            )

        sent = service.users().messages().send(userId="me", body=message).execute()
        logger.info("Email with attachments sent: %s", sent.get("id"))
        return f"Email sent with {len(attachments)} attachment(s). Message Id: {sent.get('id')}"
    except Exception as e:
        return f"Error sending email with attachments: {str(e)}"
