# Release v1.4.0 — sheet formatting

First block of the 1.4 roadmap: Sheets is no longer read-only in spirit — an agent
can now make a spreadsheet look like a report.

## `sheet_format`

One tool, one `spreadsheets.batchUpdate`, all the formatting an agent typically
needs:

| Argument | Effect |
|---|---|
| `range` | `A1:C10`, `A:C`, `1:10` or empty for the whole sheet |
| `bold`, `italic`, `font_size` | text format |
| `number_format` | Sheets pattern, e.g. `#,##0.00`, `0.0%`, `dd.mm.yyyy` |
| `background_color`, `text_color` | `#RRGGBB` |
| `horizontal_alignment` | `LEFT`, `CENTER`, `RIGHT` |
| `wrap` | `OVERFLOW_CELL`, `CLIP`, `WRAP` |
| `column_width`, `row_height` | pixels |
| `freeze_rows`, `freeze_cols` | frozen panes |

Example:

```json
{
  "spreadsheet_id": "1AbC…",
  "range": "A1:C10",
  "bold": true,
  "background_color": "#FFF2CC",
  "number_format": "#,##0.00",
  "column_width": 140,
  "freeze_rows": 1
}
```

Request building is pure and unit-tested (`build_cell_format`, `build_requests`,
`parse_a1_range`, `hex_to_color`), so range parsing and colour conversion have no
network in the loop.

## Bug found while verifying live

The first live run failed with `Unknown name "startRow" at
'requests[0].repeat_cell.range'` — the builder emitted internal names instead of
the API's `startRowIndex` / `endRowIndex` / `startColumnIndex` / `endColumnIndex`.
Unit tests could not catch it because they asserted the same wrong shape; the
end-to-end check on a real spreadsheet did. Fixed in `_grid_range()`, tests
updated to the API contract.

## Counts

- Tools: **56**
- Profiles: `full` 56, `read-write` 49, `read-only` 19
- Sheets: 12 tools

## Tests

- 86 unit tests.
- 32 live end-to-end checks — `sheet_format` now runs against a freshly created
  spreadsheet (bold + background + number format + width + freeze), which is then
  trashed.

## Next

Gmail attachments and threads, Calendar CRUD (update/delete/respond to invites),
then composite tools such as `report_from_sheet`.
