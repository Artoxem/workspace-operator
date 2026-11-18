"""Streamable HTTP transport — localhost first.

Security posture:

* default bind address is ``127.0.0.1``;
* every request must carry ``Authorization: Bearer <token>``;
* binding to a non-loopback address requires **both** ``--allow-network`` and
  ``--insecure`` (the second one acknowledges there is no TLS in front);
* DNS-rebinding protection is on: only expected ``Host`` headers pass and browser
  origins must be explicitly allowed.

The transport is stateless: no session storage, one server instance for all
requests, which matches the 2026-07-28 direction of the MCP spec and keeps the
process simple.
"""

import hmac
import html
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from .runtime import current_client

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
DEFAULT_PORT = 8765

_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
}


def secret_q(value: str) -> str:
    return quote(value, safe="")


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _authority(value: str) -> str:
    """``scheme://Host:port`` → ``host:port``, normalised for comparison.

    Loopback spellings are one server: ``localhost``, ``127.0.0.1`` and ``[::1]``
    all normalise to ``127.0.0.1``, and a missing port falls back to the scheme
    default, so ``http://localhost:8765`` compares equal to a Host of
    ``127.0.0.1:8765``.
    """
    raw = value.strip()
    if "//" not in raw:
        raw = "//" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return raw.lower()
    host = (parts.hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        host = "127.0.0.1"
    if port is None:
        port = {"http": 80, "https": 443}.get(parts.scheme.lower())
    return f"{host}:{port}" if port else host


def _same_origin(request) -> bool:
    """Reject cross-site form posts: Origin (when sent) must match Host."""
    origin = (request.headers.get("origin") or "").strip()
    host = request.headers.get("host", "")
    if origin and origin.lower() != "null":
        return _authority(origin) == _authority(host)
    if not origin:
        # Non-browser clients (curl, tests) send no Origin; the secret still applies.
        return request.headers.get("sec-fetch-site", "same-origin") in (
            "same-origin",
            "none",
        )
    # Opaque origin: sandboxed previews and embedded webviews send ``Origin: null``
    # and their Sec-Fetch-Site looks cross-site even for our own page. The approval
    # secret is still required for the POST, so accept it when we are loopback-only.
    return (urlsplit("//" + host).hostname or "").lower() in _LOOPBACK_HOSTS


@dataclass
class HttpOptions:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    allow_network: bool = False
    insecure: bool = False
    tokens: Dict[str, str] = field(default_factory=dict)
    extra_hosts: List[str] = field(default_factory=list)


def resolve_bind(host: str, allow_network: bool, insecure: bool) -> Tuple[bool, Optional[str]]:
    """Decide whether the requested bind address is allowed."""
    if host in LOOPBACK:
        return True, None
    if not allow_network:
        return False, "binding to a non-loopback address requires --allow-network"
    if not insecure:
        return (
            False,
            "network binding without TLS requires --insecure; put a TLS proxy in "
            "front for anything beyond your machine",
        )
    return True, None


WEAK_TOKENS = frozenset({"change_me", "changeme", "token", "secret", "password", "test"})
MIN_TOKEN_LENGTH = 24


def weak_token_problems(tokens: Dict[str, str]) -> List[str]:
    """Describe tokens that are too guessable to protect an HTTP endpoint."""
    problems = []
    for name, token in tokens.items():
        if token.lower() in WEAK_TOKENS:
            problems.append(f"token '{name}' is a placeholder value")
        elif len(token) < MIN_TOKEN_LENGTH:
            problems.append(
                f"token '{name}' is shorter than {MIN_TOKEN_LENGTH} characters"
            )
    return problems


def build_tokens(config) -> Dict[str, str]:
    """Token map: explicit ``http_tokens`` or the single activation token."""
    configured = getattr(config, "http_tokens", None) or {}
    if configured:
        return {str(name): str(token) for name, token in configured.items()}
    if config.mcp_auth_token:
        return {"default": str(config.mcp_auth_token)}
    return {}


def authenticate(authorization: Optional[str], tokens: Dict[str, str]) -> Optional[str]:
    """Return the client name for a valid bearer token, else ``None``."""
    if not authorization or not tokens:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    candidate = value.strip()
    for name, token in tokens.items():
        if hmac.compare_digest(candidate, token):
            return name
    return None


def _security_settings(
    host: str, port: int, extra_hosts: Optional[List[str]] = None
) -> TransportSecuritySettings:
    """Allowed ``Host`` headers for the DNS-rebinding check.

    Loopback names accept any port: publishing a container on ``-p 127.0.0.1:8791:8765``
    makes the browser send ``Host: 127.0.0.1:8791``, which the container cannot
    predict. The bind address itself is still pinned to ``host:port``.
    """
    hosts = [
        f"{host}:{port}",
        f"{host}:*",
        f"localhost:{port}",
        "localhost:*",
        f"127.0.0.1:{port}",
        "127.0.0.1:*",
        "[::1]:*",
    ]
    for extra in extra_hosts or []:
        if extra and extra not in hosts:
            hosts.append(extra)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[],
    )


