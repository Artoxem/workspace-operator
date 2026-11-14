# Справочник инструментов

Workspace Operator 2.0 содержит 39 консолидированных инструментов. Инструмент вызывается с `action`; действие проверяется до вызова handler.

## Profiles

| Профиль | Инструментов | Для чего |
|---|---:|---|
| `core` | 20 | повседневный набор по умолчанию |
| `full` | 39 | всё |
| `read-write` | 30 | без destructive |
| `read-only` | 17 | только чтение |

## Tools

| Tool | Safety | Actions | What it does |
|---|---|---|---|
| `workspace_search` | read | — | Search Drive, Gmail and Calendar in one call. |
| `drive_search` | read | — | Search Drive with full query syntax (replaces find_files and drive_search_advanced). |
| `digest` | read | — | Summarise Gmail, Calendar and Drive for the last N hours. |
| `compare_tables` | read | — | Diff two sheet ranges by a key column. |
| `drive_read` | read | `metadata`, `export`, `list_permissions` | Read Drive metadata, permissions and exported files. |
| `drive_write` | write | `create_folder`, `copy`, `move`, `rename`, `upload`, `share`, `restore` | Create, copy, move, rename, upload, share and restore Drive files. |
| `drive_trash` | destructive | — | Move a Drive file to Trash (recoverable 30 days; no permanent delete). |
| `drive_permissions` | destructive | `remove`, `revoke_public` | Remove access from a Drive file. |
| `read_doc` | read | — | Read the contents of a Google Doc. |
| `docs_write` | write | `create`, `append`, `insert_image` | Create and extend Google Docs. |
| `docs_edit` | destructive | `replace`, `format` | Replace or format text in a Google Doc, with a preview. |
| `sheets_read` | read | `meta`, `read`, `export_csv` | Read sheet metadata, values and CSV exports. |
| `sheets_write` | write | `create_spreadsheet`, `add_sheet`, `update`, `append`, `clear`, `find_replace` | Create spreadsheets and write values. |
| `sheets_format` | write | `format`, `borders`, `conditional`, `validation`, `protect` | Format ranges, borders, conditional rules, validation and protection. |
| `sheets_structure` | write | `insert_rows`, `insert_columns`, `merge`, `sort`, `named_range`, `filter_view` | Insert, merge, sort and organise sheet ranges. |
| `sheets_delete` | destructive | `delete_rows`, `delete_columns`, `delete_sheet` | Delete rows, columns or a sheet (requires confirm). |
| `sheets_data` | write | `chart`, `pivot` | Charts and pivot tables. |
| `gmail_read` | read | `profile`, `list`, `read`, `thread`, `attachment`, `search`, `labels`, `filters` | Read Gmail messages, threads, attachments, labels and filters. |
| `gmail_write` | write | `send`, `reply`, `send_with_attachments`, `draft_create`, `draft_update`, `draft_send`, `draft_list`, `archive` | Send, reply, draft and archive Gmail messages. |
| `gmail_settings` | write | `label_create`, `label_apply`, `filter_create` | Manage Gmail labels and filters. |
| `gmail_delete` | destructive | `email`, `draft` | Move messages or drafts to Trash (recoverable). |
| `calendar_read` | read | `events`, `calendars` | Read events and calendars. |
| `calendar_write` | write | `meeting`, `update`, `move`, `respond`, `color` | Create, update, move, answer and colour events. |
| `calendar_delete` | destructive | — | Delete an event (requires confirm). |
| `tasks_read` | read | `lists`, `list` | Read task lists and tasks. |
| `tasks_write` | write | `create`, `complete` | Create and complete tasks. |
| `forms_read` | read | `get`, `responses` | Read forms and responses. |
| `forms_write` | write | `create`, `add_questions` | Create forms and add questions. |
| `postmaster_read` | read | `domains`, `traffic` | Read Postmaster domains and traffic statistics. |
| `script_read` | read | `content`, `deployments` | Read Apps Script content and deployments. |
| `script_write` | write | `create_project`, `prepare`, `execute`, `cancel`, `restore`, `create_deployment`, `update_deployment` | Prepare, execute, restore and deploy Apps Script changes. |
| `script_run` | destructive | — | Run an Apps Script API function (arbitrary code; confirm required). |
| `bulk_plan` | read | — | Resolve a selector into a dry-run bulk plan. |
| `bulk_run` | destructive | — | Execute a reviewed bulk plan as a background job. |
| `bulk_status` | read | — | Read progress for a bulk job. |
| `bulk_result` | read | — | Read one page of bulk job results. |
| `bulk_list` | read | — | List recent bulk jobs. |
| `bulk_cancel` | write | — | Request cancellation of a running bulk job. |
| `bulk_undo` | destructive | — | Undo a completed bulk job (move, rename, trash). |

## Prompts

| Prompt | What it does |
|---|---|
| `summarize_inbox` | Fetch recent Gmail messages and prepare them for AI summarization. Optionally filter by a Gmail search query. |
| `analyze_spreadsheet` | Read a Google Sheet range and prepare the data for AI analysis or visualization. |
| `plan_week` | Fetch upcoming calendar events and prepare a weekly planning summary for AI-assisted scheduling. |
| `search_drive` | Search Google Drive for files and prepare a structured list for AI review or organisation suggestions. |
| `weekly_review` | Cross-source review of the last N days: mail, changed files and the coming agenda, prepared for a weekly summary. |
| `inbox_triage` | Fetch a Gmail slice and prepare it for triage: urgent, waiting, informational, archive candidates. |
| `compare_brief` | Diff two ranges by a key column and prepare a reconciliation report. |
