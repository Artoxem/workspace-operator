# Release v1.5.1 — documentation refresh

Code unchanged. Every document was re-checked against the code, the README was
rewritten from scratch, and a test now prevents this kind of drift.

## What the audit found

| Problem | Where | Fixed |
|---|---|---|
| README still described the 1.2 state, had a duplicated OAuth paragraph and `cd yet-another-google-mcp` | `README.md` | rewritten |
| Russian README was a patchwork of five versions | `README.ru.md` | rewritten |
| Antigravity server key left as `google-workspace` in examples | `README.md`, `README.ru.md` | `workspace-operator` |
| Profile table said 46 / 41 / 16 | `README`, `antigravity/README.md`, `SECURITY`, `TOOLS_REFERENCE` (EN + RU) | 59 / 52 / 21 |
| Agent Skill claimed 46 tools and `server: yet-another-google-mcp` | `skills/google-workspace/SKILL.md` | 59 tools, new capabilities documented |
| Russian IDE guide linked `../antigravity/…` (resolves inside `docs/`) | `docs/ru/IDE_SETUP.md` | `../../antigravity/…` |
| OAuth guide did not mention the Slides API or the `presentations` scope | `docs/AUTH_SETUP.md` (EN + RU) | added, with re-auth note |
| Skill path mangled by a bulk rename (`skills/workspace-operator/…`) | `antigravity/README.md` | restored |

Release notes and specs for older versions still mention `mcp_google`,
`My Google Tools` and other historical names — that is correct for them and is
excluded from the checks on purpose.

## New: `tests/test_docs.py`

Twelve tests that fail the build when documentation drifts:

* every tool from `tools/list` appears in both READMEs and both
  `TOOLS_REFERENCE` files;
* `**N tools**` and the profile table match `full` / `read-write` / `read-only`
  computed from the real tool annotations;
* the Antigravity guide and `SECURITY` tables agree with those numbers;
* no `mcp_google` or `My Google Tools` outside historical docs;
* every relative markdown link resolves;
* `antigravity/mcp_config.example.json` parses, uses the `workspace-operator` key
  and points at `server.py`;
* `config.example.yaml` parses and contains the Slides scope.

## Numbers

- Tools: 59 · profiles 59 / 52 / 21
- Unit tests: 115 (103 code + 12 documentation)
- Live checks: 35 · pptx round-trip: 5
- Version: 1.5.1
