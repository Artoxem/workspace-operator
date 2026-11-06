"""Cross-product search across Google Drive, Gmail and Calendar.

This is the local counterpart of the ``search_corpus`` tool exposed by Google's
managed Workspace MCP servers: one query, several products, one ranked answer.

Everything runs through the user's own OAuth token — no Google-hosted MCP
endpoint is involved, so the query never leaves the machine except as ordinary
Drive / Gmail / Calendar API calls.
"""

import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config

DEFAULT_SOURCES = ("drive", "gmail")
VALID_SOURCES = ("drive", "gmail", "calendar")
MAX_LIMIT = 25


def _escape_drive_term(term: str) -> str:
    """Escape a literal term for a Drive ``contains`` clause."""
    return term.replace("\\", "\\\\").replace("'", "\\'")


def _parse_sources(sources: Optional[Sequence[str] | str]) -> List[str]:
    if sources is None:
        return list(DEFAULT_SOURCES)

    if isinstance(sources, str):
        raw_items = sources.split(",")
    else:
        raw_items = [str(item) for item in sources]

    parsed: List[str] = []
    for item in raw_items:
        name = item.strip().lower()
        if not name:
            continue
        if name not in VALID_SOURCES:
            raise ValueError(
                f"Unknown search source {name!r}. "
                f"Valid sources: {', '.join(VALID_SOURCES)}."
            )
        if name not in parsed:
            parsed.append(name)

    return parsed or list(DEFAULT_SOURCES)


def _clamp_limit(limit: Any) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 10
    return max(1, min(value, MAX_LIMIT))


def _format_date(value: Optional[datetime]) -> str:
    if value is None:
        return "unknown date"
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _drive_item(file: Dict[str, Any]) -> Dict[str, Any]:
    mime = file.get("mimeType", "unknown")
    short_mime = mime.split(".")[-1].replace("vnd.google-apps.", "") or "file"
    return {
        "source": "drive",
        "title": file.get("name") or "(untitled)",
        "id": file.get("id", ""),
        "date": _parse_iso(file.get("modifiedTime")),
        "detail": f"type: {short_mime}",
        "link": file.get("webViewLink", ""),
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _gmail_item(message: Dict[str, Any], headers: Dict[str, str], snippet: str) -> Dict[str, Any]:
    raw_date = headers.get("Date", "")
    date: Optional[datetime] = None
    try:
        date = parsedate_to_datetime(raw_date) if raw_date else None
    except (TypeError, ValueError):
        date = None

    if date is None:
        internal = message.get("internalDate")
        if internal:
            try:
                date = datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                date = None

    sender = headers.get("From", "")
    return {
        "source": "gmail",
        "title": headers.get("Subject") or "(no subject)",
        "id": message.get("id", ""),
        "date": date,
        "detail": f"from: {sender}" if sender else "gmail message",
        "link": f"https://mail.google.com/mail/u/0/#all/{message.get('id', '')}",
        "snippet": snippet,
    }


def _calendar_item(event: Dict[str, Any]) -> Dict[str, Any]:
    start = event.get("start", {})
    start_raw = start.get("dateTime") or start.get("date")
    attendees = event.get("attendees") or []
    people = ", ".join(a.get("email", "") for a in attendees[:3])
    detail = f"attendees: {people}" if people else "calendar event"
    return {
        "source": "calendar",
        "title": event.get("summary") or "(no title)",
        "id": event.get("id", ""),
        "date": _parse_iso(start_raw),
        "detail": detail,
        "link": event.get("htmlLink", ""),
    }


def _search_drive(creds, query: str, limit: int) -> List[Dict[str, Any]]:
    service = build("drive", "v3", credentials=creds)
    term = _escape_drive_term(query)
    results = (
        service.files()
        .list(
            q=f"(name contains '{term}' or fullText contains '{term}') and trashed = false",
            pageSize=limit,
            orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,modifiedTime,webViewLink)",
        )
        .execute()
    )
    return [_drive_item(file) for file in results.get("files", [])]


def _search_gmail(creds, query: str, limit: int) -> List[Dict[str, Any]]:
    service = build("gmail", "v1", credentials=creds)
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit)
        .execute()
    )
    items: List[Dict[str, Any]] = []
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
        snippet = full.get("snippet", "")[:160]
        items.append(_gmail_item(message, headers, snippet))
    return items


def _search_calendar(
    creds, query: str, limit: int, days_back: int, days_ahead: int
) -> List[Dict[str, Any]]:
    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    results = (
        service.events()
        .list(
            calendarId="primary",
            q=query,
            timeMin=(now - timedelta(days=days_back)).isoformat(),
            timeMax=(now + timedelta(days=days_ahead)).isoformat(),
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [_calendar_item(event) for event in results.get("items", [])]


def _render(query: str, items: List[Dict[str, Any]], errors: List[str]) -> str:
    if not items and not errors:
        return f"No results for '{query}'."

    counts: Dict[str, int] = {}
    for item in items:
        counts[item["source"]] = counts.get(item["source"], 0) + 1
    summary = ", ".join(f"{source} ({count})" for source, count in sorted(counts.items()))

    lines = [
        f"Workspace search: '{query}' — {len(items)} result(s)"
        + (f" [{summary}]" if summary else ""),
        "",
    ]

    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. [{item['source']}] {item['title']}")
        lines.append(f"   {_format_date(item['date'])} | {item['detail']} | id: {item['id']}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet']}")
        if item.get("link"):
            lines.append(f"   {item['link']}")

    if errors:
        lines.append("")
        lines.append("Partial results — source errors:")
        lines.extend(f"  - {error}" for error in errors)

    return "\n".join(lines)


def workspace_search_handler(
    config: Config,
    logger: logging.Logger,
    query: str,
    sources: Optional[Sequence[str] | str] = None,
    limit: int = 10,
    calendar_days_back: int = 30,
    calendar_days_ahead: int = 180,
) -> str:
    """Search Drive, Gmail and Calendar with a single query.

    Partial failures are reported instead of aborting: if Drive works and Gmail
    raises, the caller still gets the Drive hits plus an error note.
    """
    try:
        if not query or not str(query).strip():
            return "Error: query is required for workspace_search."
        query = str(query).strip()
        per_source_limit = _clamp_limit(limit)
        selected = _parse_sources(sources)

        logger.info(
            "workspace_search query=%r sources=%s limit=%s",
            query,
            ",".join(selected),
            per_source_limit,
        )

        creds = get_creds(config)
        items: List[Dict[str, Any]] = []
        errors: List[str] = []

        if "drive" in selected:
            try:
                items.extend(_search_drive(creds, query, per_source_limit))
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                logger.warning("workspace_search drive failed: %s", exc)
                errors.append(f"drive: {exc}")

        if "gmail" in selected:
            try:
                items.extend(_search_gmail(creds, query, per_source_limit))
            except Exception as exc:  # noqa: BLE001
                logger.warning("workspace_search gmail failed: %s", exc)
                errors.append(f"gmail: {exc}")

        if "calendar" in selected:
            try:
                items.extend(
                    _search_calendar(
                        creds,
                        query,
                        per_source_limit,
                        int(calendar_days_back),
                        int(calendar_days_ahead),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("workspace_search calendar failed: %s", exc)
                errors.append(f"calendar: {exc}")

        items.sort(key=lambda item: item["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return _render(query, items, errors)
    except Exception as exc:  # noqa: BLE001
        return f"Error searching workspace: {exc}"
