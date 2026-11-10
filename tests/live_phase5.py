"""Live checks for the v1.18 tools (self-cleaning)."""

import asyncio
import os
import re
import sys
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


def delete_filter(filter_id: str) -> None:
    from googleapiclient.discovery import build

    from workspace_operator.auth import get_creds
    from workspace_operator.config import load_config

    service = build("gmail", "v1", credentials=get_creds(load_config()))
    service.users().settings().filters().delete(userId="me", id=filter_id).execute()


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
    cleanup = {"sheet": None, "deck": None, "event": None, "draft": None, "filter": None}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                sheet = text(await session.call_tool("create_spreadsheet", {"title": "Phase five smoke"}))
                sheet_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", sheet)
                cleanup["sheet"] = sheet_id
                await session.call_tool(
                    "update_sheet",
                    {
                        "spreadsheet_id": sheet_id,
                        "range_name": "A1:C3",
                        "values": [["Name", "Score", "Status"], ["A", "10", "ok"], ["B", "20", "ok"]],
                    },
                )

                validation = text(
                    await session.call_tool(
                        "sheet_set_data_validation",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "C2:C3",
                            "values": ["ok", "fail"],
                            "strict": True,
                        },
                    )
                )
                record(
                    "sheet_set_data_validation",
                    "Data validation set" in validation and "list of 2" in validation,
                    validation,
                )

                protection = text(
                    await session.call_tool(
                        "sheet_protect_range",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "A1:C1",
                            "description": "header",
                            "warning_only": True,
                        },
                    )
                )
                record("sheet_protect_range", "Protected A1:C1" in protection, protection[:60])

                borders = text(
                    await session.call_tool(
                        "sheet_set_borders",
                        {"spreadsheet_id": sheet_id, "range": "A1:C3", "style": "SOLID"},
                    )
                )
                record("sheet_set_borders", "Borders applied" in borders, borders[:60])

                filters = text(await session.call_tool("gmail_list_filters", {}))
                record(
                    "gmail_list_filters",
                    filters.startswith("Filters (") or filters == "No filters configured.",
                    filters.splitlines()[0],
                )

                created = text(
                    await session.call_tool(
                        "gmail_create_filter",
                        {
                            "query": "subject:workspace-operator-smoke",
                            "add_labels": ["STARRED"],
                        },
                    )
                )
                if "insufficient" in created.lower():
                    print(
                        "[SKIP] gmail_create_filter — token lacks gmail.settings.basic; "
                        "delete token.json and re-authorize to test it"
                    )
                else:
                    cleanup["filter"] = grab(r"ID:\s*([A-Za-z0-9_-]+)", created)
                    record("gmail_create_filter", "Filter created" in created, cleanup["filter"])

                draft = text(
                    await session.call_tool(
                        "send_email",
                        {
                            "to": "artoxem@gmail.com",
                            "subject": "Phase five draft",
                            "body_text": "before update",
                        },
                    )
                )
                cleanup["draft"] = grab(r"ID:\s*([A-Za-z0-9_-]+)", draft)
                updated = text(
                    await session.call_tool(
                        "gmail_update_draft",
                        {
                            "draft_id": cleanup["draft"],
                            "to": "artoxem@gmail.com",
                            "subject": "Phase five draft (updated)",
                            "body_text": "after update",
                        },
                    )
                )
                record("gmail_update_draft", "updated" in updated.lower(), updated.splitlines()[0])

                deck = text(await session.call_tool("slides_create", {"title": "Phase five deck"}))
                deck_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", deck)
                cleanup["deck"] = deck_id
                await session.call_tool(
                    "slides_add_slide", {"presentation_id": deck_id, "layout": "BLANK"}
                )
                structure = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                slide_id = re.findall(r"^\d+\. \[([A-Za-z0-9_-]+)\]", structure, re.M)[-1]
                shape = text(
                    await session.call_tool(
                        "slides_add_shape",
                        {
                            "presentation_id": deck_id,
                            "slide_id": slide_id,
                            "shape_type": "ROUND_RECTANGLE",
                            "text": "phase five",
                            "width": 300,
                            "height": 100,
                        },
                    )
                )
                record("slides_add_shape", "Shape added" in shape, shape[:70])

                event = text(
                    await session.call_tool(
                        "create_event",
                        {
                            "summary": "Phase five event",
                            "start_time": "2026-12-02T10:00:00Z",
                            "end_time": "2026-12-02T11:00:00Z",
                        },
                    )
                )
                cleanup["event"] = grab(r"ID:\s*([A-Za-z0-9_-]+)", event)
                coloured = text(
                    await session.call_tool(
                        "calendar_set_event_color",
                        {"event_id": cleanup["event"], "color_id": "5"},
                    )
                )
                record(
                    "calendar_set_event_color",
                    "colour set to 5" in coloured,
                    coloured.splitlines()[0],
                )
            finally:
                for key in ("sheet", "deck"):
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
                        await session.call_tool(
                            "gmail_delete_draft",
                            {"draft_id": cleanup["draft"], "confirm": True},
                        )
                    except Exception:
                        pass
                if cleanup["event"]:
                    try:
                        await session.call_tool(
                            "calendar_delete_event",
                            {"event_id": cleanup["event"], "confirm": True},
                        )
                    except Exception:
                        pass

    if cleanup["filter"]:
        try:
            delete_filter(cleanup["filter"])
        except Exception as exc:  # pragma: no cover - best effort
            print("filter cleanup failed:", exc)

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    failed = [name for name, ok in RESULTS if not ok]
    if failed:
        print("failed:", ", ".join(failed))
        raise SystemExit(1)


asyncio.run(main())
