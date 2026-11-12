# Настройка IDE

Подключить редактор можно двумя способами:

- **stdio** — IDE сама запускает `workspace-operator serve` дочерним процессом.
  Лучший вариант для одного настольного клиента.
- **HTTP** — контейнер или `workspace-operator serve --http` работает в фоне;
  IDE подключается к `http://127.0.0.1:8765/mcp` с bearer-токеном.

Перед началом:

```bash
pip install workspace-operator-mcp
workspace-operator version
workspace-operator doctor        # одноразовая авторизация Google
```

В конфигах клиентов используйте абсолютные пути. В Windows либо удваивайте
обратные слэши (`C:\\Users\\you\\config.yaml`), либо пишите прямые
(`C:/Users/you/config.yaml`). Замените `your_token_here` на свой
`mcp_auth_token`; если переменная уже задана в окружении, блок `env` можно
опустить.

## stdio, любой клиент

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "/абсолютный/путь/config.yaml",
        "MCP_AUTH_TOKEN": "your_token_here"
      }
    }
  }
}
```

## HTTP, любой клиент с поддержкой URL

```json
{
  "mcpServers": {
    "workspace-operator": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer your_token_here" }
    }
  }
}
```

Контейнер уже должен работать (`docker compose up -d`), а Google-токен —
быть авторизован на хосте. См. раздел Docker в [README](../../README.ru.md).

## Cursor

- Проект: `.cursor/mcp.json`
- Глобально: `~/.cursor/mcp.json` (Windows: `C:\Users\<вы>\.cursor\mcp.json`)

Используйте stdio- или HTTP-блок выше.

## Windsurf

- Windows: `%APPDATA%\Codeium\Windsurf\mcp_config.json`
- macOS: `~/.codeium/windsurf/mcp_config.json`
- Linux: `~/.config/Codeium/Windsurf/mcp_config.json`

Используйте stdio- или HTTP-блок выше.

## VS Code (Copilot MCP)

VS Code 1.102+ с включённым Copilot.

- Рабочая область: `.vscode/mcp.json`
- Пользователь: команда **MCP: Open User Configuration**

VS Code использует ключ `servers` и явный `type`:

```json
{
  "servers": {
    "workspace-operator": {
      "type": "stdio",
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/config.yaml",
        "MCP_AUTH_TOKEN": "your_token_here"
      }
    }
  }
}
```

Для HTTP используйте `"type": "http"` с `"url"` и `"headers"`.

## Google Antigravity (App, IDE, CLI)

Все три поверхности читают один файл: `~/.gemini/config/mcp_config.json`
(глобально) или `<workspace>/.agents/mcp_config.json` (на проект).

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/config.yaml",
        "MCP_AUTH_TOKEN": "your_token_here",
        "MCP_TOOL_PROFILE": "read-write"
      },
      "timeoutSeconds": 300,
      "tools": { "workspace_search": { "eager": true } }
    }
  }
}
```

Замечания:

- `timeoutSeconds` по умолчанию 180 с; операциям Apps Script нужно больше.
- Инструменты ленивые — отметьте два-три ежедневных как `"eager": true`.
- Права по умолчанию **Ask**; политики выглядят как
  `mcp(workspace-operator/workspace_search)`.

Готовый файл: [`antigravity/mcp_config.example.json`](../../antigravity/mcp_config.example.json) ·
инструкция: [`antigravity/README.md`](../../antigravity/README.md).

## Другие клиенты

Найдите файл конфигурации MCP и повторите stdio-блок. Верхний ключ может
называться `mcpServers`, `servers` или `context_servers`; поля обычно
`command`, `args`, `env`.

## Проверка

После подключения вызовите `get_gmail_profile()`. Ответ с вашим адресом значит,
что команда, путь к конфигу, OAuth-токен и профиль работают.
