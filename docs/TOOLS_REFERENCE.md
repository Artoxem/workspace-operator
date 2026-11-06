# MCP Tools Reference

Below is a list of tools, resources, and prompts available in this MCP server.
All tool calls require `MCP_AUTH_TOKEN` to be configured on the server.

## MCP Primitives

This server exposes three types of MCP primitives:

| Primitive | Description |
|-----------|-------------|
| **Tools** | Executable actions (read, write, delete). Triggered by the AI on demand. |
| **Resources** | Passive data sources that can be attached to context. Read-only snapshots of Google data. |
| **Prompts** | Reusable prompt templates that fetch live data and prepare it for AI analysis. |

## Tool Annotations

Every tool is annotated with safety hints:

| Annotation | Meaning |
|------------|---------|
| `readOnlyHint: true` | The tool only reads data and makes no changes. |
| `destructiveHint: true` | The tool can permanently delete or overwrite data. |
| `destructiveHint: false` | The tool writes or modifies data, but the action is reversible or low-risk. |

Compatible MCP clients (e.g. Cursor) use these hints to warn users before destructive actions.

## Tool profiles

`tool_profile` in `config.yaml` decides which tools exist for this deployment.
Tools outside the profile are not listed by `tools/list` and cannot be called —
the server answers with an explicit "disabled by the active tool profile" error.

| Profile | Tools | What is exposed |
|---|---:|---|
| `full` (default) | 63 | everything |
| `read-write` | 55 | everything except `destructiveHint: true` |
| `read-only` | 21 | only `readOnlyHint: true` |

`allowed_tools` and `denied_tools` are applied on top; deny wins over allow.

```yaml
tool_profile: "read-write"
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Environment overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.

## Usage examples

### Basic operations
```
# Get your Gmail address (smoke test)
Tool: get_gmail_profile
Result: Authenticated Gmail address: user@example.com

# Search for files in Drive
Tool: find_files
Arguments: {"query": "name contains 'budget'"}
Result: Found files:
- Budget_2026.xlsx (ID: 1a2b3c...) [application/vnd.google-apps.spreadsheet]

# Read a Google Sheet
Tool: read_sheet
Arguments: {
  "spreadsheet_id": "1a2b3c4d5e...",
  "range_name": "Sheet1!A1:C10"
}
Result: Data from sheet (range Sheet1!A1:C10):
| Name | Email | Status |
| John | john@example.com | Active |
...

# Create a draft email (safe by default)
Tool: send_email
Arguments: {
  "to": "colleague@example.com",
  "subject": "Meeting notes",
  "body_text": "Here are the notes from our meeting...",
  "draft_mode": true
}
Result: EMAIL DRAFT CREATED (ID: r1234...)
Email saved as DRAFT, not sent yet.
To send: send_email(..., draft_mode=False)
```

### Safety features
```
# Destructive operations require confirmation
Tool: delete_email
Arguments: {"message_id": "18abc...", "confirm": false}
Result: CONFIRMATION REQUIRED
This will permanently delete email 18abc...
To proceed, call this tool again with confirm=True

# Large operations use dry-run mode
Tool: clear_range
Arguments: {"spreadsheet_id": "1a2b...", "range_name": "Sheet1!A1:Z1000"}
Result: DRY RUN: Large range detected (26,000 cells)
Would clear range: Sheet1!A1:Z1000
To proceed: clear_range(..., confirm=True)
```

## Cross-product search
- `workspace_search(query, sources?, limit?, calendar_days_back?, calendar_days_ahead?)`
  - One query across Drive, Gmail and Calendar, merged and sorted by date.
  - `sources`: comma-separated list of `drive`, `gmail`, `calendar`. Default: `drive,gmail`.
  - `limit`: per-source limit, 1–25 (default 10).
  - Calendar window defaults: 30 days back, 180 days ahead.
  - Partial failures are reported inline; the rest of the results are still returned.

Example:

```
Tool: workspace_search
Arguments: {"query": "Q3 budget", "sources": "drive,gmail,calendar", "limit": 10}
Result:
Workspace search: 'Q3 budget' — 6 result(s) [drive (3), gmail (2), calendar (1)]

1. [drive] Budget 2026 — spreadsheet
   2026-03-02 10:11 UTC | type: spreadsheet | id: 1a2b3c
   https://docs.google.com/spreadsheets/d/1a2b3c
