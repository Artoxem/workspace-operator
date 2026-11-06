# Справочник MCP Tools

Ниже перечислены инструменты (tools), ресурсы (resources) и шаблоны запросов (prompts), доступные в MCP сервере.
Все вызовы инструментов требуют, чтобы `MCP_AUTH_TOKEN` был сконфигурирован на сервере.

## MCP-примитивы

Сервер предоставляет три типа MCP-примитивов:

| Примитив | Описание |
|----------|----------|
| **Tools** | Выполняемые действия (чтение, запись, удаление). Вызываются AI по необходимости. |
| **Resources** | Пассивные источники данных, которые можно прикрепить к контексту. Снимки данных Google только для чтения. |
| **Prompts** | Переиспользуемые шаблоны запросов, которые загружают актуальные данные и подготавливают их для AI-анализа. |

## Аннотации инструментов

Каждый инструмент помечен подсказками для клиента:

| Аннотация | Значение |
|-----------|----------|
| `readOnlyHint: true` | Инструмент только читает данные и ничего не изменяет. |
| `destructiveHint: true` | Инструмент может необратимо удалить или перезаписать данные. |
| `destructiveHint: false` | Инструмент изменяет данные, но действие обратимо или малорискованно. |

Совместимые MCP-клиенты (например, Cursor) используют эти подсказки для предупреждения пользователей перед деструктивными операциями.

## Профили инструментов

`tool_profile` в `config.yaml` определяет, какие инструменты вообще существуют в этом
развёртывании. Инструменты вне профиля не показываются в `tools/list` и не могут быть
вызваны — сервер вернёт явную ошибку «disabled by the active tool profile».

| Профиль | Инструментов | Что доступно |
|---|---:|---|
| `full` (по умолчанию) | 66 | всё |
| `read-write` | 58 | всё, кроме `destructiveHint: true` |
| `read-only` | 21 | только `readOnlyHint: true` |

`allowed_tools` и `denied_tools` применяются поверх профиля; запрет важнее разрешения.

```yaml
tool_profile: "read-write"
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.

## Примеры использования

### Базовые операции
```
# Получить адрес Gmail (smoke test)
Tool: get_gmail_profile
Результат: Authenticated Gmail address: user@example.com

# Поиск файлов в Drive
Tool: find_files
Аргументы: {"query": "name contains 'бюджет'"}
Результат: Found files:
- Бюджет_2026.xlsx (ID: 1a2b3c...) [application/vnd.google-apps.spreadsheet]

# Чтение Google таблицы
Tool: read_sheet
Аргументы: {
  "spreadsheet_id": "1a2b3c4d5e...",
  "range_name": "Лист1!A1:C10"
}
Результат: Data from sheet (range Лист1!A1:C10):
| Имя | Email | Статус |
| Иван | ivan@example.com | Активен |
...

# Создание черновика письма (безопасно по умолчанию)
Tool: send_email
Аргументы: {
  "to": "kollega@example.com",
  "subject": "Заметки со встречи",
  "body_text": "Вот заметки с нашей встречи...",
  "draft_mode": true
}
Результат: EMAIL DRAFT CREATED (ID: r1234...)
Email saved as DRAFT, not sent yet.
Для отправки: send_email(..., draft_mode=False)
```

### Функции безопасности
```
# Деструктивные операции требуют подтверждения
Tool: delete_email
Аргументы: {"message_id": "18abc...", "confirm": false}
Результат: CONFIRMATION REQUIRED
This will permanently delete email 18abc...
To proceed, call this tool again with confirm=True

# Массовые операции используют dry-run режим
Tool: clear_range
Аргументы: {"spreadsheet_id": "1a2b...", "range_name": "Лист1!A1:Z1000"}
Результат: DRY RUN: Large range detected (26,000 cells)
Would clear range: Лист1!A1:Z1000
To proceed: clear_range(..., confirm=True)
```

## Кросс-поиск
- `workspace_search(query, sources?, limit?, calendar_days_back?, calendar_days_ahead?)`
  - Один запрос по Drive, Gmail и Calendar; результаты объединяются и сортируются по дате.
  - `sources`: список через запятую — `drive`, `gmail`, `calendar`. По умолчанию `drive,gmail`.
  - `limit`: лимит на источник, 1–25 (по умолчанию 10).
  - Окно календаря по умолчанию: 30 дней назад, 180 дней вперёд.
  - Частичные сбои не фатальны: остальные результаты всё равно возвращаются.

Пример:

```
Инструмент: workspace_search
Аргументы: {"query": "бюджет Q3", "sources": "drive,gmail,calendar", "limit": 10}
Результат:
Workspace search: 'бюджет Q3' — 6 result(s) [drive (3), gmail (2), calendar (1)]

