"""Live checks for the v1.15 structural tools (self-cleaning)."""

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
    cleanup = {"sheet": None, "deck": None}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                sheet = text(await session.call_tool("create_spreadsheet", {"title": "Phase two smoke"}))
                sheet_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", sheet)
                cleanup["sheet"] = sheet_id
                await session.call_tool(
                    "update_sheet",
                    {
                        "spreadsheet_id": sheet_id,
                        "range_name": "A1:B3",
                        "values": [["Name", "Score"], ["Alpha", "10"], ["Beta", "30"]],
                    },
                )

                inserted = text(
                    await session.call_tool(
                        "sheet_insert_rows",
                        {"spreadsheet_id": sheet_id, "start_row": 2, "count": 1},
                    )
                )
                after_insert = text(
                    await session.call_tool(
                        "read_sheet", {"spreadsheet_id": sheet_id, "range_name": "A1:B4"}
                    )
                )
                record(
                    "sheet_insert_rows",
                    "Inserted 1 row(s)" in inserted and "Alpha" in after_insert.splitlines()[3],
                    "row 2 is empty, Alpha moved to 3",
                )

                preview = text(
                    await session.call_tool(
                        "sheet_delete_rows",
                        {"spreadsheet_id": sheet_id, "start_row": 2, "count": 1},
                    )
                )
                deleted = text(
                    await session.call_tool(
                        "sheet_delete_rows",
                        {
                            "spreadsheet_id": sheet_id,
                            "start_row": 2,
                            "count": 1,
                            "confirm": True,
                        },
                    )
                )
                after_delete = text(
                    await session.call_tool(
                        "read_sheet", {"spreadsheet_id": sheet_id, "range_name": "A1:B3"}
                    )
                )
                record(
                    "sheet_delete_rows",
                    "CONFIRMATION REQUIRED" in preview
                    and "Deleted 1 row" in deleted
                    and after_delete.splitlines()[2].startswith("| Alpha"),
                    "preview → confirm → Alpha back at row 2",
                )

                merged = text(
                    await session.call_tool(
                        "sheet_merge_cells",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "A4:B4",
                            "merge_type": "MERGE_ALL",
                        },
                    )
                )
                unmerged = text(
                    await session.call_tool(
                        "sheet_merge_cells",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "A4:B4",
                            "merge_type": "UNMERGE",
                        },
                    )
                )
                record(
                    "sheet_merge_cells",
                    "Merge All applied" in merged and "Unmerge applied" in unmerged,
                    "merge + unmerge",
                )

                await session.call_tool(
                    "add_sheet", {"spreadsheet_id": sheet_id, "title": "Extra"}
                )
                delete_preview = text(
                    await session.call_tool(
                        "sheet_delete_sheet",
                        {"spreadsheet_id": sheet_id, "sheet_name": "Extra"},
                    )
                )
                deleted_sheet = text(
                    await session.call_tool(
                        "sheet_delete_sheet",
                        {"spreadsheet_id": sheet_id, "sheet_name": "Extra", "confirm": True},
                    )
                )
                meta = text(
                    await session.call_tool(
                        "get_spreadsheet_meta", {"spreadsheet_id": sheet_id}
                    )
                )
                record(
                    "sheet_delete_sheet",
                    "CONFIRMATION REQUIRED" in delete_preview
                    and "deleted" in deleted_sheet
                    and "Extra" not in meta,
                    "tab removed",
                )

                deck = text(await session.call_tool("slides_create", {"title": "Phase two deck"}))
                deck_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", deck)
                cleanup["deck"] = deck_id
                await session.call_tool(
                    "slides_add_slide",
                    {"presentation_id": deck_id, "layout": "TITLE_AND_BODY"},
                )
                structure = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                ids = re.findall(r"^\d+\. \[([A-Za-z0-9_-]+)\]", structure, re.M)
                second = ids[1]
                moved = text(
                    await session.call_tool(
                        "slides_move_slide",
                        {"presentation_id": deck_id, "slide_id": second, "position": 1},
                    )
                )
                after_move = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                first_now = re.findall(r"^\d+\. \[([A-Za-z0-9_-]+)\]", after_move, re.M)[0]
                record(
                    "slides_move_slide",
                    "position 1 of 2" in moved and first_now == second,
                    "second slide became first",
                )

                notes = text(
                    await session.call_tool(
                        "slides_set_notes",
                        {
                            "presentation_id": deck_id,
                            "slide_id": second,
                            "notes": "phase two speaker notes",
                        },
                    )
                )
                record("slides_set_notes", "Speaker notes updated" in notes, notes[:60])

                labels = text(await session.call_tool("gmail_list_labels", {}))
                record(
                    "gmail_list_labels",
                    "Labels (" in labels and "System labels:" in labels,
                    labels.splitlines()[0],
                )

                trash_preview = text(
                    await session.call_tool("drive_empty_trash", {})
                )
                record(
                    "drive_empty_trash preview",
                    "CONFIRMATION REQUIRED" in trash_preview
                    and "cannot be undone" in trash_preview,
                    "no confirm sent — trash untouched",
                )
            finally:
                for value in cleanup.values():
                    if value:
                        try:
                            await session.call_tool(
                                "drive_delete_file", {"file_id": value, "confirm": True}
                            )
                        except Exception:
                            pass

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    failed = [name for name, ok in RESULTS if not ok]
    if failed:
        print("failed:", ", ".join(failed))
        raise SystemExit(1)


asyncio.run(main())
