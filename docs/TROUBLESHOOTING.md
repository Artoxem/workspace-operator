# Troubleshooting

Start with the built-in check — it covers most cases:

```bash
workspace-operator doctor            # config, token, scopes, API reachability
workspace-operator doctor --offline  # same, but skips token refresh and network probes
```

`doctor` prints what is configured, what is missing and which API answers. If it is
green and something still fails, the tables below are ordered from the outside in:
install → OAuth → transport → Docker → tools.

## Installation and startup

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'workspace_operator'` | different interpreter or venv | install into the same environment: `pip install workspace-operator-mcp`, or run `python server.py` from the checkout |
| `package requires Python >=3.10` | old interpreter | upgrade Python, or point the client at the newer one |
| `python: command not found` (Windows) | Python not on `PATH` | use `py -3.12` or the full path to `python.exe` |
| server exits immediately, nothing in the console | stdout is the MCP channel; logs go to a file | open `log_file` (default `~/.google/mcp_operations.log`) |
| `Config file not found` | `--config` or `MCP_CONFIG_FILE` names a file that does not exist; the server exits instead of silently using defaults | fix the path, or unset it and let the lookup find `./config.yaml` or the per-user file; `workspace-operator doctor` shows which file was used |

## Google OAuth

Full setup: [AUTH_SETUP.md](AUTH_SETUP.md).

| Symptom | Cause | Fix |
|---|---|---|
| `invalid_grant`, `Token has been expired or revoked` | token revoked, expired, or scopes changed | delete `token.json`, run once interactively, sign in again |
| `access_denied`, `insufficientPermissions` | API not enabled, or a scope was added later | enable the API, delete `token.json`, re-authorize |
| `redirect_uri_mismatch` | OAuth client is not a Desktop app | create a new Client ID of type **Desktop app** |
| `This app isn't verified` | consent screen in testing mode | Advanced → **Go to app (unsafe)**; or publish the app |
| `403: <API> has not been used in project …` | the API is disabled | enable it in the Cloud console, wait a minute, retry |
| `FileNotFoundError: oauth.keys.json` | wrong `client_secrets_file` | fix the path in `config.yaml` or `GOOGLE_CLIENT_SECRETS_FILE` |
| browser does not open | headless/remote session | copy the printed URL into a browser, paste the code back |
| checks pass but a tool returns `404` | file belongs to another account, or the ID is wrong | verify the ID and that the account has access |
| `doctor`: `[FAIL] stray secret files` | old `token.json.bak-*`, `service-account.json` or `credentials.json` next to the token | revoke the app in your Google account, then delete the files |
| `doctor`: `[FAIL] secret file permissions` | secrets readable by other users | restrict them to your account (`chmod 600` / an owner-only ACL); `token.json` is created that way |
| `403: Request had insufficient authentication scopes` | the token predates a scope (Gmail filters need `gmail.settings.basic`) | delete `token.json`, run once, sign in again; `doctor` reports `[FAIL] scopes` and exits 1 |

## HTTP transport

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | missing or wrong bearer token | send `Authorization: Bearer <MCP_AUTH_TOKEN>`; compare against the config |
| `421 Misdirected Request` | the `Host` header is not allowed (typical for a remapped container port) | upgrade to 1.13.1+, or pass `--allow-host 127.0.0.1:8791` |
| `403 Forbidden` from Google | quota or API not enabled | see the Google section above |
| `address already in use` | another process holds the port | `--port 8790` |
| refusal: *token 'default' is a placeholder value* / *shorter than 24 characters* | the HTTP bearer is guessable | generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` and set `MCP_AUTH_TOKEN` |
| approval page says *invalid or expired link* / `403` on Approve | the link has no secret, or the POST came from another origin | get the link with `workspace-operator approvals link <id>`; open it directly, not through a proxy that rewrites `Host`/`Origin` |
| no approval tab opens on a destructive call | `approvals watch` is not running, `MCP_APPROVAL_BROWSER_WAIT` is `0`, or the helper uses another approval queue | start `workspace-operator approvals watch` on the desktop with access to the same queue and set `MCP_APPROVAL_BROWSER_WAIT`; until then the call returns `approval_id` and you decide with `approvals approve` or `approvals link` |
| refusal: *non-loopback binding requires `--allow-network`* | network bind without acknowledgement | add **both** `--allow-network` and `--insecure`, and put a TLS proxy in front |
| `Empty reply from server` | wrong path or method | `POST /mcp`, not `/`; `GET /healthz` is the only GET |
| browser CORS error | origins are denied by design | use a native MCP client, not a web page |

Check by hand:

```bash
curl http://127.0.0.1:8765/healthz

