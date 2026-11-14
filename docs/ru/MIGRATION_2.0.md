# Переход с 1.x на 2.0

2.0 заменяет 132 узких инструмента на 39 консолидированных. У большинства
появился `action`. Профиль по умолчанию — `core` (20 инструментов), а не `full`.

## Быстрая таблица

| 1.x | 2.0 |
|---|---|
| `workspace_search` | `workspace_search` |
| `find_files`, `drive_search_advanced` | `drive_search` |
| `drive_get_metadata` / `drive_export` / `drive_list_permissions` | `drive_read` + action |
| `create_folder`, `drive_copy_file`, `move_file`, `drive_rename_file`, `drive_upload`, `share_file`, `drive_restore_file` | `drive_write` + action |
| `drive_delete_file` | `drive_trash` |
| `drive_remove_permission`, `drive_revoke_public` | `drive_permissions` + action |
| `read_doc` | `read_doc` |
| `create_doc`, `append_to_doc`, `docs_insert_image` | `docs_write` + action |
| `doc_replace_text`, `docs_format_text` | `docs_edit` + action |
| `read_sheet`, `get_spreadsheet_meta`, `sheet_export_csv` | `sheets_read` + action |
| `create_spreadsheet`, `add_sheet`, `update_sheet`, `append_row`, `clear_range`, `sheet_find_replace` | `sheets_write` + action |
| `sheet_format`, `sheet_set_borders`, `sheet_conditional_format`, `sheet_set_data_validation`, `sheet_protect_range` | `sheets_format` + action |
| `sheet_insert_*`, `sheet_merge_cells`, `sheet_sort_range`, `sheet_create_named_range`, `sheet_create_filter_view` | `sheets_structure` + action |
| `sheet_delete_rows`, `sheet_delete_columns`, `sheet_delete_sheet` | `sheets_delete` + action |
| `sheet_add_chart`, `sheet_add_pivot_table` | `sheets_data` + action |
| `list_emails`, `read_email`, `gmail_get_thread`, `gmail_get_attachment`, `gmail_search_and_summarize`, `get_gmail_profile`, `gmail_list_labels`, `gmail_list_filters` | `gmail_read` + action |
| `send_email`, `gmail_reply`, `gmail_send_with_attachments`, `create_draft`, `gmail_update_draft`, `send_draft`, `gmail_list_drafts`, `gmail_archive` | `gmail_write` + action |
| `gmail_create_label`, `gmail_label_apply`, `gmail_create_filter` | `gmail_settings` + action |
| `delete_email`, `gmail_delete_draft` | `gmail_delete` + action |
| `calendar_*` | `calendar_read` / `calendar_write` / `calendar_delete` |
| `tasks_*` / `forms_*` / `postmaster_*` | соответствующие `*_read` / `*_write` |
| `script_*` | `script_read` / `script_write` / `script_run` |
| `bulk_*` | без изменений |

## Удалено в 2.0

- **Slides**: все 11 инструментов и scope `presentations`.
- **Комментарии Drive**: create/list/reply/resolve.
- **Безвозвратное удаление**: `drive_empty_trash`.
- **Передача владения**: `drive_transfer_ownership`.
- **Скачивание**: `drive_download` (для Google-файлов — `drive_read` → `export`).
- **Ярлыки**: `drive_create_shortcut`.
- **Композиты**: `clone_and_fill`, `report_from_sheet`, `sheet_to_slides`.
- **Шаблоны**: `doc_fill_template`.
- **Свободные слоты**: `calendar_find_free_slots`.
- **Пересечения**: `create_event`, `batch_delete_emails`, `doc_export_pdf`,
  `find_files`, `drive_search_advanced` и пять отдельных draft-инструментов.

Сохранённые имена 1.x принимаются как **скрытые aliases** в 2.0.x: они не
показываются в `tools/list`, но ведут к новому инструменту/action. Вызовы
удалённых возможностей возвращают migration error. Безвозвратного удаления
файлов нет:
используйте корзину Drive/Gmail и восстанавливайте в течение 30 дней.

## Конфигурация

```yaml
tool_profile: "core"        # по умолчанию; full | read-write | read-only
scope_routing: true         # скрывать инструменты без нужного Google-скоупа
allow_public_sharing: false # публичные ссылки выключены
```

`allowed_tools` / `denied_tools` используют новые имена. Старые имена
отклоняются с понятной ошибкой — мигрируйте по таблице.

## OAuth

`presentations` больше не запрашивается. Старый токен сохраняет лишний scope до
повторной авторизации; это безвредно. Чтобы запросить только нужное,
отредактируйте `scopes:` и выполните `workspace-operator doctor`.