```

## Drive files
- `drive_upload(local_path, name?, parent_id?, mime_type?, convert_to?)`
  - Upload a local file (limit 100 MB). `convert_to`: `google-docs`, `google-sheets`
    or `google-slides` converts docx/xlsx/pptx into a native Google file.
- `drive_download(file_id, save_to?, overwrite?)`
  - Download a binary file. `save_to` may be a directory (default `~/Downloads`)
    or a full path. Google-native files are rejected with a hint to use `drive_export`.
- `drive_export(file_id, format, save_to?, overwrite?)`
  - Export a native file: `pdf`, `docx`, `xlsx`, `pptx`, `csv`, `txt`, `md`,
    `html`, `rtf`, `epub`, `odt/ods/odp`, `png/jpeg/svg`, `zip`.
  - The tool validates the format against the file type and never overwrites
    without `overwrite=true`.

## Drive
- `find_files(query)`
  - Search by name or full Drive query.
- `create_folder(name, parent_id?)`
  - Create a folder; `parent_id` is optional.
- `move_file(file_id, folder_id)`
  - Move a file to a folder.
- `share_file(file_id, role, type?, email_address?, allow_public?)`
  - `type`: `user|group|domain|anyone`, public access only with `allow_public=true`.
- `drive_search_advanced(query, limit?)`
  - Full Drive query syntax.
- `drive_list_permissions(file_id)`
  - List permissions.
- `drive_revoke_public(file_id, confirm?)`
  - Revoke public access, requires `confirm=true`.
- `drive_copy_file(file_id, name?, parent_id?)`
  - Copy a file.

## Sheets
- `read_sheet(spreadsheet_id, range_name)`
  - Read a range.
- `append_row(spreadsheet_id, range_name, values[])`
  - Append a row.
- `update_sheet(spreadsheet_id, range_name, values[][])`
  - Update a range with rows.
- `create_spreadsheet(title)`
  - Create a spreadsheet.
- `add_sheet(spreadsheet_id, title)`
  - Add a sheet (tab).
- `clear_range(spreadsheet_id, range_name, confirm?)`
  - Large ranges require `confirm=true`.
- `sheet_create_filter_view(spreadsheet_id, sheet_id, title, start_row?, end_row?, start_col?, end_col?)`
  - Create a filter view.
- `sheet_export_csv(spreadsheet_id, range_name, max_rows?)`
  - Export a range to CSV.
- `sheet_find_replace(spreadsheet_id, range_name, find_text, replace_text, dry_run?, match_case?)`
  - Defaults to `dry_run=true`.
- `sheet_create_named_range(spreadsheet_id, name, sheet_id, start_row, end_row, start_col, end_col)`
  - Named range by grid indexes.
- `get_spreadsheet_meta(spreadsheet_id)`
  - Spreadsheet metadata.

- `sheet_format(spreadsheet_id, sheet_name?, range?, bold?, italic?, font_size?, number_format?, background_color?, text_color?, horizontal_alignment?, wrap?, column_width?, row_height?, freeze_rows?, freeze_cols?)`
  - One `batchUpdate` for cell formatting, column/row sizes and frozen panes.
  - `range`: `A1:C10`, `A:C` or `1:10`; default is the whole sheet. Colours are `#RRGGBB`.
  - `column_width`/`row_height` are pixels; `freeze_rows`/`freeze_cols` are sheet-level.

## Docs
- `read_doc(document_id)`
  - Read document text.
- `create_doc(title)`
  - Create a document.
- `append_to_doc(document_id, text)`
  - Append text.
- `doc_fill_template(document_id, replacements, confirm?)`
  - Fill a template, requires `confirm=true`.
- `doc_export_pdf(document_id)`
  - Export document as a binary PDF. Returns an `EmbeddedResource` with MIME type `application/pdf`.

## Slides
- `slides_create(title)`
  - Create a presentation, returns its ID and URL.
- `slides_get(presentation_id)`
  - Slide count, slide IDs and the text on each slide.
- `slides_add_slide(presentation_id, layout?, insertion_index?)`
  - Add a slide; layouts: `TITLE_AND_BODY` (default), `TITLE_ONLY`, `BLANK`,
    `SECTION_HEADER`, `MAIN_POINT`, …
- `slides_replace_text(presentation_id, replacements, confirm?)`
  - Replace placeholders everywhere; without `confirm=true` returns a preview
    with per-key occurrence counts.
- `slides_insert_image(presentation_id, slide_id, image_url, width?, height?, left?, top?)`
  - Image URL must be publicly reachable; size and position are in pixels.

## Gmail
- `send_email(to, subject, body_text, draft_mode?)`
  - Defaults to draft mode.
- `send_draft(draft_id)`
  - Send a draft.
- `get_gmail_profile()`
  - Get authenticated address.
- `create_draft(to, subject, body_text)`
  - Create a draft.
- `list_emails(max_results?, query?)`
  - List emails with date, sender and subject (plus a cleaned snippet).
- `read_email(message_id)`
  - Read a message: From / To / Date / Subject / status / labels / attachments,
    plus the decoded body (text/plain preferred, HTML converted, 2 500 characters max).
- `delete_email(message_id, confirm?)`
  - Requires `confirm=true`.
- `batch_delete_emails(message_ids[], dry_run?)`
  - Defaults to `dry_run=true`.
- `gmail_search_and_summarize(query, max_results?)`
  - Search with a short summary.
