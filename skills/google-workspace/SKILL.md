---
name: google-workspace-automation
description: Use the Google Workspace MCP server for Drive, Docs, Sheets, Gmail, Calendar and Apps Script work. Search before reading, read before writing, and stage every Apps Script change.
license: MIT
metadata:
  server: yet-another-google-mcp
  version: "1.1.0"
---

# Google Workspace automation

You have an MCP server with 46 tools over Google Drive, Docs, Sheets, Gmail,
Calendar and Apps Script. Follow this order; it keeps context small and
operations reversible.

## 1. Search before you dig

Start with `workspace_search` for any "find everything about X" request:

```json
{"query": "Q3 budget", "sources": "drive,gmail", "limit": 10}
```

It returns a merged, date-sorted list with IDs and links. Only fall back to
per-service tools when you need a specific capability:

| Need | Tool |
|---|---|
| Drive query syntax (`name contains`, `mimeType =`) | `find_files`, `drive_search_advanced` |
| Gmail search operators (`from:`, `has:attachment`) | `list_emails`, `gmail_search_and_summarize` |
| Calendar free/busy | `calendar_find_free_slots` |

## 2. Read before you write

Never guess an ID, sheet name or placeholder.

| Task | Read first |
|---|---|
| Edit a spreadsheet | `get_spreadsheet_meta` → `read_sheet` |
| Fill a document template | `read_doc` |
| Reply to mail | `read_email` |
| Change a calendar | `list_events` |

## 3. Writes are staged or confirmed

* `send_email` defaults to `draft_mode=true` — it creates a draft, it does not
  send. Set `draft_mode=false` only when the user explicitly asks to send.
* `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` default to
  `dry_run=true`. Show the dry-run summary, get approval, then re-run with
  `dry_run=false`.
* `delete_email`, `gmail_archive`, `clear_range`, `drive_revoke_public`,
  `calendar_create_meeting`, `doc_fill_template` need `confirm=true`.
* `share_file` refuses `type=anyone` unless `allow_public=true`.

## 4. Apps Script: prepare → inspect → execute

Never rewrite a script in one step.

1. `get_script_content` — read the current files.
2. `prepare_script_update` — stage the new content, returns `operation_id`.
3. Show the diff or the staged files to the user.
4. `execute_operation` — applies the change and writes a backup automatically.
5. If something breaks: `restore_script_backup`, or `cancel_operation` for a
   staged-but-not-executed change.

## 5. Respect the profile

The server may run with `read-only` or `read-write` tool profiles. If a tool
returns "disabled by the active tool profile", do not try to work around it —
tell the user which profile is active and what would need to change.

## 6. Answer shape

When reporting results, lead with the answer, then the evidence: title, ID,
timestamp, link. For batches, give counts and the one or two items that matter.
