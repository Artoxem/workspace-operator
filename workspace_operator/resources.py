"""MCP resources: read-only views of Drive, Gmail, Calendar, Sheets and Docs."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import List

import mcp.types as types
from mcp.server.lowlevel.helper_types import ReadResourceContents
from pydantic import AnyUrl

from .config import Config
from .handlers import document_to_text
from .text import clean_text, format_timestamp, parse_email_date


def list_resources() -> List[types.Resource]:
    return [
        types.Resource(
            uri="gdrive://recent",
            name="Recent Google Drive Files",
            description="Lists the 20 most recently modified files in Google Drive",
            mime_type="text/plain",
        ),
        types.Resource(
            uri="gmail://inbox",
            name="Gmail Inbox",
            description="Recent unread messages in the Gmail inbox",
            mime_type="text/plain",
        ),
        types.Resource(
            uri="gcalendar://upcoming",
            name="Upcoming Calendar Events",
            description="Upcoming events from the primary Google Calendar (next 7 days)",
            mime_type="text/plain",
        ),
    ]


def list_resource_templates() -> List[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            uri_template="gdrive://file/{file_id}",
            name="Google Drive File",
            description="Metadata for a specific Google Drive file (ID required)",
            mime_type="text/plain",
        ),
        types.ResourceTemplate(
            uri_template="gsheets://{spreadsheet_id}/{range}",
            name="Google Sheets Range",
            description=(
                "Data from a specific spreadsheet range, e.g. "
                "gsheets://SPREADSHEET_ID/Sheet1!A1:Z100"
            ),
            mime_type="text/plain",
        ),
        types.ResourceTemplate(
            uri_template="gdocs://{document_id}",
            name="Google Document",
            description="Full text content of a specific Google Doc (ID required)",
            mime_type="text/plain",
        ),
    ]


async def read_resource(config: Config, uri: AnyUrl) -> Iterable[ReadResourceContents]:
    from googleapiclient.discovery import build

    from .auth import get_creds

    uri_str = str(uri)

    def _fetch() -> str:
        if uri_str == "gdrive://recent":
            creds = get_creds(config)
            svc = build("drive", "v3", credentials=creds)
            results = svc.files().list(
                orderBy="modifiedTime desc",
                pageSize=20,
                fields="files(id,name,mimeType,modifiedTime,owners)",
            ).execute()
            files = results.get("files", [])
            if not files:
                return "No files found."
            lines = ["Recent Google Drive files (by last modified):\n"]
            for f in files:
                owners = f.get("owners", [{}])
                owner = owners[0].get("emailAddress", "?") if owners else "?"
                lines.append(
                    f"- {f['name']} (ID: {f['id']}) [{f.get('mimeType', '?')}] "
                    f"modified={format_timestamp(f.get('modifiedTime'))} owner={owner}"
                )
            return "\n".join(lines)

        elif uri_str == "gmail://inbox":
            creds = get_creds(config)
            svc = build("gmail", "v1", credentials=creds)
            results = svc.users().messages().list(
                userId="me", maxResults=20, q="is:unread in:inbox"
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return "No unread messages in inbox."
            lines = [f"Unread inbox messages ({len(messages)}):\n"]
            for msg in messages:
                full = svc.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                hdrs = {
                    h["name"]: h["value"]
                    for h in full.get("payload", {}).get("headers", [])
                }
                lines.append(
                    f"- [{msg['id']}] {parse_email_date(hdrs.get('Date'))} | "
                    f"{clean_text(hdrs.get('From'))} | "
                    f"{clean_text(hdrs.get('Subject')) or '(no subject)'}"
                )
            return "\n".join(lines)

        elif uri_str == "gcalendar://upcoming":
            creds = get_creds(config)
            svc = build("calendar", "v3", credentials=creds)
            now = datetime.now(timezone.utc)
            time_max = (now + timedelta(days=7)).isoformat()
            results = svc.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max,
                maxResults=25,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = results.get("items", [])
            if not events:
                return "No upcoming events in the next 7 days."
            lines = ["Upcoming calendar events (next 7 days):\n"]
            for ev in events:
                start = ev.get("start", {}).get(
                    "dateTime", ev.get("start", {}).get("date", "?")
                )
                lines.append(
                    f"- {start} | {ev.get('summary', '(no title)')} (ID: {ev.get('id')})"
                )
            return "\n".join(lines)

        elif uri_str.startswith("gdrive://file/"):
            file_id = uri_str.removeprefix("gdrive://file/")
            if not file_id:
                raise ValueError("file_id is required in gdrive://file/{file_id}")
            creds = get_creds(config)
            svc = build("drive", "v3", credentials=creds)
            f = svc.files().get(
                fileId=file_id,
                fields="id,name,mimeType,size,createdTime,modifiedTime,owners,webViewLink,parents",
            ).execute()
            owners = f.get("owners", [{}])
            owner = owners[0].get("emailAddress", "?") if owners else "?"
            size_bytes = int(f.get("size", 0))
            return (
                f"File: {f.get('name')}\n"
                f"ID: {f.get('id')}\n"
                f"Type: {f.get('mimeType')}\n"
                f"Size: {size_bytes:,} bytes\n"
                f"Created: {format_timestamp(f.get('createdTime'))}\n"
                f"Modified: {format_timestamp(f.get('modifiedTime'))}\n"
                f"Owner: {owner}\n"
                f"Link: {f.get('webViewLink', 'N/A')}"
            )

        elif uri_str.startswith("gsheets://"):
            # URI form: gsheets://{spreadsheet_id}/{range}
            remainder = uri_str.removeprefix("gsheets://")
            parts = remainder.split("/", 1)
            spreadsheet_id = parts[0]
            range_name = parts[1] if len(parts) > 1 else "Sheet1"
            if not spreadsheet_id:
                raise ValueError("spreadsheet_id is required in gsheets://{spreadsheet_id}/{range}")
            creds = get_creds(config)
            svc = build("sheets", "v4", credentials=creds)
            result = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
            values = result.get("values", [])
            if not values:
                return "No data found."
            rows = [
                "| " + " | ".join(str(c) for c in row) + " |"
                for row in values
            ]
            return f"Sheet data ({range_name}):\n" + "\n".join(rows)

        elif uri_str.startswith("gdocs://"):
            document_id = uri_str.removeprefix("gdocs://")
            if not document_id:
                raise ValueError("document_id is required in gdocs://{document_id}")
            creds = get_creds(config)
            svc = build("docs", "v1", credentials=creds)
            doc = svc.documents().get(documentId=document_id).execute()
            return (
                f"Document: {doc.get('title')}\n\n"
                f"{document_to_text(doc) or '(the document has no readable text)'}"
            )

        else:
            raise ValueError(f"Unknown resource URI scheme: {uri_str}")

    text = await asyncio.to_thread(_fetch)
    return [ReadResourceContents(content=text, mime_type="text/plain")]
