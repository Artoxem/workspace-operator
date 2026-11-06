"""Composite tool: one digest across Gmail, Calendar and Drive.

Collects the last N hours of mail, the upcoming agenda and recently modified
files, then renders a single text (or Google Doc) digest.

Collection is thin; rendering is a pure function over plain item dicts, so the
format is testable without Google.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text, format_timestamp, parse_email_date

VALID_SOURCES = ("gmail", "calendar", "drive")
SECTION_TITLES = {
    "gmail": "Email",
    "calendar": "Agenda",
    "drive": "Changed files",
}


def parse_sources(value: Optional[Sequence[str] | str]) -> List[str]:
    if value is None:
        return list(VALID_SOURCES)
    raw = value.split(",") if isinstance(value, str) else [str(item) for item in value]
    selected: List[str] = []
    for item in raw:
        name = item.strip().lower()
        if not name:
            continue
        if name not in VALID_SOURCES:
            raise ValueError(
                f"unknown source {name!r}; valid: {', '.join(VALID_SOURCES)}"
            )
        if name not in selected:
            selected.append(name)
    return selected or list(VALID_SOURCES)


def render_digest(
    title: str,
    hours: int,
    sections: Dict[str, List[Dict[str, str]]],
    limit: int,
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [title, "", f"Window: last {hours}h · generated {stamp}", ""]

    total = 0
    for source in VALID_SOURCES:
        items = sections.get(source, [])
        total += len(items)
        lines.append(f"## {SECTION_TITLES[source]} ({len(items)})")
        if not items:
            lines.append("- nothing")
        else:
            for item in items[:limit]:
                lines.append(f"- {item['title']}")
                if item.get("meta"):
                    lines.append(f"  {item['meta']}")
        lines.append("")

    lines.append(f"Total items: {total}")
    return "\n".join(lines)


def _collect_gmail(service, hours: int, limit: int) -> List[Dict[str, str]]:
    results = (
        service.users()
        .messages()
        .list(userId="me", q=f"newer_than:{hours}h", maxResults=limit)
        .execute()
    )
    items: List[Dict[str, str]] = []
    for message in results.get("messages", []):
        full = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        headers = {
            header["name"]: header["value"]
            for header in full.get("payload", {}).get("headers", [])
        }
        items.append(
            {
                "title": clean_text(headers.get("Subject"), single_line=True) or "(no subject)",
                "meta": f"{parse_email_date(headers.get('Date'))} · "
                f"{clean_text(headers.get('From'), single_line=True)}",
            }
        )
    return items


def _collect_calendar(service, hours: int, limit: int) -> List[Dict[str, str]]:
    now = datetime.now(timezone.utc)
    events = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(hours=hours)).isoformat(),
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )
    items: List[Dict[str, str]] = []
    for event in events:
        start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        meta = format_timestamp(start) if start and "T" in str(start) else str(start or "?")
        if event.get("location"):
            meta += f" · {clean_text(event['location'], single_line=True)}"
        items.append(
            {
                "title": clean_text(event.get("summary"), single_line=True) or "(no title)",
                "meta": meta,
            }
        )
    return items


def _collect_drive(service, hours: int, limit: int) -> List[Dict[str, str]]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = (
        service.files()
        .list(
            q=f"modifiedTime > '{since}' and trashed = false",
            orderBy="modifiedTime desc",
            pageSize=limit,
            fields="files(id,name,mimeType,modifiedTime)",
        )
        .execute()
        .get("files", [])
    )
    return [
        {
            "title": clean_text(file.get("name"), single_line=True) or "(untitled)",
            "meta": f"{format_timestamp(file.get('modifiedTime'))} · {file.get('mimeType', '?')}",
        }
        for file in files
    ]


def digest_handler(
    config: Config,
    logger: logging.Logger,
    sources: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 10,
    output: str = "text",
    doc_title: Optional[str] = None,
) -> str:
    try:
        hours = max(1, int(since_hours))
        per_source = max(1, min(int(limit), 50))
        selected = parse_sources(sources)
        mode = str(output or "text").lower()
        if mode not in {"text", "doc"}:
            return "Error: output must be 'text' or 'doc'."

        creds = get_creds(config)
        sections: Dict[str, List[Dict[str, str]]] = {}
        errors: List[str] = []

        collectors = {
            "gmail": lambda: _collect_gmail(build("gmail", "v1", credentials=creds), hours, per_source),
            "calendar": lambda: _collect_calendar(build("calendar", "v3", credentials=creds), hours, per_source),
            "drive": lambda: _collect_drive(build("drive", "v3", credentials=creds), hours, per_source),
        }

        for source in selected:
            try:
                sections[source] = collectors[source]()
            except Exception as exc:  # noqa: BLE001 - reported, not fatal
                logger.warning("digest %s failed: %s", source, exc)
                sections[source] = []
                errors.append(f"{source}: {exc}")

        title = doc_title or f"Digest {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
        content = render_digest(title, hours, sections, per_source)
        if errors:
            content += "\n\nPartial results — failures:\n" + "\n".join(f"- {error}" for error in errors)

        if mode == "text":
            logger.info("Digest rendered: sources=%s", ",".join(selected))
            return content

        docs = build("docs", "v1", credentials=creds)
        document = docs.documents().create(body={"title": title}).execute()
        document_id = document.get("documentId")
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()
        return (
            f"Digest created: {title}\n"
            f"Document ID: {document_id}\n"
            f"URL: https://docs.google.com/document/d/{document_id}/edit"
        )
    except Exception as e:
        return f"Error building digest: {str(e)}"
