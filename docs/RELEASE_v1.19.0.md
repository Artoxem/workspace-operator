# Workspace Operator 1.19.0

Bulk operations for Google Drive: plan first, confirm, then run in the
background. 121 tools total.

## Highlights

- **Six new tools** — `bulk_plan`, `bulk_run`, `bulk_status`, `bulk_cancel`,
  `bulk_result`, `bulk_list`.
- **Plan → confirm → run.** `bulk_plan` resolves a selector once and stores an
  immutable snapshot with counts, total size and a five-item sample. Nothing
  changes until `bulk_run(plan_id, confirm=true)`.
- **Background jobs.** `bulk_run` returns a `job_id` immediately. Poll
  `bulk_status` for compact progress, page `bulk_result` for per-item outcomes,
  or read the JSONL artifact on disk.
- **Drive actions** — move, trash, restore, rename (pattern or find/replace).
  Trash is reversible; permanent deletion is not part of bulk operations.
- **Resume.** A killed or cancelled job can be resumed with
  `bulk_run(plan_id, confirm=true, job_id=...)`; finished items are skipped by id.
- **Safety caps.** 300 items per plan by default, a hard ceiling of 10,000 with
  `allow_large=true`, protected ids/patterns, shared drives off by default, and
  the global `dry_run` switch still blocks every run.

## Performance

Measured on a temporary Drive folder, default configuration (8 workers):

| Operation | Files | Time |
|---|---|---|
| `bulk_plan` (folder scope) | 100 | 1.4–2.0 s |
| `bulk_run` move | 100 | 8.6–9.1 s |
| `bulk_run` trash | 100 | 7.1 s |
| Plan response | — | 766 characters |
| Status response | — | 445 characters |

The model never receives a full file list: plans carry at most a five-item
sample, results are paginated 50 at a time.

## Configuration

New optional block; defaults match the numbers above.

```yaml
bulk:
  dir: ""                  # default: ./data/bulk
  max_items: 300
  hard_limit: 10000
  concurrency: 8
  plan_ttl: 900
  protected_ids: []
  protected_patterns: []
  allow_shared_drives: false
```

Environment overrides: `MCP_BULK_DIR`, `MCP_BULK_MAX_ITEMS`,
`MCP_BULK_HARD_LIMIT`, `MCP_BULK_CONCURRENCY`, `MCP_BULK_PLAN_TTL`,
`MCP_BULK_PROTECTED_IDS`, `MCP_BULK_PROTECTED_PATTERNS`,
`MCP_BULK_ALLOW_SHARED_DRIVES`.

## Safety

- Plans expire after 15 minutes.
- Protected ids and glob patterns are excluded with a warning.
- Destructive actions are confirmed twice: plan review plus `confirm=true`.
- Audit records the plan and the run with counts only — never argument values.
- Job state is checkpointed every 25 items, so a restart loses at most 25 results.

## Compatibility

- Additive: existing 115 tools are unchanged; total is now 121.
- Profiles: `full` 121, `read-write` 102, `read-only` 33.
- No new OAuth scopes.
- Python 3.11+ and MCP Python SDK 2.x, protocol 2026-07-28.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.19.0
# or
docker compose pull && docker compose up -d
```

For DSH and other MCP clients: restart or reconnect the server so the new tools
are listed.

## Tests

- 302 unit tests.
- Live smoke on real Drive: move, rename, trash, restore and the confirmation
  gate, with cleanup.
- Protocol smoke over stdio: 121 tools, plan, unconfirmed-run refusal, job list.
