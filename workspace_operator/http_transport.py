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

import csv
import hashlib
import hmac
import html
import io
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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


_REVIEW_PAGE_SIZE = 100
_REVIEW_AUTO_EXPAND = 20
_GROUP_PREVIEW = 10


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _review_fingerprint(review: Dict[str, Any]) -> str:
    canonical = json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _human_bytes(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}".replace(".0 ", " ")
    return f"{size:.0f} TB"


def _item_size(item: Dict[str, Any]) -> Any:
    return item.get("size_bytes", item.get("size"))


def _sources_of(item: Dict[str, Any]) -> list:
    return list(item.get("sources") or [{"name": "(no parent)", "id": ""}])


def _source_groups(review: Dict[str, Any]) -> list:
    groups: Dict[tuple, list] = {}
    for item in review["items"]:
        for source in _sources_of(item):
            key = (str(source.get("name") or ""), str(source.get("id") or ""))
            groups.setdefault(key, []).append(item)
    return sorted(groups.items(), key=lambda entry: (-len(entry[1]), entry[0][0]))


def _review_rows(items: list, *, upload: bool, with_source: bool) -> str:
    rows = []
    for item in items:
        name = _esc(item.get("name"))
        detail = _human_bytes(_item_size(item))
        if upload:
            kind = item.get("conversion_mime_type") or item.get("mime_type")
            detail = " · ".join(part for part in (detail, _esc(kind)) if part)
        if isinstance(item.get("children"), int):
            exact = item.get("children_at_least")
            inside = f"folder · {item['children']}{'+' if exact else ''} item(s) inside"
            names = ", ".join(_esc(child) for child in (item.get("children_sample") or [])[:5])
            detail = " · ".join(part for part in (inside, names, detail) if part)
        suffix = f" <span class='dim'>{detail}</span>" if detail else ""
        snippet = item.get("snippet")
        if snippet:
            suffix += f"<br><span class='dim'>{_esc(snippet)}</span>"
        source = (
            f"<td class='src'>{', '.join(_esc(s.get('name')) for s in _sources_of(item))}</td>"
            if with_source
            else ""
        )
        rows.append(f"<tr><td class='name'>{name}{suffix}</td>{source}</tr>")
    return "".join(rows)


def _review_table(rows: str, *, with_source: bool) -> str:
    head = "<th>file</th><th>from</th>" if with_source else "<th>file</th>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def _page_links(approval_id: str, secret: str, page: int, pages: int) -> str:
    base = f"/approvals/{quote(approval_id)}?k={quote(secret, safe='')}&all=1"
    links = []
    if page > 1:
        links.append(f"<a href='{base}&page={page - 1}'>← prev</a>")
    links.append(f"<span class='dim'>page {page} / {pages}</span>")
    if page < pages:
        links.append(f"<a href='{base}&page={page + 1}'>next →</a>")
    links.append(f"<a href='/approvals/{quote(approval_id)}?k={quote(secret, safe='')}'>compact view</a>")
    return "<nav>" + " · ".join(links) + "</nav>"


