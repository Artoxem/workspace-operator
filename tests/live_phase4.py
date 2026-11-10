"""Live checks for the v1.17 tools (self-cleaning)."""

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
    cleanup = {"sheet": None, "doc": None, "deck": None, "shortcut": None, "draft": None}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                sheet = text(await session.call_tool("create_spreadsheet", {"title": "Phase four smoke"}))
                sheet_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", sheet)
                cleanup["sheet"] = sheet_id
                await session.call_tool(
                    "update_sheet",
                    {
                        "spreadsheet_id": sheet_id,
                        "range_name": "A1:C4",
                        "values": [
                            ["Region", "Product", "Amount"],
                            ["EU", "A", "10"],
                            ["EU", "B", "20"],
                            ["US", "A", "5"],
                        ],
                    },
                )
                pivot = text(
                    await session.call_tool(
                        "sheet_add_pivot_table",
                        {
                            "spreadsheet_id": sheet_id,
                            "source_range": "A1:C4",
                            "rows": [1],
                            "values": [3],
                            "aggregation": "SUM",
                            "target_sheet_name": "Pivot",
                        },
                    )
                )
                meta = text(
                    await session.call_tool("get_spreadsheet_meta", {"spreadsheet_id": sheet_id})
                )
                record(
                    "sheet_add_pivot_table",
                    "Pivot table created" in pivot and "Pivot" in meta,
                    pivot.splitlines()[0],
                )

                doc = text(await session.call_tool("create_doc", {"title": "Phase four doc"}))
                doc_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", doc)
                cleanup["doc"] = doc_id
                await session.call_tool(
                    "append_to_doc",
                    {"document_id": doc_id, "text": "Hello world\nhello again"},
                )
                preview = text(
                    await session.call_tool(
                        "docs_format_text",
                        {"document_id": doc_id, "find": "hello", "bold": True},
                    )
                )
                applied = text(
                    await session.call_tool(
                        "docs_format_text",
                        {
                            "document_id": doc_id,
                            "find": "hello",
                            "bold": True,
                            "confirm": True,
                        },
                    )
                )
                record(
                    "docs_format_text",
                    "CONFIRMATION REQUIRED" in preview
                    and "2 occurrence" in preview
                    and "Styled 2 occurrence" in applied,
                    "preview → bold",
                )

                deck = text(await session.call_tool("slides_create", {"title": "Phase four deck"}))
                deck_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", deck)
                cleanup["deck"] = deck_id
                layouts = text(
                    await session.call_tool("slides_list_layouts", {"presentation_id": deck_id})
                )
                record(
                    "slides_list_layouts",
                    "Layouts (" in layouts,
                    layouts.splitlines()[0],
                )

                draft = text(
                    await session.call_tool(
                        "send_email",
                        {
                            "to": "artoxem@gmail.com",
                            "subject": "Phase four draft",
                            "body_text": "draft for list/delete",
                        },
                    )
                )
                cleanup["draft"] = grab(r"ID:\s*([A-Za-z0-9_-]+)", draft)
                listed = text(
                    await session.call_tool("gmail_list_drafts", {"limit": 5})
                )
                deleted = text(
                    await session.call_tool(
                        "gmail_delete_draft",
                        {"draft_id": cleanup["draft"], "confirm": True},
                    )
                )
                cleanup["draft"] = None
                record(
                    "gmail_list_drafts / delete_draft",
                    "Phase four draft" in listed and "deleted" in deleted,
                    "listed and removed",
                )

                shortcut = text(
                    await session.call_tool(
                        "drive_create_shortcut",
                        {"target_id": sheet_id, "name": "Phase four shortcut"},
                    )
                )
                cleanup["shortcut"] = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", shortcut)
                record(
                    "drive_create_shortcut",
                    "Shortcut created" in shortcut,
                    shortcut.splitlines()[0],
                )
            finally:
                if cleanup["draft"]:
                    try:
                        await session.call_tool(
                            "gmail_delete_draft",
                            {"draft_id": cleanup["draft"], "confirm": True},
                        )
                    except Exception:
                        pass
                for key in ("shortcut", "sheet", "doc", "deck"):
                    if cleanup[key]:
                        try:
                            await session.call_tool(
                                "drive_delete_file",
                                {"file_id": cleanup[key], "confirm": True},
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
