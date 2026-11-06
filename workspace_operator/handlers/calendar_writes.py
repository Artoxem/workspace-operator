"""Calendar writes: update, delete and answer invitations.

`create_event` and `calendar_create_meeting` already exist; these handlers cover
the rest of the lifecycle. Request bodies are built by pure helpers so the
"only change what was passed" behaviour is unit-testable.
"""

import logging
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

RESPONSES = {"accepted", "declined", "tentative"}
SEND_UPDATES = {"all", "externalOnly", "none"}


def build_event_patch(
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a patch body containing only the fields the caller provided."""
    body: Dict[str, Any] = {}
    if summary is not None:
        body["summary"] = summary
    if start_time is not None:
        body["start"] = {"dateTime": start_time, "timeZone": "UTC"}
    if end_time is not None:
        body["end"] = {"dateTime": end_time, "timeZone": "UTC"}
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if attendees is not None:
        body["attendees"] = [{"email": email} for email in attendees]
    return body


def set_attendee_response(
    event: Dict[str, Any], self_email: str, response: str
) -> tuple[List[Dict[str, Any]], bool]:
    """Return an attendee list with self's responseStatus set.

    The second value reports whether the calendar owner is on the guest list.
    """
    wanted = (self_email or "").strip().lower()
    attendees = [dict(attendee) for attendee in event.get("attendees", [])]
    found = False
    for attendee in attendees:
        if str(attendee.get("email", "")).lower() == wanted:
            attendee["responseStatus"] = response
            found = True
    return attendees, found


def _service(config: Config):
    return build("calendar", "v3", credentials=get_creds(config))


def calendar_update_event_handler(
    config: Config,
    logger: logging.Logger,
    event_id: str,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    send_updates: str = "none",
) -> str:
    try:
        body = build_event_patch(
            summary, start_time, end_time, description, location, attendees
        )
        if not body:
            return (
                "Error: nothing to update — pass at least one of summary, "
                "start_time, end_time, description, location, attendees."
            )

        notify = str(send_updates or "none")
        if notify not in SEND_UPDATES:
            return f"Error: send_updates must be one of {', '.join(sorted(SEND_UPDATES))}."

        service = _service(config)
        updated = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body, sendUpdates=notify)
            .execute()
        )

        logger.info("Event updated: %s fields=%s", event_id, ",".join(sorted(body)))
        return (
            f"Event updated: {clean_text(updated.get('summary')) or event_id}\n"
            f"ID: {updated.get('id')} | fields: {', '.join(sorted(body))}\n"
            f"{updated.get('htmlLink', '')}"
        )
    except Exception as e:
        return f"Error updating event: {str(e)}"


def calendar_delete_event_handler(
    config: Config,
    logger: logging.Logger,
    event_id: str,
    calendar_id: str = "primary",
    confirm: bool = False,
    send_updates: str = "none",
) -> str:
    try:
        if not confirm:
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will delete event {event_id} from calendar '{calendar_id}'.\n"
                "To proceed, call again with confirm=true."
            )

        notify = str(send_updates or "none")
        if notify not in SEND_UPDATES:
            return f"Error: send_updates must be one of {', '.join(sorted(SEND_UPDATES))}."

        service = _service(config)
        service.events().delete(
            calendarId=calendar_id, eventId=event_id, sendUpdates=notify
        ).execute()

        logger.info("Event deleted: %s", event_id)
        return f"Event {event_id} deleted from calendar '{calendar_id}'."
    except Exception as e:
        return f"Error deleting event: {str(e)}"


def calendar_respond_to_invite_handler(
    config: Config,
    logger: logging.Logger,
    event_id: str,
    response: str,
    calendar_id: str = "primary",
    confirm: bool = False,
    send_updates: str = "all",
) -> str:
    try:
        answer = str(response or "").strip().lower()
        if answer not in RESPONSES:
            return f"Error: response must be one of {', '.join(sorted(RESPONSES))}."

        if not confirm:
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will answer '{answer}' to event {event_id}.\n"
                "To proceed, call again with confirm=True."
            )

        notify = str(send_updates or "all")
        if notify not in SEND_UPDATES:
            return f"Error: send_updates must be one of {', '.join(sorted(SEND_UPDATES))}."

        service = _service(config)
        entry = service.calendarList().get(calendarId=calendar_id).execute()
        self_email = entry.get("id") or ""

        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        attendees, found = set_attendee_response(event, self_email, answer)
        if not found:
            return (
                f"Error: {self_email or 'your account'} is not on the guest list "
                f"of event {event_id}."
            )

        service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={"attendees": attendees},
            sendUpdates=notify,
        ).execute()

        logger.info("Invite %s: %s", event_id, answer)
        return (
            f"Answered '{answer}' to '{clean_text(event.get('summary')) or event_id}'.\n"
            f"ID: {event_id} | send_updates: {notify}"
        )
    except Exception as e:
        return f"Error responding to invite: {str(e)}"
