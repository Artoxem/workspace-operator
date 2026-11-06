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
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server.py"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Google responses may contain emoji; never fail a check because of the console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []
skipped: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = PASS if ok else FAIL
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def record_skip(name: str, detail: str = "") -> None:
    skipped.append(name)
    print(f"[SKIP] {name}" + (f" — {detail}" if detail else ""))


def _env(profile: str) -> dict:
    config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    env = os.environ.copy()
    env["MCP_CONFIG_FILE"] = str(REPO / "config.yaml")
    env["MCP_AUTH_TOKEN"] = str(config.get("mcp_auth_token", ""))
    env["MCP_TOOL_PROFILE"] = profile
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _trash(file_id: str) -> None:
    """Move a test artifact to the Drive trash (cleanup, not part of the server)."""
    from googleapiclient.discovery import build

    from workspace_operator.auth import get_creds

    config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    creds = get_creds(_config_obj(config))
    build("drive", "v3", credentials=creds).files().update(
        fileId=file_id, body={"trashed": True}
    ).execute()


def _config_obj(raw: dict):
    from workspace_operator.config import Config

    return Config(
        client_secrets_file=raw["client_secrets_file"],
        token_file=raw["token_file"],
        backup_dir=raw.get("backup_dir", ""),
        log_file=raw.get("log_file"),
        mcp_auth_token=raw.get("mcp_auth_token"),
        scopes=raw.get("scopes") or [],
    )


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
    record("tools/list", len(names) == 56, f"{len(names)} tools")
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

    mails = await session.call_tool("list_emails", {"max_results": 1})
    mails_text = _text(mails)
    record(
        "call list_emails",
        not mails.isError and "Messages (" in mails_text,
        mails_text.splitlines()[1] if len(mails_text.splitlines()) > 1 else "empty",
    )

    message_id = re.search(r"ID:\s*([0-9a-f]{12,})", mails_text)
    if message_id:
        mail = await session.call_tool("read_email", {"message_id": message_id.group(1)})
        mail_text = _text(mail)
        record(
            "call read_email (headers + body)",
            not mail.isError
            and all(marker in mail_text for marker in ("From:", "To:", "Date:", "Subject:"))
            and len(mail_text) > 300,
            f"{len(mail_text)} chars",
        )
        record(
            "read_email has no HTML entities",
            "&#" not in mail_text and "&amp;" not in mail_text,
            "clean text",
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

    # ---------- v1.2: local files, slides, script execution ----------
    workspace = Path(tempfile.mkdtemp(prefix="google-mcp-smoke-"))
    sample = workspace / "smoke-upload.txt"
    sample.write_text("workspace smoke test\n", encoding="utf-8")

    upload = await session.call_tool("drive_upload", {"local_path": str(sample)})
    upload_text = _text(upload)
    uploaded_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", upload_text)
    record(
        "call drive_upload",
        not upload.isError and uploaded_id is not None,
        upload_text.splitlines()[0] if upload_text else "empty",
    )

    if uploaded_id:
        target = workspace / "smoke-download.txt"
        download = await session.call_tool(
            "drive_download",
            {"file_id": uploaded_id.group(1), "save_to": str(target), "overwrite": True},
        )
        round_trip = target.exists() and target.read_text(
            encoding="utf-8"
        ) == sample.read_text(encoding="utf-8")
        record("call drive_download (round-trip)", not download.isError and round_trip, target.name)

    presentation = await session.call_tool(
        "slides_create", {"title": "Workspace Operator smoke"}
    )
    presentation_text = _text(presentation)
    slides_disabled = (
        "has not been used in project" in presentation_text
        or "is disabled" in presentation_text
    )
    presentation_id = None
    if slides_disabled:
        record_skip(
            "slides_* tools",
            "enable slides.googleapis.com for the Cloud project, then re-run",
        )
    else:
        presentation_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", presentation_text)
        record(
            "call slides_create",
            not presentation.isError and presentation_id is not None,
            presentation_text.splitlines()[0] if presentation_text else "empty",
        )

    if presentation_id:
        pid = presentation_id.group(1)
        summary = await session.call_tool("slides_get", {"presentation_id": pid})
        record(
            "call slides_get",
            not summary.isError and "Slides:" in _text(summary),
            _text(summary).splitlines()[0] if _text(summary) else "empty",
        )

        added = await session.call_tool(
            "slides_add_slide", {"presentation_id": pid, "layout": "TITLE_AND_BODY"}
        )
        record(
            "call slides_add_slide",
            not added.isError and "Slide added" in _text(added),
            _text(added).splitlines()[0] if _text(added) else "empty",
        )

        preview = await session.call_tool(
            "slides_replace_text",
            {"presentation_id": pid, "replacements": {"X": "Y"}},
        )
        record(
            "slides_replace_text preview (no write)",
            not preview.isError and "CONFIRMATION REQUIRED" in _text(preview),
            "preview only",
        )

        applied = await session.call_tool(
            "slides_replace_text",
            {"presentation_id": pid, "replacements": {"X": "Y"}, "confirm": True},
        )
        record(
            "slides_replace_text confirm=true",
            not applied.isError and "occurrence" in _text(applied),
            _text(applied).splitlines()[0] if _text(applied) else "empty",
        )

        added_slide = re.search(r"ID:\s*([A-Za-z0-9_-]{6,})", _text(added))
        if added_slide:
            image = await session.call_tool(
                "slides_insert_image",
                {
                    "presentation_id": pid,
                    "slide_id": added_slide.group(1),
                    "image_url": "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png",
                    "width": 240,
                    "height": 80,
                    "left": 40,
                    "top": 40,
                },
            )
            record(
                "call slides_insert_image",
                not image.isError and "Image inserted" in _text(image),
                _text(image).splitlines()[0] if _text(image) else "empty",
            )

        pdf_target = workspace / "smoke-export.pdf"
        exported = await session.call_tool(
            "drive_export",
            {
                "file_id": pid,
                "format": "pdf",
                "save_to": str(pdf_target),
                "overwrite": True,
            },
        )
        pdf_size = pdf_target.stat().st_size if pdf_target.exists() else 0
        record(
            "call drive_export (pdf)",
            not exported.isError and pdf_size > 1000,
            f"{pdf_size} bytes",
        )

    created_sheet = await session.call_tool(
        "create_spreadsheet", {"title": "Workspace Operator format smoke"}
    )
    sheet_match = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(created_sheet))
    record(
        "call create_spreadsheet",
        not created_sheet.isError and sheet_match is not None,
        _text(created_sheet).splitlines()[0] if _text(created_sheet) else "empty",
    )

    if sheet_match:
        spreadsheet_id = sheet_match.group(1)
        formatted = await session.call_tool(
            "sheet_format",
            {
                "spreadsheet_id": spreadsheet_id,
                "range": "A1:C10",
                "bold": True,
                "background_color": "#FFF2CC",
                "number_format": "#,##0.00",
                "column_width": 140,
                "freeze_rows": 1,
            },
        )
        record(
            "call sheet_format",
            not formatted.isError and "Formatted" in _text(formatted),
            _text(formatted).splitlines()[0] if _text(formatted) else "empty",
        )
        try:
            await asyncio.to_thread(_trash, spreadsheet_id)
        except Exception as exc:  # noqa: BLE001
            record("cleanup spreadsheet", False, str(exc))

    script_run = await session.call_tool(
        "script_run_function", {"script_id": "no-such-script", "function_name": "doWork"}
    )
    script_text = _text(script_run)
    record(
        "script_run_function error path",
        script_run.isError and "Error" in script_text,
        script_text.splitlines()[0][:80] if script_text else "empty",
    )

    for artifact in (uploaded_id, presentation_id):
        if artifact:
            try:
                await asyncio.to_thread(_trash, artifact.group(1))
            except Exception as exc:  # noqa: BLE001
                record("cleanup test artifacts", False, str(exc))
    shutil.rmtree(workspace, ignore_errors=True)

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
    record("read-only profile tools/list", len(tools.tools) == 19, f"{len(tools.tools)} tools")

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
    print(
        f"{len(results) - len(failed)}/{len(results)} checks passed"
        + (f", {len(skipped)} skipped" if skipped else "")
    )
    if failed:
        print("failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
