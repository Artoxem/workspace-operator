# Release v1.9.0 — Streamable HTTP, localhost first

The server can now be reached over HTTP — deliberately, and only from your own
machine unless you explicitly say otherwise.

## Why this shape

A network-exposed MCP server runs every request under **one Google identity**.
Exposing it without that understood is how tools leak data. So the default is
localhost, authentication is mandatory, and going wider takes two explicit flags.

## What was added

### `serve --http`

```bash
python -m workspace_operator serve --http --port 8765
```

* Streamable HTTP, **stateless** (`json_response`), one server instance, no sessions;
* bind `127.0.0.1:8765` by default;
* every request: `Authorization: Bearer <token>` — constant-time comparison;
* tokens: `http_tokens: {laptop: …, ci: …}` in `config.yaml`, falling back to
  `mcp_auth_token` as `default`. The audit log records the token name as `client`;
* DNS-rebinding protection: only expected `Host` values pass, browser origins are
  denied unless allow-listed;
* `GET /healthz` — public, no data, returns version and transport;
* non-loopback bind requires `--allow-network` **and** `--insecure`, so a public
  bind is always a deliberate act.

### Docker

`Dockerfile`, `docker-compose.yml`, `.dockerignore`. The compose file publishes
`127.0.0.1:8765` only and mounts the OAuth files read-only:

```bash
export MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up --build
```

### Runtime plumbing

`create_server(config, logger)` is now transport-independent, so stdio and HTTP
share exactly the same server, handlers, profiles and audit behaviour. The HTTP
transport sets a `client` context variable that the audit log reads.

## Verified

| Check | Result |
|---|---|
| `GET /healthz` | `200` with `{"status":"ok","transport":"streamable-http","stateless":true}` |
| `POST /mcp` without token | `401` |
| `POST /mcp` with a wrong token | `401` |
| `initialize` with token | `200`, `serverInfo` = `Workspace Operator 1.8.0`, instructions present |
| `tools/list` with token | `200`, **66 tools** |
| Bind `0.0.0.0` without flags | refused with an explicit reason |
| Bind `0.0.0.0` with `--allow-network` only | refused, asks for `--insecure` |
| Bind loopback | allowed |

## Tests

- 206 unit tests (14 new for the HTTP security decisions: bind matrix, token
  authentication, token map, DNS-rebinding settings).
- Documentation tests now also assert that `Dockerfile`, `docker-compose.yml`,
  `uvicorn`/`starlette` in requirements, and the `--http` / `--allow-network`
  documentation exist.

## Dependencies

`uvicorn>=0.30` and `starlette>=0.40` are added to `requirements.txt`.

## Not in this release

- TLS termination — put Caddy/nginx in front if you ever expose the port;
- per-user Google identity — the shared-identity limitation stands and is
  documented in `SECURITY.md`.
