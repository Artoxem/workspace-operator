---
name: google-workspace-automation
description: Use the Workspace Operator MCP server for Drive, Docs, Sheets, Gmail, Calendar, Tasks, Forms and Apps Script work. Search before reading, read before writing, and use action-based tools with confirm=true for destructive changes.
license: MIT
metadata:
  server: workspace-operator
  version: "2.0.1"
---

# Google Workspace automation

Workspace Operator 2.0 exposes **39 consolidated tools**. Most tools take an
`action`; call the action that matches the task and pass only its parameters.

```json
{"name": "drive_read", "arguments": {"action": "metadata", "file_id": "..."}}
```

## 1. Search before you dig

Start with `workspace_search` for "find everything about X". Use `drive_search`
for Drive query syntax, and `gmail_read` with `action="search"` for Gmail
operators.

| Need | Tool / action |
|---|---|
| Cross-service search | `workspace_search` |
| Drive query syntax | `drive_search` |
| Whole Gmail conversation | `gmail_read` → `thread` |
| Calendar free time | not exposed; use `calendar_read` → `events` |
| Inbox digest | `digest` |

## 2. Read before you write

Never guess an ID, sheet name or range.

| Task | Read first |
|---|---|
| Edit a spreadsheet | `sheets_read` → `meta`, then `read` |
| Format a spreadsheet | `sheets_read` → `meta` |
| Read a document | `read_doc` |
| Reply to mail | `gmail_read` → `read` or `thread` |
| Change a calendar | `calendar_read` → `events` |

## 3. Writes are staged, confirmed or drafted

- `gmail_write` → `send`, `reply`, `send_with_attachments` default to
  `draft_mode=true`. Set `draft_mode=false` only when the user explicitly asks.
- `sheets_write` → `find_replace` returns a preview without `confirm=true`;
  `gmail_settings` → `label_apply` defaults to `dry_run=true`.
- These actions require `confirm=true`:
  `drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
  `gmail_delete`, `calendar_delete`, `script_run`, `bulk_run`, `bulk_undo`.
- Public sharing is disabled by default; `drive_write` → `share` needs both
  `allow_public_sharing=true` in config and `allow_public=true`.
- There is no permanent Drive deletion: `drive_trash` only moves to Trash.

## 4. Drive

| Task | Tool / action |
|---|---|
| Search | `drive_search` |
| Metadata / export / permissions | `drive_read` → `metadata`, `export`, `list_permissions` |
| Create folder, copy, move, rename, upload, share, restore | `drive_write` → matching action |
| Move to Trash | `drive_trash` |
| Remove or revoke access | `drive_permissions` → `remove`, `revoke_public` |

`drive_download` and permanent deletion are not exposed in 2.0.

## 5. Docs, Sheets, Gmail, Calendar

- Docs: `read_doc`; `docs_write` → `create`, `append`, `insert_image`;
  `docs_edit` → `replace`, `format` (preview/confirm).
- Sheets: `sheets_read` → `meta`, `read`, `export_csv`; `sheets_write` → write
  values; `sheets_format`, `sheets_structure`, `sheets_data` for layout;
  `sheets_delete` for destructive row/column/sheet deletion.
- Gmail: `gmail_read` for profile/list/read/thread/attachment/search/labels;
  `gmail_write` for send/reply/drafts/archive; `gmail_settings` for labels and
  filters; `gmail_delete` for Trash.
- Calendar: `calendar_read`, `calendar_write` (meeting/update/move/respond/color),
  `calendar_delete`.

## 6. Bulk operations

For more than a handful of items, never loop single-item tools:

1. `bulk_plan` — resolve a selector, show the count and sample.
2. `bulk_run` — requires `confirm=true`; runs in the background.
3. `bulk_status`, `bulk_result` — follow progress and per-item results.
4. `bulk_undo` — reverses move, rename and trash where possible.

`bulk_plan` and `bulk_run` are the preferred path for Drive and Gmail batches.

## 7. Apps Script

1. `script_read` → `content`.
2. `script_write` → `prepare` (returns `operation_id`).
3. Show the staged change to the user.
4. `script_write` → `execute` (backup first).
5. On failure: `script_write` → `restore`, or `cancel` before execution.

`script_run` executes arbitrary Apps Script code; use it only on explicit request.

## 8. Respect the profile and scope routing

The default profile is `core` (20 tools). `full` adds formatting, destructive
edits, Forms, Postmaster and Script. `read-only` is for untrusted agents.
If a tool returns "disabled by the active tool profile" or is absent because a
Google scope is missing, report that instead of trying to work around it.

## 9. Answer shape

Lead with the answer, then the evidence: title, ID, timestamp, link. For batches,
give counts and the one or two items that matter.
