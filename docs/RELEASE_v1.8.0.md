# Release v1.8.0 — operations-grade runtime

The server stops being a script you run and becomes something you can operate.

## New in this release

### Dry run

```bash
MCP_DRY_RUN=1 python server.py       # or dry_run: true in config.yaml
```

Every tool that is **not** read-only returns a preview instead of executing:

```
DRY RUN: 'send_email' was not executed. Arguments: ['body_text', 'subject', 'to'].
Unset dry_run / MCP_DRY_RUN to apply changes.
```

Read-only tools keep working, so an agent can explore real data while every write
is intercepted. Useful for demos, for onboarding, and for letting a new agent loose
before trusting it.

### Audit log

```yaml
audit_log: "C:\\Users\\you\\.google\\audit.jsonl"
```

One JSON line per tool call:

```json
{"ts":"2026-11-06T19:21:07+00:00","tool":"send_email","profile":"full",
 "status":"dry-run","duration_ms":0,"arguments":["body_text","subject","to"]}
```

Tool, profile, status, duration and the **names** of the arguments — never their
values, so tokens and message bodies do not leak into the log. Failures get an
`error` field.

### Retries

`retry_attempts: 3` (or `MCP_RETRY_ATTEMPTS`): transient Google API failures
(429, 500, 502, 503, 504) are retried with exponential backoff before the tool
reports an error.

### CLI

```bash
python -m workspace_operator doctor     # config, token, scopes, API reachability
python -m workspace_operator tools      # catalog, --profile, --json
python -m workspace_operator version
python -m workspace_operator serve      # stdio server
```

`doctor` checks secrets and token files, compares granted scopes with the
configured ones, refreshes the token (unless `--offline`) and probes Drive, Gmail
and Calendar. Exit code 1 only for critical problems — a missing token is a
warning, not a failure.

## Counts

- Tools: 66 (unchanged — this release is about the runtime, not the surface)
- Unit tests: 192
- Live checks: 45

## Verified

- dry-run intercepted `send_email` and let `find_files` through;
- the audit file contained both entries with statuses `dry-run` and `ok`;
- `doctor` reported all checks green against the real account;
- `tools --profile read-only` lists 21 tools.

## Configuration additions

| Key | Env | Default |
|---|---|---|
| `dry_run` | `MCP_DRY_RUN` | `false` |
| `audit_log` | `MCP_AUDIT_LOG` | disabled |
| `retry_attempts` | `MCP_RETRY_ATTEMPTS` | `3` |
