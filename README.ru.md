<div align="center">

# Google Workspace MCP — глубокая автоматизация

**Apps Script со стейджингом и откатом · шаблоны документов · кросс-поиск · локальные файлы · Slides · профили**

MCP-сервер, который даёт ИИ-агенту реальный контроль над Google Drive, Sheets, Docs, Gmail
и Calendar — и закрывает то, чего нет в официальных серверах Google.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.x-blueviolet?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io)
[![Tools](https://img.shields.io/badge/tools-55-informational)](#-все-инструменты)
[![Antigravity](https://img.shields.io/badge/Antigravity-ready-4285F4?logo=google&logoColor=white)](antigravity/README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

</div>

---

## Зачем ещё один Google MCP-сервер?

В 2026 у Google есть свои Workspace MCP-серверы: девять удалённых эндпоинтов за OAuth
и открытое локальное расширение. Они хорошо справляются с поиском, чтением и написанием
черновиков — и на этом останавливаются.

Этот сервер берёт на себя остальное: **жизненный цикл проектов Apps Script**, **заполнение
шаблонов документов**, **пакетные операции с dry-run**, **глубокую работу с Sheets**
(фильтры, именованные диапазоны, поиск с заменой) и **единый поиск по Drive, Gmail и Calendar**.

| | Workspace MCP от Google (remote) | Официальное локальное расширение | **Этот сервер** |
|---|---|---|---|
| Транспорт | Streamable HTTP, хостинг Google | stdio | **stdio, локально** |
| Доступность | Developer Preview | публично | **публично, MIT** |
| Apps Script | — | — | **создание · чтение · стейджинг · запуск · отмена · откат** |
| Шаблоны документов | — | — | **`doc_fill_template`** |
| Пакетные операции | — | — | **пакетное удаление, метки, dry-run** |
| Глубина Sheets | чтение диапазонов | частично | **фильтры, именованные диапазоны, find & replace, CSV** |
| Презентации | — | — | **создание, слайды, замена текста, картинки** |
| Кросс-поиск | `search_corpus` | — | **`workspace_search`** |
| Профили инструментов на сервере | IAM / allow-list админа | — | **read-only / read-write / full + allow-deny** |
| Путь данных | эндпоинт MCP Google | локально | **локально, свой OAuth-клиент** |

> Официальные серверы — правильный выбор для «спроси у почты».
> Этот — для «измени рабочее пространство так, чтобы можно было откатить».

---

## ✨ Что умеет

| Сервис | Возможности |
|---------|-------------|
| 🔎 **Кросс-поиск** | Один запрос по Drive + Gmail + Calendar, объединение и сортировка по дате |
| 📁 **Drive** | Поиск, копирование, перемещение, шаринг, права, отзыв публичного доступа |
| 💾 **Файлы** | Загрузка локальных файлов, скачивание, экспорт Docs/Sheets/Slides в pdf/docx/xlsx/pptx |
| 📊 **Sheets** | Чтение и запись диапазонов, фильтры, именованные диапазоны, find & replace, экспорт CSV |
| 📄 **Docs** | Чтение (включая таблицы), создание, дописывание, шаблоны, экспорт в PDF |
| 🖼 **Slides** | Создание презентаций, слайды, замена плейсхолдеров, картинки |
| 📧 **Gmail** | Черновики, отправка, поиск, архив, метки, удаление с подтверждением |
| 📅 **Calendar** | Список событий, свободные слоты, встречи с участниками |
| ⚙️ **Apps Script** | Создание, чтение, стейджинг обновлений, запуск с бэкапом, откат |
| 🔗 **Ресурсы** | Живые снимки Drive / Gmail / Calendar / Sheets / Docs прямо в контексте |
| 💬 **Промпты** | Готовые сценарии: сводка почты, анализ таблицы, план недели, поиск файлов |

**55 инструментов · 3 ресурса · 3 шаблона ресурсов · 4 промпта** — у каждого инструмента
есть аннотации `readOnlyHint` / `destructiveHint`, чтобы клиент предупреждал об опасных действиях.

---

## 🚀 Быстрый старт

### 1 — Установка

```bash
git clone https://github.com/Artoxem/yet-another-google-mcp.git
cd yet-another-google-mcp
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2 — Google OAuth

Создайте OAuth 2.0 Client ID (Desktop app) в [Google Cloud Console](https://console.cloud.google.com/),
включите Drive / Docs / Sheets / Gmail / Calendar / Apps Script API, скачайте JSON.

Включите Drive, Docs, Sheets, Slides, Gmail, Calendar и Apps Script API. Обновляетесь с 1.1?
Переавторизуйтесь один раз — в 1.2 добавлен скоуп Slides.

> Пошагово: [docs/ru/AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) · [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md)

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
не начнёт обрабатывать инструменты. Подробности — [docs/ru/SECURITY.md](docs/ru/SECURITY.md).

### 4 — Подключение клиента

<details open>
<summary><strong>Google Antigravity</strong> — рекомендуется</summary>

Antigravity App, IDE и CLI читают один файл `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "python",
      "args": ["D:\\DEV\\yet-another-google-mcp\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\yet-another-google-mcp\\config.yaml",
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
<summary><strong>Claude Desktop / Cursor / VS Code / Windsurf</strong></summary>

```json
{
  "mcpServers": {
    "google-tools": {
      "command": "python",
      "args": ["D:\\DEV\\yet-another-google-mcp\\server.py"],
      "env": {
        "MCP_CONFIG_FILE": "D:\\DEV\\yet-another-google-mcp\\config.yaml",
        "MCP_AUTH_TOKEN": "MySecretToken_2026!"
      }
    }
  }
}
```

Пути для конкретных клиентов и диагностика: [docs/ru/IDE_SETUP.md](docs/ru/IDE_SETUP.md).

</details>

---

## 🛡 Профили инструментов

Профиль — это серверный allow-list: инструменты вне профиля не показываются и не вызываются.
Он дополняет OAuth-скоупы (что разрешает Google) и права клиента (что агенту можно без спроса).

| Профиль | Инструментов | Когда использовать |
|---|---:|---|
| `full` | 55 | своя машина, полное доверие |
| `read-write` | 48 | ежедневная работа — деструктивные скрыты |
| `read-only` | 19 | разведка, демо, общие машины, недоверенные агенты |

```yaml
tool_profile: "read-write"
# Необязательно, применяется поверх профиля. Deny важнее allow.
allowed_tools: ["workspace_search", "find_files", "read_sheet", "read_email"]
denied_tools: ["send_email", "share_file"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
Заблокированный вызов возвращает понятную ошибку, а не молчит.

---

## 🔎 `workspace_search`

Локальный ответ `search_corpus` — один запрос, три продукта, один список:

```json
{"query": "бюджет Q3", "sources": "drive,gmail,calendar", "limit": 10}
```

```
Workspace search: 'бюджет Q3' — 6 result(s) [drive (3), gmail (2), calendar (1)]

1. [drive] Бюджет 2026 — spreadsheet
   2026-03-02 10:11 UTC | type: spreadsheet | id: 1a2b3c
   https://docs.google.com/spreadsheets/d/1a2b3c
2. [gmail] Согласование бюджета Q3
   2026-02-27 09:14 UTC | from: cfo@corp.io | id: 18f4d2
   Прошу согласовать бюджет Q3 до пятницы.
```

Частичные сбои не фатальны: если Gmail недоступен, придут результаты Drive
и пометка `Partial results`.

---

## 🧯 Безопасность по умолчанию

| Защита | Инструменты |
|-------|-------------|
| Требуется `confirm=true` | `delete_email`, `gmail_archive`, `calendar_create_meeting`, `drive_revoke_public`, `doc_fill_template` |
| `dry_run=true` по умолчанию | `batch_delete_emails`, `sheet_find_replace`, `gmail_label_apply` |
| Авто dry-run для больших диапазонов | `clear_range` |
| Режим черновика | `send_email` (не отправит без `draft_mode=false`) |
| Публичный шаринг заблокирован | `share_file` не даёт `type=anyone` без `allow_public=true` |
| Стейджинг Apps Script | `prepare_script_update` → `execute_operation` (с бэкапом) |
| Аннотации инструментов | у каждого — `readOnlyHint` / `destructiveHint` |
| Серверный профиль | `read-only` / `read-write` / `full` + allow/deny |

> ⚠️ Агент получает доступ ко всему, что разрешает ваш OAuth-токен. Для чувствительных
> аккаунтов используйте read-only скоупы и профиль `read-only`. Детали: [docs/ru/SECURITY.md](docs/ru/SECURITY.md).

---

## 📦 Все инструменты

<details>
<summary>🔎 Кросс-поиск (1)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `workspace_search` | read | Один запрос по Drive, Gmail и Calendar, объединение и сортировка |

</details>

<details>
<summary>📁 Drive (8)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `find_files` | read | Поиск по имени или запросу Drive |
| `drive_search_advanced` | read | Полный синтаксис запросов Drive |
| `drive_list_permissions` | read | Список прав на файл |
| `create_folder` | write | Создать папку |
| `move_file` | write | Переместить файл |
| `drive_copy_file` | write | Копировать файл |
| `share_file` | write | Поделиться с пользователем/группой/доменом |
| `drive_revoke_public` | destructive | Отозвать публичный доступ (`confirm=true`) |

</details>

<details>
<summary>💾 Файлы (3)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `drive_upload` | write | Загрузить локальный файл; `convert_to` превращает docx/xlsx/pptx в Google-файлы |
| `drive_download` | read | Скачать бинарный файл Drive на диск |
| `drive_export` | read | Экспорт Doc/Sheet/Slide в pdf, docx, xlsx, pptx, csv… |

</details>

<details>
<summary>📊 Sheets (11)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `read_sheet` | read | Прочитать диапазон |
| `get_spreadsheet_meta` | read | Метаданные таблицы |
| `sheet_export_csv` | read | Экспорт диапазона в CSV |
| `append_row` | write | Добавить строку |
| `update_sheet` | write | Записать строки в диапазон |
| `create_spreadsheet` | write | Создать таблицу |
| `add_sheet` | write | Добавить лист |
| `sheet_create_filter_view` | write | Создать фильтр |
| `sheet_create_named_range` | write | Создать именованный диапазон |
| `sheet_find_replace` | write | Поиск и замена (`dry_run=true` по умолчанию) |
| `clear_range` | destructive | Очистить диапазон (авто dry-run для больших) |

</details>

<details>
<summary>📄 Docs (5)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `read_doc` | read | Прочитать текст документа |
| `doc_export_pdf` | read | Экспорт в PDF |
| `create_doc` | write | Создать документ |
| `append_to_doc` | write | Дописать текст |
| `doc_fill_template` | destructive | Заполнить шаблон (`confirm=true`) |

</details>

<details>
<summary>🖼 Slides (5)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `slides_create` | write | Создать презентацию |
| `slides_get` | read | Количество слайдов, ID и текст по слайдам |
| `slides_add_slide` | write | Добавить слайд с готовым макетом |
| `slides_replace_text` | destructive | Замена плейсхолдеров (`confirm=true`) |
| `slides_insert_image` | write | Вставить картинку по публичному URL |

</details>

<details>
<summary>📧 Gmail (11)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `get_gmail_profile` | read | Адрес авторизованного пользователя |
| `list_emails` | read | Список писем с датой, отправителем и темой |
| `read_email` | read | Заголовки, метки, вложения и тело письма |
| `gmail_search_and_summarize` | read | Поиск с краткой сводкой |
| `create_draft` | write | Создать черновик |
| `send_email` | write | Отправить или создать черновик (`draft_mode=true`) |
| `send_draft` | write | Отправить существующий черновик |
| `gmail_label_apply` | write | Навесить метку (`dry_run=true`) |
| `gmail_archive` | write | Архивировать (`confirm=true`) |
| `delete_email` | destructive | Удалить письмо (`confirm=true`) |
| `batch_delete_emails` | destructive | Удалить несколько (`dry_run=true`) |

</details>

<details>
<summary>📅 Calendar (4)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `list_events` | read | Ближайшие события |
| `calendar_find_free_slots` | read | Свободные слоты |
| `create_event` | write | Создать событие |
| `calendar_create_meeting` | write | Встреча с участниками (`confirm=true`) |

</details>

<details>
<summary>⚙️ Apps Script (6)</summary>

| Инструмент | Тип | Описание |
|------|------|-------------|
| `get_script_content` | read | Прочитать файлы проекта |
| `create_script_project` | write | Создать проект |
| `prepare_script_update` | write | Подготовить обновление, вернуть `operation_id` |
| `execute_operation` | write | Применить обновление (с бэкапом) |
| `cancel_operation` | write | Отменить подготовленное обновление |
| `restore_script_backup` | write | Восстановить из бэкапа |
| `script_run_function` | destructive | Запустить функцию из API-executable деплоя |

</details>

### Ресурсы

| URI | Что отдаёт |
|---|---|
| `gdrive://recent` | 20 последних изменённых файлов Drive |
| `gmail://inbox` | Непрочитанные письма |
| `gcalendar://upcoming` | События на 7 дней |
| `gdrive://file/{file_id}` | Метаданные файла |
| `gsheets://{spreadsheet_id}/{range}` | Диапазон таблицы как таблица |
| `gdocs://{document_id}` | Полный текст документа |

### Промпты

| Промпт | Что делает |
|--------|-------------|
| `summarize_inbox` | Собирает письма → готово для сводки |
| `analyze_spreadsheet` | Читает диапазон → готово для анализа |
| `plan_week` | Загружает события → готово для планирования |
| `search_drive` | Ищет файлы → готово для разбора |

---

## 🏗 Как устроено

```
server.py                  MCP-сервер: 55 инструментов, ресурсы, промпты, профили
mcp_google/
├─ profiles.py             read-only / read-write / full + allow-deny
├─ text.py                 нормализация текста, таймстампов и ошибок
├─ config.py               конфиг + переменные окружения
├─ auth.py                 OAuth 2.0, кэш токена
├─ operations.py           хранилище подготовленных операций (Apps Script)
├─ security.py             проверки токена и email
└─ handlers/
   ├─ search.py            workspace_search — Drive + Gmail + Calendar
   ├─ files.py             drive_upload / drive_download / drive_export
   ├─ slides.py            Slides: создание, чтение, слайды, картинки
   ├─ drive.py  sheets.py  docs.py
   ├─ gmail.py  calendar.py  apps_script.py
tests/                     юнит-тесты без сети
antigravity/               готовый mcp_config.json
skills/google-workspace/   Agent Skill: когда какой инструмент
```

Принципы:

* **Обработчик всегда возвращает строку** — исключения не выходят в транспорт.
* **Запись — только через стейджинг или подтверждение**: dry-run, `confirm=true`, черновики.
* **Apps Script — двухфазный коммит**: prepare → `operation_id` → execute, перед этим бэкап.
* **Сначала поиск, потом чтение, потом запись** — зафиксировано в Agent Skill.

---

## 🧪 Разработка

```bash
python -m unittest discover -s tests -v
```

66 тестов: профили, разбор поиска, нормализация текста, таблицы Docs, работа с путями и
хелперы v1.2. Без креденшелов и сети.

`tests/live_smoke.py` — 30 сквозных проверок на реальном аккаунте с самоочисткой.

---

## 📚 Документация

### 🇷🇺 На русском
| Документ | Описание |
|----------|----------|
| [AUTH_SETUP.md](docs/ru/AUTH_SETUP.md) | Пошаговая настройка OAuth |
| [TOOLS_REFERENCE.md](docs/ru/TOOLS_REFERENCE.md) | Справочник инструментов, ресурсов и промптов |
| [SECURITY.md](docs/ru/SECURITY.md) | Скоупы, профили, модель безопасности |
| [IDE_SETUP.md](docs/ru/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |

### 🇬🇧 English
| Document | Description |
|----------|-------------|
| [AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup |
| [TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) | Full tool reference |
| [SECURITY.md](docs/SECURITY.md) | Scopes, profiles, safety model |
| [IDE_SETUP.md](docs/IDE_SETUP.md) | Antigravity, Cursor, Windsurf, VS Code |
| [LEARN.md](LEARN.md) | How this server was built |

---

## 🗺 План

- [x] `workspace_search` — кросс-поиск
- [x] Профили инструментов (`read-only` / `read-write` / `full`)
- [x] Конфиг Antigravity + Agent Skill
- [x] `drive_upload` / `drive_download` / `drive_export`
- [x] Slides: создание, слайды, замена текста, картинки
- [x] `script_run_function` для API-executable деплоев
- [ ] Docs: замена текста и форматирование
- [ ] Фильтры `workspace_search` по типу и дате
- [ ] Опциональный HTTP-транспорт для команд (stateless, MCP 2026-07-28)

---

## ⚠️ Ответственность

Вы отвечаете за то, что агент делает с вашим аккаунтом. Прочитайте
[docs/ru/SECURITY.md](docs/ru/SECURITY.md), начните с `read-only` и держите бэкапы включёнными.

---

<div align="center">

Сделано с ❤️ на [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) ·
лицензия MIT

</div>
