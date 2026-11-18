"""MCP server exposing Google Workspace tools, resources and prompts."""

import asyncio
import base64
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import List

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from . import __version__
from .approvals import ApprovalError, ApprovalStore, challenge_text
from .config import Config, load_config
from .definitions import load_prompts, load_tools
from .dispatch import build_handlers

# Handlers are looked up by name at call time (workspace_operator.dispatch.ROUTES
# resolves them with getattr on this module), and tests patch them here. The
# imports therefore look unused to a linter; keep them.
from .handlers import (  # noqa: F401
    add_chart_handler,
    add_pivot_table_handler,
    add_sheet_handler,
    append_row_handler,
    append_to_doc_handler,
    bulk_cancel_handler,
    bulk_list_handler,
    bulk_plan_handler,
    bulk_result_handler,
    bulk_run_handler,
    bulk_status_handler,
    bulk_undo_handler,
    calendar_create_meeting_handler,
    calendar_delete_event_handler,
    calendar_respond_to_invite_handler,
    calendar_update_event_handler,
    cancel_operation_handler,
    clear_range_handler,
    compare_tables_handler,
    conditional_format_handler,
    create_deployment_handler,
    create_doc_handler,
    create_draft_handler,
    create_filter_handler,
    create_folder_handler,
    create_label_handler,
    create_script_project_handler,
    create_spreadsheet_handler,
    delete_columns_handler,
    delete_draft_tool,
    delete_email_handler,
    delete_file_handler,
    delete_rows_handler,
    delete_sheet_handler,
    digest_handler,
    document_to_text,
    drive_copy_file_handler,
    drive_export_handler,
    drive_list_permissions_handler,
    drive_revoke_public_handler,
    drive_search_advanced_handler,
    drive_upload_handler,
    execute_operation_handler,
    format_sheet_handler,
    format_text_handler,
    forms_add_questions_handler,
    forms_create_handler,
    forms_get_handler,
    forms_list_responses_handler,
    get_gmail_profile_handler,
    get_metadata_handler,
    get_script_content_handler,
    get_spreadsheet_meta_handler,
    gmail_archive_handler,
    gmail_get_attachment_handler,
    gmail_get_thread_handler,
    gmail_label_apply_handler,
    gmail_reply_handler,
    gmail_search_and_summarize_handler,
    insert_columns_handler,
    insert_image_handler,
    insert_rows_handler,
    list_calendars_handler,
    list_deployments_handler,
    list_drafts_handler,
    list_emails_handler,
    list_events_handler,
    list_filters_handler,
    list_labels_handler,
    merge_cells_handler,
    move_event_handler,
    move_file_handler,
    postmaster_list_domains_handler,
    postmaster_traffic_stats_handler,
    prepare_script_update_handler,
    protect_range_handler,
    read_doc_handler,
    read_email_handler,
    read_sheet_handler,
    remove_permission_handler,
    rename_file_handler,
    replace_text_handler,
    restore_file_handler,
    restore_script_backup_handler,
    script_run_function_handler,
    send_draft_handler,
    send_email_handler,
    send_with_attachments_handler,
    set_borders_handler,
    set_data_validation_handler,
    set_event_color_handler,
    share_file_handler,
    sheet_create_filter_view_handler,
    sheet_create_named_range_handler,
    sheet_export_csv_handler,
    sheet_find_replace_handler,
    sort_range_handler,
    tasks_complete_handler,
    tasks_create_handler,
    tasks_list_handler,
    tasks_list_lists_handler,
    update_deployment_handler,
    update_draft_handler,
    update_sheet_handler,
    workspace_search_handler,
)
from .logging import setup_logging
from .operations import BinaryResult
from .profiles import ProfileError
from .runtime import AuditLog, call_with_retry
from .security import require_token_configured
from .text import clean_text, format_timestamp, humanize_http_error, parse_email_date
from .toolset import (
    REMOVED_ALIAS_NAMES,
    RoutingError,
    build_aliases,
    build_catalog,
    build_surface,
    resolve_call,
)
from .toolset.models import Safety
from .toolset.scopes import read_granted_scopes