- `gmail_get_thread(thread_id?, message_id?, include_body?)`
  - Whole conversation with dates, senders, labels and attachments.
- `gmail_get_attachment(message_id, filename?, attachment_id?, save_to?, overwrite?)`
  - Saves an attachment to disk; with a single attachment no selector is needed.
- `gmail_reply(message_id, body_text, reply_all?, draft_mode?)`
  - Replies inside the thread with `In-Reply-To`/`References`; drafts by default.
- `gmail_archive(message_id, confirm?)`
  - Requires `confirm=true`.
- `gmail_label_apply(message_ids[], label_name, dry_run?, create_if_missing?)`
  - Defaults to `dry_run=true`.

## Calendar
- `list_events(calendar_id?, max_results?)`
  - List upcoming events (from now onwards).
- `create_event(summary, start_time, end_time, description?, calendar_id?)`
  - Create an event. `calendar_id` defaults to `"primary"`.
- `calendar_find_free_slots(calendar_id?, start_time, end_time, duration_minutes?, max_results?)`
  - Find free slots.
- `calendar_create_meeting(summary, start_time, end_time, attendees?, description?, location?, confirm?)`
  - Requires `confirm=true`.

- `calendar_update_event(event_id, calendar_id?, summary?, start_time?, end_time?, description?, location?, attendees?, send_updates?)`
  - Patch semantics: only the fields you pass are changed. `send_updates`: `all|externalOnly|none`.
- `calendar_delete_event(event_id, calendar_id?, confirm?, send_updates?)`
  - Requires `confirm=true`.
- `calendar_respond_to_invite(event_id, response, calendar_id?, confirm?, send_updates?)`
  - `response`: `accepted|declined|tentative`; requires `confirm=true`.

## Composite
- `report_from_sheet(spreadsheet_id, range?, doc_title?, max_rows?)`
  - Reads a range, computes per-column statistics (sum/avg/min/max for numeric
    columns, non-empty/unique for text) and creates a Google Doc with the summary
    and a fixed-width data preview.

## Apps Script
- `script_run_function(script_id, function_name, parameters?, dev_mode?)`
  - Run a function from a project deployed as an API executable. `dev_mode=true`
    (default) executes the latest saved code. Returns the JSON result or the
    Apps Script error with its stack trace.
- `create_script_project(title, parent_id?)`
  - Create an Apps Script project.
- `get_script_content(script_id)`
  - Get project content.
- `prepare_script_update(script_id, files[])`
  - Prepare update, returns `operation_id`.
- `execute_operation(operation_id)`
  - Execute prepared operation.
- `cancel_operation(operation_id)`
  - Cancel prepared operation.
- `restore_script_backup(backup_path)`
  - Restore from backup.

---

## Resources

Resources are read-only data snapshots that MCP clients can attach directly to the AI context window. No arguments are needed for static resources; parameterised templates require embedding the IDs in the URI.

### Static resources

| URI | Description |
|-----|-------------|
| `gdrive://recent` | 20 most recently modified files in Google Drive |
| `gmail://inbox` | Up to 20 unread messages in the Gmail inbox |
| `gcalendar://upcoming` | Upcoming events in the primary calendar (next 7 days) |

### Resource templates

| URI template | Description |
|--------------|-------------|
| `gdrive://file/{file_id}` | Metadata for a specific Google Drive file |
| `gsheets://{spreadsheet_id}/{range}` | Data from a specific spreadsheet range, e.g. `gsheets://SPREADSHEET_ID/Sheet1!A1:Z100` |
| `gdocs://{document_id}` | Full text content of a specific Google Doc |

### Examples
```
# Attach recent Drive files to context
Resource URI: gdrive://recent

# Read a specific spreadsheet range
Resource URI: gsheets://1a2b3c4d5e.../Sheet1!A1:D20

# Read a specific document
Resource URI: gdocs://1a2b3c4d5e...
```

---

## Prompts

Prompts are reusable templates that fetch live Google data and embed it into a structured message ready for AI analysis. They appear in the MCP client's prompt picker.

### `summarize_inbox`
Fetch recent Gmail messages and prepare them for AI summarization.

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `query` | No | `is:unread in:inbox` | Gmail search query |
| `max_results` | No | `20` | Maximum number of emails to include |

### `analyze_spreadsheet`
Read a Google Sheet range and prepare the data for AI analysis or visualization.

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `spreadsheet_id` | Yes | — | The Google Spreadsheet ID |
| `range` | No | `Sheet1` | Sheet range to read |

### `plan_week`
Fetch upcoming calendar events and prepare a weekly planning summary for AI-assisted scheduling.

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `days_ahead` | No | `7` | Number of days to look ahead |

### `search_drive`
Search Google Drive for files and prepare a structured list for AI review or organisation suggestions.

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `query` | Yes | — | Drive search query, e.g. `name contains "budget"` |
| `limit` | No | `20` | Maximum number of results |
