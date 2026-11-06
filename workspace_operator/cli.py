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

PROFILES = ("full", "read-write", "read-only")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = True


def tool_catalog(profile: str = "full") -> List[Dict[str, Any]]:
    from .profiles import resolve_profile
    from .server import _tools

    tools = _tools()
    exposed = resolve_profile(profile).filter(tools)
    catalog: List[Dict[str, Any]] = []
    for tool in exposed:
        annotations = getattr(tool, "annotations", None)
        kind = "read" if getattr(annotations, "readOnlyHint", False) else "write"
        if getattr(annotations, "destructiveHint", False):
            kind = "destructive"
        catalog.append(
            {
                "name": tool.name,
                "kind": kind,
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
            else f"missing: {', '.join(sorted(missing))}",
            critical=False,
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
        print(f"{len(failed)} critical problem(s) — see FAIL lines above")
        return 1
    print("configuration looks good")
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def cmd_serve(_: argparse.Namespace) -> int:
    from .server import run

    asyncio.run(run())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-operator",
        description="Workspace Operator — Google Workspace automation over MCP",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tools = subparsers.add_parser("tools", help="list the tool catalog")
    tools.add_argument("--profile", choices=PROFILES, default="full")
    tools.add_argument("--json", action="store_true")
    tools.set_defaults(func=cmd_tools)

    doctor = subparsers.add_parser("doctor", help="check configuration and connectivity")
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="skip token refresh and network probes",
    )
    doctor.set_defaults(func=cmd_doctor)

    subparsers.add_parser("version", help="print the version").set_defaults(func=cmd_version)
    subparsers.add_parser("serve", help="start the stdio MCP server").set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
