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
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .runtime import current_client

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
DEFAULT_PORT = 8765


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


def build_asgi_app(server, options: HttpOptions, version: str) -> Starlette:
    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=_security_settings(
            options.host, options.port, options.extra_hosts
        ),
    )

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

    class McpEndpoint:
        """Raw ASGI endpoint: the session manager writes its own response."""

        async def __call__(self, scope, receive, send):
            path = scope.get("path", "")
            if path not in ("/mcp", "/mcp/"):
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

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Mount("/", app=McpEndpoint()),
        ],
        lifespan=lambda app: manager.run(),
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
    options.tokens = tokens

    app = build_asgi_app(server, options, version)
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