curl -s http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Docker

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied` reading `~/.google` (Linux) | the container runs as uid 10001 | `chmod -R a+r ~/.google`, or run with `--user $(id -u):$(id -g)` |
| token refresh fails, file is read-only | the mount is `:ro` | mount the credentials **read-write**: the server rewrites the token |
| errors mentioning `C:\…` paths | a Windows `config.yaml` inside Linux | mount `config.docker.yaml` instead, it uses `/home/app/...` |
| container is `(unhealthy)` | wrong token, missing config, or a crash | `docker logs <container>`, check `MCP_AUTH_TOKEN`, check the mount paths |
| `421` on a remapped port | DNS-rebinding guard (fixed in 1.13.1) | pull `:latest`, or add `--allow-host` |
| `exec format error` | image architecture does not match the host | the image is `amd64`/`arm64`; pull again on a supported host |
| port is published but nothing answers | the image binds `127.0.0.1` inside the container by default | add `--http --host 0.0.0.0 --allow-network --insecure` (Compose already does) and keep `-p 127.0.0.1:…` |
| `Error: … protected location … cannot be uploaded` | `drive_write(action="upload")` refuses secrets, approvals, logs and anything outside `upload_roots` | upload a copy from an allowed folder; check `MCP_UPLOAD_ROOTS` |
| server starts but tools fail with 401 | `MCP_AUTH_TOKEN` not passed | `-e MCP_AUTH_TOKEN=...` |
| changes in the config are ignored | the file is baked into the image | mount `config.docker.yaml` over `/app/config.yaml` |

Minimal working command:

```bash
docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:latest \
  --http --host 0.0.0.0 --port 8765 --allow-network --insecure
```

The image binds `127.0.0.1` unless told otherwise, so without the trailing flags
the published port answers nothing. Keep the `127.0.0.1:` prefix in `-p`: the
endpoint has no TLS.

## Tools and data

| Symptom | Cause | Fix |
|---|---|---|
| `Unknown tool: …` | the profile or an allow/deny list hides it | `workspace-operator tools --profile full`; check `MCP_DENIED_TOOLS` |
| `Operation op_… not found or expired` | a prepared Apps Script update was executed already, cancelled, or older than `operation_ttl` | run the prepare step again; `data/operations/` shows what is pending |
| `CONFIRMATION REQUIRED` | destructive tool called once | repeat the call with `confirm=true` after checking the preview |
| the tool returns a preview instead of acting | dry-run is on | unset `MCP_DRY_RUN` / `dry_run: false` |
| `403 quota exceeded`, `rateLimitExceeded` | Google limits | wait; raise `MCP_RETRY_ATTEMPTS`; narrow the range |
| `File not found` | wrong ID, or the account has no access | open the file in the browser as the same account |
| download/export fails on a Google Doc or Sheet | native files have no binary content | use `drive_read(action="export")` (pdf/docx/xlsx/csv) |
| very slow read on a large sheet | whole-sheet request | pass a range (`A1:D100`) |
| A removed 1.x tool returns `unknown tool` | 2.0 uses consolidated tools | use the new name/action from `docs/MIGRATION_2.0.md` |

## Logs and reporting a bug

- `log_file` — human-readable server log; set `GOOGLE_LOG_LEVEL=DEBUG` for details.
- `MCP_AUDIT_LOG` — one JSON line per tool call: tool, profile, status, duration,
  argument **names** (values are never written).
- `workspace-operator doctor` output is safe to share — it contains paths and scopes,
  not secrets.

When reporting, include: version (`workspace-operator version`), the command you ran,
the tool name with its arguments (without secrets), and the last lines of the log.
