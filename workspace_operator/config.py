import json
import logging as _logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .runtime import parse_bool

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/postmaster.domain",
    "https://www.googleapis.com/auth/postmaster.traffic.readonly",
]

# File names looked for by the config lookup. The locations are never written
# into the code: every candidate is derived at run time from the environment
# (explicit path, current directory, or the per-user directory of the OS).
CONFIG_FILE_NAMES = ("config.yaml", "config.yml", "config.json")


class ConfigFileError(RuntimeError):
    """An explicitly requested configuration file cannot be used."""


@dataclass(frozen=True)
class Config:
    client_secrets_file: str
    token_file: str
    backup_dir: str
    log_file: Optional[str]
    mcp_auth_token: Optional[str]
    scopes: List[str]
    log_level: int = _logging.INFO
    tool_profile: str = "core"
    scope_routing: bool = True
    allow_public_sharing: bool = False
    allowed_tools: Optional[List[str]] = None
    denied_tools: Optional[List[str]] = None
    dry_run: bool = False
    audit_log: Optional[str] = None
    retry_attempts: int = 3
    http_tokens: Optional[Dict[str, str]] = None
    bulk_dir: Optional[str] = None
    approval_dir: Optional[str] = None
    approval_ttl: int = 900
    approval_browser_wait: int = 0
    approval_url: Optional[str] = "http://127.0.0.1:8765"
    bulk_max_items: int = 300
    bulk_hard_limit: int = 10000
    bulk_concurrency: int = 8
    bulk_plan_ttl: int = 900
    bulk_protected_ids: List[str] = field(default_factory=list)
    bulk_protected_patterns: List[str] = field(default_factory=list)
    bulk_allow_shared_drives: bool = False
    upload_roots: Optional[List[str]] = None
    operation_dir: Optional[str] = None
    operation_ttl: int = 600
    # Which config file was used ("explicit", "local", "user") and its path;
    # "defaults" means no file was found. Reported by the log and ``doctor``.
    config_file: Optional[str] = None
    config_source: str = "defaults"


def _default_path(*parts: str) -> str:
    return os.path.join(os.path.expanduser("~"), *parts)


