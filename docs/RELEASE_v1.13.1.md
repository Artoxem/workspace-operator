# Release v1.13.1 — container port mapping fix

A live run of the published image found the bug: the container started, reported
healthy and answered `/healthz`, but every MCP request to a **remapped port**
returned `421 Misdirected Request`.

## Cause

The DNS-rebinding guard compares the `Host` header against an allow-list built from
the bind address. Inside a container the bind is `0.0.0.0:8765`, so the allow-list
contained `127.0.0.1:8765` — while `docker run -p 127.0.0.1:8791:8765` makes the
client send `Host: 127.0.0.1:8791`. Rejected.

## Fix

- loopback names now accept **any port**: `127.0.0.1:*`, `localhost:*`, `[::1]:*`;
- the bind address itself stays pinned (`host:port`), the rebinding protection stays on;
- new `--allow-host HOST[:PORT]` (repeatable) for proxies, a LAN name, or a tunnel.

```bash
workspace-operator serve --http --port 8765   --allow-host mcp.example.com --allow-host 192.168.1.10:8765
```

## Verified

Rebuilt and pulled `ghcr.io/artoxem/workspace-operator:1.13.1`:

- `docker run -p 127.0.0.1:8791:8765` → `/healthz` 200, `tools/list` 200 with 67 tools;
- without a token → 401;
- container health status `healthy`;
- the process runs as `app` (uid 10001).

## Counts

- Tools: 67 (unchanged)
- Tests: 247 (3 new for host allow-lists and the CLI flag)
