# Release v1.10.0 — native tables in Google Docs

Reports and diffs stop looking like aligned plain text. Google Docs now gets
**real tables**: header row in bold, bordered cells, selectable columns.

## What changed

### `report_from_sheet` (default `output="doc"`)

The document is built from blocks: title and metadata, a **summary table**
(column, type, non-empty, unique + the requested aggregates) and a **data table**
(header + preview rows). `output="text"` is unchanged and still creates nothing.

### `compare_tables` (`output="doc"`)

The diff document contains three native tables: Added, Removed and Changed
(`Key | Column | Before | After`).

### How it works

The Docs API has no «insert table with data» call, so the builder is a two-phase
process (`workspace_operator/handlers/doc_tables.py`):

1. insert every block top-down — text via `insertText` at the end of the body,
   tables via `insertTable` into the trailing **empty paragraph**, which splits it
   and leaves a paragraph after the table so the next block can be appended;
2. re-read the document, compute every cell's `startIndex`, fill cells in
   descending index order (so earlier indices never shift), then re-read again and
   bold the first row.

Both phases are covered by pure helpers — `normalise_rows`, `cell_layout`,
`fill_requests`, `header_style_requests` — with 12 unit tests that use a synthetic
document structure.

### Failure handling

If a table's batch fill is rejected (index edge cases happen), the builder falls
back to one request per cell and logs what was skipped, so a document is always
produced instead of failing the whole call.

## Bug found while building this

The first implementation appended the table at the end of the body and then tried
to insert a newline «after» it. That newline landed **inside the last table cell**,
corrupting the structure and making later cell inserts fail with
`The insertion index must be inside the bounds of an existing paragraph`.
The fix was to insert the table into the trailing empty paragraph and let the API
split it.

## Verified live

The smoke suite now asserts that `report_from_sheet` produces a document whose
`read_doc` rendering contains both `Summary` and the table header (`| SKU |`),
then trashes it. 47/47 checks pass.

## Counts

- Tools: 66 (unchanged)
- Unit tests: 220 (12 new)
- Live checks: 47
