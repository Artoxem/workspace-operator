# Release v1.18.3 — HTTP session-termination fix

A live container run exposed a real bug in the HTTP transport: a `DELETE /mcp`
(session termination) crashed the ASGI application with
`TypeError: 'NoneType' object is not callable` and returned 500.

## Cause

The MCP session manager writes its own ASGI response, so the Starlette route
endpoint returned `None`. Starlette then tried to call `None` as a response object.

## Fix

- `/mcp` is now served by a raw ASGI endpoint mounted at the root, with an explicit
  path guard (`/mcp` and `/mcp/`, everything else 404);
- authentication and the per-client context still wrap the manager;
- no redirect: `POST /mcp` stays `POST /mcp` (no 307);
- `DELETE /mcp` now returns a clean `405` JSON from the stateless manager instead of
  a 500 and a traceback.

## Verified

```
healthz          200
unauth POST      401 {"error":"unauthorized"}
auth tools/list  200, 115 tools
DELETE /mcp      405 {"code":-32600,"message":"Method Not Allowed: Session termination not supported"}
GET /foo         404
no traceback in the log
```

## Unchanged

115 tools, profiles 115 / 96 / 29, 285 unit tests, protocol 2026-07-28.
