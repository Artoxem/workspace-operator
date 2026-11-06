"""MCP server exposing Google Workspace tools, resources and prompts."""

import asyncio
import base64
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import List

from pydantic import AnyUrl

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.lowlevel.helper_types import ReadResourceContents
import mcp.types as types

from .config import load_config
from .logging import setup_logging
from .profiles import ProfileError, resolve_profile
from .security import require_token_configured
from .operations import BinaryResult
from .text import clean_text, format_timestamp, humanize_http_error, parse_email_date
from .handlers import (
    add_sheet_handler,
    append_row_handler,
    append_to_doc_handler,
    batch_delete_emails_handler,
    calendar_create_meeting_handler,
    calendar_find_free_slots_handler,
    cancel_operation_handler,
    clear_range_handler,
    create_doc_handler,
    create_draft_handler,
    create_event_handler,
    create_folder_handler,
    create_script_project_handler,
    create_spreadsheet_handler,
    delete_email_handler,
    doc_export_pdf_handler,
    doc_fill_template_handler,
    drive_copy_file_handler,
    drive_list_permissions_handler,
    drive_revoke_public_handler,
    drive_search_advanced_handler,
    execute_operation_handler,
    find_files_handler,
    get_gmail_profile_handler,
    get_script_content_handler,
    get_spreadsheet_meta_handler,
    gmail_archive_handler,
    gmail_label_apply_handler,
    gmail_search_and_summarize_handler,
    list_emails_handler,
    list_events_handler,
    move_file_handler,
    prepare_script_update_handler,
    read_doc_handler,
    read_email_handler,
    read_sheet_handler,
    restore_script_backup_handler,
    send_draft_handler,
    send_email_handler,
    share_file_handler,
    sheet_create_filter_view_handler,
    sheet_create_named_range_handler,
    sheet_export_csv_handler,
    sheet_find_replace_handler,
    update_sheet_handler,
    workspace_search_handler,
    document_to_text,
    drive_download_handler,
    drive_export_handler,
    drive_upload_handler,
    script_run_function_handler,
    slides_add_slide_handler,
    slides_create_handler,
    slides_get_handler,
    slides_insert_image_handler,
    slides_replace_text_handler,
)

# ---------------------------------------------------------------------------
# Annotation presets (reused across tool definitions)
# ---------------------------------------------------------------------------
_READ_ONLY = types.ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_WRITE = types.ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_DESTRUCTIVE = types.ToolAnnotations(readOnlyHint=False, destructiveHint=True)