1. [drive] Бюджет 2026 — spreadsheet
   2026-03-02 10:11 UTC | type: spreadsheet | id: 1a2b3c
   https://docs.google.com/spreadsheets/d/1a2b3c
```

## Файлы Drive
- `drive_upload(local_path, name?, parent_id?, mime_type?, convert_to?)`
  - Загрузить локальный файл (лимит 100 МБ). `convert_to`: `google-docs`,
    `google-sheets` или `google-slides` превращает docx/xlsx/pptx в Google-файл.
- `drive_download(file_id, save_to?, overwrite?)`
  - Скачать бинарный файл. `save_to` — папка (по умолчанию `~/Downloads`) или путь
    к файлу. Для Google-файлов вернётся подсказка использовать `drive_export`.
- `drive_export(file_id, format, save_to?, overwrite?)`
  - Экспорт: `pdf`, `docx`, `xlsx`, `pptx`, `csv`, `txt`, `md`, `html`, `rtf`,
    `epub`, `odt/ods/odp`, `png/jpeg/svg`, `zip`. Формат проверяется на совместимость
    с типом файла, без `overwrite=true` ничего не перезаписывается.

## Drive
- `find_files(query)`
  - Поиск по имени или по полноценному запросу Drive query.
- `create_folder(name, parent_id?)`
  - Создать папку; `parent_id` опционален.
- `move_file(file_id, folder_id)`
  - Переместить файл в папку.
- `share_file(file_id, role, type?, email_address?, allow_public?)`
  - `type`: `user|group|domain|anyone`, публичный доступ только с `allow_public=true`.
- `drive_search_advanced(query, limit?)`
  - Полный синтаксис Drive query.
- `drive_list_permissions(file_id)`
  - Список прав доступа.
- `drive_revoke_public(file_id, confirm?)`
  - Отозвать публичный доступ, требует `confirm=true`.
- `drive_copy_file(file_id, name?, parent_id?)`
  - Копировать файл.

## Sheets
- `read_sheet(spreadsheet_id, range_name)`
  - Чтение диапазона.
- `append_row(spreadsheet_id, range_name, values[])`
  - Добавить строку.
- `update_sheet(spreadsheet_id, range_name, values[][])`
  - Обновить диапазон массивом строк.
- `create_spreadsheet(title)`
  - Создать таблицу.
- `add_sheet(spreadsheet_id, title)`
  - Добавить новый лист (tab).
- `clear_range(spreadsheet_id, range_name, confirm?)`
  - Для больших диапазонов требуется `confirm=true`.
- `sheet_create_filter_view(spreadsheet_id, sheet_id, title, start_row?, end_row?, start_col?, end_col?)`
  - Создать фильтр-вью.
- `sheet_export_csv(spreadsheet_id, range_name, max_rows?)`
  - Экспорт диапазона в CSV.
- `sheet_find_replace(spreadsheet_id, range_name, find_text, replace_text, dry_run?, match_case?)`
  - По умолчанию `dry_run=true`.
- `sheet_create_named_range(spreadsheet_id, name, sheet_id, start_row, end_row, start_col, end_col)`
  - Именованный диапазон по индексам.
- `get_spreadsheet_meta(spreadsheet_id)`
  - Метаданные таблицы.

- `sheet_format(spreadsheet_id, sheet_name?, range?, bold?, italic?, font_size?, number_format?, background_color?, text_color?, horizontal_alignment?, wrap?, column_width?, row_height?, freeze_rows?, freeze_cols?)`
  - Один `batchUpdate`: формат ячеек, ширины колонок и высоты строк, закрепление областей.
  - `range`: `A1:C10`, `A:C` или `1:10`; по умолчанию весь лист. Цвета — `#RRGGBB`.
  - `column_width`/`row_height` в пикселях; `freeze_rows`/`freeze_cols` — на уровне листа.

## Docs
- `read_doc(document_id)`
  - Прочитать текст документа.
- `create_doc(title)`
  - Создать документ.
- `append_to_doc(document_id, text)`
  - Добавить текст в конец.
- `doc_fill_template(document_id, replacements, confirm?)`
  - Заполнить шаблон, требует `confirm=true`.
