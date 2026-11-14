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

## Scope-routing

На старте сервер читает Google-скоупы из `token.json` и скрывает инструменты
без нужного скоупа. Если token file отсутствует или список пуст, фильтрация
пропускается с предупреждением.

Примеры:

- нет `presentations` → нет Slides (в 2.0 их и так нет);
- только `drive.readonly` → `drive_write`, `drive_trash`, `drive_permissions`
  скрыты;
- только `gmail.readonly` → `gmail_write`, `gmail_settings`, `gmail_delete`
  скрыты.

`workspace_search`, `digest`, `compare_tables` и `bulk_*` кросс-доменные и
остаются видимыми; при недоступном источнике они вернут частичную ошибку.

## Проверить, что активно

```bash
python -m workspace_operator tools --profile core
python -m workspace_operator doctor
curl http://127.0.0.1:8765/healthz
```

Аудит-лог пишет профиль и имя инструмента/действия, но не значения аргументов.

## Безопасные значения по умолчанию

- destructive-действия требуют `confirm=true`;
- удаление Drive — только корзина, без `drive_empty_trash`;
- публичный шаринг требует `allow_public_sharing=true` и `allow_public=true`;
- `dry_run` превращает запись в предпросмотр;
- для максимальной изоляции — read-only скоупы и профиль `read-only`.
