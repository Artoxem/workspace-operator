# Version history

A compact summary of the project. Full historical release notes remain available
on [GitHub Releases](https://github.com/Artoxem/workspace-operator/releases); the
repository keeps this single document instead of one file per patch release.

Current release: **2.3.0**.

## 2.x — compact surface

| Version | What changed |
|---|---|
| **2.3.0** | Signed approvals. Approval records are sealed with an HMAC key (`approval.key`) next to them, so a record edited on disk (status, expiry, arguments) is rejected instead of released. The browser secret is stored only as a SHA-256 hash, minted when a human asks for the link; a new link invalidates the previous one. The agent's result carries no decision path: no CLI commands and no links; the decision link goes to the operator's log. The default store is `~/.google/approvals`, the same folder as the token, so it does not depend on the working directory and the container shares it through the credentials mount. The image installs the package, so the `workspace-operator` command exists in the container. Breaking for pending approvals: records from earlier versions are not accepted; re-run the destructive call to get a new id. End-to-end tests (`tests/test_approval_security.py`) cover an agent retrying its own id, forging status, and guessing the seal. |
| **2.2.5** | Performance and durability: Google API clients are cached per configuration (the token file was re-read and the discovery document parsed on every call), staged Apps Script operations live on disk with an expiry and an atomic one-shot claim instead of a process-local dict, and the "Error" prefix heuristic is replaced by typed `ToolError`/`ToolResult` plus a strict pattern (`"Errors found: 0"` is no longer reported as an error). Compose can now pass `MCP_TOOL_PROFILE` from `.env`, so the shipped `core` default stays. 448 tests, coverage 58%. |
| **2.2.4** | Internal refactor, no behaviour change: the nested closures of `create_server` are now modules. `tool_router.py` holds the `tools/call` pipeline as the `ToolRouter` class (resolve → validate → dry-run → approve → run, with the bulk audit callbacks); `prompts.py` and `resources.py` hold the 7 prompts and 6 resource views. `create_server` complexity 84 → 16, `server.py` 1127 → 325 lines (3740 at the start of 2.2). Safety net: before moving anything, characterisation tests pinned 35 call-path scenarios (text, error flag, audit records, handler arguments, approvals, retries), 28 prompt/resource scenarios and the 250-row truncation, using snapshots taken from the old code. Injected mistakes in the new modules (changed caps and defaults, dropped checks, wrong audit status, lost `confirm` flag, ignored retry count) were all caught once the three that first slipped through got their own scenarios. Prompts and resources had no tests before; coverage of both is now 100% (total 56%). First published release since 2.1.2 (2.2.0 to 2.2.3 were internal steps); its public MCP surface was compared programmatically with 2.1.2 and is identical in all four profiles. Fixes made while preparing it: the golden snapshots were never committed because `.gitignore` hid `tests/data/`; the file-path tests only passed on Windows; `server.json` declared the previous package version (all version strings are now tested for agreement). 421 tests. |
| **2.2.3** | Internal refactor, no behaviour change: the 104 tool definitions and 7 prompts (about 2,000 lines of Python literals in `server.py`) are now data in `workspace_operator/definitions/` (one JSON per domain, `order.json` for the `tools/list` order, `prompts.json`) loaded by `load_tools()` / `load_prompts()`; `_tools()` and `_prompts()` keep their names. Packaging: JSON is not included in a wheel by default, so `[tool.setuptools.package-data]` was added (a wheel built without it contained no definitions and could not start); verified by installing the built wheel in a clean environment. `tests/test_definitions.py` pins the loaded result against a snapshot taken before the extraction (names, schemas, safety hints, order) and checks the packaging config; 7 injected data/packaging mistakes are caught. `server.py` 3142 → 1127 lines; 406 tests. |
| **2.2.2** | Internal refactor, no behaviour change: the 600-line table of handler lambdas moved out of `server.py` into the declarative `workspace_operator/dispatch.py` (name → function, argument mapping, defaults, `or {}` fallbacks). A golden test (`tests/test_handler_dispatch.py`) pins the arguments each of the 104 handlers receives, with all and with only the required arguments, and checks that destructive handlers never run without approval; its snapshots come from the pre-refactor code and it catches 5/5 injected table mistakes. `server.py` 3740 → 3142 lines; 394 tests. |
| **2.2.1** | Fixed bulk jobs losing results on cancel: items already running when a job was cancelled changed Google data but were not written to the result file, so `bulk_undo` skipped them and resume repeated them; they are now recorded. Added engine, selector and service tests with fake Google clients (bulk engine coverage 18% → 77%, selector 17% → 95%); 390 tests. |
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