- `doc_export_pdf(document_id)`
  - Экспорт документа в бинарный PDF. Возвращает `EmbeddedResource` с MIME-типом `application/pdf`.

## Slides
- `slides_create(title)`
  - Создать презентацию, вернуть ID и ссылку.
- `slides_get(presentation_id)`
  - Количество слайдов, их ID и текст.
- `slides_add_slide(presentation_id, layout?, insertion_index?)`
  - Добавить слайд; макеты: `TITLE_AND_BODY` (по умолчанию), `TITLE_ONLY`, `BLANK`,
    `SECTION_HEADER`, `MAIN_POINT`, …
- `slides_replace_text(presentation_id, replacements, confirm?)`
  - Замена плейсхолдеров; без `confirm=true` возвращает превью с числом вхождений.
- `slides_insert_image(presentation_id, slide_id, image_url, width?, height?, left?, top?)`
  - URL картинки должен быть публичным; размеры и позиция — в пикселях.

## Gmail
- `send_email(to, subject, body_text, draft_mode?)`
  - По умолчанию создаёт черновик.
- `send_draft(draft_id)`
  - Отправить черновик.
- `get_gmail_profile()`
  - Получить адрес текущего аккаунта.
- `create_draft(to, subject, body_text)`
  - Создать черновик.
- `list_emails(max_results?, query?)`
  - Список писем с датой, отправителем и темой (плюс очищенный сниппет).
- `read_email(message_id)`
  - Прочитать письмо: From / To / Date / Subject / статус / метки / вложения
    и декодированное тело (приоритет text/plain, HTML конвертируется, максимум 2 500 символов).
- `delete_email(message_id, confirm?)`
  - Требует `confirm=true`.
- `batch_delete_emails(message_ids[], dry_run?)`
  - По умолчанию `dry_run=true`.
- `gmail_search_and_summarize(query, max_results?)`
  - Поиск и краткое резюме.
- `gmail_get_thread(thread_id?, message_id?, include_body?)`
  - Вся переписка с датами, отправителями, метками и вложениями.
- `gmail_get_attachment(message_id, filename?, attachment_id?, save_to?, overwrite?)`
  - Сохраняет вложение на диск; если вложение одно, селектор не нужен.
- `gmail_reply(message_id, body_text, reply_all?, draft_mode?)`
  - Ответ в тред с `In-Reply-To`/`References`; по умолчанию черновик.
- `gmail_archive(message_id, confirm?)`
  - Требует `confirm=true`.
- `gmail_label_apply(message_ids[], label_name, dry_run?, create_if_missing?)`
  - По умолчанию `dry_run=true`.

## Calendar
- `list_events(calendar_id?, max_results?)`
  - Список ближайших событий (от текущего момента).
- `create_event(summary, start_time, end_time, description?, calendar_id?)`
  - Создать событие. `calendar_id` по умолчанию `"primary"`.
- `calendar_find_free_slots(calendar_id?, start_time, end_time, duration_minutes?, max_results?)`
  - Найти свободные слоты.
- `calendar_create_meeting(summary, start_time, end_time, attendees?, description?, location?, confirm?)`
  - Требует `confirm=true`.

- `calendar_update_event(event_id, calendar_id?, summary?, start_time?, end_time?, description?, location?, attendees?, send_updates?)`
  - Патч: меняются только переданные поля. `send_updates`: `all|externalOnly|none`.
- `calendar_delete_event(event_id, calendar_id?, confirm?, send_updates?)`
  - Требует `confirm=true`.
- `calendar_respond_to_invite(event_id, response, calendar_id?, confirm?, send_updates?)`
  - `response`: `accepted|declined|tentative`; требует `confirm=true`.

## Составные
- `report_from_sheet(spreadsheet_id, range?, doc_title?, max_rows?, header?, decimal?, columns?, aggregates?, output?)`
  - Читает диапазон, считает статистику и возвращает Doc (по умолчанию) или текст.
  - `header` (true), `decimal` (`auto|comma|dot`), `columns` (имена или индексы с 1),
    `aggregates` (`sum`, `avg`, `min`, `max`, `median`, `count`), `output` (`doc|text`).
- `digest(sources?, since_hours?, limit?, output?, doc_title?)`
  - Один дайджест по `gmail,calendar,drive` за последние N часов (по умолчанию 24).
