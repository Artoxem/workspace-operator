# Workspace Operator 1.22.2

Documentation release. No tool behaviour changed.

## Onboarding rewrite

- **Quick start** now opens with a choice: stdio for one desktop client,
  Docker/HTTP for several clients or a background service, source checkout for
  development.
- Install examples use the installed `workspace-operator` command instead of a
  hard-coded Windows path.
- **Google OAuth** lists the current ten APIs (including Tasks, Forms and
  Postmaster) and explains what to do when there is no browser: authorize on a
  desktop, copy `token.json`, mount the folder read-write.
- **Two secrets** are explained side by side: `token.json` is Google OAuth,
  `mcp_auth_token` is the local MCP bearer string.
- **Docker**: authorize on the host first, then Compose or `docker run`; commands
  for Linux/macOS and Windows PowerShell; new `.env.example`.
- **IDE setup** covers stdio and HTTP, Cursor, Windsurf, VS Code and Antigravity.

## Single-user model

The README and SECURITY now state the deployment model explicitly:

- one process = one Google account = one tool profile;
- several MCP clients are supported, each with its own bearer token, but they
  share the account, audit log and bulk jobs;
- a small team can share one account, but there is no isolation;
- multiple accounts require one instance per account;
- the server is not a multi-tenant service.

## Russian documentation

`README.ru.md`, `docs/ru/AUTH_SETUP.md` and `docs/ru/IDE_SETUP.md` are rewritten to
match the English versions, with the same single-user table and Docker steps.

## Compatibility

- 132 tools, profiles 132 / 113 / 39, 14 OAuth scopes.
- No code changes, no new scopes, no migration.
- PyPI package description is refreshed from this README.

## Upgrade

```bash
pip install --upgrade workspace-operator-mcp==1.22.2
# or
docker compose pull && docker compose up -d
```

## Tests

- 328 unit tests.
- Documentation tests: every tool listed, counts match, relative links resolve.
