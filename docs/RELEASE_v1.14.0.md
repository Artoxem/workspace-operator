# Release v1.14.0 — full arsenal, part one

Thirteen tools close the biggest gaps: Drive metadata and cleanup, comments on
Docs/Sheets/Slides, find & replace inside a document, conditional formatting,
charts, and slide deletion.

## Drive

| Tool | What it does |
|---|---|
| `drive_get_metadata` | size, owner, parents, timestamps, sharing state, link |
| `drive_rename_file` | rename in place |
| `drive_delete_file` | move to trash (`confirm=true`, recoverable for 30 days) |
| `drive_restore_file` | bring a file back from the trash |
| `drive_remove_permission` | revoke one permission (`confirm=true`) |

Permanent deletion stays out on purpose: trash is reversible, and the API's
`files.delete` is one accidental call away from data loss.

## Comments (Drive API, works for Docs, Sheets and Slides)

`drive_list_comments` shows threads, authors, quotes and replies;
`drive_create_comment` starts a thread (optionally quoting text);
`drive_reply_comment` answers in it; `drive_resolve_comment` marks it resolved
after confirmation.

## Docs

`doc_replace_text` replaces every match and reports the count. Without
`confirm=true` it returns a preview with the occurrence count and the first
excerpt, so a mass replacement is never silent.

## Sheets

- `sheet_conditional_format` — one colour rule per call: text contains / equals,
  number greater / less / between, is empty. Short aliases (`contains`,
  `greater`, `blank`) are accepted.
- `sheet_add_chart` — COLUMN, BAR, LINE, AREA, SCATTER, COMBO, STEPPED_AREA or
  PIE; the first column becomes the domain, the rest become series.

## Slides

`slides_delete_slide` previews which slide (index and text) would disappear and
requires `confirm=true`.

## Counts

- Tools: **80** (was 67)
- Profiles: `full` 80, `read-write` 68, `read-only` 23
- Unit tests: 266 (15 new)
- Live checks: 51 + **15** in `tests/live_new_tools.py`

## Bugs found by the live run

- charts failed with `400 Invalid value … target_axis "LEFT"` — the enum is
  `LEFT_AXIS`;
- resolving a comment failed because `comments.update` replaces the resource and
  needs `content`; the handler now re-sends the original text.

Both are fixed and covered by the live suite.
