# Как выбрать профиль

Workspace Operator 2.0 содержит 39 консолидированных инструментов. Профиль
`core` по умолчанию показывает 20; для каждого клиента можно выбрать более
узкую или широкую поверхность.

## Профили

| Профиль | Инструментов | Что входит | Для чего |
|---|---:|---|---|
| `read-only` | 17 | только чтение и поиск | разведка, недоверенные агенты, демо |
| `core` (по умолчанию) | 20 | повседневное чтение/запись, обратимая корзина, bulk plan/run/status | почта и документы |
| `read-write` | 30 | запись без destructive | автоматизация без удаления |
| `full` | 39 | форматирование, destructive, Forms, Postmaster, Script | опытные пользователи и админы |

`core` не включает `docs_edit`, `sheets_format`, `sheets_structure`,
`sheets_delete`, `sheets_data`, `gmail_settings`, `calendar_delete`,
`drive_permissions`, Forms, Postmaster и Apps Script. Для них нужен `full`.

## Кому какой профиль

| Вы | Начните с | Почему |
|---|---|---|
| Аналитик/исследователь | `read-only` | нет записи, минимум контекста |
| Ассистент почты | `core` | письма, треды, черновики, корзина |
| Редактор Docs/Sheets | `core`, затем `full` для форматирования | форматирование — opt-in |
| Автоматизатор | `full` + сначала `dry_run` | destructive требует confirm |
| Разработчик/админ | `full` | Script prepare/execute/deploy |
| Общая машина/демо | `read-only` | минимум прав |


## Эндпоинты профилей (HTTP)

При работе по HTTP у каждого профиля есть стабильный URL:

| URL | Профиль |
|---|---|
| `/mcp` | `tool_profile` из конфига (по умолчанию `core`) |
| `/mcp/read` | `read-only` |
| `/mcp/read-write` | `read-write` |
| `/mcp/full` | `full` |

Клиент подключается к нужному URL; список инструментов стабилен для соединения.
Все эндпоинты используют один bearer-токен и один аудит-лог.

## Настройка

Выбрать профиль на один запуск: `workspace-operator serve --profile full`. Флаг
перекрывает `tool_profile` в файле конфигурации и `MCP_TOOL_PROFILE`.

### stdio

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/.google/config.yaml",
        "MCP_AUTH_TOKEN": "длинная-случайная-строка",
        "MCP_TOOL_PROFILE": "core"
      }
    }
  }
}
```

### HTTP / Docker

```bash
MCP_TOOL_PROFILE=core
MCP_SCOPE_ROUTING=1
MCP_ALLOW_PUBLIC_SHARING=0
```

Сервер читает `tool_profile` из `config.yaml` или `MCP_TOOL_PROFILE`.
`allowed_tools` / `denied_tools` сужают выбранный профиль.

### Свой allow-list

```yaml
tool_profile: "full"
allowed_tools: ["workspace_search", "drive_read", "sheets_read", "gmail_read"]
denied_tools: ["gmail_write"]
```

Имена — новые консолидированные, не из 1.x. Запрет всегда важнее разрешения.

## Скоупы и инструменты

Видимый набор определяют два независимых фильтра:

1. **OAuth-скоупы** — что реально разрешает Google.
2. **Профиль** — что отдаёт сервер (`read-only`, `core`, `read-write`, `full`).

Scope-routing выполняется первым на старте: инструменты без нужного
Google-скоупа не показываются и не вызываются. Затем применяется профиль;
`allowed_tools` / `denied_tools` сужают его дальше.

Если `token.json` отсутствует или в нём нет списка скоупов, routing
пропускается с предупреждением: сервер пока не знает выданные скоупы.

| OAuth-скоуп(ы) | Какие инструменты видны |
|---|---|
| нет (кросс-доменные) | `workspace_search`, `digest`, `compare_tables`, `bulk_*` |
| `drive` или `drive.readonly` | `drive_search`, `drive_read` |
| `drive` | плюс `drive_write`, `drive_trash`, `drive_permissions` |
| `documents` или `documents.readonly` | `read_doc` |
| `documents` | плюс `docs_write`, `docs_edit` |
| `spreadsheets` или `spreadsheets.readonly` | `sheets_read` |
| `spreadsheets` | плюс `sheets_write`, `sheets_format`, `sheets_structure`, `sheets_delete`, `sheets_data` |
| `gmail.modify` или `gmail.readonly` | `gmail_read` |
| `gmail.modify` | плюс `gmail_write`, `gmail_delete` |
| `gmail.modify` + `gmail.settings.basic` | `gmail_settings` (нужны оба) |
| `calendar` или `calendar.readonly` | `calendar_read` |
| `calendar` | плюс `calendar_write`, `calendar_delete` |
| `tasks` или `tasks.readonly` | `tasks_read` |
| `tasks` | плюс `tasks_write` |
| `forms.body` + `forms.responses.readonly` | `forms_read`, `forms_write` (нужны оба) |
| `postmaster.domain` + `postmaster.traffic.readonly` | `postmaster_read` (нужны оба) |
| `script.projects` + `script.deployments` | `script_read`, `script_write`, `script_run` (нужны оба) |

Включение Google API — отдельный переключатель: скоуп может быть выдан, а API
выключен, тогда вызов вернёт 403. Включайте APIs по
[AUTH_SETUP.md](AUTH_SETUP.md).

### Минимальные наборы

```yaml
# Только Drive
scopes:
  - "https://www.googleapis.com/auth/drive"
```

```yaml
# Gmail чтение/запись, без администрирования меток и фильтров
scopes:
  - "https://www.googleapis.com/auth/gmail.modify"
```

```yaml
# Docs + Sheets только чтение
scopes:
  - "https://www.googleapis.com/auth/documents.readonly"
  - "https://www.googleapis.com/auth/spreadsheets.readonly"
```

Для остальных доменов нужны скоупы из таблицы. Убрали скоуп — инструменты
скрылись; добавили — переавторизуйтесь, и они вернутся.

### Если инструмента нет

1. Запустите `workspace-operator doctor` — он покажет недостающие скоупы.
2. Сравните `token.json` со таблицей выше.
3. Удалите `token.json`, запустите `workspace-operator doctor`, подтвердите доступ.
4. Проверьте профиль: `workspace-operator tools --profile core`.

Роутинг применяется один раз при старте. После изменения скоупов перезапустите
сервер или переподключите клиент.

### Роутинг выключен

`MCP_SCOPE_ROUTING=0` отключает скрытие. Инструменты могут быть видны, но
вернут `403 insufficientPermissions`; режим только для отладки.

Кросс-доменные `workspace_search`, `digest`, `compare_tables`, `bulk_*` не
имеют одного обязательного скоупа и остаются видимыми; при недоступном
источнике они возвращают частичную ошибку.

## Проверить, что активно

```bash
python -m workspace_operator tools --profile core
python -m workspace_operator doctor
curl http://127.0.0.1:8765/healthz
```

Аудит-лог пишет профиль и имя инструмента/действия, но не значения аргументов.

## Безопасные значения по умолчанию

- destructive-действия требуют approval человека (`approval_id`); одного `confirm=true` недостаточно;
- удаление Drive — только корзина, без `drive_empty_trash`;
- публичный шаринг требует `allow_public_sharing=true` и `allow_public=true`;
- `dry_run` превращает запись в предпросмотр;
- для максимальной изоляции — read-only скоупы и профиль `read-only`.
