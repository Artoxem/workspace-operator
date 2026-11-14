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

## Scope routing

At startup the server reads the Google scopes from `token.json` and hides tools
whose scope is not granted. If the token file is missing or has no scope list,
routing is skipped and a warning is logged.

Examples:

- no `presentations` scope → no Slides tools (Slides were removed in 2.0 anyway);
- only `drive.readonly` → `drive_write`, `drive_trash`, `drive_permissions` are
  hidden;
- only `gmail.readonly` → `gmail_write`, `gmail_settings`, `gmail_delete` are
  hidden.

`workspace_search`, `digest`, `compare_tables` and `bulk_*` are cross-domain and
stay visible; they report partial errors if a source is inaccessible.

## Check what is active

```bash
python -m workspace_operator tools --profile core
python -m workspace_operator doctor
curl http://127.0.0.1:8765/healthz
```

The audit log records the active profile and the tool/action name, not argument
values.

## Safety defaults

- destructive actions require `confirm=true`;
- Drive deletion is Trash only; no `drive_empty_trash`;
- public sharing requires `allow_public_sharing=true` and `allow_public=true`;
- `dry_run` turns writes into previews;
- use `read-only` scopes with the `read-only` profile for the strongest isolation.
