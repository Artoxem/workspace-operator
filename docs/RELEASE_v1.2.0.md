# Release v1.2.0 — files, automation, presentations

Three capabilities that turn the server from «read my Workspace» into «do the work».

## Highlights

### 💾 Local ↔ Drive

| Tool | What it does |
|---|---|
| `drive_upload` | Uploads a local file (100 MB limit); `convert_to` turns docx/xlsx/pptx into native Docs, Sheets or Slides |
| `drive_download` | Downloads a binary file to `~/Downloads` or an explicit path, with an overwrite guard |
| `drive_export` | Exports a Doc/Sheet/Slide to `pdf`, `docx`, `xlsx`, `pptx`, `csv`, `txt`, `md` and more, validating the format against the file type |

### ⚙️ `script_run_function`

Runs a function from an Apps Script project deployed as an API executable:
`script_id`, `function_name`, positional `parameters`, `dev_mode`.
Returns the JSON result, or the Apps Script error with its stack trace.

This is the cheapest way to expose existing automation to an agent: one tool
instead of one MCP tool per script.

Requires an **API executable** deployment; mark it `destructiveHint` because it
runs arbitrary code with your authority.

### 🖼 Slides (5 tools)

`slides_create`, `slides_get`, `slides_add_slide`, `slides_replace_text`,
`slides_insert_image`. Layouts, placeholder replacement with a confirm-gated
preview and occurrence counts, and images positioned in pixels.

## Compatibility & upgrade

- **New OAuth scope**: `https://www.googleapis.com/auth/presentations`.
  Re-run the OAuth flow once after upgrading; existing tokens will otherwise fail
  on Slides calls.
- **Slides API** must be enabled in the Cloud project
  (`slides.googleapis.com`). Without it, `slides_*` tools return a clear 403 with
  the console link.
- Tool count: 55. Profiles: `full` 55, `read-write` 48, `read-only` 19.

## Safety

- `script_run_function` and `slides_replace_text` are `destructiveHint`, so they
  are hidden by the `read-write` profile.
- Downloads and exports never overwrite a file unless `overwrite=true`.
- Uploads are capped at 100 MB per file.

## Tests

- 66 unit tests (`python -m unittest discover -s tests -v`).
- `tests/live_smoke.py` — 23 end-to-end checks, self-cleaning: uploads a temp
  file, downloads it back and compares bytes, creates a deck, exports it to PDF,
  trashes both artifacts.

## Known limitations

- `slides_insert_image` fetches the URL server-side, so the image must be
  publicly reachable (a private Drive link will fail).
- `script_run_function` requires an API-executable deployment owned or shared with
  the account.
- No Sheets formatting or Gmail attachments yet — candidates for 1.3.
