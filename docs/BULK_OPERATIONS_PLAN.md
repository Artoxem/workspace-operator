> **Historical design note.** This plan predates 2.0. The Slides domain, 1.x tool names and old counts are obsolete; use [MIGRATION_2.0.md](MIGRATION_2.0.md).

# Bulk operations: audit and plan

Status: phases 0–3 implemented (release pending).
Scope: Google Drive, Gmail, Docs, Slides, Sheets.

Implementation note: 1.19.0 added the six tools, Drive
move/trash/restore/rename, the plan store and the background engine. 1.20.0
added Gmail actions (batched 1,000 per call) and Drive share/revoke_public.
1.21.0 added `bulk_undo` for move/rename/trash and text replacement domains for
Docs (`replace_text`), Slides (`replace_text`) and Sheets (`find_replace`).
The Drive batch endpoint (100 calls per request) is not used yet; concurrency
already moves 100 files in about nine seconds.

## 1. Goals

1. Handle requests that touch thousands of objects without thousands of tool calls.
2. Keep model context small: a bulk request must cost a bounded number of tokens.
3. Stay safe: nothing destructive happens without a reviewed plan and an explicit confirm.
4. Survive failure: partial failures are isolated, reported compactly, and the job can resume.

Non-goals for the first release: real-time streaming of every item, cross-account
operations, permanent deletion in bulk, and UI work outside the existing Web GUI.

## 2. Audit of the current surface

Inventory: 115 tools.

| Domain | Tools | Bulk support |
|---|---|---|
| Drive | 19 | none: every action targets one file id |
| Sheets | 19 | range-level, but no multi-sheet or row-filter bulk |
| Gmail | 14 | one tool: `batch_delete_emails` |
| Slides | 11 | single-object |
| Calendar | 8 | single-event |
| Docs | 5 | single-document |
| Apps Script | 4 | single-project |
| Composite | 15 | read-oriented summaries |

Concrete gaps found in the code:

1. **No selection-to-action path.** `find_files` / `drive_search_advanced` return a
   list, and the client must loop `move_file` / `drive_delete_file` per item. That is
   N model turns, N tool calls and N API round trips.
2. **Sequential execution.** There is no worker pool and no use of the Drive batch
   endpoint outside Gmail. 10,000 files means 10,000 sequential HTTPS calls.
3. **Token-heavy replies.** Handlers return human-readable lists. A 100-item list is
   already expensive; 1,000 items cannot fit in context.
4. **No pagination envelope.** Only a couple of call sites consume `nextPageToken`;
   most list tools cap results and return everything inline.
5. **No durable job model.** `pending_operations` is an in-memory dict with an
   8-character id and a 10-minute TTL, used for Apps Script updates. It has no
   progress, no checkpoint, no resume and no result artifact.
6. **No shared engine.** Retry and backoff logic is scattered; there is no rate-limit
   budget, no 429 handling policy, and no per-item error classification.
7. **Safety is per-call, not per-plan.** 21 handlers accept `confirm`, and the server
   has a global dry-run switch, but a bulk change has no plan id, no scope cap, no
   protected-path list and no way to review the exact set before execution.
8. **Profiles depend on annotations.** New write tools must be annotated correctly or
   `read-only` / `read-write` profiles will expose them by mistake.

Measured baseline: moving 110 files one by one took about one minute of wall time,
and the tool output would have been unusable at 10x that scale.

## 3. Design principles

- **Plan, then run.** Every bulk change has an immutable plan: resolved ids, counts,
  sample, risks. Execution requires the plan id and `confirm=true`.
- **One engine, many actions.** Selector resolution, execution, retries, progress and
  artifacts live in one module; actions are small adapters.
- **Fewer, richer tools.** A handful of bulk tools instead of one per action, because
  every tool schema costs tokens in every request.
- **Compact by default.** Responses contain counts, a small sample, and a link to an
  artifact, never the full item list.
- **Reversible first.** Bulk delete means trash; permanent delete and ownership
  transfer are out of scope for bulk.
