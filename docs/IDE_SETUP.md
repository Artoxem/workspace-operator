# IDE setup

Two ways to connect an editor:

- **stdio** — the IDE launches `workspace-operator serve` as a child process.
  Best for one desktop client.
- **HTTP** — a container or `workspace-operator serve --http` runs in the
  background; the IDE connects to `http://127.0.0.1:8765/mcp` with a bearer
  token.

Before you start:

```bash
pip install workspace-operator-mcp
workspace-operator version
workspace-operator doctor        # one-time Google authorization
```

Use absolute paths in client configs. On Windows either double the backslashes
(`C:\\Users\\you\\config.yaml`) or use forward slashes
(`C:/Users/you/config.yaml`). Replace `your_token_here` with your
`mcp_auth_token`; if the variable is already set in the environment, the `env`
block can be omitted.

## stdio, any client

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "/absolute/path/config.yaml",
        "MCP_AUTH_TOKEN": "your_token_here"
      }
    }
  }
}
```

## HTTP, any client that supports a URL

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

The container must already be running (`docker compose up -d`) and the Google
token must have been authorized on the host. See the Docker section of the
[README](../README.md).

## Cursor

- Project: `.cursor/mcp.json`
- Global: `~/.cursor/mcp.json` (Windows: `C:\Users\<you>\.cursor\mcp.json`)

Use the stdio or HTTP block above.

## Windsurf

- Windows: `%APPDATA%\Codeium\Windsurf\mcp_config.json`
- macOS: `~/.codeium/windsurf/mcp_config.json`
- Linux: `~/.config/Codeium/Windsurf/mcp_config.json`

Use the stdio or HTTP block above.

## VS Code (Copilot MCP)

VS Code 1.102+ with Copilot enabled.

- Workspace: `.vscode/mcp.json`
- User: command **MCP: Open User Configuration**

VS Code uses `servers` and an explicit `type`:

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

For HTTP use `"type": "http"` with `"url"` and `"headers"`.

## Google Antigravity (App, IDE, CLI)

All three surfaces read the same file: `~/.gemini/config/mcp_config.json`
(global) or `<workspace>/.agents/mcp_config.json` (per project).

```json
{
  "mcpServers": {
    "workspace-operator": {
      "command": "workspace-operator",
      "args": ["serve"],
      "env": {
        "MCP_CONFIG_FILE": "C:/Users/you/config.yaml",
        "MCP_AUTH_TOKEN": "your_token_here",
        "MCP_TOOL_PROFILE": "core"
      },
      "timeoutSeconds": 300,
      "tools": { "workspace_search": { "eager": true } }
    }
  }
}
```

Notes:

- `timeoutSeconds` default is 180 s; Apps Script operations need more.
- Tools are lazy-loaded — mark two or three daily drivers as `"eager": true`.
- Permissions default to **Ask**; policies look like
  `mcp(workspace-operator/workspace_search)`.

Ready-made file: [`antigravity/mcp_config.example.json`](../antigravity/mcp_config.example.json) ·
walkthrough: [`antigravity/README.md`](../antigravity/README.md).

## Other clients

Look for an MCP configuration file and reuse the stdio block. The top-level key
may be `mcpServers`, `servers` or `context_servers`; the fields are usually
`command`, `args` and `env`.

## Smoke check

After connecting, call `get_gmail_profile()`. A reply with your address means the
command, config path, OAuth token and profile all work.