def _tools() -> List[types.Tool]:
    """Return the full list of tool definitions with annotations."""
    return [
        # ── Cross-product search ──────────────────────────────────────────
        types.Tool(
            name="workspace_search",
            description=(
                "Search Google Drive, Gmail and Calendar with one query and get a "
                "merged, date-sorted result list. Use it for 'find everything about X' "
                "questions before falling back to per-service tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text query, e.g. 'Q3 budget'",
                    },
                    "sources": {
                        "type": "string",
                        "default": "drive,gmail",
                        "description": (
                            "Comma-separated sources to search: drive, gmail, calendar"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum results per source (1-25)",
                    },
                    "calendar_days_back": {
                        "type": "integer",
                        "default": 30,
                        "description": "Calendar only: how far back to search",
                    },
                    "calendar_days_ahead": {
                        "type": "integer",
                        "default": 180,
                        "description": "Calendar only: how far ahead to search",
                    },
                },
                "required": ["query"],
            },
            annotations=_READ_ONLY,
        ),
        # ── Google Drive ──────────────────────────────────────────────────
        types.Tool(
            name="find_files",
            description="Search for files on Google Drive. Query example: 'name contains \"System\"'",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="drive_search_advanced",
            description="Advanced Google Drive search with full query syntax",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["query"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="drive_list_permissions",
            description="List permissions for a Drive file",
            inputSchema={
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="create_folder",
            description="Create a folder in Google Drive",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent_id": {"type": "string"},
                },
                "required": ["name"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="move_file",
            description="Move a file to a different folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "folder_id": {"type": "string"},
                },
                "required": ["file_id", "folder_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="drive_copy_file",
            description="Copy a Drive file to a new file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "name": {"type": "string"},
                    "parent_id": {"type": "string"},
                },
                "required": ["file_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="share_file",
            description=(
                "Share a file with a user or make it public. "
                "REQUIRES allow_public=True to share publicly!"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["reader", "commenter", "writer"],
                    },
                    "type": {
                        "type": "string",
                        "enum": ["user", "group", "domain", "anyone"],
                        "description": "Access type. 'anyone' requires allow_public=True",
                    },
                    "email_address": {
                        "type": "string",
                        "description": "Required for type 'user' or 'group'",
                    },
                    "allow_public": {
                        "type": "boolean",
                        "description": "MUST be true to share with type='anyone'. Security check.",
                        "default": False,
                    },
                },
                "required": ["file_id", "role"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="drive_revoke_public",
            description="Revoke public access (type=anyone) for a Drive file. Requires confirm=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["file_id"],
            },
            annotations=_DESTRUCTIVE,
        ),
        # ── Drive files (local ↔ cloud) ───────────────────────────────────
        types.Tool(
            name="drive_upload",
            description=(
                "Upload a local file to Google Drive. Use convert_to to turn a "
                "docx/xlsx/pptx into a native Google Doc, Sheet or Slide."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "local_path": {
                        "type": "string",
                        "description": "Path on the machine running this server",
                    },
                    "name": {
                        "type": "string",
                        "description": "Drive file name (default: the local file name)",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Destination folder ID (default: My Drive root)",
                    },
                    "mime_type": {
                        "type": "string",
                        "description": "Override the detected content type",
                    },
                    "convert_to": {
                        "type": "string",
                        "enum": ["google-docs", "google-sheets", "google-slides"],
                        "description": "Convert to a native Google file on upload",
                    },
                },
                "required": ["local_path"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="drive_download",
            description=(
                "Download a binary Google Drive file to disk. Google-native files "
                "(Docs, Sheets, Slides) must be converted with drive_export first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "save_to": {
                        "type": "string",
                        "description": "File or directory path (default: ~/Downloads)",
                    },
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["file_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="drive_export",
            description=(
                "Export a Google Doc, Sheet or Presentation to a local file: pdf, "
                "docx, xlsx, pptx, csv, txt and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "description": "pdf | docx | xlsx | pptx | csv | txt | md | html | …",
                    },
                    "save_to": {
                        "type": "string",
                        "description": "File or directory path (default: ~/Downloads)",
                    },
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["file_id", "format"],
            },
            annotations=_READ_ONLY,
        ),

        # ── Google Sheets ─────────────────────────────────────────────────
        types.Tool(
            name="read_sheet",
            description="Read data from a Google Sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                },
                "required": ["spreadsheet_id", "range_name"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="get_spreadsheet_meta",
            description="Get metadata (sheets, titles) of a spreadsheet",
            inputSchema={
                "type": "object",
                "properties": {"spreadsheet_id": {"type": "string"}},
                "required": ["spreadsheet_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="sheet_export_csv",
            description="Export a range as CSV text",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                    "max_rows": {"type": "integer", "default": 5000},
                },
                "required": ["spreadsheet_id", "range_name"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="create_spreadsheet",
            description="Create a new Google Spreadsheet",
            inputSchema={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="add_sheet",
            description="Add a new sheet (tab) to a spreadsheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["spreadsheet_id", "title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="append_row",
            description="Append a row to a Google Sheet",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                    "values": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["spreadsheet_id", "range_name", "values"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="update_sheet",
            description="Update data in a Google Sheet. 'values' must be a list of lists of strings (rows of columns).",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                    "values": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "required": ["spreadsheet_id", "range_name", "values"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="clear_range",
            description="Clear values in a spreadsheet range. Auto dry-run for large ranges (>100 cells).",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to clear large ranges (>100 cells)",
                        "default": False,
                    },
                },
                "required": ["spreadsheet_id", "range_name"],
            },
            annotations=_DESTRUCTIVE,
        ),
        types.Tool(
            name="sheet_find_replace",
            description="Find/replace in a range with dry-run preview",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range_name": {"type": "string"},
                    "find_text": {"type": "string"},
                    "replace_text": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                    "match_case": {"type": "boolean", "default": False},
                },
                "required": ["spreadsheet_id", "range_name", "find_text", "replace_text"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="sheet_create_filter_view",
            description="Create a filter view for a sheet with grid range",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "sheet_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "start_row": {"type": "integer", "default": 0},
                    "end_row": {"type": "integer"},
                    "start_col": {"type": "integer", "default": 0},
                    "end_col": {"type": "integer"},
                },
                "required": ["spreadsheet_id", "sheet_id", "title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="sheet_create_named_range",
            description="Create a named range using grid indexes",
            inputSchema={
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "name": {"type": "string"},
                    "sheet_id": {"type": "integer"},
                    "start_row": {"type": "integer"},
                    "end_row": {"type": "integer"},
                    "start_col": {"type": "integer"},
                    "end_col": {"type": "integer"},
                },
                "required": [
                    "spreadsheet_id",
                    "name",
                    "sheet_id",
                    "start_row",
                    "end_row",
                    "start_col",
                    "end_col",
                ],
            },
            annotations=_WRITE,
        ),
        # ── Google Docs ───────────────────────────────────────────────────
        types.Tool(
            name="read_doc",
            description="Read the content of a Google Doc",
            inputSchema={
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="create_doc",
            description="Create a new Google Doc",
            inputSchema={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="append_to_doc",
            description="Append text to a Google Doc",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["document_id", "text"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="doc_fill_template",
            description="Fill a Google Doc template by replacing placeholders. Requires confirm=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "replacements": {"type": "object"},
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["document_id", "replacements"],
            },
            annotations=_DESTRUCTIVE,
        ),
        types.Tool(
            name="doc_export_pdf",
            description="Export a Google Doc to PDF and return it as binary (EmbeddedResource)",
            inputSchema={
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
            },
            annotations=_READ_ONLY,
        ),
        # ── Google Slides ─────────────────────────────────────────────────
        types.Tool(
            name="slides_create",
            description="Create a new Google Slides presentation",
            inputSchema={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="slides_get",
            description=(
                "Read a presentation: title, slide count, slide IDs and the text "
                "on each slide"
            ),
            inputSchema={
                "type": "object",
                "properties": {"presentation_id": {"type": "string"}},
                "required": ["presentation_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="slides_add_slide",
            description="Add a slide to a presentation using a predefined layout",
            inputSchema={
                "type": "object",
                "properties": {
                    "presentation_id": {"type": "string"},
                    "layout": {
                        "type": "string",
                        "default": "TITLE_AND_BODY",
                        "description": "Predefined layout, e.g. TITLE_AND_BODY, TITLE_ONLY, BLANK",
                    },
                    "insertion_index": {
                        "type": "integer",
                        "description": "Where to insert the slide (default: at the end)",
                    },
                },
                "required": ["presentation_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="slides_replace_text",
            description=(
                "Replace placeholder text across a presentation. Requires "
                "confirm=true; without it returns a preview of what will change."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "presentation_id": {"type": "string"},
                    "replacements": {
                        "type": "object",
                        "description": "Map of placeholder → value",
                    },
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["presentation_id", "replacements"],
            },
            annotations=_DESTRUCTIVE,
        ),
        types.Tool(
            name="slides_insert_image",
            description=(
                "Insert an image from a public URL onto a slide. Size and position "
                "are in pixels and optional."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "presentation_id": {"type": "string"},
                    "slide_id": {"type": "string"},
                    "image_url": {"type": "string"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "left": {"type": "number"},
                    "top": {"type": "number"},
                },
                "required": ["presentation_id", "slide_id", "image_url"],
            },
            annotations=_WRITE,
        ),

        # ── Apps Script ───────────────────────────────────────────────────
        types.Tool(
            name="create_script_project",
            description="Create a new Google Apps Script project",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "parent_id": {"type": "string"},
                },
                "required": ["title"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="get_script_content",
            description="Get the content of a Google Apps Script project",
            inputSchema={
                "type": "object",
                "properties": {"script_id": {"type": "string"}},
                "required": ["script_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="prepare_script_update",
            description="STEP 1: Prepare a Google Apps Script update with automatic backup. Returns operation_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "script_id": {
                        "type": "string",
                        "description": "The Apps Script project ID",
                    },
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "source": {"type": "string"},
                            },
                            "required": ["name", "type", "source"],
                        },
                        "description": "Array of files to update",
                    },
                },
                "required": ["script_id", "files"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="execute_operation",
            description="STEP 2: Execute a prepared operation by operation_id (from prepare_script_update)",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation_id": {
                        "type": "string",
                        "description": "The operation ID from prepare_script_update",
                    }
                },
                "required": ["operation_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="cancel_operation",
            description="Cancel a prepared operation before execution",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation_id": {
                        "type": "string",
                        "description": "The operation ID to cancel",
                    }
                },
                "required": ["operation_id"],
            },
            annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
        ),
        types.Tool(
            name="restore_script_backup",
            description="Restore a script from a backup file",
            inputSchema={
                "type": "object",
                "properties": {
                    "backup_path": {
                        "type": "string",
                        "description": "Full path to the backup JSON file",
                    }
                },
                "required": ["backup_path"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="script_run_function",
            description=(
                "Run a function from an Apps Script project deployed as an API "
                "executable. Executes arbitrary code with your account's authority."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "script_id": {"type": "string"},
                    "function_name": {"type": "string"},
                    "parameters": {
                        "type": "array",
                        "items": {},
                        "description": "Positional arguments passed to the function",
                    },
                    "dev_mode": {
                        "type": "boolean",
                        "default": True,
                        "description": "Run the latest saved code instead of the deployed version",
                    },
                },
                "required": ["script_id", "function_name"],
            },
            annotations=_DESTRUCTIVE,
        ),

        # ── Gmail ─────────────────────────────────────────────────────────
        types.Tool(
            name="get_gmail_profile",
            description="Get the authenticated Gmail address for the current OAuth token",
            inputSchema={"type": "object", "properties": {}, "required": []},
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="list_emails",
            description="List emails from Gmail",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "query": {
                        "type": "string",
                        "description": "Gmail search query (e.g. 'is:unread')",
                    },
                },
                "required": [],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="read_email",
            description="Read a specific email by ID",
            inputSchema={
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="gmail_search_and_summarize",
            description="Search Gmail and return a brief summary",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 50},
                },
                "required": ["query"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="create_draft",
            description="Create a draft email in Gmail",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body_text": {"type": "string"},
                },
                "required": ["to", "subject", "body_text"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="send_email",
            description="Send an email via Gmail. Defaults to draft_mode=True for safety!",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string"},
                    "body_text": {"type": "string"},
                    "draft_mode": {
                        "type": "boolean",
                        "description": "If true (default), creates draft instead of sending. Set to false to actually send.",
                        "default": True,
                    },
                },
                "required": ["to", "subject", "body_text"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="send_draft",
            description="Send an existing draft email by draft ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {
                        "type": "string",
                        "description": "The ID of the draft to send",
                    }
                },
                "required": ["draft_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="delete_email",
            description="Delete a specific email by ID. REQUIRES confirm=True parameter for safety!",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the email to delete",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "MUST be true to actually delete the email. Safety check.",
                        "default": False,
                    },
                },
                "required": ["message_id", "confirm"],
            },
            annotations=_DESTRUCTIVE,
        ),
        types.Tool(
            name="batch_delete_emails",
            description="Delete multiple emails by their IDs. Defaults to dry_run=True for safety!",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of message IDs to delete",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true (default), shows preview without deleting. Set to false to actually delete.",
                        "default": True,
                    },
                },
                "required": ["message_ids"],
            },
            annotations=_DESTRUCTIVE,
        ),
        types.Tool(
            name="gmail_archive",
            description="Archive a Gmail message (remove INBOX). Requires confirm=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["message_id"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="gmail_label_apply",
            description="Apply a label to messages with dry-run preview",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_ids": {"type": "array", "items": {"type": "string"}},
                    "label_name": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                    "create_if_missing": {"type": "boolean", "default": True},
                },
                "required": ["message_ids", "label_name"],
            },
            annotations=_WRITE,
        ),
        # ── Google Calendar ───────────────────────────────────────────────
        types.Tool(
            name="list_events",
            description="List upcoming calendar events",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": [],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="calendar_find_free_slots",
            description="Find free time slots in a calendar",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string", "default": "primary"},
                    "start_time": {
                        "type": "string",
                        "description": "ISO format start time",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO format end time",
                    },
                    "duration_minutes": {"type": "integer", "default": 30},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["start_time", "end_time"],
            },
            annotations=_READ_ONLY,
        ),
        types.Tool(
            name="create_event",
            description="Create a calendar event",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start_time": {
                        "type": "string",
                        "description": "ISO format start time",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO format end time",
                    },
                    "description": {"type": "string"},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
                "required": ["summary", "start_time", "end_time"],
            },
            annotations=_WRITE,
        ),
        types.Tool(
            name="calendar_create_meeting",
            description="Create a calendar meeting with attendees. Requires confirm=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start_time": {
                        "type": "string",
                        "description": "ISO format start time",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO format end time",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["summary", "start_time", "end_time"],
            },
            annotations=_WRITE,
        ),
    ]


