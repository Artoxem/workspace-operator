"""Live checks for the v1.16 tools (self-cleaning)."""

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CFG = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
RESULTS = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def text(result) -> str:
    return "\n".join(getattr(block, "text", "") or "" for block in result.content)


def grab(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    if not match:
        raise RuntimeError(f"{pattern!r} not in {value[:200]}")
    return match.group(1)


def delete_draft(draft_id: str) -> None:
    from googleapiclient.discovery import build

    from workspace_operator.auth import get_creds
    from workspace_operator.config import load_config

    service = build("gmail", "v1", credentials=get_creds(load_config()))
    service.users().drafts().delete(userId="me", id=draft_id).execute()


async def main() -> None:
    env = os.environ.copy()
    env.update(
        MCP_CONFIG_FILE=str(REPO / "config.yaml"),
        MCP_AUTH_TOKEN=str(CFG["mcp_auth_token"]),
        MCP_TOOL_PROFILE="full",
        PYTHONDONTWRITEBYTECODE="1",
    )
    params = StdioServerParameters(
        command=sys.executable, args=[str(REPO / "server.py")], env=env
    )
    cleanup = {"sheet": None, "deck": None, "doc": None, "event": None, "draft": None}
    attachment = Path(tempfile.gettempdir()) / "wo live attachment.txt"

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                sheet = text(await session.call_tool("create_spreadsheet", {"title": "Phase three smoke"}))
                sheet_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", sheet)
                cleanup["sheet"] = sheet_id
                await session.call_tool(
                    "update_sheet",
                    {
                        "spreadsheet_id": sheet_id,
                        "range_name": "A1:B3",
                        "values": [["Name", "Score"], ["A", "30"], ["B", "10"]],
                    },
                )

                inserted = text(
                    await session.call_tool(
                        "sheet_insert_columns",
                        {"spreadsheet_id": sheet_id, "start_column": 1, "count": 1},
                    )
                )
                after_insert = text(
                    await session.call_tool(
                        "read_sheet", {"spreadsheet_id": sheet_id, "range_name": "A1:C1"}
                    )
                )
                preview = text(
                    await session.call_tool(
                        "sheet_delete_columns",
                        {"spreadsheet_id": sheet_id, "start_column": 1, "count": 1},
                    )
                )
                deleted = text(
                    await session.call_tool(
                        "sheet_delete_columns",
                        {
                            "spreadsheet_id": sheet_id,
                            "start_column": 1,
                            "count": 1,
                            "confirm": True,
                        },
                    )
                )
                record(
                    "sheet_insert_columns / delete_columns",
                    "Inserted 1 column" in inserted
                    and "| A" not in after_insert
                    and "CONFIRMATION REQUIRED" in preview
                    and "Deleted 1 column" in deleted,
                    "shift right, then back",
                )

                sorted_result = text(
                    await session.call_tool(
                        "sheet_sort_range",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "A2:B3",
                            "column": 2,
                            "ascending": True,
                        },
                    )
                )
                after_sort = text(
                    await session.call_tool(
                        "read_sheet", {"spreadsheet_id": sheet_id, "range_name": "A1:B3"}
                    )
                )
                rows = [line for line in after_sort.splitlines() if line.startswith("|")]
                ordered = next(
                    (index for index, row in enumerate(rows) if row.startswith("| B | 10")),
                    -1,
                )
                other = next(
                    (index for index, row in enumerate(rows) if row.startswith("| A | 30")),
                    -1,
                )
                record(
                    "sheet_sort_range",
                    "Sorted A2:B3" in sorted_result and 0 <= ordered < other,
                    "B/10 before A/30",
                )

                deck = text(await session.call_tool("slides_create", {"title": "Phase three deck"}))
                deck_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", deck)
                cleanup["deck"] = deck_id
                await session.call_tool(
                    "slides_add_slide", {"presentation_id": deck_id, "layout": "TITLE_AND_BODY"}
                )
                structure = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                slide_id = re.findall(r"^\d+\. \[([A-Za-z0-9_-]+)\]", structure, re.M)[-1]
                table = text(
                    await session.call_tool(
                        "slides_add_table",
                        {
                            "presentation_id": deck_id,
                            "slide_id": slide_id,
                            "rows": 2,
                            "columns": 3,
                        },
                    )
                )
                record("slides_add_table", "Table inserted" in table and "2×3" in table, table[:60])

                doc = text(await session.call_tool("create_doc", {"title": "Phase three doc"}))
                doc_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", doc)
                cleanup["doc"] = doc_id
                await session.call_tool(
                    "append_to_doc", {"document_id": doc_id, "text": "image below"}
                )
                image = text(
                    await session.call_tool(
                        "docs_insert_image",
                        {
                            "document_id": doc_id,
                            "image_url": (
                                "https://www.google.com/images/branding/googlelogo/2x/"
                                "googlelogo_color_272x92dp.png"
                            ),
                            "width": 120,
                        },
                    )
                )
                record("docs_insert_image", "Image inserted" in image, image[:70])

                calendars = text(await session.call_tool("calendar_list_calendars", {}))
                record(
                    "calendar_list_calendars",
                    "Calendars (" in calendars and "primary" in calendars,
                    calendars.splitlines()[0],
                )

                event = text(
                    await session.call_tool(
                        "create_event",
                        {
                            "summary": "Recurring smoke event",
                            "start_time": "2026-12-01T10:00:00Z",
                            "end_time": "2026-12-01T11:00:00Z",
                            "recurrence": ["RRULE:FREQ=DAILY;COUNT=2"],
                        },
                    )
                )
                event_id = grab(r"ID:\s*([A-Za-z0-9_-]+)", event)
                cleanup["event"] = event_id
                record("create_event recurrence", bool(event_id), f"ID {event_id[:10]}…")

                preview = text(
                    await session.call_tool(
                        "drive_transfer_ownership",
                        {"file_id": sheet_id, "email": "nobody@example.com"},
                    )
                )
                record(
                    "drive_transfer_ownership preview",
                    "CONFIRMATION REQUIRED" in preview and "lose owner rights" in preview,
                    "no confirm sent",
                )

                attachment.write_text("live attachment payload", encoding="utf-8")
                draft = text(
                    await session.call_tool(
                        "gmail_send_with_attachments",
                        {
                            "to": "artoxem@gmail.com",
                            "subject": "Workspace Operator attachment smoke",
                            "body_text": "draft with attachment",
                            "attachments": [str(attachment)],
                        },
                    )
                )
                cleanup["draft"] = grab(r"ID:\s*([A-Za-z0-9_-]+)", draft)
                record(
                    "gmail_send_with_attachments",
                    "EMAIL DRAFT CREATED" in draft and "wo live attachment.txt" in draft,
                    cleanup["draft"],
                )
            finally:
                if cleanup["event"]:
                    try:
                        await session.call_tool(
                            "calendar_delete_event",
                            {"event_id": cleanup["event"], "confirm": True},
                        )
                    except Exception:
                        pass
                for key in ("sheet", "deck", "doc"):
                    if cleanup[key]:
                        try:
                            await session.call_tool(
                                "drive_delete_file",
                                {"file_id": cleanup[key], "confirm": True},
                            )
                        except Exception:
                            pass

    if cleanup["draft"]:
        try:
            delete_draft(cleanup["draft"])
        except Exception as exc:  # pragma: no cover - cleanup best effort
            print("draft cleanup failed:", exc)
    if attachment.exists():
        attachment.unlink()

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    failed = [name for name, ok in RESULTS if not ok]
    if failed:
        print("failed:", ", ".join(failed))
        raise SystemExit(1)


asyncio.run(main())
