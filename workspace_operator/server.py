"""MCP server exposing Google Workspace tools, resources and prompts."""

import sys
from collections.abc import Iterable
from typing import List, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from . import __version__
from .approvals import ApprovalStore
from .config import Config, load_config
from .definitions import load_prompts, load_tools

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
from .profiles import ProfileError
from .prompts import get_prompt, list_prompts
from .resources import list_resource_templates, list_resources, read_resource
from .runtime import AuditLog
from .tool_router import ToolRouter
from .toolset import (
    build_aliases,
    build_catalog,
    build_surface,
)
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
            "APPROVAL_REQUIRED, or ask the human through the client's elicitation "
            "dialog. The agent cannot approve its own request: tell the user it is "
            "pending, and retry with approval_id only after they confirm it was "
            "approved. Tools outside the active profile or "
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


    router = ToolRouter(
        config,
        logger,
        tool_index=tool_index,
        aliases=aliases,
        audit=audit,
        approvals=approvals,
        profile_name=profile_name,
        handler_module=sys.modules[__name__],
    )

    async def handle_call_tool(
        name: str, arguments: dict | None, ctx=None
    ) -> types.CallToolResult:
        return await router.handle(name, arguments, ctx)


    # ------------------------------------------------------------------
    # Resources and prompts (implemented in resources.py / prompts.py)
    # ------------------------------------------------------------------

    async def handle_list_resources() -> List[types.Resource]:
        return list_resources()

    async def handle_list_resource_templates() -> List[types.ResourceTemplate]:
        return list_resource_templates()

    async def handle_read_resource(uri: AnyUrl) -> Iterable[ReadResourceContents]:
        return await read_resource(config, uri)

    async def handle_list_prompts() -> List[types.Prompt]:
        return list_prompts()

    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        return await get_prompt(config, logger, name, arguments)


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


async def run(config: Optional[Config] = None) -> None:
    config = config or load_config()
    logger = setup_logging(config.log_file, level=config.log_level)
    server = create_server(config, logger)

    async with stdio_server() as (read, write):
        await server.run(
            read_stream=read,
            write_stream=write,
            initialization_options=server.create_initialization_options(),
        )
