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


def create_event_handler(
    config: Config,
    logger: logging.Logger,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    try:
        creds = get_creds(config)
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
        }

        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"Event created: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error creating event: {str(e)}"


def calendar_find_free_slots_handler(
    config: Config,
    logger: logging.Logger,
    calendar_id: str,
    start_time: str,
    end_time: str,
    duration_minutes: int = 30,
    max_results: int = 5,
) -> str:
    """Find free time slots in a calendar between start and end."""
    try:
        creds = get_creds(config)
        service = build("calendar", "v3", credentials=creds)

        time_min = start_time
        time_max = end_time

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        def to_dt(dt: Optional[str]):
            if not dt:
                return None
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))

        start_dt = to_dt(start_time)
        end_dt = to_dt(end_time)
        if not start_dt or not end_dt:
            return "Error: Invalid start_time or end_time."

        busy = []
        for event in events:
            s = event.get("start", {}).get("dateTime") or event.get("start", {}).get(
                "date"
            )
            e = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
            s_dt = to_dt(s if "T" in str(s) else f"{s}T00:00:00+00:00")
            e_dt = to_dt(e if "T" in str(e) else f"{e}T00:00:00+00:00")
            if s_dt and e_dt:
                busy.append((s_dt, e_dt))

        busy.sort(key=lambda x: x[0])

        slots = []
        cursor = start_dt
        duration = timedelta(minutes=duration_minutes)

        for s_dt, e_dt in busy:
            if cursor + duration <= s_dt:
                slots.append((cursor, s_dt))
                if len(slots) >= max_results:
                    break
            if e_dt > cursor:
                cursor = e_dt

        if len(slots) < max_results and cursor + duration <= end_dt:
            slots.append((cursor, end_dt))

        if not slots:
            return "No free slots found."

        output = f"Free slots (duration {duration_minutes} min):\n"
        for s_dt, e_dt in slots[:max_results]:
            if s_dt.date() == e_dt.date():
                label = (
                    f"{s_dt.strftime('%Y-%m-%d %H:%M')}–"
                    f"{e_dt.strftime('%H:%M')} ({_offset(s_dt)})"
                )
            else:
                label = (
                    f"{s_dt.strftime('%Y-%m-%d %H:%M')} ({_offset(s_dt)}) → "
                    f"{e_dt.strftime('%Y-%m-%d %H:%M')} ({_offset(e_dt)})"
                )
            output += f"- {label}\n"

        logger.info(
            "Free slots found: %s between %s and %s", len(slots), start_time, end_time
        )
        return output
    except Exception as e:
        logger.error("Error finding free slots: %s", str(e))
        return f"Error finding free slots: {str(e)}"


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
        return f"✅ Meeting created: {created.get('htmlLink')}"
    except Exception as e:
        logger.error("Error creating meeting: %s", str(e))
        return f"Error creating meeting: {str(e)}"
