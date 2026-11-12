# Security and safeguards

The server includes safeguards to reduce accidental destructive actions.

## Confirmations (confirm)
- `delete_email`, `gmail_archive`, `calendar_create_meeting`,
  `drive_revoke_public` require `confirm=true`.
- `doc_fill_template`, `doc_replace_text`, `docs_format_text` require confirmation
  to avoid mass replacements.
- The current confirm-gated list is the «Safety by default» table in the README.

## Dry-run
- `batch_delete_emails` defaults to dry-run.
- `sheet_find_replace` defaults to `dry_run=true`.
- `clear_range` automatically requires confirmation for large ranges.

## Public access
- `share_file` blocks `type=anyone` unless `allow_public=true`.

## Tool profiles (server-side allow-list)

A profile removes tools before the agent ever sees them. It is enforced in two
places: `tools/list` returns only the exposed tools, and `tools/call` rejects
anything outside the profile with an explicit error.

| Profile | Tools | Use it for |
|---|---:|---|
| `full` | 132 | your own machine, full trust |
| `read-write` | 113 | daily work — destructive tools hidden |
| `read-only` | 39 | exploration, demos, shared machines, untrusted agents |

```yaml
tool_profile: "read-only"
# Optional explicit lists, applied on top. Deny beats allow.
allowed_tools: ["workspace_search", "find_files", "read_sheet"]
denied_tools: ["gmail_search_and_summarize"]
```

Env overrides: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
Every key has an environment override:

| Variable | Overrides | Notes |
|---|---|---|
| `MCP_CONFIG_FILE` | — | path to `config.yaml` / `config.json` |
| `MCP_AUTH_TOKEN` | `mcp_auth_token` | required before any tool call is served |
| `MCP_TOOL_PROFILE` | `tool_profile` | `full` / `read-write` / `read-only` |
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

## MCP_AUTH_TOKEN
All tool calls require `MCP_AUTH_TOKEN` to be configured (environment variable or
`mcp_auth_token` in `config.yaml`). This is a **server-side configuration check**
that ensures the operator has consciously enabled the server before it becomes
operational. It does **not** perform per-request client authentication.

You can think of `MCP_AUTH_TOKEN` as a **local “activation key” for this MCP
server** — an extra safeguard against accidental startup without configuration,
not a security boundary or network protection mechanism.

For STDIO-based MCP servers the transport is inherently local (the IDE launches the
server process directly), so there is no network endpoint to protect. The token
simply prevents accidental starts without a deliberate setup step.

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
  - "https://www.googleapis.com/auth/presentations"
  - "https://www.googleapis.com/auth/gmail.modify"
  - "https://www.googleapis.com/auth/gmail.settings.basic"
  - "https://www.googleapis.com/auth/calendar"
  - "https://www.googleapis.com/auth/tasks"
  - "https://www.googleapis.com/auth/forms.body"
  - "https://www.googleapis.com/auth/forms.responses.readonly"
  - "https://www.googleapis.com/auth/postmaster.readonly"
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

- `script_run_function` runs arbitrary Apps Script code with the authority of the
  OAuth token. It is marked `destructiveHint`, so the `read-write` profile hides it;
  the `full` profile exposes it deliberately.
- `drive_download` and `drive_export` write to the local filesystem on the machine
  running the server — `save_to` is honoured literally and the absolute path is
  echoed back. Never overwrite without `overwrite=true`.
- `drive_upload` reads any local file the process can read (100 MB cap); treat the
  server process as having the file access of its user.

## HTTP transport (v1.9)

- Default bind is `127.0.0.1`. A non-loopback bind requires `--allow-network`
  **and** `--insecure`; the second flag acknowledges there is no TLS.
- Every request must present `Authorization: Bearer <token>`; comparison is
  constant-time. Tokens come from `http_tokens` (name → token) or fall back to
  `mcp_auth_token` as `default`.
- DNS-rebinding protection rejects unexpected `Host` headers and every browser
  `Origin` that was not explicitly allowed.
- `GET /healthz` is public by design and exposes no data.
- The audit log records the token name as `client`, so a shared deployment can be
  traced back to a specific token.
- Network exposure means everyone shares one Google identity. For real multi-user
  use: TLS proxy in front, a dedicated service account, minimal scopes and a
  distinct token per client.
