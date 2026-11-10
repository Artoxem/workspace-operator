"""Live end-to-end checks for the v1.14 tools (self-cleaning)."""

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
    mark = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")


def text(result) -> str:
    return "\n".join(getattr(block, "text", "") or "" for block in result.content)


def grab(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    if not match:
        raise RuntimeError(f"{pattern!r} not found in {value[:200]}")
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
    cleanup = {"sheet": None, "doc": None, "deck": None}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            try:
                sheet = text(
                    await session.call_tool(
                        "create_spreadsheet", {"title": "New tools smoke"}
                    )
                )
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

                cond = text(
                    await session.call_tool(
                        "sheet_conditional_format",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "B2:B3",
                            "condition": "NUMBER_GREATER",
                            "value": "20",
                            "background_color": "#C6EFCE",
                        },
                    )
                )
                record("sheet_conditional_format", "Conditional format added" in cond, cond[:70])

                chart = text(
                    await session.call_tool(
                        "sheet_add_chart",
                        {
                            "spreadsheet_id": sheet_id,
                            "range": "A1:B3",
                            "chart_type": "COLUMN",
                            "title": "Scores",
                        },
                    )
                )
                record("sheet_add_chart", "Chart added" in chart, chart.splitlines()[0])

                meta = text(
                    await session.call_tool(
                        "drive_get_metadata", {"file_id": sheet_id}
                    )
                )
                record(
                    "drive_get_metadata",
                    "Name: New tools smoke" in meta and "Type:" in meta,
                    "name + type",
                )

                renamed = text(
                    await session.call_tool(
                        "drive_rename_file",
                        {"file_id": sheet_id, "name": "New tools smoke renamed"},
                    )
                )
                record("drive_rename_file", "renamed" in renamed.lower() or "Renamed" in renamed, renamed[:60])

                doc = text(
                    await session.call_tool("create_doc", {"title": "New tools smoke doc"})
                )
                doc_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", doc)
                cleanup["doc"] = doc_id
                await session.call_tool(
                    "append_to_doc",
                    {"document_id": doc_id, "text": "Hello WORLD\nhello again"},
                )

                preview = text(
                    await session.call_tool(
                        "doc_replace_text",
                        {
                            "document_id": doc_id,
                            "find": "hello",
                            "replace": "hi",
                        },
                    )
                )
                record(
                    "doc_replace_text preview",
                    "CONFIRMATION REQUIRED" in preview and "2 occurrence" in preview,
                    preview.splitlines()[2] if len(preview.splitlines()) > 2 else preview[:60],
                )

                applied = text(
                    await session.call_tool(
                        "doc_replace_text",
                        {
                            "document_id": doc_id,
                            "find": "hello",
                            "replace": "hi",
                            "match_case": False,
                            "confirm": True,
                        },
                    )
                )
                record("doc_replace_text apply", "Replaced 2 occurrence" in applied, applied[:70])

                body = text(await session.call_tool("read_doc", {"document_id": doc_id}))
                record(
                    "replacement visible",
                    "hi WORLD" in body and "hi again" in body,
                )

                comment = text(
                    await session.call_tool(
                        "drive_create_comment",
                        {
                            "file_id": doc_id,
                            "content": "smoke comment",
                            "quoted_text": "Hello WORLD",
                        },
                    )
                )
                comment_id = grab(r"ID:\s*([A-Za-z0-9._-]{5,})", comment)
                record("drive_create_comment", "smoke comment" in comment, comment_id)

                listed = text(
                    await session.call_tool(
                        "drive_list_comments", {"file_id": doc_id}
                    )
                )
                record(
                    "drive_list_comments",
                    "smoke comment" in listed and "quoted" in listed,
                    f"{len(listed)} chars",
                )

                resolved = text(
                    await session.call_tool(
                        "drive_resolve_comment",
                        {
                            "file_id": doc_id,
                            "comment_id": comment_id,
                            "confirm": True,
                        },
                    )
                )
                record("drive_resolve_comment", "resolved" in resolved.lower(), resolved[:60])

                preview = text(
                    await session.call_tool(
                        "drive_delete_file", {"file_id": sheet_id}
                    )
                )
                record("drive_delete_file preview", "CONFIRMATION REQUIRED" in preview, preview.splitlines()[2][:50])

                trashed = text(
                    await session.call_tool(
                        "drive_delete_file", {"file_id": sheet_id, "confirm": True}
                    )
                )
                record("drive_delete_file", "Moved to trash" in trashed, trashed[:60])

                restored = text(
                    await session.call_tool(
                        "drive_restore_file", {"file_id": sheet_id}
                    )
                )
                record("drive_restore_file", "Restored" in restored, restored[:60])

                deck = text(
                    await session.call_tool("slides_create", {"title": "New tools smoke deck"})
                )
                deck_id = grab(r"ID:\s*([A-Za-z0-9_-]{10,})", deck)
                cleanup["deck"] = deck_id
                await session.call_tool(
                    "slides_add_slide",
                    {"presentation_id": deck_id, "layout": "TITLE_AND_BODY"},
                )
                structure = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                slide_ids = re.findall(r"^\d+\. \[([A-Za-z0-9_-]+)\]", structure, re.M)
                before = len(slide_ids)
                target = slide_ids[-1]

                delete_preview = text(
                    await session.call_tool(
                        "slides_delete_slide",
                        {"presentation_id": deck_id, "slide_id": target},
                    )
                )
                record(
                    "slides_delete_slide preview",
                    "CONFIRMATION REQUIRED" in delete_preview,
                    delete_preview.splitlines()[2][:50],
                )
                deleted = text(
                    await session.call_tool(
                        "slides_delete_slide",
                        {
                            "presentation_id": deck_id,
                            "slide_id": target,
                            "confirm": True,
                        },
                    )
                )
                after = text(
                    await session.call_tool("slides_get", {"presentation_id": deck_id})
                )
                count_after = len(re.findall(r"^\d+\. \[", after, re.M))
                record(
                    "slides_delete_slide",
                    "deleted" in deleted and count_after == before - 1,
                    f"{before} → {count_after} slides",
                )

            finally:
                for key, value in cleanup.items():
                    if value:
                        try:
                            await session.call_tool(
                                "drive_delete_file",
                                {"file_id": value, "confirm": True},
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
