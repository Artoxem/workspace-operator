# Release v1.18.0 — validation, filters and shapes

The final batch of the run: spreadsheet guardrails, Gmail filters and draft edits,
slide shapes, event colours and deployment updates.

## New tools (9)

| Area | Tool |
|---|---|
| Sheets | `sheet_set_data_validation` (list or number range), `sheet_protect_range`, `sheet_set_borders` |
| Gmail | `gmail_list_filters`, `gmail_create_filter`, `gmail_update_draft` |
| Slides | `slides_add_shape` — rectangle, rounded rectangle, ellipse, triangle or text box |
| Calendar | `calendar_set_event_color` — colour ids 1–11 |
| Apps Script | `script_update_deployment` — repoint a deployment at a newer version |

## New scope

Gmail filters need `https://www.googleapis.com/auth/gmail.settings.basic`; it is now
part of the default scopes. Existing tokens must be refreshed once: delete
`token.json` and re-authorize. Without it, the filter tools return a clear 403.

## Counts

- Tools: **115**
- Profiles: `full` 115, `read-write` 96, `read-only` 29
- Unit tests: 284
- Live checks: 51 + 15 + 8 + 8 + 5 + **7**

## Verified live

- list validation on a column and a protected header row;
- borders on a range;
- filter listing (creation skipped until the token is re-authorized with the new scope);
- draft created, rewritten through `gmail_update_draft` and deleted;
- rounded rectangle with text on a slide;
- event created, coloured and deleted.

## Notes

- `sheet_protect_range` defaults to warning-only; pass `warning_only=false` to lock;
- `sheet_set_data_validation` accepts either `values` or `minimum`+`maximum`;
- `slides_add_shape` positions are pixels, sizes are converted to EMU.
