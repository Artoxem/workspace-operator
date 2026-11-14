import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..security import validate_email
from ..text import clean_text


def _parse_event_time(value: dict) -> tuple[datetime | None, str, bool]:
    """Return (datetime, label, all_day) for a Google Calendar start/end."""
    if value.get("date"):
        try:
            parsed = datetime.fromisoformat(value["date"])
        except ValueError:
            return None, value["date"], True
        return parsed, parsed.strftime("%Y-%m-%d"), True

    stamp = value.get("dateTime")
    if not stamp:
        return None, "unknown time", False

    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None, stamp, False
    return parsed, parsed.strftime("%Y-%m-%d %H:%M"), False


def _offset(parsed: datetime) -> str:
    raw = parsed.strftime("%z")
    return f"{raw[:3]}:{raw[3:]}" if raw else "UTC"


def _format_event_line(event: dict) -> str:
    start_dt, start_label, start_all_day = _parse_event_time(event.get("start") or {})
    end_dt, end_label, end_all_day = _parse_event_time(event.get("end") or {})

    if start_all_day and end_all_day:
        if start_label and end_label and start_label != end_label:
            when = f"{start_label} → {end_label} (all day)"
        else:
            when = f"{start_label} (all day)"
    elif start_dt and end_dt and start_dt.date() == end_dt.date():
        when = f"{start_label}–{end_dt.strftime('%H:%M')} ({_offset(start_dt)})"
    elif start_dt and end_dt:
        when = (
            f"{start_label} ({_offset(start_dt)}) → "
            f"{end_label} ({_offset(end_dt)})"
        )
    else:
        when = f"{start_label} → {end_label}"

    parts = [f"- {when}", clean_text(event.get("summary"), single_line=True) or "(no title)"]
    if event.get("location"):
        parts.append(clean_text(event["location"], single_line=True))
    parts.append(f"ID: {event.get('id')}")
    return " | ".join(parts)


def list_events_handler(
    config: Config, logger: logging.Logger, calendar_id: str = "primary", max_results: int = 10
) -> str:
    try:
        creds = get_creds(config)
        service = build("calendar", "v3", credentials=creds)

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=datetime.now(timezone.utc).isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            return "No upcoming events found."

        lines = ["Upcoming events:"]
        lines.extend(_format_event_line(event) for event in events)
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing events: {str(e)}"






def calendar_create_meeting_handler(
    config: Config,
    logger: logging.Logger,
    summary: str,
    start_time: str,
    end_time: str,
    attendees: Optional[List[str]] = None,
    description: str = "",
    location: str = "",
    confirm: bool = False,
) -> str:
    """Create a calendar meeting with attendees (confirm required)."""
    try:
        if not confirm:
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                "This will create a calendar event and invite attendees.\n"
                "To proceed, call again with confirm=True."
            )

        creds = get_creds(config)
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
        }
        if attendees:
            event["attendees"] = [
                {"email": a} for a in attendees if validate_email(a)
            ]

        created = (
            service.events()
            .insert(calendarId="primary", body=event, sendUpdates="all")
            .execute()
        )
        logger.info("Meeting created: %s", created.get("id"))
        return (
            f"✅ Meeting created: {clean_text(created.get('summary')) or summary}\n"
            f"ID: {created.get('id')}\n"
            f"{created.get('htmlLink', '')}"
        )
    except Exception as e:
        logger.error("Error creating meeting: %s", str(e))
        return f"Error creating meeting: {str(e)}"


def list_calendars_handler(config: Config, logger: logging.Logger) -> str:
    try:
        service = build("calendar", "v3", credentials=get_creds(config))
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        if not items:
            return "No calendars found."

        lines = [f"Calendars ({len(items)}):"]
        for item in items:
            primary = " [primary]" if item.get("primary") else ""
            access = item.get("accessRole", "?")
            lines.append(f"- {item.get('summary')} ({access}){primary} — ID: {item.get('id')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing calendars: {str(e)}"


def move_event_handler(
    config: Config,
    logger: logging.Logger,
    event_id: str,
    destination_calendar_id: str,
    calendar_id: str = "primary",
) -> str:
    try:
        if not event_id or not destination_calendar_id:
            return "Error: event_id and destination_calendar_id are required."

        service = build("calendar", "v3", credentials=get_creds(config))
        event = (
            service.events()
            .move(
                calendarId=calendar_id,
                eventId=event_id,
                destination=destination_calendar_id,
            )
            .execute()
        )
        logger.info("Event %s moved to %s", event_id, destination_calendar_id)
        return (
            f"Event moved: {clean_text(event.get('summary')) or event_id}\n"
            f"Calendar: {destination_calendar_id}\n"
            f"{event.get('htmlLink', '')}"
        )
    except Exception as e:
        return f"Error moving event: {str(e)}"


def set_event_color_handler(
    config: Config,
    logger: logging.Logger,
    event_id: str,
    color_id: str,
    calendar_id: str = "primary",
) -> str:
    """Set the event colour by Google Calendar colour id ("1".."11")."""
    try:
        if not event_id:
            return "Error: event_id is required."
        value = str(color_id).strip()
        if not value.isdigit() or not 1 <= int(value) <= 11:
            return "Error: color_id must be a string from 1 to 11."

        service = build("calendar", "v3", credentials=get_creds(config))
        event = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body={"colorId": value})
            .execute()
        )
        logger.info("Event %s colour set to %s", event_id, value)
        return (
            f"Event colour set to {value}: "
            f"{clean_text(event.get('summary')) or event_id}"
        )
    except Exception as e:
        return f"Error setting event colour: {str(e)}"
