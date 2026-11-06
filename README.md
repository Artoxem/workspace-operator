<div align="center">

# Google Workspace MCP — deep automation

**Apps Script staging with rollback · document templates · cross-product search · local file transfer · Slides · tool profiles**

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents real control over
Google Drive, Sheets, Docs, Gmail, Calendar — and the parts of Workspace that the official servers leave out.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.x-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-55-informational)](#-all-tools)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

</div>

---

## Why another Google MCP server?

In 2026 Google ships its own Workspace MCP servers: nine remote endpoints behind OAuth, plus an
open-source local extension. They are good at search, reading and composing — and that is exactly
where they stop.

This server picks up the rest of the job: **the lifecycle of Apps Script projects**, **document
template filling**, **batch operations with dry-runs**, **deep Sheets work** (filter views, named
ranges, find & replace), and **one-query search across Drive, Gmail and Calendar**.

| | Google Workspace MCP (remote) | Official local extension | **This server** |
|---|---|---|---|
| Transport | Streamable HTTP, Google-hosted | stdio | **stdio, local** |
| Availability | Developer Preview | public | **public, MIT** |
| Apps Script | — | — | **create · read · stage · execute · cancel · restore** |
| Document templates | — | — | **`doc_fill_template`** |
| Batch operations | — | — | **batch delete, batch labels, dry-runs** |
| Sheets depth | read ranges | partial | **filter views, named ranges, find & replace, CSV** |
| Presentations | — | — | **create, add slides, fill text, insert images** |
| Cross-product search | `search_corpus` | — | **`workspace_search`** |
| Server-side tool profiles | IAM / admin allow-list | — | **read-only / read-write / full + allow-deny** |
| Your data path | Google MCP endpoint | local | **local, your own OAuth client** |

> Official servers are the right default for "ask my inbox a question".
> This one is for "change my workspace and be able to undo it".

---

## ✨ What it can do

| Service | Capabilities |
|---------|-------------|
| 🔎 **Cross-search** | One query over Drive + Gmail + Calendar, merged and date-sorted |
| 📁 **Drive** | Search, copy, move, share, permissions, revoke public access |
| 💾 **Files** | Upload local files, download binaries, export Docs/Sheets/Slides to pdf/docx/xlsx/pptx |
| 📊 **Sheets** | Read/write ranges, filter views, named ranges, find & replace, CSV export |
| 📄 **Docs** | Read (tables included), create, append, fill templates, export to PDF |
| 🖼 **Slides** | Create decks, add slides, replace placeholders, insert images |
| 📧 **Gmail** | Draft, send, search, archive, labels, delete with confirmation |
| 📅 **Calendar** | List events, find free slots, create meetings with attendees |
| ⚙️ **Apps Script** | Create, read, stage updates, execute with auto-backup, rollback |
| 🔗 **Resources** | Attach live Drive / Gmail / Calendar / Sheets / Docs snapshots to context |
| 💬 **Prompts** | One-click workflows: summarize inbox, analyze sheet, plan week, search Drive |

**55 tools · 3 resources · 3 resource templates · 4 prompts** — all annotated with
`readOnlyHint` / `destructiveHint` so clients can warn before risky actions.

---

## 🚀 Quick start

### 1 — Install

```bash
git clone https://github.com/Artoxem/yet-another-google-mcp.git
cd yet-another-google-mcp
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2 — Google OAuth

Create an OAuth 2.0 Client ID (Desktop app) in [Google Cloud Console](https://console.cloud.google.com/),
enable the Drive / Docs / Sheets / Gmail / Calendar / Apps Script APIs, download the JSON.

Enable the Drive, Docs, Sheets, Slides, Gmail, Calendar and Apps Script APIs. Upgrading from
1.1? Re-run OAuth once — v1.2 adds the Slides scope.

> Step-by-step: [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) · [docs/ru/AUTH_SETUP.md](docs/ru/AUTH_SETUP.md)

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

`mcp_auth_token` is a local activation key, not network security: the server refuses to start
handling tools unless it is set. See [docs/SECURITY.md](docs/SECURITY.md).

### 4 — Connect a client

<details open>
<summary><strong>Google Antigravity</strong> — recommended</summary>

Antigravity App, IDE and CLI share `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "python",
      "args": ["D:\\DEV\\yet-another-google-mcp\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\yet-another-google-mcp\\config.yaml",
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
guide: [antigravity/README.md](antigravity/README.md) ·
optional Agent Skill: [skills/google-workspace/SKILL.md](skills/google-workspace/SKILL.md)

</details>

<details>
<summary><strong>Claude Desktop / Cursor / VS Code / Windsurf</strong></summary>

```json
{
  "mcpServers": {
    "google-tools": {
      "command": "python",
      "args": ["D:\\DEV\\yet-another-google-mcp\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\yet-another-google-mcp\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!"
      }
    }
  }
}
```

Per-client paths and troubleshooting: [docs/IDE_SETUP.md](docs/IDE_SETUP.md).

</details>

---

## 🛡 Tool profiles

A profile is a server-side allow-list: tools outside it are neither listed nor callable.
It complements OAuth scopes (what Google allows) and client permissions (what the agent may
do without asking).

| Profile | Tools | Use it when |
|---|---:|---|
| `full` | 55 | your own machine, full trust |
| `read-write` | 48 | daily work — destructive tools hidden |
| `read-only` | 19 | exploring, demos, shared machines, untrusted agents |

```yaml
tool_profile: "read-write"
# Optional, applied on top. Deny wins over allow.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Environment overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
Blocked calls return a clear error instead of failing silently.

---

## 🔎 `workspace_search`

The local answer to `search_corpus` — one query, three products, one ranked list:

```json
{"query": "Q3 budget", "sources": "drive,gmail,calendar", "limit": 10}
```

```
Workspace search: 'Q3 budget' — 6 result(s) [drive (3), gmail (2), calendar (1)]

1. [drive] Budget 2026 — spreadsheet
   2026-03-02 10:11 UTC | type: spreadsheet | id: 1a2b3c
   https://docs.google.com/spreadsheets/d/1a2b3c
2. [gmail] Q3 budget approval
   2026-02-27 09:14 UTC | from: cfo@corp.io | id: 18f4d2
   Please approve the Q3 budget by Friday.
```

Partial failures are reported, not fatal: if Gmail errors, you still get Drive hits plus
a `Partial results` note.

---

## 🧯 Safety by default

| Guard | Tools |
|-------|-------|
| `confirm=true` required | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template` |
| `dry_run=true` by default | `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` |
| Auto dry-run for large ranges | `clear_range` |
| Draft mode by default | `send_email` (never sends unless `draft_mode=false`) |
| Public sharing blocked | `share_file` blocks `type=anyone` unless `allow_public=true` |
| Staged Apps Script changes | `prepare_script_update` → `execute_operation` (auto-backup) |
| Tool annotations | every tool carries `readOnlyHint` / `destructiveHint` |
| Server-side profile | `read-only` / `read-write` / `full` + allow/deny lists |

> ⚠️ The agent can reach everything your OAuth token can. Use read-only scopes and the
> `read-only` profile for sensitive accounts. Details: [docs/SECURITY.md](docs/SECURITY.md).

---

## 📦 All tools

<details>
<summary>🔎 Cross-search (1)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `workspace_search` | read | One query across Drive, Gmail and Calendar, merged and date-sorted |

</details>

<details>
<summary>📁 Drive (8)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `find_files` | read | Search by name or Drive query |
| `drive_search_advanced` | read | Full Drive query syntax with result limit |
| `drive_list_permissions` | read | List file permissions |
| `create_folder` | write | Create a folder |
| `move_file` | write | Move a file to a folder |
| `drive_copy_file` | write | Copy a file |
| `share_file` | write | Share with user/group/domain/anyone |
| `drive_revoke_public` | destructive | Revoke public access (`confirm=true`) |

</details>

<details>
<summary>💾 Drive files (3)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `drive_upload` | write | Upload a local file; `convert_to` turns docx/xlsx/pptx into native Google files |
| `drive_download` | read | Download a binary Drive file to disk |
| `drive_export` | read | Export a Doc/Sheet/Slide to pdf, docx, xlsx, pptx, csv… |

</details>

<details>
<summary>📊 Sheets (11)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `read_sheet` | read | Read a cell range |
| `get_spreadsheet_meta` | read | Spreadsheet metadata |
| `sheet_export_csv` | read | Export range to CSV |
| `append_row` | write | Append a row |
| `update_sheet` | write | Write rows to a range |
| `create_spreadsheet` | write | Create a new spreadsheet |
| `add_sheet` | write | Add a new tab/sheet |
| `sheet_create_filter_view` | write | Create a filter view |
| `sheet_create_named_range` | write | Create a named range |
| `sheet_find_replace` | write | Find & replace (`dry_run=true` by default) |
| `clear_range` | destructive | Clear a range (auto dry-run for large ranges) |

</details>

<details>
<summary>📄 Docs (5)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `read_doc` | read | Read document text |
| `doc_export_pdf` | read | Export document as binary PDF |
| `create_doc` | write | Create a new document |
| `append_to_doc` | write | Append text |
| `doc_fill_template` | destructive | Fill template placeholders (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (5)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `slides_create` | write | Create a presentation |
| `slides_get` | read | Slide count, IDs and text per slide |
| `slides_add_slide` | write | Add a slide with a predefined layout |
| `slides_replace_text` | destructive | Replace placeholders (`confirm=true`) |
| `slides_insert_image` | write | Insert a public image URL onto a slide |

</details>

<details>
<summary>📧 Gmail (11)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `get_gmail_profile` | read | Get authenticated email address |
| `list_emails` | read | List emails with date, sender and subject |
| `read_email` | read | Headers, labels, attachments and decoded body |
| `gmail_search_and_summarize` | read | Search and return a brief summary |
| `create_draft` | write | Create a draft |
| `send_email` | write | Send or draft (`draft_mode=true` by default) |
| `send_draft` | write | Send an existing draft |
| `gmail_label_apply` | write | Apply a label (`dry_run=true` by default) |
| `gmail_archive` | write | Archive a message (`confirm=true`) |
| `delete_email` | destructive | Delete an email (`confirm=true`) |
| `batch_delete_emails` | destructive | Delete multiple emails (`dry_run=true` by default) |

</details>

<details>
<summary>📅 Calendar (4)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `list_events` | read | List upcoming events |
| `calendar_find_free_slots` | read | Find free time slots |
| `create_event` | write | Create an event |
| `calendar_create_meeting` | write | Create meeting with attendees (`confirm=true`) |

</details>

<details>
<summary>⚙️ Apps Script (6)</summary>

| Tool | Type | Description |
|------|------|-------------|
| `get_script_content` | read | Read project files |
| `create_script_project` | write | Create a new project |
| `prepare_script_update` | write | Stage an update, get `operation_id` |
| `execute_operation` | write | Execute a staged update (auto-backup) |
| `cancel_operation` | write | Cancel a pending staged update |
| `restore_script_backup` | write | Restore from auto-backup |
| `script_run_function` | destructive | Run a function from an API-executable deployment |

</details>

### Resources

| URI | What it attaches |
|---|---|
| `gdrive://recent` | 20 most recently modified Drive files |
| `gmail://inbox` | Recent unread inbox messages |
| `gcalendar://upcoming` | Events for the next 7 days |
| `gdrive://file/{file_id}` | Metadata for one file |
| `gsheets://{spreadsheet_id}/{range}` | A sheet range as a table |
| `gdocs://{document_id}` | Full text of a document |

### Prompts

| Prompt | What it does |
|--------|-------------|
| `summarize_inbox` | Fetch recent Gmail messages → ready for AI summary |
| `analyze_spreadsheet` | Read a sheet range → ready for analysis |
| `plan_week` | Load calendar events → ready for planning |
| `search_drive` | Search Drive → ready for organisation advice |

---

## 🏗 How it works

```
server.py                  MCP server: 55 tool definitions, resources, prompts, tool profiles
mcp_google/
├─ profiles.py             read-only / read-write / full + allow-deny lists
├─ text.py                 entity/whitespace normalisation, timestamps, error hints
├─ config.py               config file + env overrides
├─ auth.py                 OAuth 2.0 credentials, token cache
├─ operations.py           staged operation store (Apps Script)
├─ security.py             token checks, email validation
└─ handlers/
   ├─ search.py            workspace_search — Drive + Gmail + Calendar
   ├─ files.py             drive_upload / drive_download / drive_export
   ├─ slides.py            Slides: create, read, add, replace, images
   ├─ drive.py  sheets.py  docs.py
   ├─ gmail.py  calendar.py  apps_script.py
tests/                     unit tests, no network needed
antigravity/               ready-to-paste mcp_config.json
skills/google-workspace/   Agent Skill: when to use which tool
```

Design rules:

* **Every handler returns a string** — no exceptions escape to the transport.
* **Writes are staged or confirmed** — dry-runs, `confirm=true`, draft mode.
* **Apps Script is a two-phase commit** — prepare returns an `operation_id`,
  execute applies it, a backup is written first.
* **Search before read, read before write** — encoded in the Agent Skill.

---

## 🧪 Development

```bash
python -m unittest discover -s tests -v
```

66 tests cover profiles, search parsing, text hygiene, Docs tables, path handling and the
v1.2 helpers. No credentials, network, or Google API access required.

`tests/live_smoke.py` runs 30 end-to-end checks against a real account and
cleans up after itself (uploads, downloads and trashes a temp file; creates and trashes a deck).

`tests/pptx_roundtrip.py` verifies the Office → Google conversion path:
`drive_upload(convert_to="google-slides")` → `slides_replace_text` → `slides_get`.
Pass a `.pptx` that contains `{{NAME}}`, or run it with an interpreter that has
`python-pptx` installed.

---

## 📚 Documentation

### 🇬🇧 English
| Document | Description |
|----------|-------------|
| [AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup, step by step |
| [TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | Every tool, resource and prompt |
| [SECURITY.md](docs/SECURITY.md) | Scopes, profiles, safety model |
| [IDE_SETUP.md](docs/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [LEARN.md](LEARN.md) | How this server was built |

### 🇷🇺 На русском
| Документ | Описание |
|----------|----------|
| [AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) | Пошаговая настройка Google OAuth |
| [TOOLS_REFERENCE.md](docs/ru/TOOLS_REFERENCE.md) | Справочник инструментов |
| [SECURITY.md](docs/ru/SECURITY.md) | Скоупы, профили, модель безопасности |
| [IDE_SETUP.md](docs/ru/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |

---

## 🗺 Roadmap

- [x] `workspace_search` — cross-product search
- [x] Tool profiles (`read-only` / `read-write` / `full`)
- [x] Antigravity config + Agent Skill
- [x] `drive_upload` / `drive_download` / `drive_export`
- [x] Slides: create, add slides, replace text, insert images
- [x] `script_run_function` for API-executable deployments
- [ ] Docs: replace-text and formatting operations
- [ ] `workspace_search` filters by type and date range
- [ ] Optional HTTP transport for team deployments (stateless, MCP 2026-07-28)

---

## ⚠️ Responsibility notice

You are responsible for what the agent does with your account. Read
[docs/SECURITY.md](docs/SECURITY.md), start with `read-only`, and keep backups on.

---

<div align="center">

Built with ❤️ on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) ·
MIT licensed

</div>
