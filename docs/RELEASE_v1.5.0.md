# Release v1.5.0 — Gmail threads, attachments and replies

Gmail stopped being a list of isolated messages.

## New tools

| Tool | Purpose |
|---|---|
| `gmail_get_thread` | Whole conversation: every message with date, sender, labels, attachment names and an optional body preview |
| `gmail_get_attachment` | Save an attachment to disk (`filename` or `attachment_id`; with a single attachment neither is required) |
| `gmail_reply` | Reply **inside the thread** with proper `In-Reply-To` / `References` headers; creates a draft by default |

### Why replies matter

`send_email` can already write to someone, but a reply that is not threaded looks
like a new conversation in every mail client. `gmail_reply` reads the original
headers, builds `In-Reply-To` and `References`, reuses the subject with a `Re:`
prefix and sends with the original `threadId` — so the answer lands where it
belongs.

Recipients are computed by a pure helper: sender only by default, sender + To + Cc
with `reply_all=true`, yourself removed and duplicates collapsed.

### Attachments

Selection is forgiving: exact name, case-insensitive, substring, or automatic when
the message has exactly one attachment. When nothing matches, the error lists what
is available instead of failing blind.

Files go through the same `resolve_target` / overwrite-guard logic as
`drive_download`, so `save_to` behaves identically across Drive and Gmail.

## Counts

- Tools: **59** (Gmail: 14)
- Profiles: `full` 59, `read-write` 52, `read-only` 21
- Unit tests: 103
- Live checks: 35 (thread read, reply draft created and deleted, attachment downloaded and removed)

## Safety

- `gmail_reply` drafts by default; sending requires `draft_mode=false`.
- Attachments are never overwritten without `overwrite=true`.
- Nothing is marked destructive: replies and downloads are reversible or read-only.

## Next

Calendar CRUD (update/delete/respond to invites), then composite tools such as
`report_from_sheet`.
