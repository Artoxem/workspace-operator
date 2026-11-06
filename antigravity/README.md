# Antigravity setup

Google Antigravity (App, IDE and CLI) reads MCP servers from one shared file:

| Scope | Path |
|---|---|
| Global | `~/.gemini/config/mcp_config.json` |
| Workspace | `<workspace>/.agents/mcp_config.json` |

## Install

1. Copy `mcp_config.example.json` into the global file (or merge the
   `mcpServers` object into your existing one).
2. Replace `command`/`args` with the absolute path to this repository and
   `MCP_AUTH_TOKEN` with your token.
3. Pick a profile:

   | `MCP_TOOL_PROFILE` | What the agent sees |
   |---|---|
   | `read-only` | 21 read tools — safe for exploration |
   | `read-write` | 58 tools, destructive ones hidden |
   | `full` | all 66 tools |

4. Restart the server: **Customizations → Installed → MCP servers → Refresh**
   (App/IDE) or `/mcp` (CLI).
5. Authenticate on first use — the server opens the Google OAuth flow and
   stores the token in `token_file`.

## Why `timeoutSeconds` matters

Apps Script operations (`execute_operation`) can take minutes. Antigravity
defaults to 180 s per tool call; the example raises it to 300 s.

## Eager vs lazy tools

Antigravity lazy-loads MCP tools by default: schemas are cached on disk and the
model fetches them on demand. Mark the two or three tools you use every day as
`"eager": true` to save a round-trip — leave the rest lazy to protect the
context window.

## Installing the Agent Skill (optional)

`skills/google-workspace/SKILL.md` teaches the agent *when* to reach for which
tool (search first, then read, then write). Copy the folder into your skills
directory or install it from Antigravity: **Customizations → Skills**.
