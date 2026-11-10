# Release v1.17.0 — pivots, styling and integrations

The last batch of the "full arsenal" run: pivot tables, text styling in Docs,
draft management, layout discovery, calendar moves, deployment creation and Drive
shortcuts.

## New tools (8)

| Area | Tool |
|---|---|
| Sheets | `sheet_add_pivot_table` — rows, columns and values as 1-based offsets; SUM/COUNT/AVERAGE/MIN/MAX |
| Docs | `docs_format_text` — bold, italic, font size and heading styles for every match, with a preview |
| Gmail | `gmail_list_drafts`, `gmail_delete_draft` (confirm) |
| Calendar | `calendar_move_event` — move between calendars |
| Slides | `slides_list_layouts` — layout names with object IDs |
| Apps Script | `script_create_deployment` — deploy a saved version (latest by default) |
| Drive | `drive_create_shortcut` |

## Safety

- `docs_format_text` and `gmail_delete_draft` joined the confirm-gated set;
- the Docs styling handler previews the match count and refuses to run without
  `confirm=true`;
- deleting a draft never sends it.

## Counts

- Tools: **106**
- Profiles: `full` 106, `read-write` 87, `read-only` 28
- Unit tests: 279
- Live checks: 51 + 15 + 8 + 8 + **5**

## Verified live

- built a pivot table on a new sheet from a four-row source;
- previewed and applied bold styling to two matches in a document;
- listed 11 layouts of a new presentation;
- created a draft, found it in the list and deleted it;
- created a Drive shortcut and cleaned it up.

## Notes

- pivot `rows`, `columns` and `values` are positions inside the source range, not
  absolute sheet columns;
- `script_create_deployment` needs at least one saved version — create it in the
  Apps Script editor first, or pass `version_number`.
