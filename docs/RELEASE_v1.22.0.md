# Workspace Operator 1.22.0

Three new Google APIs: Tasks, Forms and Postmaster Tools. 132 tools.

## Tasks (4 tools)

- `tasks_list_lists` — task lists and ids.
- `tasks_list` — tasks in a list, optionally including completed ones.
- `tasks_create` — title, notes and an optional RFC 3339 due date.
- `tasks_complete` — mark a task completed.

Typical use: turn an email or a spreadsheet row into a task, then close it later.

## Forms (4 tools)

- `forms_create` — form with title and description; returns the responder link.
- `forms_add_questions` — append short-answer questions (`title`,
  `description`, `required`).
- `forms_get` — title, description, responder link and questions with ids.
- `forms_list_responses` — responses with answers mapped to question titles.

Limitations: only short-answer questions are created by this release; choice
grids, file uploads and quizzes are read-through but not created. Deleting forms
is not exposed by the API and is not attempted.

## Postmaster Tools (2 tools)

- `postmaster_list_domains` — verified domains and the account's permission.
- `postmaster_traffic_stats` — daily spam rate, domain reputation,
  DKIM/DMARC/SPF success ratios and delivery errors for a verified domain
  (up to 90 days).

This is domain-level deliverability data, not mailbox content. A domain must be
verified in Search Console and present in Postmaster Tools; otherwise the tool
returns an empty list or a clear error. Uses the v1beta1 API surface.

## Scopes and re-authorization

Four scopes were added:

```
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/forms.body
https://www.googleapis.com/auth/forms.responses.readonly
https://www.googleapis.com/auth/postmaster.readonly
```

Existing tokens do not contain them, so Google returns `403
insufficientPermissions` until the token is re-issued. Delete `token.json` and
let the server run the consent flow again (or re-run `doctor --online`). Nothing
else changes: same client secrets, same profile, same container mount.

## Compatibility

- 132 tools; profiles: `full` 132, `read-write` 113, `read-only` 39.
- Additive only: no existing tool or argument changed.
- Bulk engine untouched.

## Tests

- 327 unit tests.
- Handler tests for Tasks, Forms and Postmaster request/response formatting.
- Live checks require the re-issued token; run `doctor --online` after consent.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.0
# or
docker compose pull && docker compose up -d
```

Then re-authorize once and reconnect MCP clients.

## Deferred

- Forms: choice/grid questions, quizzes, watches.
- Tasks: subtasks, moving tasks between lists, batch operations (the API has no
  batch endpoint).
- Public release (PyPI, GHCR, GitHub release) remains postponed.
