# Version history

A compact summary of the project. Full historical release notes remain available
on [GitHub Releases](https://github.com/Artoxem/workspace-operator/releases); the
repository keeps this single document instead of one file per patch release.

Current release: **2.2.0**.

## 2.x — compact surface

| Version | What changed |
|---|---|
| **2.2.0** | Security hardening: mail-attachment/Drive names are sanitised (path traversal fix); `drive_upload` refuses secrets and honours `upload_roots`; browser approvals need a per-approval secret, an Origin check and strict headers (`approvals link`); HTTP mode rejects placeholder/short tokens; `token.json` is refreshed under a lock and written atomically owner-only; `doctor` checks secret hygiene; the Docker image binds `127.0.0.1` by default. CI (pytest, ruff, mypy, bandit, pip-audit) gates publishing; mypy 152 → 0; 334 tests. |
| **2.1.2** | Added the browser approval fallback (`/approvals/...`) for clients without MCP elicitation; approval URL config and HTTP page tests. |
| **2.1.1** | In-chat approval via MCP elicitation when the client supports it; the local `approval_id` CLI remains a fallback. |
| **2.1.0** | Human approval for destructive actions: `APPROVAL_REQUIRED` challenge, one-time argument-bound `approval_id`, `workspace-operator approvals` CLI, TTL and local approval queue. |
| **2.0.6** | Removed the stale `sheet_brief` prompt row from both READMEs; added exact README tool/prompt table tests; 293 tests. |
| **2.0.5** | README accuracy pass: profile endpoints, scope/public-sharing env rows, corrected local-file capabilities and docs tables; stale tool references removed. |
| **2.0.4** | README starts with the consolidated tool count; added the complete scope → tools matrix, minimal scope sets and missing-scope troubleshooting. |
| **2.0.3** | Documentation consolidation: version history moved to this file; duplicate README lines removed; prompt count corrected to 7; stale test/release references cleaned. |
| **2.0.2** | Removed dead Slides/comments/composite handler modules, tool definitions and dispatch branches; removed `sheet_brief`; 290-test suite. |
| **2.0.1** | Hidden 1.x aliases; migrated names resolve to the new tool/action; removed capabilities return a migration error. |
| **2.0.0** | 132 → **39 consolidated tools**; default `core` profile (20 tools); scope routing at startup; profile endpoints; no permanent Drive deletion; public sharing off by default; Slides and Drive comments removed. |

Key 2.0 properties:

- profiles: `read-only` (17), `core` (20), `read-write` (30), `full` (39);
- action-based tools such as `drive_read`, `sheets_write`, `gmail_read`;
- scope-aware filtering at startup, stable per connection;
- hidden aliases for retained 1.x names during 2.0.x;
- 13 OAuth scopes; `presentations` no longer requested.

## 1.19–1.22 — bulk operations and more APIs

| Version | What changed |
|---|---|
| **1.22.0–1.22.5** | Tasks, Forms and Postmaster; 132 tools; Gmail delete fixed to Trash; onboarding rewrite; demo GIF and banner; documentation and cleanup releases. |
| **1.21.0** | `bulk_undo` for move, rename and trash; text replacement across Docs, Slides and Sheets. |
| **1.20.0** | Bulk Gmail actions and Drive sharing. |
| **1.19.0** | Bulk operations for Drive: plan → confirm → background run, progress, results and resume. |

## 1.14–1.18 — full Google Workspace surface

| Version | What changed |
|---|---|
| **1.18.x** | Validation, filter views, shapes; doctor scope checks; HTTP session fix. |
| **1.17.0** | Pivot tables, styling and more integrations. |
| **1.16.0** | Column operations, media, integrations. |
| **1.15.0** | MCP 2026-07-28 support; structural editing. |
| **1.14.0** | Expansion to the full tool arsenal: charts, formatting, permissions, drafts and more. |

## 1.0–1.13 — foundations

| Version | What changed |
|---|---|
| **1.13.x** | Docker image on GHCR; container port fix. |
| **1.12.x** | Scenario prompts; metadata fix. |
| **1.10–1.11** | Native tables in Docs; table-to-presentation; universality guard. |
| **1.9.0** | Streamable HTTP transport, localhost-first. |
| **1.8.0** | Operations-grade runtime: retries, audit, dry-run. |
| **1.6–1.7** | Calendar lifecycle and universal composite tools. |
| **1.4–1.5** | Sheet formatting; Gmail threads, attachments and replies. |
| **1.3.0** | Renamed to **Workspace Operator**. |
| **1.0–1.2** | Initial Google Workspace MCP server; files, automation and presentations. |

## Compatibility notes

- 2.0 is a breaking release: tool names and the default profile changed.
- During 2.0.x, retained 1.x names are accepted as hidden aliases.
- Removed capabilities return a migration error; see
  [MIGRATION_2.0.md](MIGRATION_2.0.md).
- 2.0 never permanently deletes Drive files; use Trash and `drive_write` restore.
