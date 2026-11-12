<div align="center">

# Workspace Operator

**Deep automation for Google Workspace through the Model Context Protocol**

Drive · Docs · Sheets · Slides · Gmail · Calendar · Apps Script — one local MCP server
with 121 tools, staged writes and server-side tool profiles.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-121-informational)](#-tool-catalog)
[![PyPI](https://img.shields.io/badge/PyPI-workspace--operator--mcp-3775A9?logo=pypi&logoColor=white)](https://pypi.org/project/workspace-operator-mcp/)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

</div>

---

Workspace Operator runs on your machine, talks to
Google over your own OAuth client, and gives an AI agent the operations that turn
"read my inbox" into "do the work and let me undo it": staged Apps Script updates,
file transfer in both directions, presentation assembly, sheet formatting, threaded
replies and attachments.

**121 tools · 3 resources · 3 resource templates · 8 prompts**, every tool annotated
with `readOnlyHint` / `destructiveHint`.

Nothing here is tied to a specific account, spreadsheet or document: every tool
takes identifiers and ranges, and all examples use synthetic data.

## How it compares

| | Google Workspace MCP (remote) | **Workspace Operator** |
|---|---|---|
| Transport | Streamable HTTP, Google-hosted | **stdio, local** |
| Availability | Developer Preview | **public, MIT** |
| Data path | Google MCP endpoint | **your machine, your OAuth client** |
| Apps Script | — | **create · read · stage · execute · cancel · restore · run function** |
| Local files | — | **upload, download, export to pdf/docx/xlsx/pptx** |
| Slides | — | **create, add slides, fill text, insert images** |
| Sheets formatting | — | **bold, colours, number formats, widths, freeze** |
| Gmail threads | single messages | **threads, attachments, in-thread replies** |
| Server-side tool profiles | IAM / admin allow-list | **read-only / read-write / full + allow-deny** |

Official servers are the right default for "ask my mail a question". Workspace
Operator is for "change the workspace and be able to roll it back".

## What you get

| Group | Tools | Highlights |
|---|---:|---|
| 🔎 Cross-search | 1 | One query over Drive, Gmail and Calendar, merged by date |
| 📁 Drive | 16 | Search, metadata, rename, trash/restore, share, permissions |
| 💬 Comments | 4 | Threads on Docs, Sheets and Slides: read, write, reply, resolve |
| 💾 Drive files | 3 | Upload/download/export, conversion to native Google formats |
| 📊 Sheets | 25 | Read/write, formatting, conditional rules, charts, filter views, CSV |
| 📄 Docs | 8 | Read (tables included), append, find & replace, templates, PDF export |
| 🖼 Slides | 11 | Create decks, add/delete slides, replace text, insert images |
| ⚙️ Apps Script | 10 | Staged updates with backups, rollback, run functions |
| 📧 Gmail | 22 | Threads, attachments, replies, drafts, labels, batch delete |
| 📅 Calendar | 10 | Events, free slots, meetings, update/delete, invite responses |
| 🧩 Composite | 5 | report from sheet, digest, table diff, template clone, table → deck |

Plus 3 resources, 3 resource templates and 8 prompts — see the
[tool catalog](#-tool-catalog).

## Quick start

### 1 — Install

```bash
pip install workspace-operator-mcp
```

PyPI mirrors the latest GitHub release. If `workspace-operator version` reports an
older version than this README describes, install from source or use the container
below until the next release is published.

From source (development):

```bash
git clone https://github.com/Artoxem/workspace-operator.git
cd workspace-operator
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Python 3.10 or newer. The package installs the `workspace-operator` command; the
`python -m workspace_operator` form works from a source checkout too.

### 2 — Google OAuth

1. Create an OAuth 2.0 Client ID (type: **Desktop app**) in
   [Google Cloud Console](https://console.cloud.google.com/).
2. Enable these APIs: **Drive, Docs, Sheets, Slides, Gmail, Calendar, Apps Script**.
3. Download the client JSON — the server will read it on first run.

> Step by step: [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) · [docs/ru/AUTH_SETUP.md](docs/ru/AUTH_SETUP.md)
> Upgrading? Slides needs the `.../auth/presentations` scope — re-run the OAuth flow once.

### 3 — Configure

```bash
cp config.example.yaml config.yaml
```

```yaml
client_secrets_file: "C:\\Users\\you\\.google\\oauth.keys.json"
token_file: "C:\\Users\\you\\.google\\token.json"
backup_dir: "C:\\Users\\you\\.google\\backups"
mcp_auth_token: "MySecretToken_2026!"
tool_profile: "read-write"      # full | read-write | read-only
```

`mcp_auth_token` is a local activation key, not network security: the server refuses
to handle tools until it is set. Every key can be overridden by an environment
variable — see [docs/SECURITY.md](docs/SECURITY.md).

### 4 — Connect a client

<details open>
<summary><strong>Google Antigravity</strong> — App, IDE and CLI share one config</summary>

`~/.gemini/config/mcp_config.json` (global) or `<workspace>/.agents/mcp_config.json`:

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "python",
      "args": ["D:\\DEV\\workspace-operator\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\workspace-operator\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!",
        "MCP_TOOL_PROFILE": "read-write"
      },
      "timeoutSeconds": 300,
      "tools": { "workspace_search": { "eager": true } }
    }
  }
}
```

Ready-made file: [antigravity/mcp_config.example.json](antigravity/mcp_config.example.json) ·
walkthrough: [antigravity/README.md](antigravity/README.md) ·
Agent Skill: [skills/google-workspace/SKILL.md](skills/google-workspace/SKILL.md)

</details>

<details>
<summary><strong>Claude Desktop, Cursor, VS Code, Windsurf</strong></summary>

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "python",
      "args": ["D:\\DEV\\workspace-operator\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\workspace-operator\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!"
      }
    }
  }
}
```

Per-client paths: [docs/IDE_SETUP.md](docs/IDE_SETUP.md) · [docs/ru/IDE_SETUP.md](docs/ru/IDE_SETUP.md).

</details>

## Tool profiles

A profile is a server-side allow-list: tools outside it are neither listed nor
callable. It complements OAuth scopes (what Google allows) and client permissions
(what the agent may do without asking).

| Profile | Tools | Use it for |
|---|---:|---|
| `full` | 121 | your own machine, full trust |
| `read-write` | 102 | daily work — destructive tools hidden |
| `read-only` | 33 | exploration, demos, shared machines, untrusted agents |

```yaml
tool_profile: "read-write"
# Optional, applied on top. Deny wins over allow.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Environment overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.
A blocked call returns a clear explanation instead of failing silently.

## Operations

```bash
python -m workspace_operator doctor     # config, token, scopes, API reachability
python -m workspace_operator doctor --offline   # same, without network probes
python -m workspace_operator tools      # catalog (--profile read-only, --json)
python -m workspace_operator serve      # stdio server (same as python server.py)
```

| Feature | How to use it | What it does |
|---|---|---|
| **Dry run** | `MCP_DRY_RUN=1` or `dry_run: true` | Every non-read-only tool returns a preview instead of executing — safe demos, safe exploration |
| **Audit log** | `MCP_AUDIT_LOG=~/.google/audit.jsonl` | One JSON line per call: tool, profile, status, duration, argument **names** (never values) |
| **Retries** | `MCP_RETRY_ATTEMPTS=3` | Transient Google API errors (429/5xx) are retried with exponential backoff |
| **Doctor** | `python -m workspace_operator doctor` | Checks secrets, token, granted vs configured scopes and API reachability; exits 1 when a critical check fails |

In dry-run the read-only tools still work, so an agent can explore data while every
write is turned into an explicit preview.

### HTTP transport (localhost first)

```bash
python -m workspace_operator serve --http --port 8765
```

* binds `127.0.0.1` by default — not reachable from the network;
* every request needs `Authorization: Bearer <mcp_auth_token>`; extra per-client
  tokens can be listed under `http_tokens` in `config.yaml`, and the audit log
  records the token name as `client`;
* DNS-rebinding protection is on: only expected `Host` headers pass, browser
  origins are denied unless explicitly allowed;
* `GET /healthz` is unauthenticated and returns only version and transport info;
* binding a non-loopback address requires **both** `--allow-network` and
  `--insecure`; loopback names accept any host port (containers, proxies),
  anything else needs an explicit `--allow-host`;
  `--insecure`, so network exposure is always deliberate.

### Docker

```bash
docker pull ghcr.io/artoxem/workspace-operator:latest

docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:latest
```

The image runs as an unprivileged user (uid 10001), publishes only to loopback and
mounts the Google credentials read-write, because the server refreshes the token in
place. `docker compose up --build` builds the same image locally.

Clients that only speak stdio can still use the image — the entrypoint takes the
same arguments as the CLI:

```bash
docker run -i --rm \
  -v "$HOME/.google:/home/app/.google" \
  --entrypoint python \
  ghcr.io/artoxem/workspace-operator:latest -m workspace_operator serve
```

Something not working? See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Tool catalog

<details>
<summary>🔎 Cross-search (1)</summary>

| Tool | Type | Description |
|---|---|---|
| `workspace_search` | read | One query across Drive, Gmail and Calendar, date-sorted, partial failures reported |

</details>

<details>
<summary>📁 Drive (16)</summary>

| Tool | Type | Description |
|---|---|---|
| `find_files` | read | Search by name or Drive query |
| `drive_search_advanced` | read | Full Drive query syntax with a limit |
| `drive_list_permissions` | read | List permissions of a file |
| `create_folder` | write | Create a folder |
| `move_file` | write | Move a file into a folder |
| `drive_copy_file` | write | Copy a file |
| `share_file` | write | Share with user/group/domain/anyone |
| `drive_revoke_public` | destructive | Revoke public access (`confirm=true`) |
| `drive_get_metadata` | read | Size, owner, parents, timestamps and link |
| `drive_rename_file` | write | Rename without moving or copying |
| `drive_delete_file` | destructive | Move to trash (`confirm=true`) |
| `drive_restore_file` | write | Restore a file from the trash |
| `drive_remove_permission` | destructive | Revoke one permission (`confirm=true`) |
| `drive_empty_trash` | destructive | Permanently delete trashed files (`confirm=true`) |
| `drive_transfer_ownership` | destructive | Hand a file to another owner (`confirm=true`) |
| `drive_create_shortcut` | write | Create a shortcut to another file |

</details>

<details>
<summary>💾 Drive files (3)</summary>

| Tool | Type | Description |
|---|---|---|
| `drive_upload` | write | Upload a local file; `convert_to` turns docx/xlsx/pptx into native Google files |
| `drive_download` | read | Download a binary file to disk |
| `drive_export` | read | Export a Doc/Sheet/Slide to pdf, docx, xlsx, pptx, csv… |

</details>

<details>
<summary>💬 Comments (4)</summary>

| Tool | Type | Description |
|---|---|---|
| `drive_list_comments` | read | Comments and replies on a Doc, Sheet or Slide |
| `drive_create_comment` | write | Add a comment, optionally quoting text |
| `drive_reply_comment` | write | Reply in an existing thread |
| `drive_resolve_comment` | write | Mark a thread resolved (`confirm=true`) |

</details>

<details>
<summary>📦 Bulk operations (6)</summary>

| Tool | Type | Description |
|---|---|---|
| `bulk_plan` | read | Resolve a Drive selector into a reviewed, immutable plan (dry run; 300-item default cap) |
| `bulk_run` | write | Execute a reviewed plan as a background job (`confirm=true`, resumable) |
| `bulk_status` | read | Compact progress: done/total, ok, skipped, failed |
| `bulk_cancel` | write | Stop a running job; in-flight items finish |
| `bulk_result` | read | Page through per-item results (50 by default, 200 max) |
| `bulk_list` | read | Recent bulk jobs |

</details>

<details>
<summary>📊 Sheets (25)</summary>

| Tool | Type | Description |
|---|---|---|
| `read_sheet` | read | Read a cell range |
| `get_spreadsheet_meta` | read | Sheet names and IDs |
| `sheet_export_csv` | read | Export a range as CSV |
| `append_row` | write | Append a row |
| `update_sheet` | write | Write rows to a range |
| `create_spreadsheet` | write | Create a spreadsheet |
| `add_sheet` | write | Add a tab |
| `sheet_create_filter_view` | write | Create a filter view |
| `sheet_create_named_range` | write | Create a named range |
| `sheet_find_replace` | write | Find & replace (`dry_run=true` by default) |
| `sheet_format` | write | Bold, colours, number formats, widths, row heights, frozen panes |
| `clear_range` | destructive | Clear a range (auto dry-run for large ranges) |
| `sheet_conditional_format` | write | Colour cells when a condition matches |
| `sheet_add_chart` | write | Insert a COLUMN/BAR/LINE/AREA/PIE chart from a range |
| `sheet_delete_sheet` | destructive | Delete a tab (`confirm=true`) |
| `sheet_insert_rows` | write | Insert empty rows before a row number |
| `sheet_delete_rows` | destructive | Delete rows (`confirm=true`) |
| `sheet_merge_cells` | write | Merge or unmerge a range |
| `sheet_insert_columns` | write | Insert empty columns before a column |
| `sheet_delete_columns` | destructive | Delete columns (`confirm=true`) |
| `sheet_sort_range` | write | Sort a range by one column |
| `sheet_add_pivot_table` | write | Pivot table from a range onto a new sheet |
| `sheet_set_data_validation` | write | List or number-range validation |
| `sheet_protect_range` | write | Warning or locked protection |
| `sheet_set_borders` | write | Solid/dotted/dashed borders |

</details>

<details>
<summary>📄 Docs (8)</summary>

| Tool | Type | Description |
|---|---|---|
| `read_doc` | read | Read text and tables |
| `doc_export_pdf` | read | Export as binary PDF |
| `create_doc` | write | Create a document |
| `append_to_doc` | write | Append text |
| `doc_fill_template` | destructive | Fill placeholders (`confirm=true`) |
| `doc_replace_text` | destructive | Find & replace with a preview (`confirm=true`) |
| `docs_insert_image` | write | Insert an inline image from a public URL |
| `docs_format_text` | destructive | Bold/italic/size/heading for matched text (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (11)</summary>

| Tool | Type | Description |
|---|---|---|
| `slides_create` | write | Create a presentation |
| `slides_get` | read | Slide count, IDs and text per slide |
| `slides_add_slide` | write | Add a slide with a predefined layout |
| `slides_replace_text` | destructive | Replace placeholders (`confirm=true`) |
| `slides_insert_image` | write | Insert a public image URL onto a slide |
| `slides_delete_slide` | destructive | Delete a slide (`confirm=true`) |
| `slides_move_slide` | write | Move a slide to another position |
| `slides_set_notes` | write | Replace the speaker notes |
| `slides_add_table` | write | Insert a native table onto a slide |
| `slides_list_layouts` | read | Layouts available in a presentation |
| `slides_add_shape` | write | Rectangle/ellipse/text box with optional text |

</details>

<details>
<summary>⚙️ Apps Script (10)</summary>

| Tool | Type | Description |
|---|---|---|
| `get_script_content` | read | Read project files |
| `create_script_project` | write | Create a project |
| `prepare_script_update` | write | Stage an update, returns `operation_id` |
| `execute_operation` | write | Apply a staged update (auto-backup first) |
| `cancel_operation` | write | Cancel a staged update |
| `restore_script_backup` | write | Restore from a backup |
| `script_run_function` | destructive | Run a function from an API-executable deployment |
| `script_list_deployments` | read | Deployments of a project |
| `script_create_deployment` | write | Deploy a saved version |
| `script_update_deployment` | write | Point a deployment at a newer version |

</details>

<details>
<summary>📧 Gmail (22)</summary>

| Tool | Type | Description |
|---|---|---|
| `get_gmail_profile` | read | Authenticated address |
| `list_emails` | read | List with date, sender and subject |
| `read_email` | read | Headers, labels, attachments and decoded body |
| `gmail_search_and_summarize` | read | Search with a compact summary |
| `gmail_get_thread` | read | Whole conversation |
| `gmail_get_attachment` | read | Save an attachment to disk |
| `create_draft` | write | Create a draft |
| `send_email` | write | Send or draft (`draft_mode=true` by default) |
| `send_draft` | write | Send an existing draft |
| `gmail_reply` | write | Reply in-thread (`draft_mode=true` by default) |
| `gmail_label_apply` | write | Apply a label (`dry_run=true` by default) |
| `gmail_archive` | write | Archive (`confirm=true`) |
| `delete_email` | destructive | Delete (`confirm=true`) |
| `batch_delete_emails` | destructive | Delete many (`dry_run=true` by default) |
| `gmail_list_labels` | read | Labels with IDs, user and system |
| `gmail_create_label` | write | Create a label |
| `gmail_send_with_attachments` | write | Draft or send with local files (20 MB) |
| `gmail_list_drafts` | read | Drafts with recipient and subject |
| `gmail_delete_draft` | destructive | Delete a draft (`confirm=true`) |
| `gmail_list_filters` | read | Filters with criteria and actions |
| `gmail_create_filter` | write | Filter: match from/subject/query, add or remove labels |
| `gmail_update_draft` | write | Replace draft content |

</details>

<details>
<summary>🧩 Composite (5)</summary>

| Tool | Type | Description |
|---|---|---|
| `report_from_sheet` | write | Read a range → column statistics → Doc with **native tables** or plain text (`output=text`) |
| `digest` | write | Last N hours across Gmail, Calendar and Drive → text or Doc |
| `compare_tables` | write | Diff two ranges by a key column; `output=doc` builds native tables |
| `clone_and_fill` | write | Copy any Drive file and replace placeholders in the copy |
| `sheet_to_slides` | write | Read a range → deck: title slide + one slide per row group |

</details>

<details>
<summary>📅 Calendar (10)</summary>

| Tool | Type | Description |
|---|---|---|
| `list_events` | read | Upcoming events with times and locations |
| `calendar_find_free_slots` | read | Free slots in a window |
| `create_event` | write | Create an event |
| `calendar_create_meeting` | write | Meeting with attendees (`confirm=true`) |
| `calendar_update_event` | write | Change any field; only what you pass is modified |
| `calendar_delete_event` | destructive | Delete an event (`confirm=true`) |
| `calendar_respond_to_invite` | write | Accept / decline / tentative (`confirm=true`) |
| `calendar_list_calendars` | read | Calendars with access roles |
| `calendar_move_event` | write | Move an event to another calendar |
| `calendar_set_event_color` | write | Colour an event (`1`–`11`) |

</details>

### Resources

| URI | Attaches |
|---|---|
| `gdrive://recent` | 20 most recently modified Drive files |
| `gmail://inbox` | Recent unread inbox messages |
| `gcalendar://upcoming` | Events for the next 7 days |
| `gdrive://file/{file_id}` | Metadata for one file |
| `gsheets://{spreadsheet_id}/{range}` | A sheet range as a table |
| `gdocs://{document_id}` | Full document text, tables included |

### Prompts

| Prompt | What it does |
|---|---|
| `summarize_inbox` | Fetch recent mail → ready for a summary |
| `analyze_spreadsheet` | Read a range → ready for analysis |
| `plan_week` | Load calendar events → ready for planning |
| `search_drive` | Search files → ready for organisation advice |
| `weekly_review` | Last N days of mail, files and agenda → weekly summary |
| `inbox_triage` | Gmail slice → urgent / waiting / informational / archive |
| `sheet_brief` | Range → statistics plus a briefing question |
| `compare_brief` | Two ranges → reconciliation report |


## Safety by default

| Guard | Applies to |
|---|---|
| `confirm=true` required | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template`, `slides_replace_text`, `drive_delete_file`, `drive_remove_permission`, `drive_resolve_comment`, `doc_replace_text`, `slides_delete_slide`, `sheet_delete_sheet`, `sheet_delete_rows`, `drive_empty_trash`, `sheet_delete_columns`, `drive_transfer_ownership`, `docs_format_text`, `gmail_delete_draft`, `calendar_delete_event`, `calendar_respond_to_invite` |
| `dry_run=true` by default | `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` |
| Draft mode by default | `send_email`, `gmail_reply` |
| Public sharing blocked | `share_file` refuses `type=anyone` without `allow_public=true` |
| No silent overwrite | `drive_download`, `drive_export`, `gmail_get_attachment` |
| Staged Apps Script | `prepare_script_update` → `execute_operation` (backup first) |
| Tool annotations | every tool carries `readOnlyHint` / `destructiveHint` |
| Server-side profiles | `read-only` / `read-write` / `full` + allow/deny lists |

> ⚠️ An agent can reach everything your OAuth token can. Use read-only scopes and the
> `read-only` profile for sensitive accounts — [docs/SECURITY.md](docs/SECURITY.md).

## How it works

```
server.py                    MCP server: 121 tool definitions, resources, prompts, profiles
workspace_operator/
├─ profiles.py               read-only / read-write / full + allow-deny lists
├─ config.py                 config file + environment overrides
├─ auth.py                   OAuth 2.0 credentials and token cache
├─ text.py                   entity/whitespace normalisation, timestamps, error hints
├─ operations.py             staged-operation store for Apps Script
├─ security.py               token and email checks
├─ runtime.py                retries, audit log, dry-run helpers
├─ cli.py                    doctor / tools / serve
└─ handlers/
   ├─ search.py              workspace_search — Drive + Gmail + Calendar
   ├─ files.py               drive_upload / drive_download / drive_export
   ├─ formatting.py          sheet_format request builders
   ├─ gmail_threads.py       threads, attachments, in-thread replies
   ├─ slides.py              presentations
   ├─ calendar_writes.py     update / delete / invite responses
   ├─ report.py              report_from_sheet: stats + document
   ├─ digest.py              digest across mail, calendar and drive
   ├─ compare.py             table diff by key column
   ├─ template.py            clone a file and fill placeholders
   ├─ deck.py                table → presentation
   ├─ drive_extra.py         metadata, rename, trash/restore, permissions
   ├─ comments.py            Drive comments: list, create, reply, resolve
   ├─ doc_edit.py            find & replace inside a document
   ├─ sheets_extra.py        conditional formatting, charts
   ├─ sheets_structure.py    tabs, rows, merged cells
   ├─ sheets_more.py         columns and sorting
   ├─ doc_media.py           inline images in documents
   ├─ doc_format.py          bold/italic/heading for matched text
   ├─ sheets_pivot.py        pivot tables
   ├─ gmail_drafts.py        draft list, update and cleanup
   ├─ gmail_filters.py       filters: list and create
   ├─ sheets_validate.py     validation, protection, borders
   ├─ gmail_labels.py        labels and bulk message flags
   ├─ drive.py  sheets.py  docs.py
   ├─ gmail.py  calendar.py  apps_script.py
tests/                       unit, live and round-trip checks
antigravity/                 ready-to-paste mcp_config.json
skills/google-workspace/     Agent Skill: when to use which tool
```

Design rules:

* every handler returns a string — exceptions never reach the transport;
* writes are staged, confirmed or drafted, never silent;
* Apps Script is a two-phase commit with an automatic backup;
* server-side profiles keep the exposed surface small.

## Testing

```bash
python -m unittest discover -s tests -v     # 302 unit tests, no network
python tests/live_smoke.py                  # 51 checks against a real account
python tests/live_new_tools.py              # 15 checks for the v1.14 batch
python tests/live_phase2.py                 # 8 checks for the v1.15 batch
python tests/live_phase3.py                 # 8 checks for the v1.16 batch
python tests/live_phase4.py                 # 5 checks for the v1.17 batch
python tests/live_phase5.py                 # 7 checks for the v1.18 batch
python tests/pptx_roundtrip.py deck.pptx    # 5 checks: pptx → Slides → replace
```

The live suite is self-cleaning: it uploads and trashes a temp file, creates and
trashes a presentation and a spreadsheet, drafts and deletes a reply, downloads an
attachment and removes it. `tests/test_docs.py` keeps this README, the docs and the
code in sync (tool counts, profile numbers, links, examples).

## Documentation

### 🇬🇧 English
| Document | Description |
|---|---|
| [AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup, step by step |
| [TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | Every tool, resource and prompt |
| [SECURITY.md](docs/SECURITY.md) | Scopes, profiles, safety model |
| [IDE_SETUP.md](docs/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Symptom → cause → fix, including Docker |
| [LEARN.md](LEARN.md) | How this server was built |
| [docs/](docs/) | Release notes and specs for every version |

### 🇷🇺 На русском
| Документ | Описание |
|---|---|
| [AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) | Пошаговая настройка OAuth |
| [TOOLS_REFERENCE.md](docs/ru/TOOLS_REFERENCE.md) | Справочник инструментов |
| [SECURITY.md](docs/ru/SECURITY.md) | Скоупы, профили, модель безопасности |
| [IDE_SETUP.md](docs/ru/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |

## Limitations

Knowing the edges is part of the contract:

- **Drive**: deleting means "move to trash"; `drive_empty_trash` is the only
  permanent path and needs `confirm=true`.
- **Sheets**: tabs, rows, columns, merges, sorting, pivot tables, validation,
  protection and borders are handled; charts cover the basic types and conditional
  formatting takes one rule per call.
- **Docs**: text styling works on matched text; tables are created by the report
  tool but not edited cell by cell afterwards.
- **Slides**: slides, speaker notes and native tables work; shapes, diagrams and
  per-shape styling do not.
- **One account per server**: a single OAuth token, no multi-tenant mode.

## Roadmap

- [x] Cross-product search, tool profiles
- [x] Files, Slides, Apps Script execution
- [x] Sheet formatting
- [x] Gmail threads, attachments, replies
- [x] Calendar update/delete/respond
- [x] Composite tools: `report_from_sheet`, `digest`, `compare_tables`, `clone_and_fill`
- [x] Optional HTTP transport (Streamable HTTP, stateless, localhost-first)

## Responsibility

You are responsible for what the agent does with your account. Read
[docs/SECURITY.md](docs/SECURITY.md), start with `read-only`, keep backups on.

---

<div align="center">

MIT licensed · built on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

</div>
