<div align="center">

# Workspace Operator

**Deep automation for Google Workspace through the Model Context Protocol**

Drive · Docs · Sheets · Gmail · Calendar · Tasks · Forms · Apps Script — one local
MCP server with 39 tools, staged writes and server-side tool profiles.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-39-informational)](#-tool-catalog)
[![PyPI](https://img.shields.io/badge/PyPI-workspace--operator--mcp-3775A9?logo=pypi&logoColor=white)](https://pypi.org/project/workspace-operator-mcp/)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Artoxem/workspace-operator?style=social)](https://github.com/Artoxem/workspace-operator/stargazers)
[![Downloads](https://static.pepy.tech/badge/workspace-operator-mcp)](https://pepy.tech/projects/workspace-operator-mcp)

[English](README.md) · [Русский](README.ru.md)

<!-- mcp-name: io.github.Artoxem/workspace-operator -->

</div>

---

![Workspace Operator — MCP server for Google Workspace](https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/workspace-operator-banner.jpg)

Workspace Operator runs on your machine, talks to
Google over your own OAuth client, and gives an AI agent the operations that turn
"read my inbox" into "do the work and let me undo it": staged Apps Script updates, file transfer,
sheet formatting, threaded replies and attachments.

**39 tools · 3 resources · 3 resource templates · 8 prompts**, every tool annotated
with `readOnlyHint` / `destructiveHint`.

Nothing here is tied to a specific account, spreadsheet or document: every tool
takes identifiers and ranges, and all examples use synthetic data.

![Demo: read the last Gmail message and move it to Trash](https://raw.githubusercontent.com/Artoxem/workspace-operator/master/docs/images/gmail-demo.gif)

*Find the last message, read it, then move it to Trash. The message stays recoverable for 30 days.*

## How it compares

| | Google Workspace MCP (remote) | **Workspace Operator** |
|---|---|---|
| Transport | Streamable HTTP, Google-hosted | **stdio + Streamable HTTP, local or Docker** |
| Availability | Developer Preview | **public, MIT** |
| Data path | Google MCP endpoint | **your machine, your OAuth client** |
| Apps Script | — | **create · read · stage · execute · cancel · restore · run function** |
| Local files | — | **upload, download, export to pdf/docx/xlsx/pptx** |
| Sheets formatting | — | **bold, colours, number formats, widths, freeze** |
| Gmail threads | single messages | **threads, attachments, in-thread replies** |
| Server-side tool profiles | IAM / admin allow-list | **read-only / read-write / full + allow-deny** |

Official servers are the right default for "ask my mail a question". Workspace
Operator is for "change the workspace and be able to roll it back".

## What you get

| Group | Tools | Highlights |
|---|---:|---|
| 🔎 Discovery | 4 | Cross-search, Drive search, digest, table diff |
| 📦 Bulk operations | 7 | plan → confirm → run → undo for Drive, Gmail, Docs and Sheets |
| 📁 Drive | 4 | search, read, write, recoverable trash, permissions |
| 📊 Sheets | 6 | values, format, structure, data, delete (confirm) |
| 📄 Docs | 3 | read, write, replace/format (confirm) |
| 📧 Gmail | 4 | read, write, settings, recoverable trash |
| 📅 Calendar | 3 | read, write, delete |
| ✅ Tasks | 2 | read, write |
| 📝 Forms | 2 | read, write |
| 📮 Postmaster | 1 | domains and deliverability stats |
| ⚙️ Apps Script | 3 | read, staged writes, run (admin) |

Plus 3 resources, 3 resource templates and 8 prompts — see the
[tool catalog](#-tool-catalog).

## Who it is for

Workspace Operator is a **single-user server**: one process, one Google account,
one tool profile. "Several clients" does not mean "several users".

| You have | Does it fit? | What happens |
|---|---|---|
| One person with several MCP clients | **Yes** | Each client can use its own bearer token (`http_tokens`); they share the account, profile and data |
| A small team on one Google account | **Works, without isolation** | Everyone sees the same Drive/Gmail; bulk jobs and the audit log are shared; use the `read-only` profile for people you do not fully trust |
| Several Google accounts | **One instance per account** | Separate config, OAuth token, data directory and port or container per person |
| Public service or multi-tenant SaaS | **No** | No per-user authentication, quotas, job ownership or data separation |

A bearer token only identifies a client in the audit log; it does not create a
separate user. Anyone holding a valid token can call every exposed tool and
cancel any bulk job in that instance. Read
[SECURITY.md](docs/SECURITY.md#deployment-models-and-isolation) before sharing an
instance with other people.

## Quick start

### 0 — Choose how to run it

| You want | Use | What it means |
|---|---|---|
| One desktop client (Claude Desktop, Cursor, DSH, Windsurf, Cline) | **stdio** | The client starts the server as a child process. No port, no bearer header, no background service; the server stops when the client stops. |
| One server shared by several clients or agents | **Docker / HTTP** | A long-running container on `127.0.0.1:8765`. Every client connects by URL with a bearer token. |
| Change the code | **source checkout** | Same as stdio, installed from `requirements.txt`. |

Both paths need **Google OAuth once**. The HTTP path additionally needs a local
`MCP_AUTH_TOKEN` string; it is not a Google credential and has nothing to do with
your Google account.

### 1 — Install

**stdio (recommended for a single desktop client)**

```bash
pip install workspace-operator-mcp
workspace-operator version
```

**Docker / HTTP (recommended for several clients)**

```bash
docker pull ghcr.io/artoxem/workspace-operator:1.22.1
```

**From source (development)**

```bash
git clone https://github.com/Artoxem/workspace-operator.git
cd workspace-operator
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Python 3.10 or newer. The package installs the `workspace-operator` command;
`python -m workspace_operator` works from a source checkout too.

### 2 — Google OAuth (once)

1. Create or pick a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the APIs you need: **Drive, Docs, Sheets, Gmail, Calendar,
   Apps Script**, plus **Tasks** and **Forms**. **Postmaster Tools** is optional
   and only useful for domains you have verified.
3. Configure the OAuth consent screen: **External**, add your account as a test
   user while the app is in Testing.
4. Create an **OAuth client ID** of type **Desktop app**, then download the JSON
   and save it as `oauth.keys.json` in `~/.google/`.
5. Authorize once:

```bash
workspace-operator doctor
```

The first run opens a browser. Sign in, allow the scopes, and the token is saved
to `~/.google/token.json`.

**No browser (server, SSH, Docker host)?** Authorize on a machine with a
browser, then copy `token.json` next to `oauth.keys.json` on the target and
mount that directory read-write into the container. The server refreshes the
token in place, so a read-only mount breaks it.

**Changed scopes or upgraded a major version?** Delete `token.json` and run
`workspace-operator doctor` again. The doctor prints exactly which scopes are
missing instead of failing silently.

> Step by step:
> [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) · [docs/ru/AUTH_SETUP.md](docs/ru/AUTH_SETUP.md)

### 3 — Configure

```bash
cp config.example.yaml config.yaml
```

```yaml
client_secrets_file: "/home/you/.google/oauth.keys.json"
token_file: "/home/you/.google/token.json"
backup_dir: "/home/you/.google/backups"
mcp_auth_token: "put-a-long-random-string-here"
tool_profile: "core"            # core | full | read-write | read-only
```

On Windows use forward slashes (`C:/Users/you/.google/oauth.keys.json`) or double
backslashes in YAML. Every key can be overridden by an environment variable; see
[docs/SECURITY.md](docs/SECURITY.md).

Two different secrets, do not mix them up:

| Secret | What it is | Who creates it |
|---|---|---|
| `token.json` | Google OAuth token — proof that Google granted the scopes | Google, after you click **Allow** in the browser |
| `mcp_auth_token` | Local bearer string — a gate for the MCP server (and the HTTP `Authorization` header) | You, any random string |

`mcp_auth_token` is not network security by itself; it is an activation key and
a per-request bearer for the HTTP transport.

### 4 — Connect a client

**stdio client** — the client launches the installed command:

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/.google/config.yaml",
        "MCP_AUTH_TOKEN": "put-a-long-random-string-here"
      }
    }
  }
}
```

**HTTP client** — the container or `workspace-operator serve --http` is already
running:

```json
{
  "mcpServers": {
    "workspace-operator": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer put-a-long-random-string-here" }
    }
  }
}
```

Per-client file locations: [docs/IDE_SETUP.md](docs/IDE_SETUP.md) ·
[docs/ru/IDE_SETUP.md](docs/ru/IDE_SETUP.md). Antigravity has its own walkthrough:
[antigravity/README.md](antigravity/README.md).

If the client cannot start the command, check `workspace-operator version` in
the same shell the client uses — IDEs often have a different `PATH`.

## Tool profiles

A profile is a server-side allow-list: tools outside it are neither listed nor
callable. It complements OAuth scopes (what Google allows) and client permissions
(what the agent may do without asking).

| Profile | Tools | Use it for |
|---|---:|---|
| `core` | 20 | everyday read/write, no formatting or destructive edits |
| `full` | 39 | formatting, destructive edits, Forms, Postmaster, Script |
| `read-write` | 30 | automation without destructive actions |
| `read-only` | 17 | exploration, demos, shared machines, untrusted agents |

```yaml
tool_profile: "core"
# Optional, applied on top. Deny wins over allow.
allowed_tools: ["workspace_search", "sheets_read", "read_doc", "gmail_read"]
denied_tools: ["gmail_write", "drive_write"]
```

Environment overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.
A blocked call returns a clear explanation instead of failing silently.

See [choosing a profile](docs/PROFILES.md) and the [2.0 migration guide](docs/MIGRATION_2.0.md).

## Operations

```bash
python -m workspace_operator doctor     # config, token, scopes, API reachability
python -m workspace_operator doctor --offline   # same, without network probes
python -m workspace_operator tools      # catalog (--profile read-only, --json)
python -m workspace_operator serve      # stdio server
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

The container speaks **HTTP**. It cannot open a browser, so authorize Google
**on the host first**:

```bash
pip install workspace-operator-mcp   # or use a source checkout
workspace-operator doctor           # browser -> ~/.google/token.json
```

Then use Compose (recommended) or a single `docker run`.

**Compose**

```bash
cp .env.example .env                # set MCP_AUTH_TOKEN and GOOGLE_DIR
docker compose up -d
curl http://127.0.0.1:8765/healthz
```

`docker-compose.yml` mounts `config.docker.yaml`, the Google folder read-write,
and `./data` for the audit log and bulk jobs.

**docker run — Linux/macOS**

```bash
docker run -d --name workspace-operator --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -v "$PWD/data:/home/app/data" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:1.22.1
```

**docker run — Windows PowerShell**

```powershell
$token = python -c "import secrets; print(secrets.token_urlsafe(32))"
docker run -d --name workspace-operator --restart unless-stopped `
  -p 127.0.0.1:8765:8765 `
  -v "${env:USERPROFILE}\.google:/home/app/.google" `
  -v "${PWD}\config.docker.yaml:/app/config.yaml:ro" `
  -v "${PWD}\data:/home/app/data" `
  -e MCP_AUTH_TOKEN=$token `
  ghcr.io/artoxem/workspace-operator:1.22.1
```

Point the HTTP client at `http://127.0.0.1:8765/mcp` with
`Authorization: Bearer <token>`. The Google folder is mounted read-write on
purpose: the server refreshes `token.json` in place.

![Healthy container and the public health endpoint](docs/images/docker-health.png)

*`docker compose ps` reports healthy and `/healthz` returns the running version.*

**stdio clients that only speak stdio** can still use the image — the entrypoint
takes the same arguments as the CLI:

```bash
docker run -i --rm \
  -v "$HOME/.google:/home/app/.google" \
  --entrypoint python \
  ghcr.io/artoxem/workspace-operator:1.22.1 -m workspace_operator serve
```

Something not working? See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Something not working? See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Tool catalog

39 consolidated tools. The default `core` profile exposes 20; `full` adds formatting, destructive edits, Forms, Postmaster and Script actions.

Call a consolidated tool with an `action`, for example `drive_read(action="metadata", file_id=...)` or `sheets_write(action="append", spreadsheet_id=..., range=..., values=...)`.

| Tool | Safety | Actions | What it does |
|---|---|---|---|
| `workspace_search` | read | - | Search Drive, Gmail and Calendar in one call. |
| `drive_search` | read | - | Search Drive with full query syntax (replaces find_files and drive_search_advanced). |
| `digest` | read | - | Summarise Gmail, Calendar and Drive for the last N hours. |
| `compare_tables` | read | - | Diff two sheet ranges by a key column. |
| `drive_read` | read | metadata, export, list_permissions | Read Drive metadata, permissions and exported files. |
| `drive_write` | write | create_folder, copy, move, rename, upload, share, restore | Create, copy, move, rename, upload, share and restore Drive files. |
| `drive_trash` | destructive | - | Move a Drive file to Trash (recoverable 30 days; no permanent delete). |
| `drive_permissions` | destructive | remove, revoke_public | Remove access from a Drive file. |
| `read_doc` | read | - | Read the contents of a Google Doc. |
| `docs_write` | write | create, append, insert_image | Create and extend Google Docs. |
| `docs_edit` | destructive | replace, format | Replace or format text in a Google Doc, with a preview. |
| `sheets_read` | read | meta, read, export_csv | Read sheet metadata, values and CSV exports. |
| `sheets_write` | write | create_spreadsheet, add_sheet, update, append, clear, find_replace | Create spreadsheets and write values. |
| `sheets_format` | write | format, borders, conditional, validation, protect | Format ranges, borders, conditional rules, validation and protection. |
| `sheets_structure` | write | insert_rows, insert_columns, merge, sort, named_range, filter_view | Insert, merge, sort and organise sheet ranges. |
| `sheets_delete` | destructive | delete_rows, delete_columns, delete_sheet | Delete rows, columns or a sheet (requires confirm). |
| `sheets_data` | write | chart, pivot | Charts and pivot tables. |
| `gmail_read` | read | profile, list, read, thread, attachment, search, labels, filters | Read Gmail messages, threads, attachments, labels and filters. |
| `gmail_write` | write | send, reply, send_with_attachments, draft_create, draft_update, draft_send, draft_list, archive | Send, reply, draft and archive Gmail messages. |
| `gmail_settings` | write | label_create, label_apply, filter_create | Manage Gmail labels and filters. |
| `gmail_delete` | destructive | email, draft | Move messages or drafts to Trash (recoverable). |
| `calendar_read` | read | events, calendars | Read events and calendars. |
| `calendar_write` | write | meeting, update, move, respond, color | Create, update, move, answer and colour events. |
| `calendar_delete` | destructive | - | Delete an event (requires confirm). |
| `tasks_read` | read | lists, list | Read task lists and tasks. |
| `tasks_write` | write | create, complete | Create and complete tasks. |
| `forms_read` | read | get, responses | Read forms and responses. |
| `forms_write` | write | create, add_questions | Create forms and add questions. |
| `postmaster_read` | read | domains, traffic | Read Postmaster domains and traffic statistics. |
| `script_read` | read | content, deployments | Read Apps Script content and deployments. |
| `script_write` | write | create_project, prepare, execute, cancel, restore, create_deployment, update_deployment | Prepare, execute, restore and deploy Apps Script changes. |
| `script_run` | destructive | - | Run an Apps Script API function (arbitrary code; confirm required). |
| `bulk_plan` | read | - | Resolve a selector into a dry-run bulk plan. |
| `bulk_run` | destructive | - | Execute a reviewed bulk plan as a background job. |
| `bulk_status` | read | - | Read progress for a bulk job. |
| `bulk_result` | read | - | Read one page of bulk job results. |
| `bulk_list` | read | - | List recent bulk jobs. |
| `bulk_cancel` | write | - | Request cancellation of a running bulk job. |
| `bulk_undo` | destructive | - | Undo a completed bulk job (move, rename, trash). |

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
| `confirm=true` | `drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`, `gmail_delete`, `calendar_delete`, `script_run`, `bulk_run`, `bulk_undo` |
| `dry_run` / preview | `bulk_plan`, `sheets_write.find_replace`, `gmail_settings.label_apply` |
| Draft mode by default | `gmail_write.send`, `gmail_write.reply`, `gmail_write.send_with_attachments` |
| Public sharing | disabled unless `allow_public_sharing=true` **and** `allow_public=true` |
| No permanent file delete | Drive tools only move to Trash; `drive_empty_trash` and `drive_transfer_ownership` are not exposed |
| Staged Apps Script | `script_write.prepare` → `script_write.execute` (backup first) |
| Scope routing | tools whose Google scope is missing are hidden at startup |
| Tool annotations | every tool carries `readOnlyHint` / `destructiveHint` |
| Profiles | `core` (default), `full`, `read-write`, `read-only` + allow/deny lists |

> ⚠️ An agent can reach everything your OAuth token can. Use read-only scopes and the
> `read-only` profile for sensitive accounts — [docs/SECURITY.md](docs/SECURITY.md).

## How it works

```
server.py                    MCP protocol wiring and dispatch
workspace_operator/
├─ toolset/                  typed catalog, action router, scope/profile surface
│  ├─ models.py              ToolSpec / ActionSpec / Safety / Surface
│  ├─ catalog.py             39 consolidated tools and action → handler map
│  ├─ surface.py             profile + scope filtering
│  ├─ routing.py             action validation and confirm gate
│  └─ scopes.py              granted Google scopes from the token file
├─ profiles.py               core / full / read-write / read-only
├─ config.py                 config file + environment overrides
├─ auth.py                   OAuth 2.0 credentials and token cache
├─ text.py                   entity/whitespace normalisation, timestamps, error hints
├─ operations.py             staged-operation store for Apps Script
├─ security.py               token and email checks
├─ runtime.py                retries, audit log, dry-run helpers
├─ cli.py                    doctor / tools / serve
└─ handlers/                 Google API implementations used by the catalog
tests/                       unit, surface and in-memory MCP checks
antigravity/                 ready-to-paste mcp_config.json
skills/google-workspace/     Agent Skill: when to use which tool
```

Design rules:

* the catalog is the single source of truth for names, actions, scopes and docs;
* every action maps to exactly one handler and is validated before dispatch;
* destructive actions require `confirm=true` at the router and in the handler;
* no tool permanently deletes a Drive file; Trash is the boundary;
* server-side profiles and scope routing keep the exposed surface small.

## Testing

```bash
python -m unittest discover -s tests -v     # 354 unit tests, no network
python tests/live_smoke.py                  # 51 checks against a real account
python tests/live_new_tools.py              # 15 checks for the v1.14 batch
python tests/live_phase2.py                 # 8 checks for the v1.15 batch
python tests/live_phase3.py                 # 8 checks for the v1.16 batch
python tests/live_phase4.py                 # 5 checks for the v1.17 batch
python tests/live_phase5.py                 # 7 checks for the v1.18 batch
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

- **Drive**: deleting means "move to Trash"; there is no permanent-delete or
  ownership-transfer tool.
- **Sheets**: tabs, rows, columns, merges, sorting, pivot tables, validation,
  protection and borders are handled; charts cover the basic types.
- **Docs**: text styling works on matched text; no template-fill tool is exposed.
- **Slides and Drive comments** were removed in 2.0; see the migration guide.
- **One account per server**: a single OAuth token, no multi-tenant mode.

## Roadmap

- [x] Cross-product search, tool profiles
- [x] Files, Apps Script execution
- [x] Sheet formatting
- [x] Gmail threads, attachments, replies
- [x] Calendar update/delete/respond
- [x] `digest` and `compare_tables`
- [x] Optional HTTP transport (Streamable HTTP, stateless, localhost-first)
- [x] 2.0 consolidated surface, scope routing, core profile

## Responsibility

You are responsible for what the agent does with your account. Read
[docs/SECURITY.md](docs/SECURITY.md), start with `read-only`, keep backups on.

---

<div align="center">

MIT licensed · built on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

</div>
