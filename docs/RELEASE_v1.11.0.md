# Release v1.11.0 — table → presentation, and a universality guard

## `sheet_to_slides`

A fifth composite tool, built the same way as the others: identifiers and ranges
in, a Google artifact out, no assumptions about the data.

```json
{"spreadsheet_id": "1AbC…", "range": "A1:D50", "title": "Weekly numbers", "rows_per_slide": 6}
```

* the first row becomes the header (disable with `header=false`);
* every data row becomes one bullet line — `Header: value · Header2: value2`,
  empty cells skipped, long lines truncated;
* rows are grouped into slides (`rows_per_slide`, default 8, max 20);
* the deck starts with a generated title slide and the **default empty slide is
  deleted**, so the presentation starts where the content starts;
* returns the deck ID, URL and the real slide count.

Rendering is done with text boxes created and filled inside a single
`batchUpdate` per slide (client-assigned object IDs make the references valid
within the batch), then styled: 40 pt bold title, 26 pt section titles, 14 pt body.

## Universality is now enforced by a test

The project must not assume one account's data. `tests/test_docs.py` gained a
check that scans every source, doc and config for account-specific terms
(company names, product names, personal domains). Historical release notes are
excluded on purpose — they describe the past.

Along the way two leftovers were removed:

* test fixtures used real product names — replaced with neutral `Widget A/B/C`;
* a module docstring mentioned dealers — reworded to «catalogues, inventories».

The README now states the rule explicitly: every tool takes identifiers and
ranges, all examples use synthetic data.

## Bug found while verifying

The first version reported `slides = chunks + 1` while the deck actually had
`chunks + 2` slides: a fresh presentation ships with one empty slide that was
never removed. The live check caught the mismatch (`Slides: 4` instead of `3`);
the handler now deletes the default slide in the same batch that creates the
title slide.

## Counts

- Tools: **67** (composite: 5)
- Profiles: `full` 67, `read-write` 59, `read-only` 21
- Unit tests: 234 (14 new for chunking, formatting and slide requests)
- Live checks: 49

## Verified live

`sheet_to_slides` on a synthetic 3-row sheet with `rows_per_slide=2` produced a
deck with exactly 3 slides (title + 2), `slides_get` confirmed the count, and both
the deck and the source spreadsheet were trashed afterwards.
