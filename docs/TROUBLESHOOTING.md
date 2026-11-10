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
| `config file not found` | `MCP_CONFIG_FILE` points nowhere | pass an absolute path; the server also works with env vars only |

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
| `403: Request had insufficient authentication scopes` | the token predates a scope (Gmail filters need `gmail.settings.basic`) | delete `token.json`, run once, sign in again; `doctor` reports `[FAIL] scopes` and exits 1 |

## HTTP transport

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | missing or wrong bearer token | send `Authorization: Bearer <MCP_AUTH_TOKEN>`; compare against the config |
| `421 Misdirected Request` | the `Host` header is not allowed (typical for a remapped container port) | upgrade to 1.13.1+, or pass `--allow-host 127.0.0.1:8791` |
| `403 Forbidden` from Google | quota or API not enabled | see the Google section above |
| `address already in use` | another process holds the port | `--port 8790` |
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
| server starts but tools fail with 401 | `MCP_AUTH_TOKEN` not passed | `-e MCP_AUTH_TOKEN=...` |
| changes in the config are ignored | the file is baked into the image | mount `config.docker.yaml` over `/app/config.yaml` |

Minimal working command:

```bash
docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="change_me" \
  ghcr.io/artoxem/workspace-operator:latest
```

## Tools and data

| Symptom | Cause | Fix |
|---|---|---|
| `Unknown tool: …` | the profile or an allow/deny list hides it | `workspace-operator tools --profile full`; check `MCP_DENIED_TOOLS` |
| `CONFIRMATION REQUIRED` | destructive tool called once | repeat the call with `confirm=true` after checking the preview |
| the tool returns a preview instead of acting | dry-run is on | unset `MCP_DRY_RUN` / `dry_run: false` |
| `403 quota exceeded`, `rateLimitExceeded` | Google limits | wait; raise `MCP_RETRY_ATTEMPTS`; narrow the range |
| `File not found` | wrong ID, or the account has no access | open the file in the browser as the same account |
| download fails on a Google Doc/Sheet/Slide | native files have no binary content | use `drive_export` (pdf/docx/xlsx/pptx/csv) |
| very slow read on a large sheet | whole-sheet request | pass a range (`A1:D100`) |
| `slides_replace_text` refuses to run | it is destructive and needs consent | add `confirm=true` |

## Logs and reporting a bug

- `log_file` — human-readable server log; set `GOOGLE_LOG_LEVEL=DEBUG` for details.
- `MCP_AUDIT_LOG` — one JSON line per tool call: tool, profile, status, duration,
  argument **names** (values are never written).
- `workspace-operator doctor` output is safe to share — it contains paths and scopes,
  not secrets.

When reporting, include: version (`workspace-operator version`), the command you ran,
the tool name with its arguments (without secrets), and the last lines of the log.