- `compare_tables(spreadsheet_id, range_a, range_b, other_spreadsheet_id?, key_column?, header?, output?, doc_title?)`
  - Сравнение по ключевой колонке (имя или индекс): добавленные, удалённые, изменённые.
- `clone_and_fill(file_id, replacements?, name?, folder_id?)`
  - Копирует любой файл Drive и заменяет плейсхолдеры в копии (Docs, Slides, Sheets).

## Apps Script
- `report_from_sheet(spreadsheet_id, range?, doc_title?, max_rows?)`
  - Читает диапазон, считает статистику по колонкам (sum/avg/min/max для чисел,
    непустые/уникальные для текста) и создаёт Google Doc со сводкой и превью данных.

## Apps Script
- `script_run_function(script_id, function_name, parameters?, dev_mode?)`
  - Запустить функцию из проекта, развёрнутого как API executable. `dev_mode=true`
    (по умолчанию) выполняет последний сохранённый код. Возвращает JSON-результат
    или ошибку Apps Script со стеком.
- `create_script_project(title, parent_id?)`
  - Создать проект Apps Script.
- `get_script_content(script_id)`
  - Получить контент.
- `prepare_script_update(script_id, files[])`
  - Подготовка обновления, возвращает `operation_id`.
- `execute_operation(operation_id)`
  - Выполнить подготовленную операцию.
- `cancel_operation(operation_id)`
  - Отменить подготовленную операцию.
- `restore_script_backup(backup_path)`
  - Откатить из backup.

---

## Ресурсы (Resources)

Ресурсы — это снимки данных только для чтения, которые MCP-клиенты могут прикреплять непосредственно к контексту AI. Статические ресурсы не требуют аргументов; параметризованные шаблоны требуют встроенных идентификаторов в URI.

### Статические ресурсы

| URI | Описание |
|-----|----------|
| `gdrive://recent` | 20 недавно изменённых файлов в Google Drive |
| `gmail://inbox` | До 20 непрочитанных сообщений в папке «Входящие» Gmail |
| `gcalendar://upcoming` | Ближайшие события основного календаря (следующие 7 дней) |

### Шаблоны ресурсов

| Шаблон URI | Описание |
|------------|----------|
| `gdrive://file/{file_id}` | Метаданные конкретного файла в Google Drive |
| `gsheets://{spreadsheet_id}/{range}` | Данные из конкретного диапазона таблицы, например `gsheets://SPREADSHEET_ID/Лист1!A1:Z100` |
| `gdocs://{document_id}` | Полный текст конкретного Google-документа |

### Примеры
```
# Прикрепить последние файлы Drive к контексту
Resource URI: gdrive://recent

# Прочитать конкретный диапазон таблицы
Resource URI: gsheets://1a2b3c4d5e.../Лист1!A1:D20

# Прочитать конкретный документ
Resource URI: gdocs://1a2b3c4d5e...
```

---

## Шаблоны запросов (Prompts)

Prompts — это переиспользуемые шаблоны, которые загружают актуальные данные Google и встраивают их в структурированное сообщение для AI-анализа. Они отображаются в меню выбора prompts в MCP-клиенте.

### `summarize_inbox`
Загрузить последние сообщения Gmail и подготовить их для AI-суммаризации.

| Аргумент | Обязателен | По умолчанию | Описание |
|----------|------------|--------------|----------|
| `query` | Нет | `is:unread in:inbox` | Поисковый запрос Gmail |
| `max_results` | Нет | `20` | Максимальное количество писем |

### `analyze_spreadsheet`
Прочитать диапазон Google Sheets и подготовить данные для AI-анализа или визуализации.

| Аргумент | Обязателен | По умолчанию | Описание |
|----------|------------|--------------|----------|
| `spreadsheet_id` | Да | — | ID Google-таблицы |
| `range` | Нет | `Sheet1` | Диапазон для чтения |

### `plan_week`
Загрузить предстоящие события календаря и подготовить сводку для AI-планирования недели.

| Аргумент | Обязателен | По умолчанию | Описание |
|----------|------------|--------------|----------|
| `days_ahead` | Нет | `7` | Количество дней для просмотра вперёд |

### `search_drive`
Найти файлы в Google Drive и подготовить структурированный список для AI-анализа или предложений по организации.

| Аргумент | Обязателен | По умолчанию | Описание |
|----------|------------|--------------|----------|
| `query` | Да | — | Запрос поиска Drive, например `name contains "бюджет"` |
| `limit` | Нет | `20` | Максимальное количество результатов |
