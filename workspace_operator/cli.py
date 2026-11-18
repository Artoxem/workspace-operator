"""Command line entry point: ``python -m workspace_operator``.

Commands:

* ``tools``   — list the tool catalog (optionally for one profile);
* ``doctor``  — check configuration, token, scopes and service connectivity;
* ``version`` — print the package version;
* ``serve``   — start the stdio MCP server (same as ``python server.py``).
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .config import Config, load_config

PROFILES = ("core", "full", "read-write", "read-only")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = True


def tool_catalog(profile: str = "core") -> List[Dict[str, Any]]:
    from .server import _tools
    from .toolset.catalog import build_catalog
    from .toolset.surface import build_surface

    surface = build_surface(build_catalog(_tools()), profile)
    catalog: List[Dict[str, Any]] = []
    for tool in surface.tools:
        catalog.append(
            {
                "name": tool.name,
                "kind": tool.safety.value,
                "actions": list(tool.action_names),
                "description": (tool.description or "").split("\n")[0],
            }
        )
    return catalog


def render_catalog(catalog: Sequence[Dict[str, Any]]) -> str:
    if not catalog:
        return "(no tools)"
    width = max(len(item["name"]) for item in catalog) + 2
    lines = [f"{'TOOL'.ljust(width)}KIND         DESCRIPTION"]
    for item in catalog:
        lines.append(
            f"{item['name'].ljust(width)}{item['kind'].ljust(13)}{item['description']}"
        )
    lines.append("")
    lines.append(f"{len(catalog)} tool(s)")
    return "\n".join(lines)


def check_config(config: Config) -> List[Check]:
    checks: List[Check] = []

    secrets = Path(config.client_secrets_file).expanduser()
    checks.append(Check("client secrets", secrets.exists(), str(secrets), critical=True))

    token = Path(config.token_file).expanduser()
    checks.append(Check("token file", token.exists(), str(token), critical=False))

    if config.log_file:
        log_path = Path(config.log_file).expanduser()
        checks.append(
            Check("log directory", log_path.parent.exists(), str(log_path.parent), critical=False)
        )

    if config.backup_dir:
        backup = Path(config.backup_dir).expanduser()
        checks.append(Check("backup directory", backup.exists(), str(backup), critical=False))

    if config.audit_log:
        audit = Path(config.audit_log).expanduser()
        checks.append(
            Check("audit directory", audit.parent.exists(), str(audit.parent), critical=False)
        )

    checks.append(
        Check(
            "tool profile",
            config.tool_profile in PROFILES,
            config.tool_profile,
            critical=True,
        )
    )
    checks.append(
        Check("dry run", True, "enabled" if config.dry_run else "disabled", critical=False)
    )
    checks.extend(check_security(config))
    return checks


def check_security(config: Config) -> List[Check]:
    """Hygiene checks for secrets: where they live and who can read them."""
    import os

    from .secure_files import audit_permissions, mask

    checks: List[Check] = []

    if config.mcp_auth_token and not os.environ.get("MCP_AUTH_TOKEN"):
        checks.append(
            Check(
                "auth token source",
                False,
                f"mcp_auth_token is stored in the config file ({mask(config.mcp_auth_token)}); "
                "prefer the MCP_AUTH_TOKEN environment variable",
                critical=False,
            )
        )

    secret_paths = [
        Path(config.token_file).expanduser(),
        Path(config.client_secrets_file).expanduser(),
    ]
    google_dir = Path(config.token_file).expanduser().parent
    if google_dir.exists():
        known = {path.name for path in secret_paths}
        extras = sorted(
            entry.name
            for entry in google_dir.iterdir()
            if entry.is_file()
            and entry.name not in known
            and (
                entry.name.startswith("token.json.")
                or entry.name in {"service-account.json", "service_account.json", "credentials.json"}
            )
        )
        if extras:
            checks.append(
                Check(
                    "stray secret files",
                    False,
                    f"unused credentials next to the token: {', '.join(extras)} — delete them",
                    critical=False,
                )
            )
        secret_paths.append(google_dir)

    warnings = audit_permissions(secret_paths)
    checks.append(
        Check(
            "secret file permissions",
            not warnings,
            "owner-only" if not warnings else "; ".join(warnings),
            critical=False,
        )
    )
    return checks


def _read_token(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check_token(config: Config, refresh: bool = True) -> List[Check]:
    token_path = Path(config.token_file).expanduser()
    if not token_path.exists():
        return [
            Check(
                "token",
                False,
                "missing — run the server once to authorize",
                critical=False,
            )
        ]

    data = _read_token(token_path)
    if data is None:
        return [Check("token", False, "unreadable JSON", critical=False)]

    checks: List[Check] = []
    granted = set(data.get("scopes") or [])
    missing = [scope for scope in config.scopes if scope not in granted]
    checks.append(
        Check(
            "scopes",
            not missing,
            "all configured scopes granted"
            if not missing
            else (
                f"missing: {', '.join(sorted(missing))} — delete token.json and "
                "re-authorize"
            ),
            critical=True,
        )
    )

    if not refresh:
        return checks

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(token_path))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            checks.append(Check("token refresh", True, "refreshed", critical=False))
        else:
            checks.append(
                Check(
                    "token refresh",
                    True,
                    "still valid" if not creds.expired else "no refresh token",
                    critical=False,
                )
            )
    except Exception as exc:  # noqa: BLE001 - reported as a check
        checks.append(Check("token refresh", False, str(exc), critical=False))

    return checks


def check_services(config: Config) -> List[Check]:
    checks: List[Check] = []
    try:
        from googleapiclient.discovery import build

        from .auth import get_creds

        creds = get_creds(config)
    except Exception as exc:  # noqa: BLE001
        return [Check("credentials", False, str(exc), critical=True)]

    probes = {
        "drive": ("drive", "v3", lambda service: service.about().get(fields="user").execute()),
        "gmail": ("gmail", "v1", lambda service: service.users().getProfile(userId="me").execute()),
        "calendar": (
            "calendar",
            "v3",
            lambda service: service.calendarList().get(calendarId="primary").execute(),
        ),
    }

    for name, (api, version, probe) in probes.items():
        try:
            service = build(api, version, credentials=creds, cache_discovery=False)
            probe(service)
            checks.append(Check(f"{name} API", True, "reachable", critical=False))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check(f"{name} API", False, str(exc)[:160], critical=False))

    return checks


def render_checks(checks: Sequence[Check]) -> str:
    lines = []
    for check in checks:
        mark = "ok  " if check.ok else "FAIL"
        lines.append(f"[{mark}] {check.name}: {check.detail}")
    return "\n".join(lines)


def cmd_tools(args: argparse.Namespace) -> int:
    catalog = tool_catalog(args.profile)
    if args.json:
        print(json.dumps(catalog, indent=2, ensure_ascii=False))
    else:
        print(render_catalog(catalog))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    print(f"Workspace Operator {__version__}\n")

    checks = check_config(config) + check_token(config, refresh=not args.offline)
    if not args.offline:
        checks += check_services(config)

    print(render_checks(checks))

    failed = [check for check in checks if not check.ok and check.critical]
    print()
    if failed:
        print(f"configuration has problems: {len(failed)} critical check(s) failed")
        return 1
    print("configuration looks good")
    return 0


def cmd_approvals(args: argparse.Namespace) -> int:
    from .approvals import ApprovalError, ApprovalStore, render_records

    config = load_config()
    store = ApprovalStore(config)
    action = args.approval_action
    try:
        if action == "list":
            records = store.list_pending()
            print(render_records(records))
            return 0
        if action == "show":
            record = store.get(args.approval_id)
            for key in (
                "id", "status", "tool", "action", "summary",
                "created_at", "expires_at", "approved_at", "used_at",
            ):
                if record.get(key):
                    print(f"{key}: {record[key]}")
            return 0
        if action == "approve":
            record = store.approve(args.approval_id)
            print(f"APPROVED {record['id']}: {record['summary']}")
            print("The agent may now retry the exact call with this approval_id.")
            return 0
        if action == "deny":
            record = store.deny(args.approval_id)
            print(f"DENIED {record['id']}: {record['summary']}")
            return 0
    except ApprovalError as exc:
        print(f"error: {exc}")
        return 1
    print("error: unknown approvals command")
    return 2


def cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import create_server, run

    if not args.http:
        asyncio.run(run())
        return 0

    from .http_transport import HttpOptions, serve_http
    from .logging import setup_logging

    config = load_config()
    logger = setup_logging(config.log_file, level=config.log_level)
    server = create_server(config, logger)
    options = HttpOptions(
        host=args.host,
        port=args.port,
        allow_network=args.allow_network,
        insecure=args.insecure,
        extra_hosts=args.allow_host,
    )
    return serve_http(server, config, logger, options, __version__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-operator",
        description="Workspace Operator — Google Workspace automation over MCP",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tools = subparsers.add_parser("tools", help="list the tool catalog")
    tools.add_argument("--profile", choices=PROFILES, default="core")
    tools.add_argument("--json", action="store_true")
    tools.set_defaults(func=cmd_tools)

    doctor = subparsers.add_parser("doctor", help="check configuration and connectivity")
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="skip token refresh and network probes",
    )
    doctor.set_defaults(func=cmd_doctor)

    approvals = subparsers.add_parser(
        "approvals", help="approve or deny destructive tool calls"
    )
    approval_sub = approvals.add_subparsers(dest="approval_action", required=True)
    approval_sub.add_parser("list", help="list pending approvals").set_defaults(
        func=cmd_approvals
    )
    approval_show = approval_sub.add_parser("show", help="show one approval")
    approval_show.add_argument("approval_id")
    approval_show.set_defaults(func=cmd_approvals)
    approval_approve = approval_sub.add_parser("approve", help="approve one call")
    approval_approve.add_argument("approval_id")
    approval_approve.set_defaults(func=cmd_approvals)
    approval_deny = approval_sub.add_parser("deny", help="deny one call")
    approval_deny.add_argument("approval_id")
    approval_deny.set_defaults(func=cmd_approvals)

    subparsers.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    serve = subparsers.add_parser("serve", help="start the MCP server (stdio or HTTP)")
    serve.add_argument("--http", action="store_true", help="serve over Streamable HTTP")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--allow-network",
        action="store_true",
        help="required to bind a non-loopback address",
    )
    serve.add_argument(
        "--insecure",
        action="store_true",
        help="acknowledge there is no TLS in front of a network-exposed bind",
    )
    serve.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="HOST[:PORT]",
        help=(
            "extra Host header to accept (repeatable); loopback names already "
            "accept any port, useful behind a proxy or a container port mapping"
        ),
    )
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
