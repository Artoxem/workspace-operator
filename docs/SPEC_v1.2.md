# Technical spec — v1.2 «Files, automation, presentations»

Status: implemented (v1.2.0)
Owner: Artoxem
Scope: 9 new tools, 1 new service (Slides), local file I/O, Apps Script execution

## Goals

Close the three gaps that block real work rather than reading:

1. **Local ↔ Drive** — the server can search files but cannot move them in or out.
2. **Code as a tool** — run an existing Apps Script function on demand instead of
   rewriting automation as new MCP tools.
3. **Slides** — presentations are the last first-class Workspace surface with no
   coverage at all.

Non-goals: Sheets formatting, Gmail attachments, Calendar CRUD, webhooks. Those
are candidates for 1.3.

## Design rules

- Every tool works against **any** account/project; nothing depends on a specific
  workspace, file name or script.
- Local paths are resolved and expanded (`~`, relative), never invented silently:
  a tool reports the absolute path it used.
- Downloads never overwrite an existing file unless `overwrite=true`.
- Anything that runs code or rewrites content is `destructiveHint` (confirm-gated
  or explicitly flagged), so `read-only` / `read-write` profiles behave predictably.
- Errors follow the existing convention: `Error ...` string, humanised by
  `text.humanize_http_error`, surfaced as `isError: true`.

## Tools

### Drive files (3)

| Tool | Annotations | Arguments | Returns |
|---|---|---|---|
| `drive_upload` | write | `local_path` (req), `name?`, `parent_id?`, `mime_type?`, `convert_to?` | `Uploaded <name> (ID: …) [mime] · <link> · <size>` |
| `drive_download` | read | `file_id` (req), `save_to?`, `overwrite?` (false) | `Saved <path> (<size>)` |
| `drive_export` | read | `file_id` (req), `format` (req), `save_to?`, `overwrite?` (false) | `Exported <name> as <format> → <path> (<size>)` |

Details:

- `drive_upload`: accepts any local file ≤ 100 MB (Drive simple upload limit is
  larger, but memory-bound streaming is out of scope). `convert_to` ∈
  `google-docs | google-sheets | google-slides` converts on upload — the standard
  way to turn `.docx/.xlsx/.pptx` into native Docs/Sheets/Slides.
- `drive_download`: for binary files uses `files.get(alt=media)`. For Google-native
  files requires `format` — if omitted, the tool fails with a message that lists
  the valid formats for that MIME type (never guesses).
- `drive_export`: native files only; `format` ∈ `pdf, docx, xlsx, pptx, csv, txt,
  md, html, epub, rtf, zip`. Binary files should use `drive_download`.
- `save_to`: file path or directory. Default directory: `~/Downloads`.
- Overwrite policy: if the target exists and `overwrite` is false → error listing
  the path, so the caller decides.

### Apps Script (1)

| Tool | Annotations | Arguments | Returns |
|---|---|---|---|
| `script_run_function` | destructive | `script_id` (req), `function_name` (req), `parameters?` (list), `dev_mode?` (true) | execution result, or the Apps Script error with stack trace |

Details:

- Uses `scripts.run`. Requires the script to be deployed as an **API executable**
  (or the caller to own it and `dev_mode=true`).
- `dev_mode=true` runs the latest saved code, not the deployed version.
- Result formatting: if `response.result` is present → JSON dump (truncated at
  4 000 chars); if `response.error` → `Error: <message>` + stack entries.
- Explicitly documented as running arbitrary code with the user's authority —
  this is why it is `destructiveHint` and hidden by the `read-write` profile.

### Slides (5)

| Tool | Annotations | Arguments | Returns |
|---|---|---|---|
| `slides_create` | write | `title` (req) | `Presentation created (ID: …) · <url>` |
| `slides_get` | read | `presentation_id` (req) | title, slide count, per-slide index + text summary |
| `slides_add_slide` | write | `presentation_id` (req), `layout?` (TITLE_AND_BODY), `insertion_index?` | `Slide added at index N (ID: …)` |
| `slides_replace_text` | destructive | `presentation_id`, `replacements` (dict), `confirm?` (false) | preview, then `N replacements applied` |
| `slides_insert_image` | write | `presentation_id`, `slide_id`, `image_url`, `width?`, `height?`, `left?`, `top?` | `Image inserted (ID: …)` |

Details:

- `slides_get` extracts text per slide from `pageElements[].shape.text`, so the
  agent can see what a deck contains without images.
- `slides_replace_text` mirrors `doc_fill_template`: without `confirm` it returns
  the list of keys and the slide count it will touch.
- `slides_insert_image` fetches the URL server-side, so the URL must be publicly
  reachable (Drive links need `?export=download` on a public file). Documented.

## Scopes

Add to `DEFAULT_SCOPES` and `config.example.yaml`:

```
https://www.googleapis.com/auth/presentations
```

Drive file I/O and Apps Script execution are covered by the existing `drive` and
`script.projects` scopes. Users must re-run OAuth after upgrading.

## Tests

Unit (no network):

- path resolution: `~` expansion, directory vs file target, overwrite guard;
- format validation per MIME type, including the "native file without format" error;
- Slides request builders (add-slide layout, insert-image size/position);
- result formatting for `script_run_function` (result vs error response).

Live (`tests/live_smoke.py`, self-cleaning):

- upload a temp text file → download it back → compare bytes → trash the file;
- create a presentation → read it back → add a slide → replace text → trash;
- `script_run_function` error path with a non-existent script id.

## Acceptance

- `tools/list` → 55 tools; `read-only` profile excludes all new write/destructive
  tools; `read-write` keeps upload/download/export and slides writes but hides
  `script_run_function` and `slides_replace_text`.
- Unit suite green, live smoke green against a real account.
- README + TOOLS_REFERENCE (EN/RU) updated, release notes written.
