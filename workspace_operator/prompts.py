"""MCP prompts: scenario prompts that fetch live data and wrap it in instructions.

The prompt definitions (names, descriptions, arguments) are data in
``workspace_operator/definitions/prompts.json``; this module builds the messages.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

import mcp.types as types

from .config import Config
from .definitions import load_prompts
from .google_clients import api_client
from .handlers import (
    compare_tables_handler,
    digest_handler,
    gmail_search_and_summarize_handler,
)
from .text import clean_text, format_timestamp, parse_email_date


def list_prompts() -> List[types.Prompt]:
    """Scenario prompts offered to MCP clients."""
    return load_prompts()


async def get_prompt(
    config: Config, logger: logging.Logger, name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:


    args = arguments or {}

    if name == "summarize_inbox":
        query = args.get("query", "is:unread in:inbox")
        max_results = int(args.get("max_results", "20"))

        def _fetch_emails() -> str:
            svc = api_client(config, 'gmail', 'v1')
            results = svc.users().messages().list(
                userId="me", maxResults=min(max_results, 50), q=query
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return f"No messages found for query: {query}"
            lines = [f"Found {len(messages)} message(s) for '{query}':\n"]
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
                snippet = clean_text(full.get("snippet", ""), limit=140)
                lines.append(
                    f"\n---\nID: {msg['id']}\n"
                    f"Date: {parse_email_date(hdrs.get('Date'))}\n"
                    f"From: {clean_text(hdrs.get('From'), single_line=True)}\n"
                    f"Subject: {clean_text(hdrs.get('Subject'), single_line=True) or '(no subject)'}\n"
                    f"Preview: {snippet}"
                )
            return "\n".join(lines)

        email_data = await asyncio.to_thread(_fetch_emails)
        return types.GetPromptResult(
            description=f"Gmail inbox summary — query: {query}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"Here are the recent emails from Gmail (query: '{query}'):\n\n"
                            f"{email_data}\n\n"
                            "Please summarize these emails, grouping by sender or topic where "
                            "relevant. Highlight any urgent or action-required items."
                        ),
                    ),
                )
            ],
        )

    elif name == "analyze_spreadsheet":
        spreadsheet_id = args.get("spreadsheet_id", "")
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id is required for the analyze_spreadsheet prompt")
        range_name = args.get("range", "Sheet1")

        def _fetch_sheet() -> tuple[str, str]:
            svc = api_client(config, 'sheets', 'v4')
            meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            title = meta.get("properties", {}).get("title", spreadsheet_id)
            result = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
            values = result.get("values", [])
            if not values:
                return title, "No data found in the specified range."
            rows = [
                "| " + " | ".join(str(c) for c in row) + " |"
                for row in values[:200]
            ]
            return title, "\n".join(rows)

        title, sheet_data = await asyncio.to_thread(_fetch_sheet)
        return types.GetPromptResult(
            description=f"Analysis prompt for spreadsheet: {title}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"Here is data from Google Spreadsheet '{title}' "
                            f"(range: {range_name}):\n\n"
                            f"{sheet_data}\n\n"
                            "Please analyse this data. Identify patterns, trends, and notable "
                            "insights. If there are headers in the first row, use them to "
                            "understand the data structure."
                        ),
                    ),
                )
            ],
        )

    elif name == "plan_week":
        days_ahead = int(args.get("days_ahead", "7"))

        def _fetch_events() -> str:
            svc = api_client(config, 'calendar', 'v3')
            now = datetime.now(timezone.utc)
            time_max = (now + timedelta(days=days_ahead)).isoformat()
            results = svc.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = results.get("items", [])
            if not events:
                return f"No events in the next {days_ahead} days."
            lines = [f"Calendar events for the next {days_ahead} days:\n"]
            for ev in events:
                start = ev.get("start", {}).get(
                    "dateTime", ev.get("start", {}).get("date", "?")
                )
                end = ev.get("end", {}).get(
                    "dateTime", ev.get("end", {}).get("date", "?")
                )
                attendees = ev.get("attendees", [])
                att_list = (
                    ", ".join(a.get("email", "") for a in attendees[:5])
                    if attendees
                    else "none"
                )
                lines.append(
                    f"- {start} → {end}\n"
                    f"  Title: {ev.get('summary', '(no title)')}\n"
                    f"  Attendees: {att_list}\n"
                    f"  ID: {ev.get('id')}"
                )
            return "\n".join(lines)

        events_data = await asyncio.to_thread(_fetch_events)
        return types.GetPromptResult(
            description=f"Weekly planning — next {days_ahead} days",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"{events_data}\n\n"
                            "Based on these calendar events, please help me plan my week. "
                            "Identify busy periods, suggest preparation for important meetings, "
                            "and highlight any scheduling conflicts or time blocks that need "
                            "attention."
                        ),
                    ),
                )
            ],
        )

    elif name == "search_drive":
        query = args.get("query", "")
        if not query:
            raise ValueError("query is required for the search_drive prompt")
        limit = int(args.get("limit", "20"))

        def _fetch_drive() -> str:
            svc = api_client(config, 'drive', 'v3')
            results = svc.files().list(
                q=query,
                pageSize=min(limit, 50),
                fields="files(id,name,mimeType,modifiedTime,owners,webViewLink)",
            ).execute()
            files = results.get("files", [])
            if not files:
                return f"No files found for: {query}"
            lines = [f"Found {len(files)} file(s) for query '{query}':\n"]
            for f in files:
                owners = f.get("owners", [{}])
                owner = owners[0].get("emailAddress", "?") if owners else "?"
                lines.append(
                    f"- {f.get('name')}\n"
                    f"  ID: {f.get('id')} | Type: {f.get('mimeType', '?')}\n"
                    f"  Modified: {format_timestamp(f.get('modifiedTime'))} | Owner: {owner}\n"
                    f"  Link: {f.get('webViewLink', 'N/A')}"
                )
            return "\n".join(lines)

        drive_data = await asyncio.to_thread(_fetch_drive)
        return types.GetPromptResult(
            description=f"Drive search results — query: {query}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"{drive_data}\n\n"
                            "Please review these Google Drive files and provide a summary "
                            "report. Group related files, identify the most recently modified "
                            "ones, and suggest any organisation improvements if relevant."
                        ),
                    ),
                )
            ],
        )

    elif name == "weekly_review":
        days = max(1, int(args.get("days_back", "7")))
        digest_text = await asyncio.to_thread(
            digest_handler,
            config,
            logger,
            "gmail,calendar,drive",
            days * 24,
            15,
            "text",
            None,
        )
        return types.GetPromptResult(
            description=f"Weekly review — last {days} days",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"{digest_text}\n\n"
                            "Review this week: what needs a decision, which threads "
                            "are waiting on someone, what changed unexpectedly, and "
                            "which three things deserve attention first."
                        ),
                    ),
                )
            ],
        )

    elif name == "inbox_triage":
        query = args.get("query", "is:unread in:inbox")
        max_results = int(args.get("max_results", "15"))
        listing = await asyncio.to_thread(
            gmail_search_and_summarize_handler, config, logger, query, max_results
        )
        return types.GetPromptResult(
            description=f"Inbox triage — query: {query}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"{listing}\n\n"
                            "Triage these messages into: needs a reply today, waiting "
                            "on someone else, informational, and archive candidates. "
                            "For each, give one line of reasoning. Do not send or delete "
                            "anything — propose actions only."
                        ),
                    ),
                )
            ],
        )

    elif name == "compare_brief":
        spreadsheet_id = args.get("spreadsheet_id", "")
        range_a = args.get("range_a", "")
        range_b = args.get("range_b", "")
        if not (spreadsheet_id and range_a and range_b):
            raise ValueError(
                "spreadsheet_id, range_a and range_b are required for compare_brief"
            )
        diff = await asyncio.to_thread(
            compare_tables_handler,
            config,
            logger,
            spreadsheet_id,
            range_a,
            range_b,
            None,
            args.get("key_column", "1"),
            True,
            "text",
            None,
        )
        return types.GetPromptResult(
            description=f"Reconciliation brief — {range_a} vs {range_b}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=(
                            f"{diff}\n\n"
                            "Explain this diff in business terms: which changes look "
                            "intentional, which look like errors, and what should be "
                            "checked before applying the new data."
                        ),
                    ),
                )
            ],
        )

    else:
        raise ValueError(f"Unknown prompt: {name}")
