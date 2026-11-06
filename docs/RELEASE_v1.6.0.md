# Release v1.6.0 — calendar lifecycle and the first composite tool

Two things an agent needs to finish a job: change a calendar entry it created
earlier, and turn a spreadsheet into a report in one call.

## Calendar: update, delete, respond

| Tool | Behaviour |
|---|---|
| `calendar_update_event` | Patch semantics: only the fields you pass are changed (`summary`, times, description, location, attendees). `send_updates` = `all / externalOnly / none` |
| `calendar_delete_event` | Deletes an event, `confirm=true` required |
| `calendar_respond_to_invite` | `accepted / declined / tentative`, `confirm=true` required; finds you in the guest list by the calendar owner address and reports clearly when you are not invited |

`create_event` and `calendar_create_meeting` now return the event **ID**, not just
the link. Without it the new tools were unusable in sequence — the live smoke test
found this immediately, since it creates an event and then updates and deletes it.

## Composite: `report_from_sheet`

```json
{"spreadsheet_id": "1AbC…", "range": "A1:C200", "doc_title": "March sales"}
```

One call: read the range → compute per-column statistics → create a Google Doc
with the summary table and a fixed-width data preview.

* numeric columns get `sum / avg / min / max` (parses `4 882,50`, `€`, `%`);
* text columns get non-empty and unique counts;
* the preview is capped (`max_rows`, default 25) with a "... N more rows" note;
* the response contains the document ID and URL.

The analysis and rendering are pure functions (`to_number`, `summarise_columns`,
`render_table`, `render_report`), so the whole report format is unit-tested
without touching Google.

## Counts

- Tools: **63** — Drive 8, files 3, Sheets 12, Docs 5, Slides 5, Apps Script 7,
  Gmail 14, Calendar 7, cross-search 1, composite 1
- Profiles: `full` 63, `read-write` 55, `read-only` 21
- Unit tests: 142 · live checks: 40

## Verification

The live suite now creates a spreadsheet with sample data, builds a report from it
and trashes both; creates a calendar event, renames it, tries to answer its own
invitation (expects a clear "not on the guest list") and deletes it.

## Known limits

- `report_from_sheet` renders the data as aligned text, not as a native Docs table.
  A native table needs cell-by-cell index bookkeeping; candidate for 1.7.
- `calendar_respond_to_invite` works for events where your address is on the guest
  list; events you created yourself have no guest entry.
- `report_from_sheet` scans up to 2 000 rows for statistics.

## Docs

README (EN/RU), TOOLS_REFERENCE, SECURITY and the Antigravity guide were updated;
`tests/test_docs.py` enforces that every one of the 63 tools is documented.
