# Release v1.16.0 — columns, media and integrations

Nine tools that finish the everyday surface: columns and sorting in Sheets, native
tables in Slides, images in Docs, attachments in Gmail, calendar discovery,
ownership transfer, recurrence and Apps Script deployments.

## What is new

| Area | Tools |
|---|---|
| Sheets | `sheet_insert_columns`, `sheet_delete_columns` (confirm), `sheet_sort_range` |
| Slides | `slides_add_table` — native table with size and position in pixels |
| Docs | `docs_insert_image` — inline image from a public URL, points for size |
| Gmail | `gmail_send_with_attachments` — draft by default, 20 MB total cap |
| Calendar | `calendar_list_calendars`; `create_event` accepts `recurrence` (RRULE lines) |
| Drive | `drive_transfer_ownership` (confirm; you lose owner rights) |
| Apps Script | `script_list_deployments` |

## Safety

- deleting columns and transferring ownership join the confirm-gated set;
- attachments are read only from local paths the server process can access, and the
  total size is checked before the message is built;
- `create_event` still defaults to no notifications and UTC, as before.

## Counts

- Tools: **98** (was 89)
- Profiles: `full` 98, `read-write` 81, `read-only` 26
- Unit tests: 275 (5 new)
- Live checks: 51 + 15 + 8 + **8** (`tests/live_phase3.py`)

## Verified live

- inserted and deleted a column, sorted a range by a numeric column;
- inserted a 2×3 table into a slide;
- inserted an inline image into a document;
- listed calendars and created a daily recurring event, then deleted it;
- drafted an email with a real attachment and removed the draft afterwards;
- previewed an ownership transfer without confirming it.

## Notes

- `sheet_sort_range` sorts the given range as a block: exclude the header row from
  the range if the header must stay in place.
- `drive_transfer_ownership` needs the file to be owned by the authenticated account
  and the new owner to have a Google account.
