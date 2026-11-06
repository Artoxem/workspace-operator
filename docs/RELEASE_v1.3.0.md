# Release v1.3.0 — renamed to Workspace Operator

The project is no longer «yet another» Google MCP server. Same code, same
behaviour, new identity — done now, before the first PyPI publication, so nobody
ever has to migrate an import.

## What changed

| Layer | Before | After |
|---|---|---|
| Product name | MCP Google Tools / yet-another-google-mcp | **Workspace Operator** |
| Python package | `mcp_google/` | `workspace_operator/` |
| Distribution name | `yet-another-google-mcp` | `workspace-operator-mcp` |
| MCP server name | `My Google Tools` | `Workspace Operator` |
| Server version reported to clients | SDK version (`1.22.0`) | `1.3.0` — the actual release |
| Antigravity server key | `google-workspace` | `workspace-operator` |
| Local checkout | `D:\DEV\yet-another-google-mcp` | `D:\DEV\workspace-operator` |

## Protocol metadata

`initialize` now returns the real version and a short instruction block, so a
client knows the surface before listing tools:

```
Workspace Operator v1.3.0
«Workspace Operator gives you deep control over Google Workspace: Drive, Docs,
Sheets, Slides, Gmail, Calendar and Apps Script. Start with workspace_search for
open-ended questions, read before writing…»
```

## Breaking changes

- Import path: `from mcp_google…` → `from workspace_operator…`.
- Antigravity policies must use the new server key:
  `mcp(workspace-operator/workspace_search)` instead of `mcp(google-workspace/…)`.
- Existing `mcp_config.json` entries keep working only after the key is renamed —
  the tools themselves are unchanged.

## Unchanged

- 55 tools, profiles `full` 55 / `read-write` 48 / `read-only` 19.
- All OAuth scopes and config keys (`MCP_CONFIG_FILE`, `MCP_TOOL_PROFILE`, …).
- On-disk layout of `config.yaml`, tokens and backups.

## Verification

- 66 unit tests.
- 30 live end-to-end checks (`tests/live_smoke.py`).
- 5 pptx round-trip checks (`tests/pptx_roundtrip.py`).
- `initialize` confirms `Workspace Operator v1.3.0`.
