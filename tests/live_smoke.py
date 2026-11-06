"""Live smoke test: talk to the server exactly like a real MCP client.

Requires a working OAuth token (config.yaml), a real Google account, and
network access. Performs **read-only** calls only.

    python tests/live_smoke.py            # full profile
    python tests/live_smoke.py --verbose  # print every response

Exit code 0 means every check passed.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server.py"

# Google responses may contain emoji; never fail a check because of the console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = PASS if ok else FAIL
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def _env(profile: str) -> dict:
    config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    env = os.environ.copy()
    env["MCP_CONFIG_FILE"] = str(REPO / "config.yaml")
    env["MCP_AUTH_TOKEN"] = str(config.get("mcp_auth_token", ""))
    env["MCP_TOOL_PROFILE"] = profile
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _text(result) -> str:
    parts = []
    for block in result.content:
        parts.append(getattr(block, "text", "") or "")
    return "\n".join(part for part in parts if part)


async def session_run(profile: str, checks) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env=_env(profile)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await checks(session)


async def full_checks(session: ClientSession) -> None:
    init = await session.initialize()
    record(
        "initialize",
        bool(init.serverInfo),
        f"{init.serverInfo.name} v{init.serverInfo.version} / protocol {init.protocolVersion}",
    )

    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    record("tools/list", len(names) == 46, f"{len(names)} tools")
    record("workspace_search present", "workspace_search" in names)
    record(
        "tool annotations",
        all(getattr(tool, "annotations", None) is not None for tool in tools.tools),
        "readOnlyHint / destructiveHint on every tool",
    )

    prompts = await session.list_prompts()
    record("prompts/list", len(prompts.prompts) == 4, f"{len(prompts.prompts)} prompts")

    resources = await session.list_resources()
    record("resources/list", len(resources.resources) == 3, f"{len(resources.resources)} resources")

    templates = await session.list_resource_templates()
    record(
        "resource templates",
        len(templates.resourceTemplates) == 3,
        f"{len(templates.resourceTemplates)} templates",
    )

    profile_result = await session.call_tool("get_gmail_profile", {})
    text = _text(profile_result)
    record(
        "call get_gmail_profile",
        not profile_result.isError and "@" in text,
        text.strip().splitlines()[0] if text.strip() else "empty",
    )

    search = await session.call_tool(
        "workspace_search", {"query": "test", "sources": "drive", "limit": 3}
    )
    search_text = _text(search)
    record(
        "call workspace_search (drive)",
        not search.isError and "Workspace search" in search_text,
        search_text.splitlines()[0] if search_text else "empty",
    )

    files = await session.call_tool("find_files", {"query": "trashed = false"})
    files_text = _text(files)
    record(
        "call find_files",
        not files.isError and ("Found files" in files_text or "No files found" in files_text),
        files_text.splitlines()[0] if files_text else "empty",
    )

    recent = await session.read_resource("gdrive://recent")
    recent_text = recent.contents[0].text if recent.contents else ""
    record(
        "read resource gdrive://recent",
        "Recent Google Drive files" in recent_text,
        recent_text.splitlines()[0] if recent_text else "empty",
    )

    docs = await session.call_tool(
        "drive_search_advanced",
        {"query": "mimeType = 'application/vnd.google-apps.document'", "limit": 1},
    )
    match = re.search(r"ID:\s*([A-Za-z0-9_-]+)", _text(docs))
    if not match:
        record("read_doc / doc_export_pdf", True, "skipped — no Google Docs in account")
    else:
        doc_id = match.group(1)
        doc = await session.call_tool("read_doc", {"document_id": doc_id})
        doc_text = _text(doc)
        record(
            "call read_doc",
            not doc.isError and len(doc_text) > 0,
            f"{len(doc_text)} chars from {doc_id[:12]}…",
        )

        pdf = await session.call_tool("doc_export_pdf", {"document_id": doc_id})
        block = pdf.content[0] if pdf.content else None
        kind = getattr(block, "type", "?")
        mime = getattr(getattr(block, "resource", None), "mimeType", "")
        record(
            "call doc_export_pdf (binary resource)",
            not pdf.isError and kind == "resource" and mime == "application/pdf",
            f"{kind} {mime}",
        )

    broken = await session.call_tool(
        "read_sheet", {"spreadsheet_id": "definitely-not-a-real-id", "range_name": "A1:B2"}
    )
    broken_text = _text(broken)
    record(
        "failed call is flagged isError",
        broken.isError and "Error" in broken_text,
        broken_text.splitlines()[0][:80] if broken_text else "empty",
    )

    validation = await session.call_tool("drive_search_advanced", {"query": ""})
    validation_text = _text(validation)
    record(
        "validation error is flagged isError",
        validation.isError and "Query is required" in validation_text,
        validation_text.splitlines()[0][:80] if validation_text else "empty",
    )


async def read_only_checks(session: ClientSession) -> None:
    await session.initialize()
    tools = await session.list_tools()
    record("read-only profile tools/list", len(tools.tools) == 16, f"{len(tools.tools)} tools")

    blocked = await session.call_tool(
        "send_email", {"to": "nobody@example.com", "subject": "x", "body_text": "x"}
    )
    text = _text(blocked)
    record(
        "write tool blocked by profile",
        blocked.isError and "disabled by the active tool profile" in text,
        text.strip().splitlines()[0] if text.strip() else "empty",
    )


async def main() -> int:
    await session_run("full", full_checks)
    await session_run("read-only", read_only_checks)

    failed = [name for name, ok, _ in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