- **Fail small.** One bad item does not abort the job; failures are classified and
  reported in a paginated artifact.

## 4. Proposed tool surface

Six tools, one namespace, no per-action duplication:

| Tool | Purpose | Read-only |
|---|---|---|
| `bulk_plan` | Resolve a selector, return plan id, counts, sample, warnings | yes |
| `bulk_run` | Execute a reviewed plan, start a background job | no |
| `bulk_status` | Compact progress for one job | yes |
| `bulk_cancel` | Request cancellation | no |
| `bulk_result` | Paginated successes/failures, or artifact pointer | yes |
| `bulk_list` | Recent jobs for this profile | yes |

### `bulk_plan` input

```json
{
  "domain": "drive",
  "action": "move",
  "selector": {
    "query": "mimeType contains 'image/' and name contains 'IMG'",
    "scope": { "folder_id": "FOLDER_ID", "recursive": true },
    "mime_types": ["image/jpeg", "image/png"],
    "modified": { "before": "2025-01-01" },
    "ids": [],
    "exclude_ids": [],
    "limit": 10000,
    "include_trashed": false
  },
  "options": { "target_folder_id": "FOLDER_ID", "create_target": true }
}
```

Response (compact):

```json
{
  "ok": true,
  "plan_id": "bp_7f3c1a2b",
  "domain": "drive",
  "action": "move",
  "matched": 9987,
  "estimated_bytes": 1234567890,
  "sample": [{"id": "...", "name": "IMG_0001.jpg"}],
  "warnings": ["1,204 items already in the target folder"],
  "expires_in_seconds": 900,
  "next": "bulk_run(plan_id, confirm=true)"
}
```

### Actions for the first phase

| Action | Options | Notes |
|---|---|---|
| `drive.move` | `target_folder_id`, `create_target` | stores previous parents for undo |
| `drive.trash` | none | trash only, never permanent |
| `drive.restore` | none | reverses a previous trash job |
| `drive.rename` | `pattern`, `find`, `replace` | pattern supports `{name}`, `{ext}`, `{index}` |

Phase 2 adds `drive.share`, `drive.revoke`, `gmail.archive`, `gmail.label`,
`gmail.trash`, `gmail.mark_read`, and `bulk_undo`.

## 5. Selector DSL

Resolution happens once, server-side, and the ids are snapshotted into the plan.

| Field | Semantics |
|---|---|
| `query` | raw provider query (Drive `q`, Gmail `q`) |
| `scope.folder_id` + `recursive` | subtree restriction; resolved with pagination |
| `mime_types` | prefix or exact match |
| `name.contains` / `name.regex` | server-side filter with a safe regex subset |
| `modified.before` / `after` | ISO dates |
| `size.min` / `max` | bytes |
| `ids` | explicit set, mutually exclusive with `query` |
| `exclude_ids`, `exclude_name_patterns` | deny list applied last |
| `limit` | hard cap, default 1,000, max 10,000 |
| `sample` | number of items returned in the plan (default 5, max 20) |

Rules: `ids` cannot be combined with `query`; destructive actions require a scope
(folder, query or explicit ids) and refuse an unbounded account-wide selector unless
`allow_account_scope=true` is passed together with a confirm phrase.

## 6. Execution engine

- **Snapshot.** Plan stores ids, parents, sizes and the selector hash in
  `data/bulk/<plan_id>.json`, written atomically.
- **Workers.** A pool of 8 (configurable 1–16) performs per-item calls; metadata-only
  Drive updates are grouped through the Drive batch endpoint, 100 calls per request.
- **Rate budget.** Token bucket per user (default 10 requests/second), adaptive
  backoff on `429` / `403 rateLimitExceeded`, jittered exponential retry (max 5).
- **Checkpoint.** Job state is flushed every 50 items to `data/bulk/jobs/<job_id>.json`;
  on restart the engine scans that directory and resumes unfinished jobs.
- **Idempotency.** Each item records its outcome; a re-run skips items already in the
  desired state (same parent, already trashed, already renamed).
- **Failure isolation.** Per-item status codes: `ok`, `skipped`, `failed_retryable`,
  `failed_permanent`; a permanent failure never stops the batch.

