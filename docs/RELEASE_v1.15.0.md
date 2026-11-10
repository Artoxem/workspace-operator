# Release v1.15.0 — MCP 2026-07-28 and structural editing

Two things landed together: the server moved to the current MCP protocol, and the
missing structural operations appeared.

## Protocol: 2025-06-18 → 2026-07-28

The server now runs on **MCP Python SDK 2.3.0**, which speaks the
[2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28/).

What changed under the hood:

- the low-level `Server` no longer has `@server.list_tools()` decorators — handlers
  are registered with `add_request_handler(method, params_type, handler)` and return
  typed results (`ListToolsResult`, `CallToolResult`, `ReadResourceResult`, …);
- annotation fields are `snake_case` in 2.x (`read_only_hint`, `destructive_hint`);
  `profiles.py` reads both spellings, so the tool profiles keep working;
- `requirements.txt` and `pyproject.toml` now pin `mcp>=2.3.0,<3`;
- the stdio and HTTP transports were re-verified against real Google APIs.

The stateless Streamable HTTP design the server already had matches the 2026-07-28
direction, so no transport rewrites were needed.

## Structural tools (9)

**Sheets**

- `sheet_delete_sheet` — delete a tab after a preview; the last sheet is protected.
- `sheet_insert_rows`, `sheet_delete_rows` — 1-based rows; deletion requires
  `confirm=true`.
- `sheet_merge_cells` — `MERGE_ALL`, `MERGE_ROWS`, `MERGE_COLUMNS`, `UNMERGE`.

**Slides**

- `slides_move_slide` — reorder and report the resulting order.
- `slides_set_notes` — replace speaker notes.

**Gmail**

- `gmail_list_labels` — user and system labels with IDs.
- `gmail_create_label` — create a label.

**Drive**

- `drive_empty_trash` — the only irreversible operation in the server; requires
  `confirm=true` and previews what is in the trash.

## Counts

- Tools: **89** (was 80)
- Profiles: `full` 89, `read-write` 74, `read-only` 24
- Unit tests: 270 (4 new)
- Live checks: 51 + 15 + **8** (`tests/live_phase2.py`)

## Bugs found by the live run

- speaker notes live at `slides[].slideProperties.notesPage`, not
  `slides[].notesPage` — the fields mask was rejected until fixed;
- `deleteText` with `ALL` fails on an empty notes shape (startIndex 0 == endIndex 0),
  so the handler deletes only when text exists and otherwise just inserts.

Both are covered by the phase-2 live suite.
