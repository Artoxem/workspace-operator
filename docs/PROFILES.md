# Choosing a profile

Workspace Operator exposes 39 consolidated tools. The default `core` profile
shows 20; choose a narrower or wider surface for each client.

## Profiles

| Profile | Tools | What it includes | Use it for |
|---|---:|---|---|
| `read-only` | 17 | reads and searches only | exploration, untrusted agents, demos |
| `core` (default) | 20 | everyday reads/writes, recoverable Trash, bulk plan/run/status | inbox and document work |
| `read-write` | 30 | writes without destructive actions | automation that must not delete or overwrite |
| `full` | 39 | formatting, destructive edits, Forms, Postmaster, Script | power users and admins |

`core` excludes `docs_edit`, `sheets_format`, `sheets_structure`,
`sheets_delete`, `sheets_data`, `gmail_settings`, `calendar_delete`,
`drive_permissions`, Forms, Postmaster and Apps Script. Switch to `full` when
you need those actions.

## Choose by user

| You are | Start with | Why |
|---|---|---|
| Analyst or researcher | `read-only` | no writes, smallest context |
| Inbox assistant | `core` | mail, threads, drafts and Trash |
| Docs/Sheets editor | `core`, then `full` for formatting | formatting tools are opt-in |
| Automation builder | `full` + `dry_run` first | destructive actions need confirm |
| Developer/admin | `full` | Script prepare/execute/deploy |
| Shared machine / demo | `read-only` | least privilege |


## Profile endpoints (HTTP)

When the server runs over HTTP, each profile has a stable endpoint:

| URL | Profile |
|---|---|
| `/mcp` | `tool_profile` from config (default `core`) |
| `/mcp/read` | `read-only` |
| `/mcp/read-write` | `read-write` |
| `/mcp/full` | `full` |

Each client connects to the URL it needs; the tool list stays stable for that
connection. All endpoints use the same bearer token and audit log.

## Configure

Pick a profile for a single run with `workspace-operator serve --profile full`; it
wins over `tool_profile` in the config file and over `MCP_TOOL_PROFILE`.

### stdio

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/.google/config.yaml",
        "MCP_AUTH_TOKEN": "long-random-token",
        "MCP_TOOL_PROFILE": "core"
      }
    }
  }
}
```

### HTTP / Docker

```bash
MCP_TOOL_PROFILE=core
MCP_SCOPE_ROUTING=1
MCP_ALLOW_PUBLIC_SHARING=0
```

The server reads `tool_profile` from `config.yaml` or `MCP_TOOL_PROFILE`.
`allowed_tools` / `denied_tools` narrow the chosen profile further.

### Custom allow-list

```yaml
tool_profile: "full"
allowed_tools: ["workspace_search", "drive_read", "sheets_read", "gmail_read"]
denied_tools: ["gmail_write"]
```

Names are the consolidated tool names, not 1.x names. A denied name always wins.

## Scopes and tools

Two independent filters decide what the agent sees:

1. **OAuth scopes** — what Google will actually allow.
2. **Profile** — what this server exposes (`read-only`, `core`, `read-write`, `full`).

Scope routing runs first at startup: tools whose required Google scope is missing
are not listed and cannot be called. The profile is applied to the remaining
tools; `allowed_tools` / `denied_tools` narrow it further.

If `token.json` is missing or has no scope list, routing is skipped with a
warning: the server cannot know the granted scopes yet.

| OAuth scope(s) | Tools that become visible |
|---|---|
| none (cross-domain) | `workspace_search`, `digest`, `compare_tables`, `bulk_*` |
| `drive` or `drive.readonly` | `drive_search`, `drive_read` |
| `drive` | plus `drive_write`, `drive_permissions` (deletion via bulk) |
| `documents` or `documents.readonly` | `read_doc` |
| `documents` | plus `docs_write`, `docs_edit` |
| `spreadsheets` or `spreadsheets.readonly` | `sheets_read` |
| `spreadsheets` | plus `sheets_write`, `sheets_format`, `sheets_structure`, `sheets_delete`, `sheets_data` |
| `gmail.modify` or `gmail.readonly` | `gmail_read` |
| `gmail.modify` | plus `gmail_write`, `gmail_delete` |
| `gmail.modify` + `gmail.settings.basic` | `gmail_settings` (both required) |
| `calendar` or `calendar.readonly` | `calendar_read` |
| `calendar` | plus `calendar_write`, `calendar_delete` |
| `tasks` or `tasks.readonly` | `tasks_read` |
| `tasks` | plus `tasks_write` |
| `forms.body` + `forms.responses.readonly` | `forms_read`, `forms_write` (both required) |
| `postmaster.domain` + `postmaster.traffic.readonly` | `postmaster_read` (both required) |
| `script.projects` + `script.deployments` | `script_read`, `script_write`, `script_run` (both required) |

Google API enablement is a separate switch: a scope can be granted while the API
is disabled, and the call then fails with 403. Enable the APIs listed in
[AUTH_SETUP.md](AUTH_SETUP.md).

### Minimal scope sets

```yaml
# Drive only
scopes:
  - "https://www.googleapis.com/auth/drive"
```

```yaml
# Gmail read/write, no settings/labels administration
scopes:
  - "https://www.googleapis.com/auth/gmail.modify"
```

```yaml
# Docs + Sheets read-only
scopes:
  - "https://www.googleapis.com/auth/documents.readonly"
  - "https://www.googleapis.com/auth/spreadsheets.readonly"
```

Other domains need the scopes from the table. Removing a scope also hides its
tools; add it and re-authorize to bring them back.

### If a tool is missing

1. Run `workspace-operator doctor` — it prints missing configured scopes.
2. Check `token.json` scopes against the table above.
3. Delete `token.json`, run `workspace-operator doctor`, approve the new consent.
4. Check the effective profile: `workspace-operator tools --profile core`.

Routing is applied once at startup. After changing scopes, restart or reconnect
the server.

### Routing off

`MCP_SCOPE_ROUTING=0` disables hiding. Tools may then be visible but still fail
with `403 insufficientPermissions`; this mode is for debugging only.

Cross-domain tools (`workspace_search`, `digest`, `compare_tables`, `bulk_*`)
have no single required scope and stay visible; they report partial errors when a
source is inaccessible.

## Check what is active

```bash
python -m workspace_operator tools --profile core
python -m workspace_operator doctor
curl http://127.0.0.1:8765/healthz
```

The audit log records the active profile and the tool/action name, not argument
values.

## Safety defaults

- destructive actions require a human `approval_id`; `confirm=true` alone is not enough;
- Drive deletion is Trash only; no `drive_empty_trash`;
- public sharing requires `allow_public_sharing=true` and `allow_public=true`;
- `dry_run` turns writes into previews;
- use `read-only` scopes with the `read-only` profile for the strongest isolation.
