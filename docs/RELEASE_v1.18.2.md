# Release v1.18.2 — documentation metadata refresh

No code changes. This release exists so PyPI picks up the cleaned-up README:
the package page still shows the previous tag's text, and PyPI metadata is immutable
per upload.

## What changed

- the README (EN/RU) no longer mentions the project's former working name;
- the release notes for 1.3.0 and 1.5.1 keep the rename fact but without the old
  literal name;
- the confirm-gated tool list now includes `calendar_delete_event` and
  `calendar_respond_to_invite`, matching the code;
- `config.example.yaml` matches the default scopes exactly (9 of 9, including
  `gmail.settings.basic`);
- the README states that PyPI mirrors the latest release, with source and the
  container as the fallback.

## Unchanged

- 115 tools, profiles 115 / 96 / 29;
- 285 unit tests, 94 live checks;
- protocol 2026-07-28, MCP SDK 2.3.0.

## Install

```bash
pip install workspace-operator-mcp==1.18.2
```
