<div align="center">

# Workspace Operator

**Глубокая автоматизация Google Workspace через Model Context Protocol**

Drive · Docs · Sheets · Slides · Gmail · Calendar · Apps Script — один локальный
MCP-сервер с 115 инструментами, многошаговыми записями и профилями на стороне сервера.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-115-informational)](#-каталог-инструментов)
[![PyPI](https://img.shields.io/badge/PyPI-workspace--operator--mcp-3775A9?logo=pypi&logoColor=white)](https://pypi.org/project/workspace-operator-mcp/)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

</div>

---

Workspace Operator (ранее *yet-another-google-mcp*) работает на вашей машине,
обращается к Google через ваш собственный OAuth-клиент и даёт ИИ-агенту операции,
которые превращают «прочитай мою почту» в «сделай работу, и чтобы можно было откатить»:
стейджинг Apps Script, передача файлов в обе стороны, сборка презентаций,
форматирование таблиц, ответы в тред и работа с вложениями.

**115 инструментов · 3 ресурса · 3 шаблона ресурсов · 8 промптов**, у каждого инструмента
аннотации `readOnlyHint` / `destructiveHint`.

Ничто здесь не привязано к конкретному аккаунту, таблице или документу: каждый
инструмент принимает идентификаторы и диапазоны, а примеры используют синтетические данные.

## Сравнение

| | Google Workspace MCP (remote) | **Workspace Operator** |
|---|---|---|
| Транспорт | Streamable HTTP, хостинг Google | **stdio, локально** |
| Доступность | Developer Preview | **публично, MIT** |
| Путь данных | эндпоинт MCP Google | **ваша машина, ваш OAuth-клиент** |
| Apps Script | — | **создание · чтение · стейджинг · запуск · отмена · откат · вызов функции** |
| Локальные файлы | — | **загрузка, скачивание, экспорт в pdf/docx/xlsx/pptx** |
| Slides | — | **создание, слайды, замена текста, картинки** |
| Форматирование Sheets | — | **жирный, цвета, форматы чисел, ширины, закрепление** |
| Треды Gmail | отдельные письма | **треды, вложения, ответы в тред** |
| Профили инструментов на сервере | IAM / allow-list админа | **read-only / read-write / full + allow-deny** |

Официальные серверы — правильный выбор для «спроси у почты».
Workspace Operator — для «измени рабочее пространство так, чтобы можно было откатить».

## Что внутри

| Группа | Инструментов | Ключевое |
|---|---:|---|
| 🔎 Кросс-поиск | 1 | Один запрос по Drive, Gmail и Calendar, сортировка по дате |
| 📁 Drive | 16 | Поиск, метаданные, переименование, корзина, шаринг, права |
| 💬 Комментарии | 4 | Треды у Docs, Sheets и Slides: чтение, создание, ответ, решение |
| 💾 Файлы Drive | 3 | Загрузка, скачивание, экспорт, конвертация в нативные форматы |
| 📊 Sheets | 25 | Чтение и запись, форматирование, условные правила, графики, фильтры, CSV |
| 📄 Docs | 8 | Чтение (включая таблицы), дописывание, поиск и замена, шаблоны, PDF |
| 🖼 Slides | 11 | Создание, добавление и удаление слайдов, замена текста, картинки |
| ⚙️ Apps Script | 10 | Стейджинг с бэкапами, откат, запуск функций |
| 📧 Gmail | 22 | Треды, вложения, ответы, черновики, метки, пакетное удаление |
| 📅 Calendar | 10 | События, слоты, встречи, изменение/удаление, ответ на приглашения |
| 🧩 Составные | 5 | отчёт, дайджест, сравнение, клон шаблона, таблица → колода |

Плюс 3 ресурса, 3 шаблона ресурсов и 8 промптов — см. [каталог](#-каталог-инструментов).

## Быстрый старт

### 1 — Установка

```bash
pip install workspace-operator-mcp
```

Из исходников (для разработки):

```bash
git clone https://github.com/Artoxem/workspace-operator.git
cd workspace-operator
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Нужен Python 3.10+. Пакет ставит команду `workspace-operator`; форма
`python -m workspace_operator` тоже работает из исходников.

### 2 — Google OAuth

1. Создайте OAuth 2.0 Client ID (тип **Desktop app**) в
   [Google Cloud Console](https://console.cloud.google.com/).
2. Включите API: **Drive, Docs, Sheets, Slides, Gmail, Calendar, Apps Script**.
3. Скачайте JSON клиента — сервер прочитает его при первом запуске.

> Пошагово: [docs/ru/AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) · [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md)
> Обновляетесь? Для Slides нужен скоуп `.../auth/presentations` — переавторизуйтесь один раз.

### 3 — Конфигурация

```bash
cp config.example.yaml config.yaml
```

```yaml
client_secrets_file: "C:\\Users\\you\\.google\\oauth.keys.json"
token_file: "C:\\Users\\you\\.google\\token.json"
backup_dir: "C:\\Users\\you\\.google\\backups"
mcp_auth_token: "MySecretToken_2026!"
tool_profile: "read-write"      # full | read-write | read-only
```

`mcp_auth_token` — локальный ключ активации, а не сетевая защита: без него сервер
не начнёт обрабатывать инструменты. Любой ключ можно переопределить переменной
окружения — см. [docs/ru/SECURITY.md](docs/ru/SECURITY.md).

### 4 — Подключение клиента

<details open>
<summary><strong>Google Antigravity</strong> — App, IDE и CLI читают один конфиг</summary>

`~/.gemini/config/mcp_config.json` (глобально) или `<workspace>/.agents/mcp_config.json`:

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "python",
      "args": ["D:\\DEV\\workspace-operator\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\workspace-operator\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!",
        "MCP_TOOL_PROFILE": "read-write"
      },
      "timeoutSeconds": 300,
      "tools": { "workspace_search": { "eager": true } }
    }
  }
}
```

Готовый файл: [antigravity/mcp_config.example.json](antigravity/mcp_config.example.json) ·
инструкция: [antigravity/README.md](antigravity/README.md) ·
Agent Skill: [skills/google-workspace/SKILL.md](skills/google-workspace/SKILL.md)

</details>

<details>
<summary><strong>Claude Desktop, Cursor, VS Code, Windsurf</strong></summary>

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "python",
      "args": ["D:\\DEV\\workspace-operator\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\workspace-operator\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!"
      }
    }
  }
}
```

Пути для конкретных клиентов: [docs/ru/IDE_SETUP.md](docs/ru/IDE_SETUP.md).

</details>

## Профили инструментов

Профиль — серверный allow-list: инструменты вне профиля не показываются и не
вызываются. Он дополняет OAuth-скоупы (что разрешает Google) и права клиента
(что агенту можно без спроса).

| Профиль | Инструментов | Для чего |
|---|---:|---|
| `full` | 115 | своя машина, полное доверие |
| `read-write` | 96 | ежедневная работа — деструктивные скрыты |
| `read-only` | 29 | разведка, демо, общие машины, недоверенные агенты |

```yaml
tool_profile: "read-write"
# Необязательно, применяется поверх профиля. Запрет важнее разрешения.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.
Заблокированный вызов возвращает понятное объяснение, а не молчит.

## Эксплуатация

```bash
python -m workspace_operator doctor     # конфиг, токен, скоупы, доступность API
python -m workspace_operator doctor --offline   # то же, но без сети
python -m workspace_operator tools      # каталог (--profile read-only, --json)
python -m workspace_operator serve      # stdio-сервер (то же, что python server.py)
```

| Возможность | Как включить | Что делает |
|---|---|---|
| **Dry run** | `MCP_DRY_RUN=1` или `dry_run: true` | Все инструменты, кроме read-only, возвращают превью вместо выполнения — безопасные демо и разведка |
| **Аудит-лог** | `MCP_AUDIT_LOG=~/.google/audit.jsonl` | Одна JSON-строка на вызов: инструмент, профиль, статус, длительность, **имена** аргументов (без значений) |
| **Ретраи** | `MCP_RETRY_ATTEMPTS=3` | Транзиентные ошибки Google (429/5xx) повторяются с экспоненциальной паузой |
| **Doctor** | `python -m workspace_operator doctor` | Проверяет секреты, токен, выданные скоупы и доступность Drive/Gmail/Calendar |

В dry-run read-only инструменты продолжают работать, поэтому агент может изучать
данные, пока каждая запись превращается в явное превью.

### HTTP-транспорт (сначала localhost)

```bash
python -m workspace_operator serve --http --port 8765
```

* по умолчанию слушает `127.0.0.1` — из сети недоступен;
* каждый запрос требует `Authorization: Bearer <mcp_auth_token>`; дополнительные
  токены клиентов задаются в `http_tokens` в `config.yaml`, а аудит-лог пишет имя
  токена в поле `client`;
* включена защита от DNS-rebinding: проходят только ожидаемые `Host`, браузерные
  `Origin` отклоняются;
* `GET /healthz` не требует токена и отдаёт только версию и транспорт;
* привязка к не-loopback адресу требует **одновременно** `--allow-network` и
  `--insecure`; loopback-имена принимают любой порт (контейнеры, прокси),
  для остального нужен явный `--allow-host`;
  `--insecure`, поэтому выход в сеть всегда осознанный.

### Docker

```bash
docker pull ghcr.io/artoxem/workspace-operator:latest

docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:latest
```

Образ работает под непривилегированным пользователем (uid 10001), публикует порт только
на loopback и монтирует Google-креденшелы на запись — сервер обновляет токен на месте.
`docker compose up --build` собирает тот же образ локально.

Клиенты, которые умеют только stdio, тоже могут работать с образом — entrypoint
принимает те же аргументы, что и CLI:

```bash
docker run -i --rm \
  -v "$HOME/.google:/home/app/.google" \
  --entrypoint python \
  ghcr.io/artoxem/workspace-operator:latest -m workspace_operator serve
```

Что-то не работает? Смотрите [docs/ru/TROUBLESHOOTING.md](docs/ru/TROUBLESHOOTING.md).

## Каталог инструментов

<details>
<summary>🔎 Кросс-поиск (1)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `workspace_search` | read | Один запрос по Drive, Gmail и Calendar; сортировка по дате, частичные сбои не фатальны |

</details>

<details>
<summary>📁 Drive (16)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `find_files` | read | Поиск по имени или запросу Drive |
| `drive_search_advanced` | read | Полный синтаксис запросов Drive |
| `drive_list_permissions` | read | Права на файл |
| `create_folder` | write | Создать папку |
| `move_file` | write | Переместить файл |
| `drive_copy_file` | write | Копировать файл |
| `share_file` | write | Поделиться с пользователем/группой/доменом |
| `drive_revoke_public` | destructive | Отозвать публичный доступ (`confirm=true`) |
| `drive_get_metadata` | read | Размер, владелец, родители, даты и ссылка |
| `drive_rename_file` | write | Переименовать без перемещения |
| `drive_delete_file` | destructive | В корзину (`confirm=true`) |
| `drive_restore_file` | write | Восстановить из корзины |
| `drive_remove_permission` | destructive | Отозвать одно право (`confirm=true`) |
| `drive_empty_trash` | destructive | Очистить корзину навсегда (`confirm=true`) |
| `drive_transfer_ownership` | destructive | Передать файл другому владельцу (`confirm=true`) |
| `drive_create_shortcut` | write | Создать ярлык на другой файл |

</details>

<details>
<summary>💾 Файлы Drive (3)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `drive_upload` | write | Загрузить файл; `convert_to` превращает docx/xlsx/pptx в Google-файлы |
| `drive_download` | read | Скачать бинарный файл на диск |
| `drive_export` | read | Экспорт Doc/Sheet/Slide в pdf, docx, xlsx, pptx, csv… |

</details>

<details>
<summary>💬 Комментарии (4)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `drive_list_comments` | read | Комментарии и ответы у Doc, Sheet или Slide |
| `drive_create_comment` | write | Добавить комментарий, можно с цитатой |
| `drive_reply_comment` | write | Ответить в существующем треде |
| `drive_resolve_comment` | write | Пометить тред решённым (`confirm=true`) |

</details>

<details>
<summary>📊 Sheets (25)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `read_sheet` | read | Прочитать диапазон |
| `get_spreadsheet_meta` | read | Названия листов и их ID |
| `sheet_export_csv` | read | Экспорт диапазона в CSV |
| `append_row` | write | Добавить строку |
| `update_sheet` | write | Записать строки в диапазон |
| `create_spreadsheet` | write | Создать таблицу |
| `add_sheet` | write | Добавить лист |
| `sheet_create_filter_view` | write | Создать фильтр |
| `sheet_create_named_range` | write | Создать именованный диапазон |
| `sheet_find_replace` | write | Поиск и замена (`dry_run=true` по умолчанию) |
| `sheet_format` | write | Жирный, цвета, форматы чисел, ширины, высоты строк, закрепление |
| `clear_range` | destructive | Очистить диапазон (авто dry-run для больших) |
| `sheet_conditional_format` | write | Закрасить ячейки по условию |
| `sheet_add_chart` | write | Вставить график COLUMN/BAR/LINE/AREA/PIE по диапазону |
| `sheet_delete_sheet` | destructive | Удалить лист (`confirm=true`) |
| `sheet_insert_rows` | write | Вставить пустые строки перед номером |
| `sheet_delete_rows` | destructive | Удалить строки (`confirm=true`) |
| `sheet_merge_cells` | write | Объединить или разъединить диапазон |
| `sheet_insert_columns` | write | Вставить пустые колонки |
| `sheet_delete_columns` | destructive | Удалить колонки (`confirm=true`) |
| `sheet_sort_range` | write | Отсортировать диапазон по колонке |
| `sheet_add_pivot_table` | write | Сводная таблица из диапазона на новом листе |
| `sheet_set_data_validation` | write | Проверка по списку или диапазону чисел |
| `sheet_protect_range` | write | Предупреждение или блокировка |
| `sheet_set_borders` | write | Границы: solid/dotted/dashed |

</details>

<details>
<summary>📄 Docs (8)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `read_doc` | read | Текст и таблицы |
| `doc_export_pdf` | read | Экспорт в бинарный PDF |
| `create_doc` | write | Создать документ |
| `append_to_doc` | write | Дописать текст |
| `doc_fill_template` | destructive | Заполнить шаблон (`confirm=true`) |
| `doc_replace_text` | destructive | Поиск и замена с превью (`confirm=true`) |
| `docs_insert_image` | write | Вставить картинку по публичному URL |
| `docs_format_text` | destructive | Жирный/курсив/размер/заголовок для найденного текста (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (11)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `slides_create` | write | Создать презентацию |
| `slides_get` | read | Количество слайдов, ID и текст |
| `slides_add_slide` | write | Добавить слайд с готовым макетом |
| `slides_replace_text` | destructive | Замена плейсхолдеров (`confirm=true`) |
| `slides_insert_image` | write | Вставить картинку по публичному URL |
| `slides_delete_slide` | destructive | Удалить слайд (`confirm=true`) |
| `slides_move_slide` | write | Переместить слайд на другую позицию |
| `slides_set_notes` | write | Заменить заметки докладчика |
| `slides_add_table` | write | Вставить нативную таблицу на слайд |
| `slides_list_layouts` | read | Макеты презентации |
| `slides_add_shape` | write | Прямоугольник/эллипс/текстовое поле с текстом |

</details>

<details>
<summary>⚙️ Apps Script (10)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `get_script_content` | read | Прочитать файлы проекта |
| `create_script_project` | write | Создать проект |
| `prepare_script_update` | write | Подготовить обновление, вернуть `operation_id` |
| `execute_operation` | write | Применить обновление (сначала бэкап) |
| `cancel_operation` | write | Отменить подготовленное обновление |
| `restore_script_backup` | write | Восстановить из бэкапа |
| `script_run_function` | destructive | Запустить функцию из API-executable деплоя |
| `script_list_deployments` | read | Деплои проекта |
| `script_create_deployment` | write | Задеплоить сохранённую версию |
| `script_update_deployment` | write | Перевести деплой на новую версию |

</details>

<details>
<summary>📧 Gmail (22)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `get_gmail_profile` | read | Адрес авторизованного пользователя |
| `list_emails` | read | Список с датой, отправителем и темой |
| `read_email` | read | Заголовки, метки, вложения и тело письма |
| `gmail_search_and_summarize` | read | Поиск с краткой сводкой |
| `gmail_get_thread` | read | Вся переписка |
| `gmail_get_attachment` | read | Сохранить вложение на диск |
| `create_draft` | write | Создать черновик |
| `send_email` | write | Отправить или создать черновик (`draft_mode=true`) |
| `send_draft` | write | Отправить существующий черновик |
| `gmail_reply` | write | Ответ в тред (`draft_mode=true` по умолчанию) |
| `gmail_label_apply` | write | Навесить метку (`dry_run=true`) |
| `gmail_archive` | write | Архивировать (`confirm=true`) |
| `delete_email` | destructive | Удалить письмо (`confirm=true`) |
| `batch_delete_emails` | destructive | Удалить несколько (`dry_run=true`) |
| `gmail_list_labels` | read | Метки с ID, пользовательские и системные |
| `gmail_create_label` | write | Создать метку |
| `gmail_send_with_attachments` | write | Черновик или отправка с файлами (20 МБ) |
| `gmail_list_drafts` | read | Черновики с получателем и темой |
| `gmail_delete_draft` | destructive | Удалить черновик (`confirm=true`) |
| `gmail_list_filters` | read | Фильтры с условиями и действиями |
| `gmail_create_filter` | write | Фильтр: from/subject/query + метки |
| `gmail_update_draft` | write | Заменить содержимое черновика |

</details>

<details>
<summary>🧩 Составные (5)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `report_from_sheet` | write | Диапазон → статистика → Doc с **нативными таблицами** или текст (`output=text`) |
| `digest` | write | Последние N часов по Gmail, Calendar и Drive → текст или Doc |
| `compare_tables` | write | Сравнение по ключевой колонке; `output=doc` собирает нативные таблицы |
| `clone_and_fill` | write | Копия любого файла Drive с заменой плейсхолдеров |
| `sheet_to_slides` | write | Диапазон → колода: титул + слайд на группу строк |

</details>

<details>
<summary>📅 Calendar (10)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `list_events` | read | Ближайшие события со временем и местом |
| `calendar_find_free_slots` | read | Свободные слоты в окне |
| `create_event` | write | Создать событие |
| `calendar_create_meeting` | write | Встреча с участниками (`confirm=true`) |
| `calendar_update_event` | write | Изменить любое поле; меняется только переданное |
| `calendar_delete_event` | destructive | Удалить событие (`confirm=true`) |
| `calendar_respond_to_invite` | write | Принять / отклонить / под вопросом (`confirm=true`) |
| `calendar_list_calendars` | read | Календари с ролями доступа |
| `calendar_move_event` | write | Перенести событие в другой календарь |
| `calendar_set_event_color` | write | Цвет события (`1`–`11`) |

</details>

### Ресурсы

| URI | Что отдаёт |
|---|---|
| `gdrive://recent` | 20 последних изменённых файлов Drive |
| `gmail://inbox` | Непрочитанные письма |
| `gcalendar://upcoming` | События на 7 дней |
| `gdrive://file/{file_id}` | Метаданные файла |
| `gsheets://{spreadsheet_id}/{range}` | Диапазон таблицы как таблица |
| `gdocs://{document_id}` | Полный текст документа, включая таблицы |

### Промпты

| Промпт | Что делает |
|---|---|
| `summarize_inbox` | Собирает письма → готово для сводки |
| `analyze_spreadsheet` | Читает диапазон → готово для анализа |
| `plan_week` | Загружает события → готово для планирования |
| `search_drive` | Ищет файлы → готово для разбора |
| `weekly_review` | Почта, файлы и календарь за N дней → недельная сводка |
| `inbox_triage` | Срез Gmail → срочно / ждём / к сведению / в архив |
| `sheet_brief` | Диапазон → статистика и вопрос для брифинга |
| `compare_brief` | Два диапазона → отчёт о сверке |


## Безопасность по умолчанию

| Защита | Инструменты |
|---|---|
| Требуется `confirm=true` | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template`, `slides_replace_text`, `drive_delete_file`, `drive_remove_permission`, `drive_resolve_comment`, `doc_replace_text`, `slides_delete_slide`, `sheet_delete_sheet`, `sheet_delete_rows`, `drive_empty_trash`, `sheet_delete_columns`, `drive_transfer_ownership`, `docs_format_text`, `gmail_delete_draft` |
| `dry_run=true` по умолчанию | `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` |
| Режим черновика | `send_email`, `gmail_reply` |
| Публичный шаринг заблокирован | `share_file` не даёт `type=anyone` без `allow_public=true` |
| Без молчаливой перезаписи | `drive_download`, `drive_export`, `gmail_get_attachment` |
| Стейджинг Apps Script | `prepare_script_update` → `execute_operation` (сначала бэкап) |
| Аннотации инструментов | у каждого — `readOnlyHint` / `destructiveHint` |
| Серверные профили | `read-only` / `read-write` / `full` + allow/deny |

> ⚠️ Агент получает доступ ко всему, что разрешает ваш OAuth-токен. Для чувствительных
> аккаунтов — read-only скоупы и профиль `read-only`: [docs/ru/SECURITY.md](docs/ru/SECURITY.md).

## Как устроено

```
server.py                    MCP-сервер: 115 инструментов, ресурсы, промпты, профили
workspace_operator/
├─ profiles.py               read-only / read-write / full + allow-deny
├─ config.py                 конфиг + переменные окружения
├─ auth.py                   OAuth 2.0 и кэш токена
├─ text.py                   нормализация текста, таймстампов и ошибок
├─ operations.py             хранилище подготовленных операций Apps Script
├─ security.py               проверки токена и email
├─ runtime.py                ретраи, аудит-лог, dry-run
├─ cli.py                    doctor / tools / serve
└─ handlers/
   ├─ search.py              workspace_search — Drive + Gmail + Calendar
   ├─ files.py               drive_upload / drive_download / drive_export
   ├─ formatting.py          сборка запросов sheet_format
   ├─ gmail_threads.py       треды, вложения, ответы в тред
   ├─ slides.py              презентации
   ├─ calendar_writes.py     обновление / удаление / ответы на приглашения
   ├─ report.py              report_from_sheet: статистика + документ
   ├─ digest.py              дайджест по почте, календарю и Drive
   ├─ compare.py             сравнение таблиц по ключевой колонке
   ├─ template.py            клон файла с заменой плейсхолдеров
   ├─ deck.py                таблица → презентация
   ├─ drive_extra.py         метаданные, переименование, корзина, права
   ├─ comments.py            комментарии Drive: чтение, создание, ответ, решение
   ├─ doc_edit.py            поиск и замена внутри документа
   ├─ sheets_extra.py        условное форматирование, графики
   ├─ sheets_structure.py    листы, строки, объединение ячеек
   ├─ sheets_more.py         колонки и сортировка
   ├─ doc_media.py           картинки в документах
   ├─ doc_format.py          жирный/курсив/заголовки для найденного текста
   ├─ sheets_pivot.py        сводные таблицы
   ├─ gmail_drafts.py        список, обновление и удаление черновиков
   ├─ gmail_filters.py       фильтры: список и создание
   ├─ sheets_validate.py     валидация, защита, границы
   ├─ gmail_labels.py        метки и массовые флаги писем
   ├─ drive.py  sheets.py  docs.py
   ├─ gmail.py  calendar.py  apps_script.py
tests/                       юнит-, живые и round-trip проверки
antigravity/                 готовый mcp_config.json
skills/google-workspace/     Agent Skill: когда какой инструмент
```

Принципы:

* каждый обработчик возвращает строку — исключения не выходят в транспорт;
* запись только через стейджинг, подтверждение или черновик;
* Apps Script — двухфазный коммит с автоматическим бэкапом;
* серверные профили держат поверхность маленькой.

## Тестирование

```bash
python -m unittest discover -s tests -v     # 284 юнит-тестов, без сети
python tests/live_smoke.py                  # 51 проверка на реальном аккаунте
python tests/live_new_tools.py              # 15 проверок партии v1.14
python tests/live_phase2.py                 # 8 проверок партии v1.15
python tests/live_phase3.py                 # 8 проверок партии v1.16
python tests/live_phase4.py                 # 5 проверок партии v1.17
python tests/live_phase5.py                 # 7 проверок партии v1.18
python tests/pptx_roundtrip.py deck.pptx    # 5 проверок: pptx → Slides → замена
```

Живой набор самоочищается: загружает и удаляет временный файл, создаёт и удаляет
презентацию и таблицу, создаёт и удаляет черновик ответа, скачивает и удаляет
вложение. `tests/test_docs.py` держит README, документацию и код согласованными
(количество инструментов, числа профилей, ссылки, примеры).

## Документация

### 🇷🇺 На русском
| Документ | Описание |
|---|---|
| [AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) | Пошаговая настройка OAuth |
| [TOOLS_REFERENCE.md](docs/ru/TOOLS_REFERENCE.md) | Справочник инструментов |
| [SECURITY.md](docs/ru/SECURITY.md) | Скоупы, профили, модель безопасности |
| [IDE_SETUP.md](docs/ru/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [TROUBLESHOOTING.md](docs/ru/TROUBLESHOOTING.md) | Симптом → причина → решение, включая Docker |

### 🇬🇧 English
| Document | Description |
|---|---|
| [AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup |
| [TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | Full tool reference |
| [SECURITY.md](docs/SECURITY.md) | Scopes, profiles, safety model |
| [IDE_SETUP.md](docs/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Symptom → fix, including Docker |
| [LEARN.md](LEARN.md) | How this server was built |
| [docs/](docs/) | Release notes and specs |

## Ограничения

Границы возможностей — часть контракта:

- **Drive**: удаление — это «в корзину»; `drive_empty_trash` — единственный
  необратимый путь, требует `confirm=true`.
- **Sheets**: листы, строки, колонки, объединение, сортировка, сводные таблицы,
  валидация, защита и границы поддержаны; графики базовых типов, условное
  форматирование — одно правило за вызов.
- **Docs**: стилизация найденного текста работает; таблицы создаёт инструмент
  отчёта, но редактировать их по ячейкам потом нельзя.
- **Slides**: слайды, заметки и нативные таблицы работают; фигур, диаграмм и
  стилизации отдельных фигур нет.
- **Один аккаунт на сервер**: один OAuth-токен, мультиаккаунтности нет.

## План

- [x] Кросс-поиск и профили инструментов
- [x] Файлы, Slides, запуск Apps Script
- [x] Форматирование Sheets
- [x] Треды, вложения и ответы в Gmail
- [x] Calendar: обновление, удаление, ответ на приглашения
- [x] Составные: `report_from_sheet`, `digest`, `compare_tables`, `clone_and_fill`
- [x] Опциональный HTTP-транспорт (Streamable HTTP, stateless, localhost-first)

## Ответственность

Вы отвечаете за то, что агент делает с вашим аккаунтом. Прочитайте
[docs/ru/SECURITY.md](docs/ru/SECURITY.md), начните с `read-only` и держите бэкапы.

---

<div align="center">

Лицензия MIT · сделано на [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

</div>
