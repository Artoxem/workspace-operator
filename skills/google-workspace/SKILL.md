---
name: google-workspace-automation
description: Use the Workspace Operator MCP server for Drive, Docs, Sheets, Slides, Gmail, Calendar and Apps Script work. Search before reading, read before writing, and stage every destructive change.
license: MIT
metadata:
  server: workspace-operator
  version: "1.22.2"
---

# Google Workspace automation

You have an MCP server with 132 tools over Google Drive, Docs, Sheets, Slides,
Gmail, Calendar and Apps Script. Follow this order; it keeps context small and
operations reversible.

## 1. Search before you dig

Start with `workspace_search` for any "find everything about X" request:

```json
{"query": "Q3 budget", "sources": "drive,gmail,calendar", "limit": 10}
```

It returns a merged, date-sorted list with IDs and links. Fall back to per-service
tools only for a specific capability:

| Need | Tool |
|---|---|
| Drive query syntax (`name contains`, `mimeType =`) | `find_files`, `drive_search_advanced` |
| Gmail operators (`from:`, `has:attachment`, `is:unread`) | `list_emails`, `gmail_search_and_summarize` |
| A whole conversation | `gmail_get_thread` |
| Calendar free/busy | `calendar_find_free_slots` |

## 2. Read before you write

Never guess an ID, sheet name or placeholder.

| Task | Read first |
|---|---|
| Edit a spreadsheet | `get_spreadsheet_meta` → `read_sheet` |
| Format a spreadsheet | `get_spreadsheet_meta` (sheet name and size) |
| Fill a document template | `read_doc` |
| Fill a presentation | `slides_get` |
| Reply to mail | `read_email` or `gmail_get_thread` |
| Change a calendar | `list_events` |

## 3. Writes are staged, confirmed or drafted

* `send_email` and `gmail_reply` default to `draft_mode=true` — they create drafts,
  they do not send. Set `draft_mode=false` only when the user explicitly asks.
* `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` default to
  `dry_run=true`. Show the dry-run summary, get approval, then re-run.
* `delete_email`, `gmail_archive`, `clear_range`, `drive_revoke_public`,
  `calendar_create_meeting`, `doc_fill_template`, `slides_replace_text`,
  `drive_delete_file`, `drive_remove_permission`, `drive_resolve_comment`,
  `doc_replace_text`, `slides_delete_slide`, `sheet_delete_sheet`,
  `sheet_delete_rows`, `drive_empty_trash`, `sheet_delete_columns`,
  `drive_transfer_ownership`, `docs_format_text`, `gmail_delete_draft` need `confirm=true`.
* `share_file` refuses `type=anyone` unless `allow_public=true`.
* `drive_download`, `drive_export`, `gmail_get_attachment` never overwrite without
  `overwrite=true`.

## 4. Files and presentations

* Bringing a local file in: `drive_upload` (add `convert_to` for
  `google-docs|google-sheets|google-slides` — this is how a .docx/.xlsx/.pptx
  becomes a native file).
* Taking a file out: `drive_download` for binaries, `drive_export` for Google Docs,
  Sheets and Slides (pdf/docx/xlsx/pptx/csv…).
* Building a deck: `slides_create` → `slides_add_slide` → `slides_replace_text`
  (preview first) → `slides_insert_image`; `slides_delete_slide` removes one after
  a preview.
* Editing a document in place: `doc_replace_text` — without `confirm=true` it only
  reports how many occurrences would change.
* Making a sheet readable: `sheet_format` — bold, colours, number formats, column
  widths, frozen rows; `sheet_conditional_format` colours cells by rule, and
  `sheet_add_chart` turns a range into a chart.
* Cleaning up Drive: `drive_get_metadata` first, then `drive_delete_file`
  (trash, reversible for 30 days) and `drive_restore_file`; `drive_remove_permission`
  revokes a single share.
* Discussing a document: `drive_list_comments` → `drive_create_comment` /
  `drive_reply_comment` → `drive_resolve_comment`.

## 5. Apps Script: prepare → inspect → execute

Never rewrite a script in one step.

1. `get_script_content` — read the current files.
2. `prepare_script_update` — stage the new content, returns `operation_id`.
3. Show the diff or the staged files to the user.
4. `execute_operation` — applies the change and writes a backup automatically.
5. If something breaks: `restore_script_backup`, or `cancel_operation` for a
   staged-but-not-executed change.

`script_run_function` runs an existing deployment; treat it as running code, not as
a read.

## 6. Respect the profile

The server may run with `read-only` or `read-write` tool profiles. If a tool returns
"disabled by the active tool profile", do not work around it — tell the user which
profile is active and what would need to change.

## 7. Answer shape

Lead with the answer, then the evidence: title, ID, timestamp, link. For batches,
give counts and the one or two items that matter.
