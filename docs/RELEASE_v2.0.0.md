# Workspace Operator 2.0.0

A smaller, safer, more predictable MCP surface.

## Highlights

- **39 consolidated tools** instead of 132 single-purpose tools.
- **Default `core` profile** with 20 tools and roughly 2 800 schema tokens.
- **Scope routing**: tools whose Google scope is missing are hidden at startup.
- **Profile endpoints** for HTTP: `/mcp`, `/mcp/read`, `/mcp/read-write`,
  `/mcp/full`.
- **No permanent Drive deletion**: `drive_trash` only moves to Trash.
- **Public sharing off by default**: requires `allow_public_sharing=true`.
- **Removed Slides and Drive comments**, plus overlapping and obsolete tools.

## Tool surface

| Profile | Tools |
|---|---:|
| `read-only` | 17 |
| `core` (default) | 20 |
| `read-write` | 30 |
| `full` | 39 |

Every tool carries `readOnlyHint` / `destructiveHint`. Destructive actions are
confirmed in the router before the handler runs.

## Safety changes

- `drive_empty_trash` removed; there is no permanent file-delete path.
- `drive_transfer_ownership` removed.
- `gmail_delete` moves messages to Trash.
- Public links require both `allow_public_sharing=true` and
  `allow_public=true`.
- `script_run` is destructive and confirm-gated.
- `scope_routing` hides tools that the token cannot use.
- `MCP_DRY_RUN` still turns writes into previews.

## Removed

Slides (11 tools + `presentations` scope), Drive comments (4), `drive_download`,
`drive_create_shortcut`, `drive_empty_trash`, `drive_transfer_ownership`,
`clone_and_fill`, `report_from_sheet`, `sheet_to_slides`, `doc_fill_template`,
`calendar_find_free_slots`, `create_event`, `batch_delete_emails`,
`doc_export_pdf`, `find_files`, `drive_search_advanced`, and the five standalone
draft tools.

See [MIGRATION_2.0.md](MIGRATION_2.0.md) for the old → new mapping.

## Configuration

```yaml
tool_profile: "core"
scope_routing: true
allow_public_sharing: false
```

Environment: `MCP_TOOL_PROFILE`, `MCP_SCOPE_ROUTING`,
`MCP_ALLOW_PUBLIC_SHARING`.

## OAuth

The default scope set is now 13 entries; `presentations` is no longer requested.
Existing tokens keep the extra scope until re-authorization; it is harmless.

## Compatibility

- Breaking: tool names and arguments changed; default profile changed.
- Old tool names are not exposed. Removed calls return `unknown tool`.
- No data migration; existing Google files, token and bulk data stay in place.
- 354 unit tests; in-memory MCP surface tests cover core/full/read-only and
  scope routing.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==2.0.0
# or
docker compose pull && docker compose up -d
```

Then run:

```bash
python -m workspace_operator doctor --offline
python -m workspace_operator tools --profile core
```
