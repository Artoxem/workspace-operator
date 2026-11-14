# Workspace Operator 2.0.1

Compatibility and verification release.

## Added

- **Hidden 1.x aliases**: retained old tool names are accepted for the 2.0.x
  line even though they are no longer listed in `tools/list`. The server maps
  them to the consolidated tool/action, so existing client configs keep working
  during migration.
- Aliases respect the active profile and scope routing: if the target is hidden,
  the call returns a clear "hidden by profile or scope" error.
- Removed capabilities (Slides, Drive comments, permanent deletion, ownership
  transfer, `drive_download`, composites, templates, free slots) return a
  migration error pointing to `docs/MIGRATION_2.0.md`.

## Verified on demo data

Two small live checks through the 2.0 surface:

1. **Read/write:** created a synthetic Google Doc, appended one paragraph, read
   it back and moved it to Trash.
2. **Safety:** confirmed that destructive tools and aliases require
   `confirm=true`, and that a tool hidden by the active profile returns an error
   instead of calling Google.

## Tests

- 359 unit and in-memory MCP tests.
- Alias coverage test: every retained 1.x name maps to a 2.0 tool/action.
- Removed-name test: removed capabilities are explicit, not silent.

## Compatibility

- No new scopes and no data migration.
- `core` remains the default profile.
- Existing 2.0.0 configs keep working.