def _tools() -> List[types.Tool]:
    """Return the retained legacy definitions used by the catalog.

    The definitions are data (``workspace_operator/definitions/*.json``). The five
    standalone draft tools remain as schema sources for the ``gmail_write`` /
    ``gmail_delete`` actions; they are not exposed.
    """
    return load_tools()


def _prompts() -> List[types.Prompt]:
    """Scenario prompts offered to MCP clients."""
    return load_prompts()


def create_server(config: Config, logger) -> Server:
    """Build a fully configured MCP server (transport independent)."""
    legacy_tools = _tools()
    catalog = build_catalog(legacy_tools)
    granted_scopes = (
        read_granted_scopes(config.token_file) if config.scope_routing else None
    )
    try:
        surface = build_surface(
            catalog,
            config.tool_profile,
            granted_scopes,
            allowed=config.allowed_tools,
            denied=config.denied_tools,
        )
    except ProfileError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    server = Server(
        "Workspace Operator",
        version=__version__,
        instructions=(
            "Workspace Operator exposes Google Workspace through a compact, "
            "action-based tool surface. Start with workspace_search for unknown "
            "ids; read before writing; use the bulk_plan/bulk_run flow for more "
            "than a handful of items. Destructive actions first return "
            "APPROVAL_REQUIRED; if the client supports elicitation the user is "
            "asked in-chat, otherwise ask them to run "
            "`workspace-operator approvals approve <id>` and retry with approval_id. Tools outside the active profile or "
            "without their OAuth scope are hidden by design."
        ),
    )
    exposed_tools = surface.mcp_tools()
    exposed_specs = surface.by_name
    aliases = build_aliases(catalog)
    profile_name = surface.profile

    audit = AuditLog(config.audit_log)
    approvals = ApprovalStore(config)
    tool_index = exposed_specs

    logger.info(
        "Starting with profile %s — %d of %d tools exposed%s%s",
        profile_name,
        len(exposed_tools),
        len(legacy_tools),
        " [dry-run]" if config.dry_run else "",
        f" [audit: {config.audit_log}]" if audit.enabled else "",
    )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def handle_list_tools() -> List[types.Tool]:
        return exposed_tools


    async def _elicit_approval(ctx, name, plan, argument_names):
        """Ask the human in the client UI when the client supports elicitation."""
        if ctx is None:
            return None
        try:
            capabilities = getattr(ctx.session, "client_capabilities", None)
            elicitation = getattr(capabilities, "elicitation", None)
            if getattr(elicitation, "form", None) is None:
                return None
            summary = __import__("workspace_operator.approvals", fromlist=["summarize"]).summarize(
                name, plan.action, plan.arguments
            )
            result = await ctx.session.elicit_form(
                message=(
                    "Approve this destructive Workspace Operator action?\n\n"
                    f"{summary}\n\n"
                    "The action will run once and is bound to these arguments."
                ),
                requested_schema={
                    "type": "object",
                    "properties": {
                        "approve": {
                            "type": "boolean",
                            "title": "Approve",
                            "description": "Run this exact destructive action.",
                        }
                    },
                    "required": ["approve"],
                },
                related_request_id=getattr(ctx, "request_id", None),
            )
            if result.action == "accept" and (result.content or {}).get("approve") is True:
                return "approved"
            if result.action == "accept":
                return "declined"
            return "declined" if result.action == "decline" else "cancelled"
        except Exception as exc:  # noqa: BLE001 - fallback must never break a call
            logger.warning("Elicitation unavailable, falling back to approval_id: %s", exc)
            return None


    def _approval_link(record):
        base = (getattr(config, "approval_url", None) or "").rstrip("/")
        return f"{base}/approvals/{record['id']}" if base else None

    async def handle_call_tool(
        name: str, arguments: dict | None, ctx=None
    ) -> types.CallToolResult:
        if not arguments:
            arguments = {}

        spec = tool_index.get(name)
        if spec is None and name in aliases:
            target, action = aliases[name]
            spec = tool_index.get(target)
            if spec is None:
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=(
                                f"Tool '{name}' maps to '{target}', which is hidden by "
                                f"the active profile ({profile_name}) or by scope routing."
                            ),
                        )
                    ],
                    is_error=True,
                )
            if action:
                arguments = dict(arguments or {})
                arguments["action"] = action
            logger.info("Legacy alias %s -> %s%s", name, target, f":{action}" if action else "")
        if spec is None:
            if name in REMOVED_ALIAS_NAMES:
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=(
                                f"Tool '{name}' was removed in Workspace Operator 2.0. "
                                "See docs/MIGRATION_2.0.md for the replacement."
                            ),
                        )
                    ],
                    is_error=True,
                )
            logger.warning("Blocked tool call outside profile: %s", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            f"Tool '{name}' is disabled by the active tool profile "
                            f"({profile_name}). Adjust tool_profile, allowed_tools or "
                            "denied_tools in config.yaml to enable it."
                        ),
                    )
                ],
                is_error=True,
            )

        try:
            plan = resolve_call(
                spec,
                arguments,
                require_confirm=not config.dry_run and spec.safety is not Safety.DESTRUCTIVE,
            )
        except RoutingError as exc:
            audit.record(
                name,
                profile_name,
                "invalid",
                0,
                tuple((arguments or {}).keys()),
                error=str(exc),
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                is_error=True,
            )

        is_read_only = spec.safety is Safety.READ
        argument_names = tuple(plan.arguments.keys())
        if plan.action:
            argument_names = argument_names + ("action",)
        started = time.perf_counter()

        if config.dry_run and not is_read_only:
            logger.info("Dry run: %s was not executed", name)
            audit.record(name, profile_name, "dry-run", 0, argument_names)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            f"DRY RUN: '{name}' was not executed. "
                            f"Arguments: {sorted(argument_names)}. "
                            "Unset dry_run / MCP_DRY_RUN to apply changes."
                        ),
                    )
                ]
            )

        if spec.safety is Safety.DESTRUCTIVE:
            elicitation = await _elicit_approval(ctx, name, plan, argument_names)
            if elicitation == "approved":
                plan.arguments["confirm"] = True
                audit.record(name, profile_name, "approved-in-chat", 0, argument_names)
            elif elicitation in ("declined", "cancelled"):
                audit.record(name, profile_name, f"approval-{elicitation}", 0, argument_names)
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=(
                                "The user did not approve this action; nothing was "
                                "changed. Do not retry unless the user asks."
                            ),
                        )
                    ]
                )
            else:
                try:
                    approval_id = plan.arguments.get("approval_id")
                    if not approval_id:
                        record = approvals.request(name, plan.action, plan.arguments)
                        audit.record(
                            name,
                            profile_name,
                            "approval-required",
                            0,
                            argument_names + ("approval_id",),
                        )
                        return types.CallToolResult(
                            content=[types.TextContent(type="text", text=challenge_text(record, _approval_link(record)))]
                        )
                    ok, reason = approvals.consume(
                        str(approval_id), name, plan.action, plan.arguments
                    )
                    if not ok:
                        record = approvals.request(name, plan.action, plan.arguments)
                        audit.record(
                            name,
                            profile_name,
                            "approval-rejected",
                            0,
                            argument_names,
                            error=reason,
                        )
                        return types.CallToolResult(
                            content=[
                                types.TextContent(
                                    type="text",
                                    text=(
                                        f"Approval could not be used: {reason}\n\n"
                                        + challenge_text(record, _approval_link(record))
                                    ),
                                )
                            ]
                        )
                    plan.arguments["confirm"] = True
                except ApprovalError as exc:
                    audit.record(name, profile_name, "approval-error", 0, argument_names, error=str(exc))
                    return types.CallToolResult(
                        content=[
                            types.TextContent(
                                type="text",
                                text=f"Approval error: {exc}. The action was not executed.",
                            )
                        ],
                        is_error=True,
                    )

        try:
            require_token_configured(config.mcp_auth_token)

            def _record_bulk_finish(tool_name, job, _audit=audit, _profile=profile_name):
                try:
                    start = datetime.fromisoformat(job.started_at).timestamp()
                    end = (
                        datetime.fromisoformat(job.finished_at).timestamp()
                        if job.finished_at
                        else time.time()
                    )
                    duration = max(0, int((end - start) * 1000))
                except Exception:  # noqa: BLE001 - audit must never break a job
                    duration = 0
                status = (
                    "ok"
                    if job.state == "completed"
                    else ("cancelled" if job.state == "cancelled" else "error")
                )
                _audit.record(
                    tool_name,
                    _profile,
                    status,
                    duration,
                    ("plan_id", "confirm", "job_id"),
                    error=job.error,
                )

            def _on_bulk_finish(job):
                _record_bulk_finish("bulk_run", job)

            def _on_undo_finish(job):
                _record_bulk_finish("bulk_undo", job)

            handlers = build_handlers(
                sys.modules[__name__],
                config,
                logger,
                {"_on_bulk_finish": _on_bulk_finish, "_on_undo_finish": _on_undo_finish},
            )

            if plan.legacy_name not in handlers:
                raise ValueError(f"Unknown tool: {plan.legacy_name}")

            result = await asyncio.to_thread(
                call_with_retry,
                lambda: handlers[plan.legacy_name](plan.arguments),
                config.retry_attempts,
                logger=logger,
            )

            if isinstance(result, BinaryResult):
                return types.CallToolResult(
                    content=[
                        types.EmbeddedResource(
                            type="resource",
                            resource=types.BlobResourceContents(
                                uri=result.uri,
                                mime_type=result.mime_type,
                                blob=base64.b64encode(result.data).decode(),
                            ),
                        )
                    ]
                )

            text = str(result)
            # Handlers report recoverable failures as "Error ..." strings; turn
            # those into a protocol-level isError so clients can react to them,
            # and strip googleapiclient's raw <HttpError ...> dumps.
            is_error = text.lstrip().startswith("Error")
            if is_error:
                text = humanize_http_error(text)
            audit.record(
                name,
                profile_name,
                "error" if is_error else "ok",
                int((time.perf_counter() - started) * 1000),
                argument_names,
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                is_error=is_error,
            )

        except Exception as e:
            audit.record(
                name,
                profile_name,
                "exception",
                int((time.perf_counter() - started) * 1000),
                argument_names,
                error=str(e),
            )
            logger.exception("Tool call error [%s]: %s", name, e)
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text=f"Error: {humanize_http_error(e)}")
                ],
                is_error=True,
            )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def handle_list_resources() -> List[types.Resource]:
        return [
            types.Resource(
                uri="gdrive://recent",
                name="Recent Google Drive Files",
                description="Lists the 20 most recently modified files in Google Drive",
                mime_type="text/plain",
            ),
            types.Resource(
                uri="gmail://inbox",
                name="Gmail Inbox",
                description="Recent unread messages in the Gmail inbox",
                mime_type="text/plain",
            ),
            types.Resource(
                uri="gcalendar://upcoming",
                name="Upcoming Calendar Events",
                description="Upcoming events from the primary Google Calendar (next 7 days)",
                mime_type="text/plain",
            ),
        ]

    async def handle_list_resource_templates() -> List[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                uri_template="gdrive://file/{file_id}",
                name="Google Drive File",
                description="Metadata for a specific Google Drive file (ID required)",
                mime_type="text/plain",
            ),
            types.ResourceTemplate(
                uri_template="gsheets://{spreadsheet_id}/{range}",
                name="Google Sheets Range",
                description=(
                    "Data from a specific spreadsheet range, e.g. "
                    "gsheets://SPREADSHEET_ID/Sheet1!A1:Z100"
                ),
                mime_type="text/plain",
            ),
            types.ResourceTemplate(
                uri_template="gdocs://{document_id}",
                name="Google Document",
                description="Full text content of a specific Google Doc (ID required)",
                mime_type="text/plain",
            ),
        ]

    async def handle_read_resource(uri: AnyUrl) -> Iterable[ReadResourceContents]:
        from googleapiclient.discovery import build

        from .auth import get_creds

        uri_str = str(uri)

        def _fetch() -> str:
            if uri_str == "gdrive://recent":
                creds = get_creds(config)
                svc = build("drive", "v3", credentials=creds)
                results = svc.files().list(
                    orderBy="modifiedTime desc",
                    pageSize=20,
                    fields="files(id,name,mimeType,modifiedTime,owners)",
                ).execute()
                files = results.get("files", [])
                if not files:
                    return "No files found."
                lines = ["Recent Google Drive files (by last modified):\n"]
                for f in files:
                    owners = f.get("owners", [{}])
                    owner = owners[0].get("emailAddress", "?") if owners else "?"
                    lines.append(
                        f"- {f['name']} (ID: {f['id']}) [{f.get('mimeType', '?')}] "
                        f"modified={format_timestamp(f.get('modifiedTime'))} owner={owner}"
                    )
                return "\n".join(lines)

            elif uri_str == "gmail://inbox":
                creds = get_creds(config)
                svc = build("gmail", "v1", credentials=creds)
                results = svc.users().messages().list(
                    userId="me", maxResults=20, q="is:unread in:inbox"
                ).execute()
                messages = results.get("messages", [])
                if not messages:
                    return "No unread messages in inbox."
                lines = [f"Unread inbox messages ({len(messages)}):\n"]
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
                    lines.append(
                        f"- [{msg['id']}] {parse_email_date(hdrs.get('Date'))} | "
                        f"{clean_text(hdrs.get('From'))} | "
                        f"{clean_text(hdrs.get('Subject')) or '(no subject)'}"
                    )
                return "\n".join(lines)

            elif uri_str == "gcalendar://upcoming":
                creds = get_creds(config)
                svc = build("calendar", "v3", credentials=creds)
                now = datetime.now(timezone.utc)
                time_max = (now + timedelta(days=7)).isoformat()
                results = svc.events().list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=time_max,
                    maxResults=25,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                events = results.get("items", [])
                if not events:
                    return "No upcoming events in the next 7 days."
                lines = ["Upcoming calendar events (next 7 days):\n"]
                for ev in events:
                    start = ev.get("start", {}).get(
                        "dateTime", ev.get("start", {}).get("date", "?")
                    )
                    lines.append(
                        f"- {start} | {ev.get('summary', '(no title)')} (ID: {ev.get('id')})"
                    )
                return "\n".join(lines)

            elif uri_str.startswith("gdrive://file/"):
                file_id = uri_str.removeprefix("gdrive://file/")
                if not file_id:
                    raise ValueError("file_id is required in gdrive://file/{file_id}")
                creds = get_creds(config)
                svc = build("drive", "v3", credentials=creds)
                f = svc.files().get(
                    fileId=file_id,
                    fields="id,name,mimeType,size,createdTime,modifiedTime,owners,webViewLink,parents",
                ).execute()
                owners = f.get("owners", [{}])
                owner = owners[0].get("emailAddress", "?") if owners else "?"
                size_bytes = int(f.get("size", 0))
                return (
                    f"File: {f.get('name')}\n"
                    f"ID: {f.get('id')}\n"
                    f"Type: {f.get('mimeType')}\n"
                    f"Size: {size_bytes:,} bytes\n"
                    f"Created: {format_timestamp(f.get('createdTime'))}\n"
                    f"Modified: {format_timestamp(f.get('modifiedTime'))}\n"
                    f"Owner: {owner}\n"
                    f"Link: {f.get('webViewLink', 'N/A')}"
                )

            elif uri_str.startswith("gsheets://"):
                # URI form: gsheets://{spreadsheet_id}/{range}
                remainder = uri_str.removeprefix("gsheets://")
                parts = remainder.split("/", 1)
                spreadsheet_id = parts[0]
                range_name = parts[1] if len(parts) > 1 else "Sheet1"
                if not spreadsheet_id:
                    raise ValueError("spreadsheet_id is required in gsheets://{spreadsheet_id}/{range}")
                creds = get_creds(config)
                svc = build("sheets", "v4", credentials=creds)
                result = svc.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id, range=range_name
                ).execute()
                values = result.get("values", [])
                if not values:
                    return "No data found."
                rows = [
                    "| " + " | ".join(str(c) for c in row) + " |"
                    for row in values
                ]
                return f"Sheet data ({range_name}):\n" + "\n".join(rows)

            elif uri_str.startswith("gdocs://"):
                document_id = uri_str.removeprefix("gdocs://")
                if not document_id:
                    raise ValueError("document_id is required in gdocs://{document_id}")
                creds = get_creds(config)
                svc = build("docs", "v1", credentials=creds)
                doc = svc.documents().get(documentId=document_id).execute()
                return (
                    f"Document: {doc.get('title')}\n\n"
                    f"{document_to_text(doc) or '(the document has no readable text)'}"
                )

            else:
                raise ValueError(f"Unknown resource URI scheme: {uri_str}")

        text = await asyncio.to_thread(_fetch)
        return [ReadResourceContents(content=text, mime_type="text/plain")]

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    async def handle_list_prompts() -> List[types.Prompt]:
        return _prompts()

    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        from googleapiclient.discovery import build

        from .auth import get_creds

        args = arguments or {}

        if name == "summarize_inbox":
            query = args.get("query", "is:unread in:inbox")
            max_results = int(args.get("max_results", "20"))

            def _fetch_emails() -> str:
                creds = get_creds(config)
                svc = build("gmail", "v1", credentials=creds)
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
                creds = get_creds(config)
                svc = build("sheets", "v4", credentials=creds)
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
                creds = get_creds(config)
                svc = build("calendar", "v3", credentials=creds)
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
                creds = get_creds(config)
                svc = build("drive", "v3", credentials=creds)
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

    # MCP SDK 2.x registers handlers explicitly; the decorator API is gone.
    async def _list_tools(_context, _params):
        return types.ListToolsResult(tools=await handle_list_tools())

    async def _call_tool(_context, params):
        return await handle_call_tool(params.name, params.arguments, _context)

    async def _list_resources(_context, _params):
        return types.ListResourcesResult(resources=await handle_list_resources())

    async def _list_resource_templates(_context, _params):
        return types.ListResourceTemplatesResult(
            resource_templates=await handle_list_resource_templates()
        )

    async def _read_resource(_context, params):
        items = await handle_read_resource(params.uri)
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=str(params.uri),
                    mime_type=item.mime_type,
                    text=item.content,
                )
                for item in items
            ]
        )

    async def _list_prompts(_context, _params):
        return types.ListPromptsResult(prompts=await handle_list_prompts())

    async def _get_prompt(_context, params):
        return await handle_get_prompt(params.name, params.arguments)

    server.add_request_handler(
        "tools/list", types.PaginatedRequestParams, _list_tools
    )
    server.add_request_handler(
        "tools/call", types.CallToolRequestParams, _call_tool
    )
    server.add_request_handler(
        "resources/list", types.PaginatedRequestParams, _list_resources
    )
    server.add_request_handler(
        "resources/templates/list",
        types.PaginatedRequestParams,
        _list_resource_templates,
    )
    server.add_request_handler(
        "resources/read", types.ReadResourceRequestParams, _read_resource
    )
    server.add_request_handler(
        "prompts/list", types.PaginatedRequestParams, _list_prompts
    )
    server.add_request_handler(
        "prompts/get", types.GetPromptRequestParams, _get_prompt
    )

    return server


async def run() -> None:
    config = load_config()
    logger = setup_logging(config.log_file, level=config.log_level)
    server = create_server(config, logger)

    async with stdio_server() as (read, write):
        await server.run(
            read_stream=read,
            write_stream=write,
            initialization_options=server.create_initialization_options(),
        )
