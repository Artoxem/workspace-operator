"""Consolidated 2.0 tool catalog.

The catalog is deliberately data-first: each tool lists its actions and the
legacy handler that implements each action. Schemas are assembled from the
handler definitions, so an action cannot drift away from its parameters.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from mcp import types

from .models import ActionSpec, Safety, ScopeMode, ToolSpec, annotations_for


CORE_TOOL_NAMES = frozenset(
    {
        "workspace_search",
        "drive_search",
        "drive_read",
        "drive_write",
        "drive_trash",
        "read_doc",
        "docs_write",
        "sheets_read",
        "sheets_write",
        "gmail_read",
        "gmail_write",
        "gmail_delete",
        "calendar_read",
        "calendar_write",
        "tasks_read",
        "tasks_write",
        "bulk_plan",
        "bulk_run",
        "bulk_status",
        "bulk_result",
    }
)

READ_ONLY_TIMEOUT = frozenset()


def _scopes(*names: str, mode: ScopeMode = ScopeMode.ALL) -> Tuple[frozenset, ScopeMode]:
    return frozenset(names), mode


def _any(*names: str) -> Tuple[frozenset, ScopeMode]:
    return frozenset(names), ScopeMode.ANY


def _legacy_index(tools: Iterable[types.Tool]) -> Dict[str, types.Tool]:
    return {tool.name: tool for tool in tools}


def _schema_for_actions(
    actions: Sequence[ActionSpec], legacy: Mapping[str, types.Tool]
) -> Dict[str, Any]:
    """Build a compact schema: one action enum plus the union of parameters."""
    properties: Dict[str, Any] = {
        "action": {
            "type": "string",
            "enum": [action.name for action in actions],
            "description": "Operation to perform.",
        }
    }
    for action in actions:
        source = legacy[action.legacy].input_schema
        for name, schema in (source.get("properties") or {}).items():
            properties.setdefault(name, schema)
    return {
        "type": "object",
        "properties": properties,
        "required": ["action"],
    }


def build_catalog(tools: Sequence[types.Tool]) -> Tuple[ToolSpec, ...]:
    """Return the 2.0 catalog for the given legacy definitions."""
    legacy = _legacy_index(tools)

    def action(
        name: str, legacy_name: str, summary: str, confirm: bool = False
    ) -> ActionSpec:
        source = legacy[legacy_name]
        required = tuple((source.input_schema or {}).get("required") or ())
        return ActionSpec(
            name=name,
            legacy=legacy_name,
            summary=summary,
            required=required,
            confirm=confirm,
        )

    def group(
        name: str,
        domain: str,
        safety: Safety,
        description: str,
        actions: Sequence[ActionSpec],
        scope_rule: Tuple[frozenset, ScopeMode] = (frozenset(), ScopeMode.ALL),
    ) -> ToolSpec:
        scopes, mode = scope_rule
        rendered = ", ".join(action.name for action in actions)
        return ToolSpec(
            name=name,
            description=f"{description} Actions: {rendered}.",
            input_schema=_schema_for_actions(actions, legacy),
            annotations=annotations_for(safety),
            domain=domain,
            safety=safety,
            actions=tuple(actions),
            required_scopes=scopes,
            scope_mode=mode,
        )

    def direct(
        name: str,
        legacy_name: str,
        domain: str,
        safety: Safety,
        description: str,
        scope_rule: Tuple[frozenset, ScopeMode] = (frozenset(), ScopeMode.ALL),
        confirm: bool = False,
    ) -> ToolSpec:
        source = legacy[legacy_name]
        scopes, mode = scope_rule
        schema = dict(source.input_schema or {})
        if confirm:
            properties = dict(schema.get("properties") or {})
            properties.setdefault(
                "confirm",
                {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true to apply this destructive action.",
                },
            )
            schema["properties"] = properties
        return ToolSpec(
            name=name,
            description=description,
            input_schema=schema,
            annotations=annotations_for(safety),
            domain=domain,
            safety=safety,
            legacy=legacy_name,
            required_scopes=scopes,
            scope_mode=mode,
            requires_confirm=confirm,
        )

    return (
        # ── Discovery / cross-domain ─────────────────────────────────────
        direct(
            "workspace_search",
            "workspace_search",
            "discovery",
            Safety.READ,
            "Search Drive, Gmail and Calendar in one call.",
        ),
        direct(
            "drive_search",
            "drive_search_advanced",
            "drive",
            Safety.READ,
            "Search Drive with full query syntax (replaces find_files and drive_search_advanced).",
            _any("drive", "drive.readonly"),
        ),
        direct(
            "digest",
            "digest",
            "discovery",
            Safety.READ,
            "Summarise Gmail, Calendar and Drive for the last N hours.",
        ),
        direct(
            "compare_tables",
            "compare_tables",
            "discovery",
            Safety.READ,
            "Diff two sheet ranges by a key column.",
        ),
        # ── Drive ────────────────────────────────────────────────────────
        group(
            "drive_read",
            "drive",
            Safety.READ,
            "Read Drive metadata, permissions and exported files.",
            (
                action("metadata", "drive_get_metadata", "File metadata."),
                action("export", "drive_export", "Export a Google file to a local format."),
                action("list_permissions", "drive_list_permissions", "List file permissions."),
            ),
            _any("drive", "drive.readonly"),
        ),
        group(
            "drive_write",
            "drive",
            Safety.WRITE,
            "Create, copy, move, rename, upload, share and restore Drive files.",
            (
                action("create_folder", "create_folder", "Create a folder."),
                action("copy", "drive_copy_file", "Copy a file."),
                action("move", "move_file", "Move a file to another folder."),
                action("rename", "drive_rename_file", "Rename a file."),
                action("upload", "drive_upload", "Upload a local file."),
                action("share", "share_file", "Share a file with a user."),
                action("restore", "drive_restore_file", "Restore a file from Trash."),
            ),
            _scopes("drive"),
        ),
        direct(
            "drive_trash",
            "drive_delete_file",
            "drive",
            Safety.DESTRUCTIVE,
            "Move a Drive file to Trash (recoverable 30 days; no permanent delete).",
            _scopes("drive"),
            confirm=True,
        ),
        group(
            "drive_permissions",
            "drive",
            Safety.DESTRUCTIVE,
            "Remove access from a Drive file.",
            (
                action(
                    "remove",
                    "drive_remove_permission",
                    "Remove one permission.",
                    confirm=True,
                ),
                action(
                    "revoke_public",
                    "drive_revoke_public",
                    "Revoke public access.",
                    confirm=True,
                ),
            ),
            _scopes("drive"),
        ),
        # ── Docs ─────────────────────────────────────────────────────────
        direct(
            "read_doc",
            "read_doc",
            "docs",
            Safety.READ,
            "Read the contents of a Google Doc.",
            _any("documents", "documents.readonly"),
        ),
        group(
            "docs_write",
            "docs",
            Safety.WRITE,
            "Create and extend Google Docs.",
            (
                action("create", "create_doc", "Create a document."),
                action("append", "append_to_doc", "Append text."),
                action("insert_image", "docs_insert_image", "Insert an image from a URL."),
            ),
            _scopes("documents"),
        ),
        group(
            "docs_edit",
            "docs",
            Safety.DESTRUCTIVE,
            "Replace or format text in a Google Doc, with a preview.",
            (
                action(
                    "replace",
                    "doc_replace_text",
                    "Replace text (preview without confirm).",
                    confirm=True,
                ),
                action(
                    "format",
                    "docs_format_text",
                    "Format all occurrences (preview without confirm).",
                    confirm=True,
                ),
            ),
            _scopes("documents"),
        ),
        # ── Sheets ───────────────────────────────────────────────────────
        group(
            "sheets_read",
            "sheets",
            Safety.READ,
            "Read sheet metadata, values and CSV exports.",
            (
                action("meta", "get_spreadsheet_meta", "List sheets and titles."),
                action("read", "read_sheet", "Read a range."),
                action("export_csv", "sheet_export_csv", "Export a range as CSV."),
            ),
            _any("spreadsheets", "spreadsheets.readonly"),
        ),
        group(
            "sheets_write",
            "sheets",
            Safety.WRITE,
            "Create spreadsheets and write values.",
            (
                action("create_spreadsheet", "create_spreadsheet", "Create a spreadsheet."),
                action("add_sheet", "add_sheet", "Add a sheet."),
                action("update", "update_sheet", "Write values."),
                action("append", "append_row", "Append a row."),
                action("clear", "clear_range", "Clear a range."),
                action("find_replace", "sheet_find_replace", "Find and replace with preview."),
            ),
            _scopes("spreadsheets"),
        ),
        group(
            "sheets_format",
            "sheets",
            Safety.WRITE,
            "Format ranges, borders, conditional rules, validation and protection.",
            (
                action("format", "sheet_format", "Format cells."),
                action("borders", "sheet_set_borders", "Draw borders."),
                action("conditional", "sheet_conditional_format", "Add conditional formatting."),
                action("validation", "sheet_set_data_validation", "Add data validation."),
                action("protect", "sheet_protect_range", "Protect a range."),
            ),
            _scopes("spreadsheets"),
        ),
        group(
            "sheets_structure",
            "sheets",
            Safety.WRITE,
            "Insert, merge, sort and organise sheet ranges.",
            (
                action("insert_rows", "sheet_insert_rows", "Insert rows."),
                action("insert_columns", "sheet_insert_columns", "Insert columns."),
                action("merge", "sheet_merge_cells", "Merge or unmerge cells."),
                action("sort", "sheet_sort_range", "Sort a range."),
                action("named_range", "sheet_create_named_range", "Create a named range."),
                action("filter_view", "sheet_create_filter_view", "Create a filter view."),
            ),
            _scopes("spreadsheets"),
        ),
        group(
            "sheets_delete",
            "sheets",
            Safety.DESTRUCTIVE,
            "Delete rows, columns or a sheet (requires confirm).",
            (
                action("delete_rows", "sheet_delete_rows", "Delete rows.", confirm=True),
                action(
                    "delete_columns",
                    "sheet_delete_columns",
                    "Delete columns.",
                    confirm=True,
                ),
                action("delete_sheet", "sheet_delete_sheet", "Delete a sheet.", confirm=True),
            ),
            _scopes("spreadsheets"),
        ),
        group(
            "sheets_data",
            "sheets",
            Safety.WRITE,
            "Charts and pivot tables.",
            (
                action("chart", "sheet_add_chart", "Insert a chart."),
                action("pivot", "sheet_add_pivot_table", "Create a pivot table."),
            ),
            _scopes("spreadsheets"),
        ),
        # ── Gmail ────────────────────────────────────────────────────────
        group(
            "gmail_read",
            "gmail",
            Safety.READ,
            "Read Gmail messages, threads, attachments, labels and filters.",
            (
                action("profile", "get_gmail_profile", "Get the authenticated address."),
                action("list", "list_emails", "List messages."),
                action("read", "read_email", "Read a message."),
                action("thread", "gmail_get_thread", "Read a conversation."),
                action("attachment", "gmail_get_attachment", "Save an attachment."),
                action("search", "gmail_search_and_summarize", "Search and summarise."),
                action("labels", "gmail_list_labels", "List labels."),
                action("filters", "gmail_list_filters", "List filters."),
            ),
            _any("gmail.modify", "gmail.readonly"),
        ),
        group(
            "gmail_write",
            "gmail",
            Safety.WRITE,
            "Send, reply, draft and archive Gmail messages.",
            (
                action("send", "send_email", "Send or draft a message."),
                action("reply", "gmail_reply", "Reply in a thread."),
                action(
                    "send_with_attachments",
                    "gmail_send_with_attachments",
                    "Send or draft with attachments.",
                ),
                action("draft_create", "create_draft", "Create a draft."),
                action("draft_update", "gmail_update_draft", "Replace a draft."),
                action("draft_send", "send_draft", "Send a draft."),
                action("draft_list", "gmail_list_drafts", "List drafts."),
                action("archive", "gmail_archive", "Archive a message."),
            ),
            _scopes("gmail.modify"),
        ),
        group(
            "gmail_settings",
            "gmail",
            Safety.WRITE,
            "Manage Gmail labels and filters.",
            (
                action("label_create", "gmail_create_label", "Create a label."),
                action("label_apply", "gmail_label_apply", "Apply a label."),
                action("filter_create", "gmail_create_filter", "Create a filter."),
            ),
            _scopes("gmail.modify", "gmail.settings.basic"),
        ),
        group(
            "gmail_delete",
            "gmail",
            Safety.DESTRUCTIVE,
            "Move messages or drafts to Trash (recoverable).",
            (
                action("email", "delete_email", "Move an email to Trash.", confirm=True),
                action(
                    "draft",
                    "gmail_delete_draft",
                    "Delete a draft.",
                    confirm=True,
                ),
            ),
            _scopes("gmail.modify"),
        ),
        # ── Calendar ─────────────────────────────────────────────────────
        group(
            "calendar_read",
            "calendar",
            Safety.READ,
            "Read events and calendars.",
            (
                action("events", "list_events", "List upcoming events."),
                action("calendars", "calendar_list_calendars", "List calendars."),
            ),
            _any("calendar", "calendar.readonly"),
        ),
        group(
            "calendar_write",
            "calendar",
            Safety.WRITE,
            "Create, update, move, answer and colour events.",
            (
                action("meeting", "calendar_create_meeting", "Create a meeting."),
                action("update", "calendar_update_event", "Update an event."),
                action("move", "calendar_move_event", "Move an event."),
                action("respond", "calendar_respond_to_invite", "Answer an invite."),
                action("color", "calendar_set_event_color", "Set an event colour."),
            ),
            _scopes("calendar"),
        ),
        direct(
            "calendar_delete",
            "calendar_delete_event",
            "calendar",
            Safety.DESTRUCTIVE,
            "Delete an event (requires confirm).",
            _scopes("calendar"),
            confirm=True,
        ),
        # ── Tasks / Forms / Postmaster ───────────────────────────────────
        group(
            "tasks_read",
            "tasks",
            Safety.READ,
            "Read task lists and tasks.",
            (
                action("lists", "tasks_list_lists", "List task lists."),
                action("list", "tasks_list", "List tasks."),
            ),
            _any("tasks", "tasks.readonly"),
        ),
        group(
            "tasks_write",
            "tasks",
            Safety.WRITE,
            "Create and complete tasks.",
            (
                action("create", "tasks_create", "Create a task."),
                action("complete", "tasks_complete", "Complete a task."),
            ),
            _scopes("tasks"),
        ),
        group(
            "forms_read",
            "forms",
            Safety.READ,
            "Read forms and responses.",
            (
                action("get", "forms_get", "Read a form."),
                action("responses", "forms_list_responses", "List responses."),
            ),
            _scopes("forms.body", "forms.responses.readonly"),
        ),
        group(
            "forms_write",
            "forms",
            Safety.WRITE,
            "Create forms and add questions.",
            (
                action("create", "forms_create", "Create a form."),
                action("add_questions", "forms_add_questions", "Add short-answer questions."),
            ),
            _scopes("forms.body", "forms.responses.readonly"),
        ),
        group(
            "postmaster_read",
            "postmaster",
            Safety.READ,
            "Read Postmaster domains and traffic statistics.",
            (
                action("domains", "postmaster_list_domains", "List verified domains."),
                action("traffic", "postmaster_traffic_stats", "Read traffic stats."),
            ),
            _scopes("postmaster.domain", "postmaster.traffic.readonly"),
        ),
        # ── Apps Script ──────────────────────────────────────────────────
        group(
            "script_read",
            "script",
            Safety.READ,
            "Read Apps Script content and deployments.",
            (
                action("content", "get_script_content", "Read project content."),
                action("deployments", "script_list_deployments", "List deployments."),
            ),
            _scopes("script.projects", "script.deployments"),
        ),
        group(
            "script_write",
            "script",
            Safety.WRITE,
            "Prepare, execute, restore and deploy Apps Script changes.",
            (
                action("create_project", "create_script_project", "Create a project."),
                action("prepare", "prepare_script_update", "Prepare an update with backup."),
                action("execute", "execute_operation", "Execute a prepared update."),
                action("cancel", "cancel_operation", "Cancel a prepared update."),
                action("restore", "restore_script_backup", "Restore a backup."),
                action("create_deployment", "script_create_deployment", "Create a deployment."),
                action("update_deployment", "script_update_deployment", "Update a deployment."),
            ),
            _scopes("script.projects", "script.deployments"),
        ),
        direct(
            "script_run",
            "script_run_function",
            "script",
            Safety.DESTRUCTIVE,
            "Run an Apps Script API function (arbitrary code; confirm required).",
            _scopes("script.projects", "script.deployments"),
            confirm=True,
        ),
        # ── Bulk ─────────────────────────────────────────────────────────
        direct(
            "bulk_plan",
            "bulk_plan",
            "bulk",
            Safety.READ,
            "Resolve a selector into a dry-run bulk plan.",
        ),
        direct(
            "bulk_run",
            "bulk_run",
            "bulk",
            Safety.DESTRUCTIVE,
            "Execute a reviewed bulk plan as a background job.",
            confirm=True,
        ),
        direct(
            "bulk_status",
            "bulk_status",
            "bulk",
            Safety.READ,
            "Read progress for a bulk job.",
        ),
        direct(
            "bulk_result",
            "bulk_result",
            "bulk",
            Safety.READ,
            "Read one page of bulk job results.",
        ),
        direct(
            "bulk_list",
            "bulk_list",
            "bulk",
            Safety.READ,
            "List recent bulk jobs.",
        ),
        direct(
            "bulk_cancel",
            "bulk_cancel",
            "bulk",
            Safety.WRITE,
            "Request cancellation of a running bulk job.",
        ),
        direct(
            "bulk_undo",
            "bulk_undo",
            "bulk",
            Safety.DESTRUCTIVE,
            "Undo a completed bulk job (move, rename, trash).",
            confirm=True,
        ),
    )
