# Release v1.7.0 — universal composite tools

Four tools that each replace a multi-step routine, built so that nothing about the
owner's data is assumed. Every one of them has a `output="text"` mode: you can get
the result without creating a file.

## What changed

### `report_from_sheet` is now configurable

| Parameter | Default | Why |
|---|---|---|
| `header` | `true` | set `false` when the first row is data |
| `decimal` | `auto` | `comma` / `dot` for ambiguous numbers |
| `columns` | all | subset by name or 1-based index |
| `aggregates` | `sum, avg, min, max` | add `median`, `count` |
| `output` | `doc` | `text` returns the report without creating a document |

### New: `digest`

One summary of the last N hours across any subset of `gmail, calendar, drive`.
Text by default, Google Doc on request. Partial failures are reported inline.

### New: `compare_tables`

Diff two ranges by a key column (name or index), optionally across different
spreadsheets. Returns added / removed / changed rows with before→after values;
`output="doc"` writes it to a document. Works on any two tables — price lists,
catalogues, exports before and after a change.

### New: `clone_and_fill`

Copies any Drive file and replaces placeholders **in the copy**:

* Docs → `replaceAllText`;
* Slides → `replaceAllText`;
* Sheets → `findReplace` across all sheets;
* anything else → the copy is made and the tool says placeholders were not filled.

`name` and `folder_id` control where the copy lands.

## Why this is «universal» and not «for one workspace»

- every tool takes IDs, ranges and column names — no hard-coded files or schemas;
- heuristics are explicit parameters, not hidden assumptions;
- text mode means the tool can be used safely just to look, with no artifacts;
- the pure cores (`to_number`, `summarise_columns`, `diff_tables`, `render_digest`,
  `replacement_requests`) are unit-tested independently of Google.

## Counts

- Tools: **66** (composite: 4)
- Profiles: `full` 66, `read-write` 58, `read-only` 21
- Unit tests: 168 · live checks: 45

## Verified live

- `compare_tables` on two real spreadsheets: `added: 1 | removed: 1 | changed: 1`;
- `report_from_sheet(output="text", columns=["Price"])` — 463 chars, no document;
- `digest` over the real mailbox (last 7 days);
- `clone_and_fill` on a real Doc: the copy contained `ACME` and no `{{CLIENT}}`.

## Known limits

- `compare_tables` matches columns by header name only — rename detection is out of scope.
- `clone_and_fill` does not replace inside Slides notes or Sheets formulas that are
  stored as formulas (use `sheet_find_replace` for a targeted pass).
- `digest` uses the account's primary calendar only.
