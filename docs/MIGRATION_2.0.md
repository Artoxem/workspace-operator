# Migrating from 1.x to 2.0

2.0 replaces 132 single-purpose tools with 39 consolidated tools. Most tools now
take an `action`. The default profile is `core` (20 tools), not `full`.

## Quick mapping

| 1.x | 2.0 |
|---|---|
| `workspace_search` | `workspace_search` |
| `find_files`, `drive_search_advanced` | `drive_search` |
| `drive_get_metadata` | `drive_read` + `action="metadata"` |
| `drive_export` | `drive_read` + `action="export"` |
| `drive_list_permissions` | `drive_read` + `action="list_permissions"` |
| `create_folder`, `drive_copy_file`, `move_file`, `drive_rename_file`, `drive_upload`, `share_file`, `drive_restore_file` | `drive_write` + action |
| `drive_delete_file` | `drive_trash` |
| `drive_remove_permission`, `drive_revoke_public` | `drive_permissions` + action |
| `read_doc` | `read_doc` |
| `create_doc`, `append_to_doc`, `docs_insert_image` | `docs_write` + action |
| `doc_replace_text`, `docs_format_text` | `docs_edit` + action |
| `read_sheet`, `get_spreadsheet_meta`, `sheet_export_csv` | `sheets_read` + action |
| `create_spreadsheet`, `add_sheet`, `update_sheet`, `append_row`, `clear_range`, `sheet_find_replace` | `sheets_write` + action |
| `sheet_format`, `sheet_set_borders`, `sheet_conditional_format`, `sheet_set_data_validation`, `sheet_protect_range` | `sheets_format` + action |
| `sheet_insert_rows`, `sheet_insert_columns`, `sheet_merge_cells`, `sheet_sort_range`, `sheet_create_named_range`, `sheet_create_filter_view` | `sheets_structure` + action |
| `sheet_delete_rows`, `sheet_delete_columns`, `sheet_delete_sheet` | `sheets_delete` + action |
| `sheet_add_chart`, `sheet_add_pivot_table` | `sheets_data` + action |
| `list_emails`, `read_email`, `gmail_get_thread`, `gmail_get_attachment`, `gmail_search_and_summarize`, `get_gmail_profile`, `gmail_list_labels`, `gmail_list_filters` | `gmail_read` + action |
| `send_email`, `gmail_reply`, `gmail_send_with_attachments`, `create_draft`, `gmail_update_draft`, `send_draft`, `gmail_list_drafts`, `gmail_archive` | `gmail_write` + action |
| `gmail_create_label`, `gmail_label_apply`, `gmail_create_filter` | `gmail_settings` + action |
| `delete_email`, `gmail_delete_draft` | `gmail_delete` + action |
| `list_events`, `calendar_list_calendars` | `calendar_read` + action |
| `calendar_create_meeting`, `calendar_update_event`, `calendar_move_event`, `calendar_respond_to_invite`, `calendar_set_event_color` | `calendar_write` + action |
| `calendar_delete_event` | `calendar_delete` |
| `tasks_*` | `tasks_read` / `tasks_write` + action |
| `forms_*` | `forms_read` / `forms_write` + action |
| `postmaster_*` | `postmaster_read` + action |
| `get_script_content`, `script_list_deployments` | `script_read` + action |
| `create_script_project`, `prepare_script_update`, `execute_operation`, `cancel_operation`, `restore_script_backup`, `script_create_deployment`, `script_update_deployment` | `script_write` + action |
| `script_run_function` | `script_run` |
| `bulk_*` | unchanged names |

## Removed in 2.0

- **Slides**: all 11 tools and the `presentations` scope.
- **Drive comments**: create/list/reply/resolve.
- **Permanent deletion**: `drive_empty_trash`.
- **Ownership transfer**: `drive_transfer_ownership`.
- **Download**: `drive_download` (use `drive_read` → `export` for Google-native
  files).
- **Shortcuts**: `drive_create_shortcut`.
- **Composites**: `clone_and_fill`, `report_from_sheet`, `sheet_to_slides`.
- **Templates**: `doc_fill_template`.
- **Calendar free slots**: `calendar_find_free_slots`.
- **Overlaps**: `create_event`, `batch_delete_emails`, `doc_export_pdf`,
  `find_files`, `drive_search_advanced`, and the five standalone draft tools.

Retained 1.x names are accepted as **hidden aliases** during 2.0.x: they are not
listed in `tools/list` but resolve to the new tool/action. Calls to removed
capabilities return a migration error. There is no permanent file
deletion; use `drive_trash` / Gmail Trash and recover within 30 days.

## Configuration

```yaml
tool_profile: "core"        # default; full | read-write | read-only
scope_routing: true         # hide tools whose Google scope is missing
allow_public_sharing: false # public links off by default
```

`allowed_tools` / `denied_tools` use consolidated names. Old names in those
lists are rejected with a clear message; migrate them with the table above.

## OAuth

`presentations` is no longer requested. Existing tokens keep the extra scope
until re-authorization; it is harmless. To request only what you need, edit
`scopes:` and re-authorize with `workspace-operator doctor`.

## Testing the migration

```bash
python -m workspace_operator tools --profile core
python -m workspace_operator tools --profile full
python -m workspace_operator doctor --offline
```
