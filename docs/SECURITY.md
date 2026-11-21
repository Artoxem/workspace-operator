# Security and safeguards

The server includes safeguards to reduce accidental destructive actions.

## Confirmations and human approval
- Destructive calls first return `APPROVAL_REQUIRED`; a human decides the request in the CLI or on the browser page (`workspace-operator approvals …`), and the agent retries with the one-time `approval_id`.
- The agent is never told how to approve: its tool result carries no commands and no link. The browser link holds a per-approval secret and is written to the server log for the operator. See [APPROVALS.md](APPROVALS.md).
- Approval is bound to a hash of the tool/action/arguments, expires after `approval_ttl` and is single-use.
- `drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
  `gmail_delete`, `calendar_delete`, `script_run`, `bulk_run` and `bulk_undo`
  require `confirm=true`.
- The router enforces this before the handler runs; handlers keep their own
  checks as a second layer.

## Dry-run and previews
- `bulk_plan` is always a dry run.
- `sheets_write` → `find_replace` returns a preview without `confirm=true`.
- `gmail_settings` → `label_apply` defaults to `dry_run=true`.

## No permanent file deletion
- `drive_trash` only moves a file to Trash; there is no `drive_empty_trash` and
  no ownership-transfer tool.
- Gmail deletion moves messages to Trash.

## Public access
- Public sharing is disabled by default. `drive_write` → `share` requires both
  `allow_public_sharing=true` in config and `allow_public=true`.

## Tool profiles (server-side allow-list)

A profile removes tools before the agent ever sees them. It is enforced in two
places: `tools/list` returns only the exposed tools, and `tools/call` rejects
anything outside the profile with an explicit error.

| Profile | Tools | Use it for |
|---|---:|---|
| `core` | 20 | everyday read/write, no formatting or destructive edits |
| `full` | 39 | formatting, destructive edits, Forms, Postmaster, Script |
| `read-write` | 30 | automation without destructive actions |
| `read-only` | 17 | exploration, demos, shared machines, untrusted agents |

```yaml
tool_profile: "read-only"
# Optional explicit lists, applied on top. Deny beats allow.
allowed_tools: ["workspace_search", "sheets_read", "gmail_read"]
denied_tools: ["gmail_write", "drive_write"]
```

Env overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
Every key has an environment override:

| Variable | Overrides | Notes |
|---|---|---|
| `MCP_CONFIG_FILE` | — | path to `config.yaml` / `config.json`; wins over the lookup (`./config.yaml`, then `<user config dir>/workspace-operator/config.yaml`), and must exist |
| `MCP_AUTH_TOKEN` | `mcp_auth_token` | required before any tool call is served |
| `MCP_TOOL_PROFILE` | `tool_profile` | `core` / `full` / `read-write` / `read-only` |
| `MCP_APPROVAL_DIR` | `approval_dir` | human approval queue; default `~/.google/approvals` (read-write in Docker) |
| `MCP_APPROVAL_TTL` | `approval_ttl` | approval lifetime in seconds |
| `MCP_APPROVAL_BROWSER_WAIT` | `approval_browser_wait` | seconds a destructive call waits for a browser decision (`0` disables, capped at 45) |
| `MCP_APPROVAL_URL` | `approval_url` | base URL for the browser approval page |
| `MCP_OPERATION_DIR` | `operation_dir` | staged Apps Script operations (default `data/operations`) |
| `MCP_OPERATION_TTL` | `operation_ttl` | seconds a prepared operation stays executable (default 600) |
| `MCP_UPLOAD_ROOTS` | `upload_roots` | comma-separated folders `drive_write(action="upload")` may read; empty = any folder except secrets |
| `MCP_SCOPE_ROUTING` | `scope_routing` | hide tools whose Google scope is missing |
| `MCP_ALLOW_PUBLIC_SHARING` | `allow_public_sharing` | enable public links (off by default) |
| `MCP_ALLOWED_TOOLS` | `allowed_tools` | comma-separated allow list |
| `MCP_DENIED_TOOLS` | `denied_tools` | comma-separated deny list; deny beats allow |
| `MCP_DRY_RUN` | `dry_run` | `1` turns writes into previews |
| `MCP_AUDIT_LOG` | `audit_log` | JSONL audit trail |
| `MCP_RETRY_ATTEMPTS` | `retry_attempts` | retries on 429/5xx |
| `GOOGLE_CLIENT_SECRETS_FILE` | `client_secrets_file` | OAuth client JSON |
| `GOOGLE_TOKEN_FILE` | `token_file` | cached token, rewritten on refresh |
| `GOOGLE_BACKUP_DIR` | `backup_dir` | Apps Script backups |
| `GOOGLE_LOG_FILE` | `log_file` | server log |
| `GOOGLE_LOG_LEVEL` | `log_level` | `DEBUG` / `INFO` / `WARNING` |


Profiles are a **defense-in-depth layer, not a security boundary you can rely on
alone**: the OAuth token still carries whatever scopes you granted. The strongest
combination is read-only scopes **and** the `read-only` profile — then neither the
token nor the server can write.

## Deployment models and isolation

Workspace Operator is a **single-user server**. One process uses one OAuth token
and exposes one tool profile. Several MCP clients can connect, but they are
clients of the same user, not separate users.

| Model | Supported | Notes |
|---|---|---|
| One person, several clients | Yes | `http_tokens` gives each client a name for the audit log; all share the account and profile |
| Team sharing one Google account | Yes, no isolation | Same Drive/Gmail, same audit log, same bulk jobs; use `read-only` for untrusted members |
| Several Google accounts | No, one instance each | Per user: own `config.yaml`, `token.json`, `data/` and port |
| Public or multi-tenant service | No | No user accounts, quotas, per-user profiles or job ownership |

### What a bearer token does and does not do

- It authenticates a request to this instance and gives the token a name in the
  audit log (`client` field).
- It does **not** scope tools, data or jobs. Every token sees every exposed tool
  and can call `bulk_status`, `bulk_cancel` or `bulk_result` for any job.
- `http_tokens` is a client registry, not a user registry. There is no role
  model: the profile and allow/deny lists are global.

### Recommended deployments

**One person, one or more clients.** Use stdio for a single desktop client, or
one HTTP container with a token per client. Keep the port on loopback.

**Small team on one account.** It works, but treat everyone as the same user.
Run the `read-only` profile for people who only need to look, keep
`MCP_AUTH_TOKEN` private, and remember that the audit log is shared.

**Several accounts.** Run one instance per account:

```bash
docker run -d --name workspace-alice \
  -p 127.0.0.1:8765:8765 \
  -v /home/alice/.google:/home/app/.google \
  -v /home/alice/workspace-data:/home/app/data \
  -e MCP_AUTH_TOKEN=... \
  ghcr.io/artoxem/workspace-operator:latest
