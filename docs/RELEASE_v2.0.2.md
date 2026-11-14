# Workspace Operator 2.0.2

Code cleanup release. No new tools and no new OAuth scopes.

## Removed dead code

- Deleted `handlers/slides.py`, `handlers/comments.py`, `handlers/deck.py`,
  `handlers/report.py`, `handlers/template.py`.
- Removed their imports, exports, tool definitions and dispatch branches.
- Removed obsolete handler functions: `find_files`, `drive_download`,
  `create_event`, `calendar_find_free_slots`, `doc_export_pdf`,
  `doc_fill_template`, `drive_empty_trash`, `drive_transfer_ownership`,
  `drive_create_shortcut`, `batch_delete_emails`.
- Removed Slides conversion/export from `drive_upload`/`drive_export`.
- Removed the remaining Slides domain handling from the bulk engine.
- Removed `sheet_brief` prompt because it depended on the removed report handler;
  prompt count is now 7.
- Removed stale 1.x live scripts from `tests/`; the executable suite is the
  290-test unit/in-memory suite.

## Preserved

- 39 consolidated tools; `core` = 20, `read-only` = 17, `read-write` = 30,
  `full` = 39.
- Hidden 1.x aliases from 2.0.1.
- Scope routing, profile endpoints, no permanent Drive deletion, public sharing
  disabled by default.
- Removed capabilities return the migration error instead of an `unknown tool`.

## Verification

- 290 tests, all green.
- CLI catalog: `core` 20, `full` 39.
- Live read/write check on a synthetic Google Doc; removed after the test.
- HTTP endpoints `/mcp`, `/mcp/read`, `/mcp/read-write`, `/mcp/full`.

