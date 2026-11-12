# Workspace Operator 1.21.0

Undo for bulk jobs, plus text replacement across Docs, Slides and Sheets.
122 tools.

## Undo

`bulk_undo(job_id, confirm=true)` reverts a finished bulk job from the state
saved in its results:

| Job | Undo |
|---|---|
| `move` | restores every file's previous parents |
| `rename` | restores every file's previous name |
| `trash` | restores files from the trash |

The inverse runs as a normal background job: progress, cancellation, results and
audit work exactly like `bulk_run`. Jobs created before this release have no
saved previous state and are refused with a clear message.

## Docs, Slides and Sheets

`bulk_plan` gained three domains. Each selects Drive files by the matching MIME
type, then applies one text operation to every file:

| Domain | Action | API |
|---|---|---|
| `docs` | `replace_text` | `documents.batchUpdate` → `replaceAllText` |
| `slides` | `replace_text` | `presentations.batchUpdate` → `replaceAllText` |
| `sheets` | `find_replace` | `spreadsheets.batchUpdate` → `findReplace` |

Options: `find` (required), `replace`, `match_case`; for Sheets also `sheet_id`
(omit to cover all sheets). The selector supports the usual `query`, `folder_id`,
`recursive`, `ids`, `exclude_ids`, `limit`.

Example: replace `{{CLIENT}}` with a name across every document in a folder.

## Safety

- `bulk_undo` requires `confirm=true`; the global `dry_run` blocks it.
- Text replacement only touches the selected file type (`mimeType` is forced by
  the domain), so a `docs` plan can never edit a spreadsheet by accident.
- Undo of move/rename relies on data written by 1.20.1+ jobs.
- Caps, protected ids and audit are unchanged.

## Compatibility

- 122 tools (`bulk_undo` added; six existing bulk tools gained capabilities).
- Profiles: `full` 122, `read-write` 103, `read-only` 33.
- No new OAuth scopes.

## Tests

- 319 unit tests.
- Live smoke: move → undo, rename → undo (parents and names restored).
- Live smoke: Doc replace, Sheet find/replace (all sheets), Slides replace.
- Protocol smoke over stdio: tool catalog and schemas.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.21.0
# or
docker compose pull && docker compose up -d
```

Reconnect MCP clients so the new domain/action enums are visible.

## Deferred

- Drive batch endpoint (concurrency already handles typical volumes).
- Gmail permanent delete (needs the full-mailbox scope).
- Public release: PyPI, GHCR, GitHub release notes — intentionally postponed.