## 7. Safety model

1. `bulk_plan` is always a dry run; it changes nothing.
2. `bulk_run` requires `confirm=true` and a non-expired plan id (TTL 15 minutes).
3. Destructive actions (`trash`, `revoke`, `share`) always trash/revoke, never
   permanent-delete, and record enough state for `bulk_undo`.
4. Caps: default 1,000 items; hard maximum 10,000. Above 1,000 the plan must set
   `allow_large=true`; above 10,000 it is refused.
5. Protected ids and folders come from config (`bulk.protected_folder_ids`,
   `bulk.protected_name_patterns`); overlapping items are excluded with a warning.
6. Shared drives are refused unless `allow_shared_drives=true`.
7. The global `dry_run` configuration makes `bulk_run` refuse to start.
8. Audit: one record for the plan (selector hash, counts, sample ids) and one for the
   run (job id, ok/failed/skipped counts, duration). Argument values are never logged.
9. Profiles: write actions carry `readOnlyHint=false`; `trash`/`revoke`/`share` carry
   `destructiveHint=true`, so `read-write` and `read-only` filter them out.

## 8. Token economy

- Six tools instead of ~20 action-specific ones. Tool schemas are sent on every
  request, so this matters more than the code size.
- Plan/status responses are capped at ~2 KB; sample 5 by default.
- `bulk_result` is paginated (50 per page) and can return a JSONL/CSV artifact saved
  to Drive or `data/bulk/`; the model gets a pointer, not 10,000 rows.
- Progress is a delta summary, not a log: `{"state":"running","done":4200,"failed":3}`.
- Existing single-object tools remain for precise, one-off edits.

## 9. Compatibility

- Existing 115 tools are untouched; new tools are additive (121 total).
- No breaking changes to `confirm` / `dry_run` semantics.
- New config block, all optional:

```yaml
bulk:
  max_items: 1000
  hard_limit: 10000
  concurrency: 8
  plan_ttl_seconds: 900
  protected_folder_ids: []
  protected_name_patterns: []
  allow_shared_drives: false
```

## 10. Roadmap

| Phase | Deliverable | Estimate |
|---|---|---|
| 0 | `bulk/` module: selector, plan store, engine skeleton, audit, config | 1 day |
| 1 | Drive move / trash / restore / rename + 6 tools + tests + docs | 2 days |
| 2 | Drive share / revoke, Gmail archive / label / trash / mark read, undo | 2 days |
| 3 | Sheets bulk (rows, formatting, clearing by filter), Docs/Slides batches | 2 days |
| 4 | Benchmarks, artifacts UI, prompts, release notes | 1 day |

Release cadence: 1.19.0 for phases 0–1, 1.20.0 for phase 2, 1.21.0 for phase 3.

## 11. Acceptance criteria

1. 10,000 Drive files: plan under 30 s, run under 10 min at default concurrency
   (quota permitting), job resumable after a kill.
2. Plan response ≤ 2 KB; status ≤ 1 KB; no response contains more than 20 item names.
3. Killing the process mid-run and restarting resumes without duplicate actions.
4. A 30% injected failure rate leaves 70% successful and reports 30% compactly.
5. `read-only` profile exposes none of the bulk write tools.
6. `bulk_run` without `confirm=true` performs zero API writes.
7. Audit contains plan and run records with counts; no argument values.
8. Live test: 1,000 generated files in a temporary folder, moved and trashed, then
   cleaned up.

## 12. Open decisions

1. Unified `bulk_plan`/`bulk_run` vs per-action tools (`drive_bulk_move`, ...).
   Recommendation: unified, for token economy and one engine.
2. Result artifacts in Drive vs local `data/bulk/`. Recommendation: local by default,
   optional Drive upload for remote clients.
3. Whether `bulk_run` should block until completion for small jobs (<100) or always
   return a job id. Recommendation: always a job id, with an optional `wait_seconds`.
4. Default concurrency: 8 vs 16. Recommendation: 8, to stay far from quota limits.
