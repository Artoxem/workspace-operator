# Release v1.1.0 — deep automation

This release repositions the server from "another Google MCP" to the part of Google
Workspace that the official MCP servers do not cover.

## Highlights

### 🔎 `workspace_search` — cross-product search

One query across Drive, Gmail and Calendar, merged and sorted by date. This is the
local counterpart of `search_corpus` from Google's managed Workspace MCP servers and
the biggest functional gap this project had.

```json
{"query": "Q3 budget", "sources": "drive,gmail,calendar", "limit": 10}
```

Partial failures are reported inline instead of aborting the call.

### 🛡 Tool profiles

`tool_profile` controls which tools exist at all — enforced in both `tools/list`
and `tools/call`.

| Profile | Tools |
|---|---:|
| `full` | 46 |
| `read-write` | 41 |
| `read-only` | 16 |

Plus `allowed_tools` / `denied_tools` lists and the `MCP_TOOL_PROFILE`,
`MCP_ALLOWED_TOOLS`, `MCP_DENIED_TOOLS` environment variables.

### 🚀 Antigravity packaging

- `antigravity/mcp_config.example.json` — ready-to-paste configuration with
  `timeoutSeconds`, profile selection and eager tools.
- `antigravity/README.md` — install walkthrough.
- `skills/google-workspace/SKILL.md` — Agent Skill that teaches the agent
  search → read → write order and the Apps Script staging flow.

### 📖 Documentation

- Rewritten English README with a comparison against the official Google servers.
- New Russian README (`README.ru.md`).
- Updated `TOOLS_REFERENCE`, `SECURITY`, `IDE_SETUP` in both languages.

### 🧪 Tests

22 unit tests (`python -m unittest discover -s tests -v`) covering profile filtering
and search parsing/formatting. No credentials or network required.

`tests/live_smoke.py` — an opt-in end-to-end check against a real Google account:
17 assertions over the MCP handshake, tool/resource/prompt listing, real Drive,
Gmail and Docs calls, binary PDF export, profile enforcement and error propagation.
Read-only: it never writes to the account.

### 🐛 Protocol correctness

Tool failures are now reported with `isError: true` at the protocol level
(previously the flag was attached to a `TextContent` field that does not exist,
so clients saw plain text and could not distinguish a failure from a result).
All handler error messages are normalised to a single `Error ...` form.

## Breaking changes

- **Python 3.10+** is now required (the code already used 3.9+/3.10 syntax; the
  metadata was wrong).
- Default behaviour is unchanged: `tool_profile` defaults to `full`, so every tool
  stays visible until you opt into a narrower profile.

## Upgrade

```bash
git pull
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Nothing to migrate in `config.yaml`; add `tool_profile` when you want a narrower surface.

## Tool count

46 tools (was 45) + 1 cross-search. Resources and prompts unchanged.
