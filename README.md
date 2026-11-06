<div align="center">

# Workspace Operator

**Deep automation for Google Workspace through the Model Context Protocol**

Drive · Docs · Sheets · Slides · Gmail · Calendar · Apps Script — one local MCP server
with 59 tools, staged writes and server-side tool profiles.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.x-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-59-informational)](#-tool-catalog)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

</div>

---

Workspace Operator (formerly *yet-another-google-mcp*) runs on your machine, talks to
Google over your own OAuth client, and gives an AI agent the operations that turn
"read my inbox" into "do the work and let me undo it": staged Apps Script updates,
file transfer in both directions, presentation assembly, sheet formatting, threaded
replies and attachments.

**59 tools · 3 resources · 3 resource templates · 4 prompts**, every tool annotated
with `readOnlyHint` / `destructiveHint`.

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
| 📁 Drive | 8 | Search, move, copy, share, permissions, revoke public access |
| 💾 Drive files | 3 | Upload/download/export, conversion to native Google formats |
| 📊 Sheets | 12 | Read/write, formatting, filter views, named ranges, CSV |
| 📄 Docs | 5 | Read (tables included), append, templates, PDF export |
| 🖼 Slides | 5 | Create decks, add slides, replace text, insert images |
| ⚙️ Apps Script | 7 | Staged updates with backups, rollback, run functions |
| 📧 Gmail | 14 | Threads, attachments, replies, drafts, labels, batch delete |
| 📅 Calendar | 4 | Events, free slots, meetings with attendees |

Plus 3 resources, 3 resource templates and 4 prompts — see the
[tool catalog](#-tool-catalog).

## Quick start

### 1 — Install

```bash
git clone https://github.com/Artoxem/workspace-operator.git
cd workspace-operator
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Python 3.10 or newer. The package is not on PyPI yet — install from source.

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
| `full` | 59 | your own machine, full trust |
| `read-write` | 52 | daily work — destructive tools hidden |
| `read-only` | 21 | exploration, demos, shared machines, untrusted agents |

```yaml
tool_profile: "read-write"
# Optional, applied on top. Deny wins over allow.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Environment overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.
A blocked call returns a clear explanation instead of failing silently.

## Tool catalog

<details>
<summary>🔎 Cross-search (1)</summary>

| Tool | Type | Description |
|---|---|---|
| `workspace_search` | read | One query across Drive, Gmail and Calendar, date-sorted, partial failures reported |

</details>

<details>
<summary>📁 Drive (8)</summary>

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
<summary>📊 Sheets (12)</summary>

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

</details>

<details>
<summary>📄 Docs (5)</summary>

| Tool | Type | Description |
|---|---|---|
| `read_doc` | read | Read text and tables |
| `doc_export_pdf` | read | Export as binary PDF |
| `create_doc` | write | Create a document |
| `append_to_doc` | write | Append text |
| `doc_fill_template` | destructive | Fill placeholders (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (5)</summary>

| Tool | Type | Description |
|---|---|---|
| `slides_create` | write | Create a presentation |
| `slides_get` | read | Slide count, IDs and text per slide |
| `slides_add_slide` | write | Add a slide with a predefined layout |
| `slides_replace_text` | destructive | Replace placeholders (`confirm=true`) |
| `slides_insert_image` | write | Insert a public image URL onto a slide |

</details>

<details>
<summary>⚙️ Apps Script (7)</summary>

| Tool | Type | Description |
|---|---|---|
| `get_script_content` | read | Read project files |
| `create_script_project` | write | Create a project |
| `prepare_script_update` | write | Stage an update, returns `operation_id` |
| `execute_operation` | write | Apply a staged update (auto-backup first) |
| `cancel_operation` | write | Cancel a staged update |
| `restore_script_backup` | write | Restore from a backup |
| `script_run_function` | destructive | Run a function from an API-executable deployment |

</details>

<details>
<summary>📧 Gmail (14)</summary>

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

</details>

<details>
<summary>📅 Calendar (4)</summary>

| Tool | Type | Description |
|---|---|---|
| `list_events` | read | Upcoming events with times and locations |
| `calendar_find_free_slots` | read | Free slots in a window |
| `create_event` | write | Create an event |
| `calendar_create_meeting` | write | Meeting with attendees (`confirm=true`) |

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

## Safety by default

| Guard | Applies to |
|---|---|
| `confirm=true` required | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template`, `slides_replace_text` |
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
server.py                    MCP server: 59 tool definitions, resources, prompts, profiles
workspace_operator/
├─ profiles.py               read-only / read-write / full + allow-deny lists
├─ config.py                 config file + environment overrides
├─ auth.py                   OAuth 2.0 credentials and token cache
├─ text.py                   entity/whitespace normalisation, timestamps, error hints
├─ operations.py             staged-operation store for Apps Script
├─ security.py               token and email checks
└─ handlers/
   ├─ search.py              workspace_search — Drive + Gmail + Calendar
   ├─ files.py               drive_upload / drive_download / drive_export
   ├─ formatting.py          sheet_format request builders
   ├─ gmail_threads.py       threads, attachments, in-thread replies
   ├─ slides.py              presentations
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
python -m unittest discover -s tests -v     # 115 unit tests, no network
python tests/live_smoke.py                  # 35 checks against a real account
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
| [LEARN.md](LEARN.md) | How this server was built |
| [docs/](docs/) | Release notes and specs for every version |

### 🇷🇺 На русском
| Документ | Описание |
|---|---|
| [AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) | Пошаговая настройка OAuth |
| [TOOLS_REFERENCE.md](docs/ru/TOOLS_REFERENCE.md) | Справочник инструментов |
| [SECURITY.md](docs/ru/SECURITY.md) | Скоупы, профили, модель безопасности |
| [IDE_SETUP.md](docs/ru/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |

## Roadmap

- [x] Cross-product search, tool profiles
- [x] Files, Slides, Apps Script execution
- [x] Sheet formatting
- [x] Gmail threads, attachments, replies
- [ ] Calendar update/delete/respond
- [ ] Composite tools: `report_from_sheet`
- [ ] Optional HTTP transport (stateless, MCP 2026-07-28)

## Responsibility

You are responsible for what the agent does with your account. Read
[docs/SECURITY.md](docs/SECURITY.md), start with `read-only`, keep backups on.

---

<div align="center">

MIT licensed · built on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

</div>
