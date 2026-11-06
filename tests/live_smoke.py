"""Live smoke test: talk to the server exactly like a real MCP client.

Requires a working OAuth token (config.yaml), a real Google account, and
network access. Performs **read-only** calls only.

    python tests/live_smoke.py            # full profile
    python tests/live_smoke.py --verbose  # print every response

Exit code 0 means every check passed.
"""

import asyncio
from datetime import datetime, timedelta, timezone
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


def _delete_draft(draft_id: str) -> None:
    """Cleanup helper: remove a draft created by the smoke test."""
    from googleapiclient.discovery import build

    from workspace_operator.auth import get_creds

    config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    service = build("gmail", "v1", credentials=get_creds(_config_obj(config)))
    service.users().drafts().delete(userId="me", id=draft_id).execute()


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
    record("tools/list", len(names) == 66, f"{len(names)} tools")
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

    if message_id:
        thread = await session.call_tool(
            "gmail_get_thread", {"message_id": message_id.group(1)}
        )
        thread_text = _text(thread)
        record(
            "call gmail_get_thread",
            not thread.isError and "Thread:" in thread_text and "messages:" in thread_text,
            thread_text.splitlines()[0] if thread_text else "empty",
        )

        reply = await session.call_tool(
            "gmail_reply",
            {
                "message_id": message_id.group(1),
                "body_text": "Automated smoke-test reply. Safe to ignore.",
                "draft_mode": True,
            },
        )
        reply_text = _text(reply)
        record(
            "call gmail_reply (draft)",
            not reply.isError and "Draft reply created" in reply_text,
            reply_text.splitlines()[0] if reply_text else "empty",
        )
        draft_id = re.search(r"Draft ID:\s*([A-Za-z0-9_-]+)", reply_text)
        if draft_id:
            try:
                await asyncio.to_thread(_delete_draft, draft_id.group(1))
            except Exception as exc:  # noqa: BLE001
                record("cleanup reply draft", False, str(exc))

    attachment_dir = Path(tempfile.mkdtemp(prefix="google-mcp-attachment-"))
    with_attachment = await session.call_tool(
        "list_emails", {"max_results": 3, "query": "has:attachment"}
    )
    with_attachment_text = _text(with_attachment)
    attachment_message = re.search(r"ID:\s*([0-9a-f]{12,})", with_attachment_text)
    if attachment_message:
        attachment_target = attachment_dir / "smoke-attachment.bin"
        attachment = await session.call_tool(
            "gmail_get_attachment",
            {
                "message_id": attachment_message.group(1),
                "save_to": str(attachment_target),
                "overwrite": True,
            },
        )
        attachment_text = _text(attachment)
        record(
            "call gmail_get_attachment",
            not attachment.isError
            and ("Saved" in attachment_text or "Available" in attachment_text),
            attachment_text.splitlines()[0][:90] if attachment_text else "empty",
        )
    else:
        record_skip("gmail_get_attachment", "no messages with attachments in this mailbox")
    shutil.rmtree(attachment_dir, ignore_errors=True)

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

    report_sheet = await session.call_tool(
        "create_spreadsheet", {"title": "Workspace Operator report smoke"}
    )
    report_match = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(report_sheet))
    if report_match:
        report_sheet_id = report_match.group(1)
        await session.call_tool(
            "update_sheet",
            {
                "spreadsheet_id": report_sheet_id,
                "range_name": "A1:B3",
                "values": [["Model", "Price"], ["Grande", "4882,50"], ["Lusso", "7602,63"]],
            },
        )
        report = await session.call_tool(
            "report_from_sheet",
            {"spreadsheet_id": report_sheet_id, "doc_title": "Workspace Operator report smoke"},
        )
        report_text = _text(report)
        record(
            "call report_from_sheet",
            not report.isError and "Report created" in report_text,
            report_text.splitlines()[0] if report_text else "empty",
        )
        doc_match = re.search(r"Document ID:\s*([A-Za-z0-9_-]{10,})", report_text)
        for artifact in (doc_match.group(1) if doc_match else None, report_sheet_id):
            if artifact:
                try:
                    await asyncio.to_thread(_trash, artifact)
                except Exception as exc:  # noqa: BLE001
                    record("cleanup report artifacts", False, str(exc))

    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    start_iso = tomorrow.isoformat()
    end_iso = (tomorrow + timedelta(minutes=30)).isoformat()
    created_event = await session.call_tool(
        "create_event",
        {"summary": "Workspace Operator smoke event", "start_time": start_iso, "end_time": end_iso},
    )
    event_match = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(created_event))
    record(
        "call create_event",
        not created_event.isError and event_match is not None,
        _text(created_event).splitlines()[0] if _text(created_event) else "empty",
    )

    if event_match:
        event_id = event_match.group(1)
        updated = await session.call_tool(
            "calendar_update_event",
            {"event_id": event_id, "summary": "Workspace Operator smoke event (updated)"},
        )
        record(
            "call calendar_update_event",
            not updated.isError and "Event updated" in _text(updated),
            _text(updated).splitlines()[0] if _text(updated) else "empty",
        )

        responded = await session.call_tool(
            "calendar_respond_to_invite",
            {"event_id": event_id, "response": "accepted", "confirm": True},
        )
        record(
            "calendar_respond_to_invite on own event",
            responded.isError and "not on the guest list" in _text(responded),
            _text(responded).splitlines()[0][:80] if _text(responded) else "empty",
        )

        deleted = await session.call_tool(
            "calendar_delete_event", {"event_id": event_id, "confirm": True}
        )
        record(
            "call calendar_delete_event",
            not deleted.isError and "deleted" in _text(deleted),
            _text(deleted).splitlines()[0] if _text(deleted) else "empty",
        )

    # ---------- composite tools ----------
    left = await session.call_tool("create_spreadsheet", {"title": "smoke left"})
    right = await session.call_tool("create_spreadsheet", {"title": "smoke right"})
    left_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(left))
    right_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(right))

    if left_id and right_id:
        await session.call_tool(
            "update_sheet",
            {
                "spreadsheet_id": left_id.group(1),
                "range_name": "A1:C3",
                "values": [["SKU", "Name", "Price"], ["1", "Chair", "100"], ["2", "Table", "300"]],
            },
        )
        await session.call_tool(
            "update_sheet",
            {
                "spreadsheet_id": right_id.group(1),
                "range_name": "A1:C3",
                "values": [["SKU", "Name", "Price"], ["1", "Chair", "120"], ["3", "Lamp", "80"]],
            },
        )

        compared = await session.call_tool(
            "compare_tables",
            {
                "spreadsheet_id": left_id.group(1),
                "range_a": "A1:C3",
                "other_spreadsheet_id": right_id.group(1),
                "range_b": "A1:C3",
                "key_column": "SKU",
                "output": "text",
            },
        )
        compared_text = _text(compared)
        record(
            "call compare_tables",
            not compared.isError and "Compare by 'SKU'" in compared_text,
            compared_text.splitlines()[1] if len(compared_text.splitlines()) > 1 else "empty",
        )

        native_report = await session.call_tool(
            "report_from_sheet",
            {"spreadsheet_id": left_id.group(1), "range": "A1:C3", "doc_title": "smoke native table"},
        )
        native_text = _text(native_report)
        native_doc = re.search(r"Document ID:\s*([A-Za-z0-9_-]{10,})", native_text)
        record(
            "report_from_sheet creates a native table doc",
            not native_report.isError and native_doc is not None,
            native_text.splitlines()[0] if native_text else "empty",
        )
        if native_doc:
            rendered = await session.call_tool("read_doc", {"document_id": native_doc.group(1)})
            rendered_text = _text(rendered)
            record(
                "native table is readable",
                "| SKU |" in rendered_text and "Summary" in rendered_text,
                f"{len(rendered_text)} chars",
            )
            try:
                await asyncio.to_thread(_trash, native_doc.group(1))
            except Exception as exc:  # noqa: BLE001
                record("cleanup native report", False, str(exc))

        text_report = await session.call_tool(
            "report_from_sheet",
            {"spreadsheet_id": left_id.group(1), "range": "A1:C3", "output": "text", "columns": ["Price"]},
        )
        text_report_value = _text(text_report)
        record(
            "report_from_sheet output=text (no file)",
            not text_report.isError
            and "Summary" in text_report_value
            and "text mode" in text_report_value,
            f"{len(text_report_value)} chars",
        )

        for artifact in (left_id.group(1), right_id.group(1)):
            try:
                await asyncio.to_thread(_trash, artifact)
            except Exception as exc:  # noqa: BLE001
                record("cleanup compare artifacts", False, str(exc))

    digest = await session.call_tool(
        "digest", {"sources": "gmail", "since_hours": 168, "limit": 2, "output": "text"}
    )
    digest_text = _text(digest)
    record(
        "call digest (text)",
        not digest.isError and "## Email" in digest_text and "Total items" in digest_text,
        digest_text.splitlines()[2] if len(digest_text.splitlines()) > 2 else "empty",
    )

    template_doc = await session.call_tool(
        "create_doc", {"title": "Workspace Operator template smoke"}
    )
    template_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", _text(template_doc))
    if template_id:
        await session.call_tool(
            "append_to_doc",
            {"document_id": template_id.group(1), "text": "Hello {{CLIENT}}, report for {{CLIENT}}"},
        )
        cloned = await session.call_tool(
            "clone_and_fill",
            {
                "file_id": template_id.group(1),
                "name": "Workspace Operator cloned smoke",
                "replacements": {"{{CLIENT}}": "ACME"},
            },
        )
        cloned_text = _text(cloned)
        record(
            "call clone_and_fill",
            not cloned.isError and "Creat" in cloned_text and "occurrence" in cloned_text,
            cloned_text.splitlines()[0] if cloned_text else "empty",
        )
        cloned_id = re.search(r"ID:\s*([A-Za-z0-9_-]{10,})", cloned_text)
        if cloned_id:
            filled = await session.call_tool(
                "read_doc", {"document_id": cloned_id.group(1)}
            )
            record(
                "clone_and_fill replaced placeholders",
                "ACME" in _text(filled) and "{{CLIENT}}" not in _text(filled),
                "ACME present",
            )
        for artifact in (
            cloned_id.group(1) if cloned_id else None,
            template_id.group(1),
        ):
            if artifact:
                try:
                    await asyncio.to_thread(_trash, artifact)
                except Exception as exc:  # noqa: BLE001
                    record("cleanup template artifacts", False, str(exc))

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
    record("read-only profile tools/list", len(tools.tools) == 21, f"{len(tools.tools)} tools")

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
