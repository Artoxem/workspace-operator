"""Read granted Google OAuth scopes for startup scope routing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _short(scope: str) -> str:
    return str(scope).rstrip("/").rsplit("/", 1)[-1]


def read_granted_scopes(token_file: str | Path) -> Optional[frozenset[str]]:
    """Return short scope names from a token file.

    ``None`` means "unknown, do not filter". An empty set is also treated as
    unknown by the surface filter, so a missing token never hides everything.
    """
    path = Path(token_file)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    scopes = data.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        return None
    return frozenset(_short(scope) for scope in scopes if scope)
