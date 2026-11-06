<div align="center">

# Workspace Operator

**Глубокая автоматизация Google Workspace через Model Context Protocol**

Drive · Docs · Sheets · Slides · Gmail · Calendar · Apps Script — один локальный
MCP-сервер с 63 инструментами, многошаговыми записями и профилями на стороне сервера.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.x-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-66-informational)](#-каталог-инструментов)
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

**66 инструментов · 3 ресурса · 3 шаблона ресурсов · 4 промпта**, у каждого инструмента
аннотации `readOnlyHint` / `destructiveHint`.

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
| 📁 Drive | 8 | Поиск, перемещение, копирование, шаринг, права, отзыв публичного доступа |
| 💾 Файлы Drive | 3 | Загрузка, скачивание, экспорт, конвертация в нативные форматы |
| 📊 Sheets | 12 | Чтение и запись, форматирование, фильтры, именованные диапазоны, CSV |
| 📄 Docs | 5 | Чтение (включая таблицы), дописывание, шаблоны, экспорт в PDF |
| 🖼 Slides | 5 | Создание презентаций, слайды, замена текста, картинки |
| ⚙️ Apps Script | 7 | Стейджинг с бэкапами, откат, запуск функций |
| 📧 Gmail | 14 | Треды, вложения, ответы, черновики, метки, пакетное удаление |
| 📅 Calendar | 7 | События, слоты, встречи, изменение/удаление, ответ на приглашения |
| 🧩 Составные | 4 | отчёт из таблицы, дайджест, сравнение таблиц, клон шаблона |

Плюс 3 ресурса, 3 шаблона ресурсов и 4 промпта — см. [каталог](#-каталог-инструментов).

## Быстрый старт

### 1 — Установка

```bash
git clone https://github.com/Artoxem/workspace-operator.git
cd workspace-operator
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Нужен Python 3.10+. В PyPI пакета пока нет — установка из исходников.

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
| `full` | 66 | своя машина, полное доверие |
| `read-write` | 58 | ежедневная работа — деструктивные скрыты |
| `read-only` | 21 | разведка, демо, общие машины, недоверенные агенты |

```yaml
tool_profile: "read-write"
# Необязательно, применяется поверх профиля. Запрет важнее разрешения.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS`.
Заблокированный вызов возвращает понятное объяснение, а не молчит.

## Каталог инструментов

<details>
<summary>🔎 Кросс-поиск (1)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `workspace_search` | read | Один запрос по Drive, Gmail и Calendar; сортировка по дате, частичные сбои не фатальны |

</details>

<details>
<summary>📁 Drive (8)</summary>

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
<summary>📊 Sheets (12)</summary>

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

</details>

<details>
<summary>📄 Docs (5)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `read_doc` | read | Текст и таблицы |
| `doc_export_pdf` | read | Экспорт в бинарный PDF |
| `create_doc` | write | Создать документ |
| `append_to_doc` | write | Дописать текст |
| `doc_fill_template` | destructive | Заполнить шаблон (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (5)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `slides_create` | write | Создать презентацию |
| `slides_get` | read | Количество слайдов, ID и текст |
| `slides_add_slide` | write | Добавить слайд с готовым макетом |
| `slides_replace_text` | destructive | Замена плейсхолдеров (`confirm=true`) |
| `slides_insert_image` | write | Вставить картинку по публичному URL |

</details>

<details>
<summary>⚙️ Apps Script (7)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `get_script_content` | read | Прочитать файлы проекта |
| `create_script_project` | write | Создать проект |
| `prepare_script_update` | write | Подготовить обновление, вернуть `operation_id` |
| `execute_operation` | write | Применить обновление (сначала бэкап) |
| `cancel_operation` | write | Отменить подготовленное обновление |
| `restore_script_backup` | write | Восстановить из бэкапа |
| `script_run_function` | destructive | Запустить функцию из API-executable деплоя |

</details>

<details>
<summary>📧 Gmail (14)</summary>

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

</details>

<details>
<summary>🧩 Составные (4)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `report_from_sheet` | write | Диапазон → статистика по колонкам → Doc или текст (`output=text`) |
| `digest` | write | Последние N часов по Gmail, Calendar и Drive → текст или Doc |
| `compare_tables` | write | Сравнение двух диапазонов по ключевой колонке: добавлено / удалено / изменено |
| `clone_and_fill` | write | Копия любого файла Drive с заменой плейсхолдеров |

</details>

<details>
<summary>📅 Calendar (7)</summary>

| Инструмент | Тип | Описание |
|---|---|---|
| `list_events` | read | Ближайшие события со временем и местом |
| `calendar_find_free_slots` | read | Свободные слоты в окне |
| `create_event` | write | Создать событие |
| `calendar_create_meeting` | write | Встреча с участниками (`confirm=true`) |
| `calendar_update_event` | write | Изменить любое поле; меняется только переданное |
| `calendar_delete_event` | destructive | Удалить событие (`confirm=true`) |
| `calendar_respond_to_invite` | write | Принять / отклонить / под вопросом (`confirm=true`) |

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

## Безопасность по умолчанию

| Защита | Инструменты |
|---|---|
| Требуется `confirm=true` | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template`, `slides_replace_text` |
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
server.py                    MCP-сервер: 63 инструмента, ресурсы, промпты, профили
workspace_operator/
├─ profiles.py               read-only / read-write / full + allow-deny
├─ config.py                 конфиг + переменные окружения
├─ auth.py                   OAuth 2.0 и кэш токена
├─ text.py                   нормализация текста, таймстампов и ошибок
├─ operations.py             хранилище подготовленных операций Apps Script
├─ security.py               проверки токена и email
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
python -m unittest discover -s tests -v     # 168 юнит-тестов, без сети
python tests/live_smoke.py                  # 45 проверок на реальном аккаунте
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

### 🇬🇧 English
| Document | Description |
|---|---|
| [AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup |
| [TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | Full tool reference |
| [SECURITY.md](docs/SECURITY.md) | Scopes, profiles, safety model |
| [IDE_SETUP.md](docs/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [LEARN.md](LEARN.md) | How this server was built |
| [docs/](docs/) | Release notes and specs |

## План

- [x] Кросс-поиск и профили инструментов
- [x] Файлы, Slides, запуск Apps Script
- [x] Форматирование Sheets
- [x] Треды, вложения и ответы в Gmail
- [x] Calendar: обновление, удаление, ответ на приглашения
- [x] Составные: `report_from_sheet`, `digest`, `compare_tables`, `clone_and_fill`
- [ ] Опциональный HTTP-транспорт (stateless, MCP 2026-07-28)

## Ответственность

Вы отвечаете за то, что агент делает с вашим аккаунтом. Прочитайте
[docs/ru/SECURITY.md](docs/ru/SECURITY.md), начните с `read-only` и держите бэкапы.

---

<div align="center">

Лицензия MIT · сделано на [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

</div>