```

Repeat with another port, config and Google folder for each person. A reverse
proxy can route by hostname or path. This is the only configuration with real
data isolation; horizontal scaling of one token across several instances is not
supported because bulk plans and jobs live on local disk.

### If you need multi-tenancy

It is out of scope today. A real multi-user service would need per-user OAuth,
token-to-user mapping, per-user profiles and quotas, job ownership and a shared
job store. None of that exists in this server.

## MCP_AUTH_TOKEN
All tool calls require `MCP_AUTH_TOKEN` to be configured (environment variable or
`mcp_auth_token` in `config.yaml`). This is a **server-side configuration check**
that ensures the operator has consciously enabled the server before it becomes
operational. It does **not** perform per-request client authentication.

Over **stdio** you can think of `MCP_AUTH_TOKEN` as a **local “activation key”** —
the transport is inherently local (the IDE launches the server process directly), so
the token only prevents accidental starts without a deliberate setup step.

Over **HTTP** the same value (or the per-client `http_tokens`) is the real
`Authorization: Bearer` credential for every request, so it must be random and
secret: the server refuses to start with a placeholder (`change_me`, …) or a token
shorter than 24 characters.

Where to keep it:

- Prefer the `MCP_AUTH_TOKEN` environment variable (or your secret manager) over
  `mcp_auth_token` in `config.yaml`; `workspace-operator doctor` warns when the token
  is stored in the config file.
- Generate it with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- Rotating it does not require a new Google authorization.

## Secrets on disk

| File | What it grants | Handling |
|---|---|---|
| `token.json` | access to your Google account within the granted scopes | written atomically under a file lock, owner-only permissions (`0600`, an owner-only ACL on Windows) |
| `oauth.keys.json` | the OAuth client identity (client secret) | keep outside the repository, owner-only |
| `~/.google/approvals/*.json` | one-time approval secrets | created owner-only; never returned to the agent |
| `data/operations/*.json` | staged Apps Script source | owner-only; expires after `operation_ttl`; consumed on execution |
| `.env` | `MCP_AUTH_TOKEN` for Docker Compose | git-ignored; keep owner-only |

`workspace-operator doctor` checks that secret files are not readable by other
users and flags leftovers next to the token (old `token.json.bak-*`,
`service-account.json`, `credentials.json`). Delete credentials you do not use: a
backup of a token is a working credential until it is revoked.

**If a secret may have leaked:** revoke the app at
<https://myaccount.google.com/permissions> (this invalidates every copy of the
refresh token at once), delete the Cloud service-account key if you had one, delete
`token.json` and the backups, generate a new `MCP_AUTH_TOKEN`, then run
`workspace-operator doctor` to authorize again.

`drive_write(action="upload")`, local file exports and approvals all go through one
list of protected paths (`secure_files.protected_paths`), so an agent cannot use
them to move your credentials around.

## Understanding OAuth Scopes

OAuth scopes define what the server can access in your Google account. You can customize these in `config.yaml` under the `scopes:` section.

### Default Scopes (Full Access)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
  - "https://www.googleapis.com/auth/drive"
  - "https://www.googleapis.com/auth/script.projects"
  - "https://www.googleapis.com/auth/script.deployments"
  - "https://www.googleapis.com/auth/documents"
  - "https://www.googleapis.com/auth/gmail.modify"
  - "https://www.googleapis.com/auth/gmail.settings.basic"
  - "https://www.googleapis.com/auth/calendar"
  - "https://www.googleapis.com/auth/tasks"
  - "https://www.googleapis.com/auth/forms.body"
  - "https://www.googleapis.com/auth/forms.responses.readonly"
  - "https://www.googleapis.com/auth/postmaster.domain"
  - "https://www.googleapis.com/auth/postmaster.traffic.readonly"
```

### Read-Only Configuration (Safer for Exploration)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets.readonly"
  - "https://www.googleapis.com/auth/drive.readonly"
  - "https://www.googleapis.com/auth/documents.readonly"
  - "https://www.googleapis.com/auth/gmail.readonly"
  - "https://www.googleapis.com/auth/calendar.readonly"
```

### Minimal Configuration (Sheets Only)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
```

### Custom Scenarios

**Scenario 1: Email assistant (read + draft)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/gmail.readonly"
  - "https://www.googleapis.com/auth/gmail.compose"  # Draft only, no send
```

**Scenario 2: Document automation (Sheets + Docs)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
  - "https://www.googleapis.com/auth/documents"
```

**Scenario 3: File organization (Drive only)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/drive.file"  # Only files created by this app
```

### Changing Scopes
1. Edit `scopes:` in `config.yaml`
2. Delete your `token.json` file
3. Restart the server — a new OAuth prompt will appear with updated permissions

## Best Practices

### For Testing
- Create a separate Google account
- Use default scopes to test all features
- Keep test data separate from personal/work data

### For Production
- Use minimal scopes for your use case
- Review the scope list above and remove unused APIs
- Test with read-only scopes first, then add write permissions as needed

### For Work/Organization Accounts
- Check your organization's IT policies before connecting
- Consider using a dedicated service account
- Keep logs of operations for audit purposes
- Review the [Google Workspace Admin scope documentation](https://developers.google.com/identity/protocols/oauth2/scopes)

## AI Agent Access

**Important:** Your AI agent (MCP client) will have access to all data permitted by the OAuth scopes you grant. The `MCP_AUTH_TOKEN` is a configuration check, not a client-facing authentication mechanism — it does not restrict the AI agent itself.

If you're concerned about accidental actions:
- Start with read-only scopes
- Use the built-in confirmations (`confirm=True`, `dry_run=False`)
- Test with a separate Google account first
- Monitor the server logs (`log_file` in config)

## Responsibility notice
You are responsible for understanding the risks and the consequences of
operations performed by this server. Use it at your own discretion and
follow your organization's security policies.

For questions about specific scopes, see [Google's OAuth 2.0 Scopes documentation](https://developers.google.com/identity/protocols/oauth2/scopes).

## Code execution and local files (v1.2)

- `script_run` runs arbitrary Apps Script code with the authority of the
  OAuth token. It is marked `destructiveHint`, so the `read-write` profile hides it;
  the `full` profile exposes it deliberately.
- `drive_read(action="export")` writes to the local filesystem on the machine
  running the server — `save_to` is honoured literally and the absolute path is
  echoed back. Never overwrite without `overwrite=true`.
- `drive_write(action="upload")` reads local files (100 MB cap). OAuth secrets are
  always refused: the configured token, client-secrets and backup paths, `~/.google`,
  `~/.ssh`, `~/.aws`, `~/.gnupg`, and files named `token.json`, `.env*`,
  `oauth.keys.json` and similar. Set `upload_roots` (`MCP_UPLOAD_ROOTS`) to restrict
  uploads to specific folders; in the Docker config it defaults to
  `/home/app/data/upload`. Without `upload_roots` the process otherwise has the
  file access of its user.
- Names that come from remote data (mail attachments, Drive titles) are reduced to a
  leaf file name before saving (`../`, drive letters, reserved Windows names and
  invalid characters are removed), so a malicious attachment cannot write outside
  the target directory. An explicit `save_to` file path chosen by the caller is
  still honoured.

## HTTP transport (v1.9)

- Default bind is `127.0.0.1`. A non-loopback bind requires `--allow-network`
  **and** `--insecure`; the second flag acknowledges there is no TLS.
- Every request must present `Authorization: Bearer <token>`; comparison is
  constant-time. Tokens come from `http_tokens` (name → token) or fall back to
  `mcp_auth_token` as `default`.
- DNS-rebinding protection rejects unexpected `Host` headers and every browser
  `Origin` that was not explicitly allowed.
- `GET /healthz` is public by design and exposes no data.
- The server refuses to start over HTTP with a placeholder token (`change_me`, …) or
  one shorter than 24 characters. Generate one with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"` and keep it out of
  `config.yaml`: prefer the `MCP_AUTH_TOKEN` environment variable.
- The browser approval pages are protected by a per-approval secret, an
  `Origin`/`Host` check and restrictive response headers; see `APPROVALS.md`.
- The Docker image binds `127.0.0.1` by default. `docker-compose.yml` passes
  `--allow-network --insecure` together with a loopback-only port mapping; with a
  plain `docker run` you must opt in to network binding yourself.
- The audit log records the token name as `client`, so a shared deployment can be
  traced back to a specific token.
- Network exposure means everyone shares one Google identity. For real multi-user
  use: TLS proxy in front, a dedicated service account, minimal scopes and a
  distinct token per client.