def _manager_for(server, options: HttpOptions) -> StreamableHTTPSessionManager:
    return StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=_security_settings(
            options.host, options.port, options.extra_hosts
        ),
    )


def build_asgi_app(
    servers,
    options: HttpOptions,
    version: str,
    approval_store=None,
    approval_url: str | None = None,
) -> Starlette:
    """Build the HTTP app.

    ``servers`` is either one MCP ``Server`` (the legacy default) or a mapping
    of path → server, used for the profile endpoints.
    """
    if not isinstance(servers, dict):
        servers = {"/mcp": servers}
    managers = {path: _manager_for(server, options) for path, server in servers.items()}

    async def healthz(_request):
        return JSONResponse(
            {
                "status": "ok",
                "server": "Workspace Operator",
                "version": version,
                "transport": "streamable-http",
                "stateless": True,
            }
        )

    async def approval_page(request: Request):
        if approval_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        approval_id = request.path_params.get("approval_id", "")
        secret = request.query_params.get("k", "")
        if not approval_store.verify_secret(approval_id, secret):
            # Same answer for unknown id and wrong secret: no id probing.
            return HTMLResponse(
                "<h1>Approval not found</h1><p>This link is invalid or expired. "
                "Use the link from <code>workspace-operator approvals link &lt;id&gt;</code>.</p>",
                status_code=404,
                headers=_PAGE_HEADERS,
            )
        record = approval_store.get(approval_id)
        status = record.get("status", "?")
        summary = html.escape(str(record.get("summary", "")))
        expires = html.escape(str(record.get("expires_at", "")))
        action_forms = ""
        if status == "pending":
            action_forms = f"""
            <form method="post" action="/approvals/{html.escape(approval_id)}/approve">
              <input type="hidden" name="k" value="{html.escape(secret)}">
              <button type="submit" style="background:#2f6fdc;color:white;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer">Approve</button>
            </form>
            <form method="post" action="/approvals/{html.escape(approval_id)}/deny" style="margin-top:8px">
              <input type="hidden" name="k" value="{html.escape(secret)}">
              <button type="submit" style="background:#3a1d1d;color:#f1b0b0;border:1px solid #5a2a2a;border-radius:8px;padding:9px 18px;font:inherit;cursor:pointer">Deny</button>
            </form>"""
        return HTMLResponse(
            f"""<!doctype html><meta charset="utf-8"><title>Approve action</title>
            <style>body{{background:#101014;color:#e8e8ee;font:15px/1.5 system-ui;max-width:640px;margin:48px auto;padding:0 20px}}
            code{{background:#17171d;border:1px solid #26262f;border-radius:6px;padding:2px 6px}}
            .card{{background:#17171d;border:1px solid #26262f;border-radius:12px;padding:20px;margin-top:18px}}
            .status{{color:#f0c674}}</style>
            <h1>Workspace Operator approval</h1>
            <div class="card">
              <p><strong>Action:</strong> {summary}</p>
              <p><strong>Status:</strong> {html.escape(status)}</p>
              <p><strong>Expires:</strong> {expires}</p>
              <p><code>{html.escape(approval_id)}</code></p>
              {action_forms}
              <p style="color:#9a9aa8;margin-top:18px">After approving, return to the chat and tell the agent to retry the exact call with this <code>approval_id</code>. Nothing runs until then.</p>
            </div>""",
            headers=_PAGE_HEADERS,
        )

    async def approval_action(request: Request):
        if approval_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        approval_id = request.path_params.get("approval_id", "")
        action = request.path_params.get("action", "")
        if not _same_origin(request):
            return HTMLResponse(
                "<h1>Forbidden</h1><p>Cross-origin request rejected.</p>",
                status_code=403,
                headers=_PAGE_HEADERS,
            )
        form = await request.form()
        if not approval_store.verify_secret(approval_id, str(form.get("k", ""))):
            return HTMLResponse(
                "<h1>Forbidden</h1><p>Missing or wrong approval secret.</p>",
                status_code=403,
                headers=_PAGE_HEADERS,
            )
        try:
            if action == "approve":
                approval_store.approve(approval_id, actor="web")
            elif action == "deny":
                approval_store.deny(approval_id, actor="web")
            else:
                return JSONResponse({"error": "not found"}, status_code=404)
        except Exception as exc:
            return HTMLResponse(
                f"<h1>Approval failed</h1><p>{html.escape(str(exc))}</p>",
                status_code=400,
                headers=_PAGE_HEADERS,
            )
        return RedirectResponse(
            f"/approvals/{approval_id}?k={secret_q(str(form.get('k', '')))}",
            status_code=303,
            headers=_PAGE_HEADERS,
        )

    class McpEndpoint:
        """Raw ASGI endpoint: the session manager writes its own response."""

        async def __call__(self, scope, receive, send):
            path = scope.get("path", "").rstrip("/") or "/"
            manager = managers.get(path)
            if manager is None:
                response = JSONResponse({"error": "not found"}, status_code=404)
                await response(scope, receive, send)
                return

            headers = Headers(scope=scope)
            client = authenticate(headers.get("authorization"), options.tokens)
            if client is None:
                response = JSONResponse(
                    {"error": "unauthorized", "hint": "Authorization: Bearer <token>"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return

            token = current_client.set(client)
            try:
                await manager.handle_request(scope, receive, send)
            finally:
                current_client.reset(token)

    @asynccontextmanager
    async def lifespan(_app):
        async with AsyncExitStack() as stack:
            for manager in managers.values():
                await stack.enter_async_context(manager.run())
            yield

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/approvals/{approval_id}", approval_page, methods=["GET"]),
            Route("/approvals/{approval_id}/{action}", approval_action, methods=["POST"]),
            Mount("/", app=McpEndpoint()),
        ],
        lifespan=lifespan,
    )
    return app