def _user_config_dir() -> Path:
    """Per-user configuration directory reported by the operating system."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "workspace-operator"
        return Path(_default_path(".config")) / "workspace-operator"
    if sys.platform == "darwin":
        return Path(
            _default_path("Library", "Application Support", "workspace-operator")
        )
    base = os.environ.get("XDG_CONFIG_HOME") or _default_path(".config")
    return Path(base) / "workspace-operator"


def _discover_config() -> Optional[Tuple[Path, str]]:
    """First existing config file and where it came from: current dir, then user dir."""
    local = Path.cwd()
    for name in CONFIG_FILE_NAMES:
        candidate = local / name
        if candidate.is_file():
            return candidate, "local"
    user_dir = _user_config_dir()
    for name in CONFIG_FILE_NAMES:
        candidate = user_dir / name
        if candidate.is_file():
            return candidate, "user"
    return None


def _env_list(name: str) -> Optional[List[str]]:
    """Read a comma-separated list from an environment variable."""
    raw = os.environ.get(name)
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_config_file(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}

    _, ext = os.path.splitext(path.lower())
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if ext == ".json":
        return json.loads(content)
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "YAML config file detected but PyYAML is not installed. "
                "Install PyYAML or use JSON config."
            ) from exc
        return yaml.safe_load(content) or {}

    raise ValueError(f"Unsupported config format: {ext}")


def load_config(
    config_path: Optional[str] = None, tool_profile: Optional[str] = None
) -> Config:
    """Resolve settings: explicit file, then lookup, then environment, then defaults.

    ``config_path`` (``--config``) wins over ``MCP_CONFIG_FILE``; an explicitly
    named file that does not exist is an error, not a silent fallback.
    """
    explicit = config_path or os.environ.get("MCP_CONFIG_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigFileError(
                f"Config file not found: {path}. Point --config or MCP_CONFIG_FILE "
                "at an existing config.yaml/.yml/.json, or unset it to use the "
                "lookup (./config.yaml, then <user config dir>/workspace-operator/"
                "config.yaml) and the built-in defaults."
            )
        resolved: Optional[Path] = path
        source = "explicit"
    else:
        found = _discover_config()
        resolved = found[0] if found else None
        source = found[1] if found else "defaults"
    config_file = str(resolved) if resolved is not None else None
    file_config = _load_config_file(config_file) if config_file else {}

    client_secrets_file = os.environ.get(
        "GOOGLE_CLIENT_SECRETS_FILE",
        file_config.get("client_secrets_file", _default_path(".google", "oauth.keys.json")),
    )
    token_file = os.environ.get(
        "GOOGLE_TOKEN_FILE",
        file_config.get("token_file", _default_path(".google", "token.json")),
    )
    backup_dir = os.environ.get(
        "GOOGLE_BACKUP_DIR",
        file_config.get("backup_dir", _default_path(".google", "backups")),
    )
    log_file = os.environ.get(
        "GOOGLE_LOG_FILE",
        file_config.get("log_file", _default_path(".google", "mcp_operations.log")),
    )
    mcp_auth_token = os.environ.get("MCP_AUTH_TOKEN", file_config.get("mcp_auth_token"))

    scopes = file_config.get("scopes") or DEFAULT_SCOPES
    scopes = list(scopes)

    log_level_str = os.environ.get(
        "GOOGLE_LOG_LEVEL", str(file_config.get("log_level", "INFO"))
    )
    log_level = getattr(_logging, log_level_str.upper(), _logging.INFO)

    tool_profile = (
        tool_profile
        or os.environ.get("MCP_TOOL_PROFILE")
        or str(file_config.get("tool_profile", "core"))
    )

    allowed_tools = _env_list("MCP_ALLOWED_TOOLS") or file_config.get("allowed_tools")
    if allowed_tools is not None:
        allowed_tools = [str(item) for item in allowed_tools]

    denied_tools = _env_list("MCP_DENIED_TOOLS") or file_config.get("denied_tools")
    if denied_tools is not None:
        denied_tools = [str(item) for item in denied_tools]

    http_tokens = file_config.get("http_tokens")
    if http_tokens is not None:
        http_tokens = {str(name): str(token) for name, token in dict(http_tokens).items()}

    dry_run = parse_bool(
        os.environ.get("MCP_DRY_RUN", file_config.get("dry_run", False))
    )

    audit_log = os.environ.get(
        "MCP_AUDIT_LOG", file_config.get("audit_log")
    )

    try:
        retry_attempts = int(
            os.environ.get("MCP_RETRY_ATTEMPTS", file_config.get("retry_attempts", 3))
        )
    except (TypeError, ValueError):
        retry_attempts = 3

    bulk_config = file_config.get("bulk")
    if not isinstance(bulk_config, dict):
        bulk_config = {}

    def _bulk_int(name: str, key: str, default: int) -> int:
        try:
            return int(os.environ.get(name, bulk_config.get(key, default)))
        except (TypeError, ValueError):
            return default

    bulk_dir = os.environ.get("MCP_BULK_DIR", bulk_config.get("dir"))
    approval_dir = os.environ.get("MCP_APPROVAL_DIR", file_config.get("approval_dir"))
    approval_url = os.environ.get("MCP_APPROVAL_URL", file_config.get("approval_url", "http://127.0.0.1:8765"))
    try:
        approval_ttl = int(os.environ.get("MCP_APPROVAL_TTL", file_config.get("approval_ttl", 900)))
    except (TypeError, ValueError):
        approval_ttl = 900
    try:
        approval_browser_wait = min(45, max(0, int(os.environ.get(
            "MCP_APPROVAL_BROWSER_WAIT", file_config.get("approval_browser_wait", 0)
        ))))
    except (TypeError, ValueError):
        approval_browser_wait = 0
    bulk_protected_ids = (
        _env_list("MCP_BULK_PROTECTED_IDS") or bulk_config.get("protected_ids") or []
    )
    bulk_protected_patterns = (
        _env_list("MCP_BULK_PROTECTED_PATTERNS")
        or bulk_config.get("protected_patterns")
        or []
    )
    bulk_allow_shared_drives = parse_bool(
        os.environ.get(
            "MCP_BULK_ALLOW_SHARED_DRIVES",
            bulk_config.get("allow_shared_drives", False),
        )
    )

    upload_roots = _env_list("MCP_UPLOAD_ROOTS") or file_config.get("upload_roots")
    if upload_roots is not None:
        upload_roots = [str(item) for item in upload_roots]

    operation_dir = os.environ.get("MCP_OPERATION_DIR", file_config.get("operation_dir"))
    try:
        operation_ttl = int(
            os.environ.get("MCP_OPERATION_TTL", file_config.get("operation_ttl", 600))
        )
    except (TypeError, ValueError):
        operation_ttl = 600

    return Config(
        client_secrets_file=client_secrets_file,
        token_file=token_file,
        backup_dir=backup_dir,
        log_file=log_file,
        mcp_auth_token=mcp_auth_token,
        scopes=scopes,
        log_level=log_level,
        tool_profile=tool_profile,
        scope_routing=parse_bool(
            os.environ.get("MCP_SCOPE_ROUTING", file_config.get("scope_routing", True))
        ),
        allow_public_sharing=parse_bool(
            os.environ.get(
                "MCP_ALLOW_PUBLIC_SHARING",
                file_config.get("allow_public_sharing", False),
            )
        ),
        allowed_tools=allowed_tools,
        denied_tools=denied_tools,
        dry_run=dry_run,
        audit_log=audit_log,
        retry_attempts=retry_attempts,
        http_tokens=http_tokens,
        bulk_dir=bulk_dir,
        approval_dir=approval_dir,
        approval_ttl=approval_ttl,
        approval_browser_wait=approval_browser_wait,
        approval_url=approval_url,
        bulk_max_items=_bulk_int("MCP_BULK_MAX_ITEMS", "max_items", 300),
        bulk_hard_limit=_bulk_int("MCP_BULK_HARD_LIMIT", "hard_limit", 10000),
        bulk_concurrency=_bulk_int("MCP_BULK_CONCURRENCY", "concurrency", 8),
        bulk_plan_ttl=_bulk_int("MCP_BULK_PLAN_TTL", "plan_ttl", 900),
        bulk_protected_ids=[str(item) for item in bulk_protected_ids],
        bulk_protected_patterns=[str(item) for item in bulk_protected_patterns],
        bulk_allow_shared_drives=bulk_allow_shared_drives,
        upload_roots=upload_roots,
        operation_dir=operation_dir,
        operation_ttl=operation_ttl,
        config_file=config_file,
        config_source=source,
    )