def _review_html(
    review: Dict[str, Any], *, approval_id: str, secret: str, show_all: bool, page: int
) -> str:
    """Compact summary by default; the complete list stays one click away."""
    items = list(review["items"])
    upload = review.get("operation") == "upload"
    destination = review.get("destination") or {}
    total_bytes = sum(int(_item_size(item) or 0) for item in items)
    drive_id = destination.get("driveId") or destination.get("drive_id")
    drive = f" <span class='dim'>shared drive {_esc(drive_id)}</span>" if drive_id else ""
    dest_id = f" <span class='dim'>{_esc(destination.get('id'))}</span>" if destination.get("id") else ""
    warnings = "".join(f"<li>{_esc(w)}</li>" for w in review.get("warnings", []))
    notices = f"<ul class='warn'>{warnings}</ul>" if warnings else ""
    size = _human_bytes(total_bytes) if total_bytes else ""
    verb = {
        "move": "Move", "upload": "Upload", "trash": "Delete", "archive": "Archive",
        "restore": "Restore", "rename": "Rename", "share": "Share",
        "revoke_public": "Revoke public access", "label": "Label",
        "mark_read": "Mark read", "mark_unread": "Mark unread",
        "replace_text": "Replace text", "find_replace": "Replace text",
    }.get(str(review.get("operation")), "Review")
    total = int(review.get("total") or len(items))
    sampled = bool(review.get("sampled"))
    noun = "message(s)" if sampled else ("item(s)" if review.get("operation") == "trash" else "file(s)")
    plural = noun.replace("(s)", "s")
    note = f"<p class='dim'>{_esc(review['note'])}</p>" if review.get("note") else ""
    sample_notice = (
        f"<p class='warn'>Showing the first {len(items)} of {total} matches. "
        "Every matching message is affected — narrow the selector for a shorter list.</p>"
        if sampled and total > len(items)
        else ""
    )
    head = (
        f"<p class='head'>{verb} <b>{total}</b> {noun}{f' · {size}' if size else ''} → "
        f"<b>{_esc(destination.get('name'))}</b>{dest_id}{drive}</p>"
    )

    if show_all:
        pages = max(1, (len(items) + _REVIEW_PAGE_SIZE - 1) // _REVIEW_PAGE_SIZE)
        page = max(1, min(page, pages))
        start = (page - 1) * _REVIEW_PAGE_SIZE
        slice_ = items[start:start + _REVIEW_PAGE_SIZE]
        body = _review_table(_review_rows(slice_, upload=upload, with_source=True), with_source=True)
        nav = _page_links(approval_id, secret, page, pages)
    elif sampled:
        # A Gmail sample is already short: show every entry with its sender.
        body = _review_table(_review_rows(items, upload=upload, with_source=True), with_source=True)
        nav = (
            f"<nav><a href='/approvals/{quote(approval_id)}?k={quote(secret, safe='')}&all=1'>"
            f"show all {total} {plural}</a> · "
            f"<a href='/approvals/{quote(approval_id)}/manifest.csv?k={quote(secret, safe='')}'>"
            "download CSV</a></nav>"
        )
    else:
        groups = _source_groups(review)
        auto_open = len(items) <= _REVIEW_AUTO_EXPAND
        blocks = []
        for (source_name, _source_id), group in groups:
            group_bytes = sum(int(_item_size(item) or 0) for item in group)
            amount = _human_bytes(group_bytes) if group_bytes else ""
            preview = group[:_GROUP_PREVIEW]
            hidden = len(group) - len(preview)
            rows = _review_rows(preview, upload=upload, with_source=False)
            if hidden:
                rows += f"<tr><td class='dim'>… and {hidden} more</td></tr>"
            blocks.append(
                f"<details{' open' if auto_open else ''}><summary>{len(group)} file(s) from "
                f"<bdi>{_esc(source_name)}</bdi> <span class='dim'>{amount}</span></summary>"
                f"{_review_table(rows, with_source=False)}</details>"
            )
        body = "".join(blocks)
        nav = (
            f"<nav><a href='/approvals/{quote(approval_id)}?k={quote(secret, safe='')}&all=1'>"
            f"show all {total} {plural}</a></nav>"
        )
    return (
        "<section>"
        f"{head}{note}{sample_notice}{notices}<div class='review'>{body}</div>{nav}"
        f"<p class='dim'>fingerprint {_review_fingerprint(review)} · "
        f"<a href='/approvals/{quote(approval_id)}/manifest.csv?k={quote(secret, safe='')}'>"
        "download CSV</a></p>"
        "</section>"
    )


def _review_csv(review: Dict[str, Any]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    destination = review.get("destination") or {}
    writer.writerow(
        [
            "operation", "fingerprint", "destination", "destination_id",
            "name", "id", "source_folders", "source_ids", "size_bytes", "type", "snippet",
        ]
    )
    for item in review["items"]:
        sources = _sources_of(item)
        writer.writerow(
            [
                review.get("operation", ""),
                _review_fingerprint(review),
                destination.get("name", ""),
                destination.get("id", ""),
                item.get("name", ""),
                item.get("id", ""),
                " | ".join(str(source.get("name") or "") for source in sources),
                " | ".join(str(source.get("id") or "") for source in sources),
                _item_size(item) or "",
                item.get("conversion_mime_type") or item.get("mime_type") or "",
                item.get("snippet") or "",
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def _review_page(record: Dict[str, Any], approval_id: str, secret: str, show_all: bool, page: int) -> str:
    status = record.get("status", "?")
    action_forms = ""
    if status == "pending":
        action_forms = f"""
        <form method="post" action="/approvals/{_esc(approval_id)}/approve">
          <input type="hidden" name="k" value="{_esc(secret)}">
          <button class="approve" type="submit">APPROVE</button>
        </form>
        <form method="post" action="/approvals/{_esc(approval_id)}/deny">
          <input type="hidden" name="k" value="{_esc(secret)}">
          <button class="deny" type="submit">DENY</button>
        </form>"""
    review = (
        _review_html(record["review"], approval_id=approval_id, secret=secret, show_all=show_all, page=page)
        if "review" in record
        else ""
    )
    return f"""<!doctype html><meta charset="utf-8"><title>Workspace Operator approval</title>
<style>body{{background:#080b09;color:#93e3a0;font:12.5px/1.35 ui-monospace,"Cascadia Mono","Cascadia Code",Consolas,"Courier New",monospace;max-width:960px;margin:24px auto;padding:0 16px}}
h1{{font-size:14px;color:#d6ffde;letter-spacing:.1em;text-transform:uppercase;margin:0 0 12px}}
b{{color:#eaff9c;font-weight:600}} a{{color:#7fd7ff;text-decoration:none}} a:hover{{text-decoration:underline}}
.card{{border:1px solid #1d3a24;background:#0c120d;padding:12px 14px}}
p{{margin:4px 0}} .dim{{color:#5c8a64}} .warn{{color:#e6c07b;margin:6px 0 0;padding-left:18px}}
table{{width:100%;border-collapse:collapse;font-size:11.5px;margin:4px 0 8px}}
th{{text-align:left;color:#5c8a64;font-weight:400;padding:1px 8px;border-bottom:1px solid #1d3a24;text-transform:uppercase;letter-spacing:.06em}}
td{{padding:1px 8px;border-bottom:1px solid #14251a;overflow-wrap:anywhere}}
td.name{{color:#c8f5cf}} td.src{{color:#7fbf8a;white-space:nowrap}}
details{{margin:3px 0}} summary{{cursor:pointer;color:#eaff9c;padding:2px 0}}
.review{{max-height:60vh;overflow:auto;margin:8px 0}}
nav{{margin:8px 0;color:#5c8a64}} nav a{{margin-right:6px}}
form{{display:inline-block;margin:8px 8px 0 0}} button{{font:inherit;cursor:pointer;padding:4px 14px;border-radius:2px}}
.approve{{background:#0f2b16;color:#9ef0a8;border:1px solid #2f6b3a}} .deny{{background:#2b1010;color:#f0a8a8;border:1px solid #6b2f2f}}
.head{{font-size:12.5px}} code{{color:#7fbf8a}}
</style>
<h1>Workspace Operator · approval</h1>
<div class="card">
<p><span class="dim">action</span> {_esc(record.get("summary", ""))}</p>
<p><span class="dim">status</span> {_esc(status)} · <span class="dim">expires</span> {_esc(record.get("expires_at", ""))}</p>
{review}
{action_forms}
<p class="dim">Approve allows exactly what is listed above. If the chat still waits, it resumes by itself; otherwise tell the agent your decision.</p>
<p class="dim">request {_esc(approval_id)}</p>
</div>"""


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
        show_all = request.query_params.get("all") == "1"
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            page = 1
        return HTMLResponse(
            _review_page(record, approval_id, secret, show_all, page),
            headers=_PAGE_HEADERS,
        )

    async def approval_manifest(request: Request):
        if approval_store is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        approval_id = request.path_params.get("approval_id", "")
        secret = request.query_params.get("k", "")
        if not approval_store.verify_secret(approval_id, secret):
            return JSONResponse({"error": "not found"}, status_code=404)
        record = approval_store.get(approval_id)
        if "review" not in record:
            return JSONResponse({"error": "no review for this request"}, status_code=404)
        headers = dict(_PAGE_HEADERS)
        headers.update(
            {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f'attachment; filename="approval-{approval_id}.csv"',
            }
        )
        return Response(_review_csv(record["review"]), headers=headers)

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
            Route("/approvals/{approval_id}/manifest.csv", approval_manifest, methods=["GET"]),
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