def serve_http(server, config, logger: logging.Logger, options: HttpOptions, version: str) -> int:
    allowed, reason = resolve_bind(options.host, options.allow_network, options.insecure)
    if not allowed:
        logger.error("Refusing to start: %s", reason)
        print(f"error: {reason}")
        return 2

    tokens = build_tokens(config)
    if not tokens:
        print("error: no bearer token configured (mcp_auth_token or http_tokens)")
        return 2
    problems = weak_token_problems(tokens)
    if problems:
        print(
            "error: " + "; ".join(problems) + ". Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
        return 2
    options.tokens = tokens

    from dataclasses import replace

    from .server import create_server

    servers = {"/mcp": server}
    for path, profile in (
        ("/mcp/read", "read-only"),
        ("/mcp/full", "full"),
        ("/mcp/read-write", "read-write"),
    ):
        if profile != config.tool_profile:
            servers[path] = create_server(
                replace(config, tool_profile=profile), logger
            )

    from .approvals import ApprovalStore

    app = build_asgi_app(
        servers,
        options,
        version,
        approval_store=ApprovalStore(config),
        approval_url=getattr(config, "approval_url", None),
    )
    where = "localhost only" if options.host in LOOPBACK else "NETWORK EXPOSED"
    print(
        f"Workspace Operator {version} — Streamable HTTP on "
        f"http://{options.host}:{options.port}/mcp ({where}, "
        f"{len(tokens)} token(s), stateless)"
    )
    if options.host not in LOOPBACK:
        print("warning: no TLS — tokens travel in clear text; use a TLS proxy")

    uvicorn.run(app, host=options.host, port=options.port, log_level="warning")
    return 0