async def run() -> None:
    config = load_config()
    logger = setup_logging(config.log_file, level=config.log_level)

    try:
        profile = resolve_profile(
            config.tool_profile, config.allowed_tools, config.denied_tools
        )
    except ProfileError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    server = Server("My Google Tools")
    all_tools = _tools()
    exposed_tools = profile.filter(all_tools)
    exposed_names = frozenset(tool.name for tool in exposed_tools)
    logger.info(
        "Starting with tool %s — %d of %d tools exposed",
        profile.describe(),
        len(exposed_tools),
        len(all_tools),
    )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        return exposed_tools

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> types.CallToolResult:
        if not arguments:
            arguments = {}

        if name not in exposed_names:
            logger.warning("Blocked tool call outside profile: %s", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            f"Tool '{name}' is disabled by the active tool profile "
                            f"({profile.name}). Adjust tool_profile, allowed_tools or "
                            "denied_tools in config.yaml to enable it."
                        ),
                    )
                ],
                isError=True,
            )

        try:
            require_token_configured(config.mcp_auth_token)

            handlers = {
                "workspace_search": lambda a: workspace_search_handler(
                    config,
                    logger,
                    a.get("query"),
                    a.get("sources"),
                    a.get("limit", 10),
                    a.get("calendar_days_back", 30),
                    a.get("calendar_days_ahead", 180),
                ),
                "drive_upload": lambda a: drive_upload_handler(
                    config,
                    logger,
                    a.get("local_path"),
                    a.get("name"),
                    a.get("parent_id"),
                    a.get("mime_type"),
                    a.get("convert_to"),
                ),
                "drive_download": lambda a: drive_download_handler(
                    config,
                    logger,
                    a.get("file_id"),
                    a.get("save_to"),
                    a.get("overwrite", False),
                ),
                "drive_export": lambda a: drive_export_handler(
                    config,
                    logger,
                    a.get("file_id"),
                    a.get("format"),
                    a.get("save_to"),
                    a.get("overwrite", False),
                ),
                "slides_create": lambda a: slides_create_handler(
                    config, logger, a.get("title")
                ),
                "slides_get": lambda a: slides_get_handler(
                    config, logger, a.get("presentation_id")
                ),
                "slides_add_slide": lambda a: slides_add_slide_handler(
                    config,
                    logger,
                    a.get("presentation_id"),
                    a.get("layout", "TITLE_AND_BODY"),
                    a.get("insertion_index"),
                ),
                "slides_replace_text": lambda a: slides_replace_text_handler(
                    config,
                    logger,
                    a.get("presentation_id"),
                    a.get("replacements") or {},
                    a.get("confirm", False),
                ),
                "slides_insert_image": lambda a: slides_insert_image_handler(
                    config,
                    logger,
                    a.get("presentation_id"),
                    a.get("slide_id"),
                    a.get("image_url"),
                    a.get("width"),
                    a.get("height"),
                    a.get("left"),
                    a.get("top"),
                ),
                "script_run_function": lambda a: script_run_function_handler(
                    config,
                    logger,
                    a.get("script_id"),
                    a.get("function_name"),
                    a.get("parameters"),
                    a.get("dev_mode", True),
                ),
                "find_files": lambda a: find_files_handler(config, logger, a.get("query")),
                "read_sheet": lambda a: read_sheet_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("range_name")
                ),
                "append_row": lambda a: append_row_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("range_name"), a.get("values")
                ),
                "update_sheet": lambda a: update_sheet_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("range_name"), a.get("values")
                ),
                "create_script_project": lambda a: create_script_project_handler(
                    config, logger, a.get("title"), a.get("parent_id")
                ),
                "get_script_content": lambda a: get_script_content_handler(
                    config, logger, a.get("script_id")
                ),
                "prepare_script_update": lambda a: prepare_script_update_handler(
                    config, logger, a.get("script_id"), a.get("files")
                ),
                "execute_operation": lambda a: execute_operation_handler(
                    config, logger, a.get("operation_id")
                ),
                "cancel_operation": lambda a: cancel_operation_handler(
                    config, logger, a.get("operation_id")
                ),
                "restore_script_backup": lambda a: restore_script_backup_handler(
                    config, logger, a.get("backup_path")
                ),
                "read_doc": lambda a: read_doc_handler(config, logger, a.get("document_id")),
                "create_doc": lambda a: create_doc_handler(config, logger, a.get("title")),
                "append_to_doc": lambda a: append_to_doc_handler(
                    config, logger, a.get("document_id"), a.get("text")
                ),
                "doc_fill_template": lambda a: doc_fill_template_handler(
                    config, logger, a.get("document_id"), a.get("replacements"), a.get("confirm", False)
                ),
                "doc_export_pdf": lambda a: doc_export_pdf_handler(
                    config, logger, a.get("document_id")
                ),
                "create_spreadsheet": lambda a: create_spreadsheet_handler(
                    config, logger, a.get("title")
                ),
                "add_sheet": lambda a: add_sheet_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("title")
                ),
                "clear_range": lambda a: clear_range_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("range_name"), a.get("confirm", False)
                ),
                "sheet_create_filter_view": lambda a: sheet_create_filter_view_handler(
                    config,
                    logger,
                    a.get("spreadsheet_id"),
                    a.get("sheet_id"),
                    a.get("title"),
                    a.get("start_row", 0),
                    a.get("end_row"),
                    a.get("start_col", 0),
                    a.get("end_col"),
                ),
                "sheet_export_csv": lambda a: sheet_export_csv_handler(
                    config, logger, a.get("spreadsheet_id"), a.get("range_name"), a.get("max_rows", 5000)
                ),
                "sheet_find_replace": lambda a: sheet_find_replace_handler(
                    config,
                    logger,
                    a.get("spreadsheet_id"),
                    a.get("range_name"),
                    a.get("find_text"),
                    a.get("replace_text"),
                    a.get("dry_run", True),
                    a.get("match_case", False),
                ),
                "sheet_create_named_range": lambda a: sheet_create_named_range_handler(
                    config,
                    logger,
                    a.get("spreadsheet_id"),
                    a.get("name"),
                    a.get("sheet_id"),
                    a.get("start_row"),
                    a.get("end_row"),
                    a.get("start_col"),
                    a.get("end_col"),
                ),
                "get_spreadsheet_meta": lambda a: get_spreadsheet_meta_handler(
                    config, logger, a.get("spreadsheet_id")
                ),
                "send_email": lambda a: send_email_handler(
                    config, logger, a.get("to"), a.get("subject"), a.get("body_text"), a.get("draft_mode", True)
                ),
                "send_draft": lambda a: send_draft_handler(config, logger, a.get("draft_id")),
                "get_gmail_profile": lambda a: get_gmail_profile_handler(config, logger),
                "create_draft": lambda a: create_draft_handler(
                    config, logger, a.get("to"), a.get("subject"), a.get("body_text")
                ),
                "list_emails": lambda a: list_emails_handler(
                    config, logger, a.get("max_results", 10), a.get("query")
                ),
                "read_email": lambda a: read_email_handler(config, logger, a.get("message_id")),
                "delete_email": lambda a: delete_email_handler(
                    config, logger, a.get("message_id"), a.get("confirm", False)
                ),
                "batch_delete_emails": lambda a: batch_delete_emails_handler(
                    config, logger, a.get("message_ids"), a.get("dry_run", True)
                ),
                "gmail_search_and_summarize": lambda a: gmail_search_and_summarize_handler(
                    config, logger, a.get("query"), a.get("max_results", 50)
                ),
                "gmail_archive": lambda a: gmail_archive_handler(
                    config, logger, a.get("message_id"), a.get("confirm", False)
                ),
                "gmail_label_apply": lambda a: gmail_label_apply_handler(
                    config,
                    logger,
                    a.get("message_ids"),
                    a.get("label_name"),
                    a.get("dry_run", True),
                    a.get("create_if_missing", True),
                ),
                "list_events": lambda a: list_events_handler(
                    config, logger, a.get("calendar_id", "primary"), a.get("max_results", 10)
                ),
                "create_event": lambda a: create_event_handler(
                    config,
                    logger,
                    a.get("summary"),
                    a.get("start_time"),
                    a.get("end_time"),
                    a.get("description", ""),
                    a.get("calendar_id", "primary"),
                ),
                "calendar_find_free_slots": lambda a: calendar_find_free_slots_handler(
                    config,
                    logger,
                    a.get("calendar_id", "primary"),
                    a.get("start_time"),
                    a.get("end_time"),
                    a.get("duration_minutes", 30),
                    a.get("max_results", 5),
                ),
                "calendar_create_meeting": lambda a: calendar_create_meeting_handler(
                    config,
                    logger,
                    a.get("summary"),
                    a.get("start_time"),
                    a.get("end_time"),
                    a.get("attendees"),
                    a.get("description", ""),
                    a.get("location", ""),
                    a.get("confirm", False),
                ),
                "create_folder": lambda a: create_folder_handler(
                    config, logger, a.get("name"), a.get("parent_id")
                ),
                "move_file": lambda a: move_file_handler(
                    config, logger, a.get("file_id"), a.get("folder_id")
                ),
                "share_file": lambda a: share_file_handler(
                    config,
                    logger,
                    a.get("file_id"),
                    a.get("role"),
                    a.get("type", "user"),
                    a.get("email_address"),
                    a.get("allow_public", False),
                ),
                "drive_search_advanced": lambda a: drive_search_advanced_handler(
                    config, logger, a.get("query"), a.get("limit", 50)
                ),
                "drive_list_permissions": lambda a: drive_list_permissions_handler(
                    config, logger, a.get("file_id")
                ),
                "drive_revoke_public": lambda a: drive_revoke_public_handler(
                    config, logger, a.get("file_id"), a.get("confirm", False)
                ),
                "drive_copy_file": lambda a: drive_copy_file_handler(
                    config, logger, a.get("file_id"), a.get("name"), a.get("parent_id")
                ),
            }

            if name not in handlers:
                raise ValueError(f"Unknown tool: {name}")

            result = await asyncio.to_thread(handlers[name], arguments)

            if isinstance(result, BinaryResult):
                return types.CallToolResult(
                    content=[
                        types.EmbeddedResource(
                            type="resource",
                            resource=types.BlobResourceContents(
                                uri=result.uri,
                                mimeType=result.mime_type,
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
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                isError=is_error,
            )

        except Exception as e:
            logger.exception("Tool call error [%s]: %s", name, e)
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text=f"Error: {humanize_http_error(e)}")
                ],
                isError=True,
            )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    @server.list_resources()
    async def handle_list_resources() -> List[types.Resource]:
        return [
            types.Resource(
                uri="gdrive://recent",
                name="Recent Google Drive Files",
                description="Lists the 20 most recently modified files in Google Drive",
                mimeType="text/plain",
            ),
            types.Resource(
                uri="gmail://inbox",
                name="Gmail Inbox",
                description="Recent unread messages in the Gmail inbox",
                mimeType="text/plain",
            ),
            types.Resource(
                uri="gcalendar://upcoming",
                name="Upcoming Calendar Events",
                description="Upcoming events from the primary Google Calendar (next 7 days)",
                mimeType="text/plain",
            ),
        ]

    @server.list_resource_templates()
    async def handle_list_resource_templates() -> List[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                uriTemplate="gdrive://file/{file_id}",
                name="Google Drive File",
                description="Metadata for a specific Google Drive file (ID required)",
                mimeType="text/plain",
            ),
            types.ResourceTemplate(
                uriTemplate="gsheets://{spreadsheet_id}/{range}",
                name="Google Sheets Range",
                description=(
                    "Data from a specific spreadsheet range, e.g. "
                    "gsheets://SPREADSHEET_ID/Sheet1!A1:Z100"
                ),
                mimeType="text/plain",
            ),
            types.ResourceTemplate(
                uriTemplate="gdocs://{document_id}",
                name="Google Document",
                description="Full text content of a specific Google Doc (ID required)",
                mimeType="text/plain",
            ),
        ]

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> Iterable[ReadResourceContents]:
        from .auth import get_creds
        from googleapiclient.discovery import build

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

    @server.list_prompts()
    async def handle_list_prompts() -> List[types.Prompt]:
        return [
            types.Prompt(
                name="summarize_inbox",
                description=(
                    "Fetch recent Gmail messages and prepare them for AI summarization. "
                    "Optionally filter by a Gmail search query."
                ),
                arguments=[
                    types.PromptArgument(
                        name="query",
                        description="Gmail search query (default: 'is:unread in:inbox')",
                        required=False,
                    ),
                    types.PromptArgument(
                        name="max_results",
                        description="Maximum number of emails to include (default: 20)",
                        required=False,
                    ),
                ],
            ),
            types.Prompt(
                name="analyze_spreadsheet",
                description=(
                    "Read a Google Sheet range and prepare the data for AI analysis "
                    "or visualization."
                ),
                arguments=[
                    types.PromptArgument(
                        name="spreadsheet_id",
                        description="The Google Spreadsheet ID",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="range",
                        description="Sheet range to read (default: Sheet1)",
                        required=False,
                    ),
                ],
            ),
            types.Prompt(
                name="plan_week",
                description=(
                    "Fetch upcoming calendar events and prepare a weekly planning summary "
                    "for AI-assisted scheduling."
                ),
                arguments=[
                    types.PromptArgument(
                        name="days_ahead",
                        description="Number of days to look ahead (default: 7)",
                        required=False,
                    ),
                ],
            ),
            types.Prompt(
                name="search_drive",
                description=(
                    "Search Google Drive for files and prepare a structured list "
                    "for AI review or organisation suggestions."
                ),
                arguments=[
                    types.PromptArgument(
                        name="query",
                        description="Drive search query (e.g. 'name contains \"budget\"')",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="limit",
                        description="Maximum number of results (default: 20)",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        from .auth import get_creds
        from googleapiclient.discovery import build

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

        else:
            raise ValueError(f"Unknown prompt: {name}")

    # ------------------------------------------------------------------
    # Start server
    # ------------------------------------------------------------------

    async with stdio_server() as (read, write):
        await server.run(
            read_stream=read,
            write_stream=write,
            initialization_options=server.create_initialization_options(),
        )
