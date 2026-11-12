# Workspace Operator 1.20.0

Phase 2 of bulk operations: Gmail actions and Drive sharing. 121 tools,
311 unit tests.

## Gmail bulk actions

`bulk_plan` now accepts `domain: "gmail"`. Selector fields:

- `query` — any Gmail search string (`subject:`, `from:`, `has:attachment`, …);
- `ids` — explicit message ids (cannot be combined with `query`);
- `include_spam_trash` — search Spam and Trash as well;
- `limit`, `exclude_ids`.

Actions:

| Action | Effect |
|---|---|
| `archive` | remove `INBOX` |
| `label` | add and/or remove labels (`add_labels`, `remove_labels`, names or ids) |
| `trash` | add `TRASH` (reversible) |
| `restore` | remove `TRASH` |
| `mark_read` | remove `UNREAD` |
| `mark_unread` | add `UNREAD` |

Execution uses `messages.batchModify` with up to **1,000 messages per request**,
so 10,000 messages are ten API calls rather than ten thousand. Permanent deletion
is intentionally out of scope: bulk Gmail only moves to Trash.

`bulk_plan` returns the first five messages with subject, sender and date, so the
plan can be reviewed without downloading the mailbox.

## Drive sharing

Two new actions in the Drive domain:

- `share` — `role` (`reader`/`commenter`/`writer`), `type`
  (`user`/`group`/`domain`/`anyone`), `email_address`, `domain`,
  `send_notification`. Sharing with `anyone` requires `allow_public=true`.
- `revoke_public` — remove every `type: "anyone"` permission from each selected
  file.

Both go through the same plan → confirm → run flow, and are sized by the same caps.

## Safety

- Gmail `trash` and Drive `trash` remain reversible; no permanent deletion.
- Public sharing is a two-key operation: `type=anyone` plus `allow_public=true`,
  inside a reviewed plan.
- Label names are resolved once at plan time; unknown labels fail the plan.
- Protected ids/patterns still apply to Drive selectors.
- Audit records the plan and the run with counts only.

## Compatibility

- Still 121 tools; only the existing `bulk_*` tools gained capabilities.
- Profiles unchanged: `full` 121, `read-write` 102, `read-only` 33.
- No new OAuth scopes.
- Version: `1.20.0`.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.20.0
# or
docker compose pull && docker compose up -d
```

Reconnect MCP clients so the updated `bulk_plan` schema is visible.

## Tests

- 311 unit tests.
- Live Gmail smoke: 3 messages, label → archive → mark unread/read → trash →
  restore, all verified.
- Live Drive smoke: make a file public, `revoke_public`, verify no `anyone`
  permission remains.
- Protocol smoke: 121 tools, plan, confirmation gate, job listing.

## Deferred

- Undo for move/rename jobs (trash already has `restore`).
- Batch endpoint optimisation for Drive (concurrency already handles the volume).
- Gmail permanent delete (requires the full-mailbox scope; intentionally avoided).
