"""Cached Google API clients.

Every handler used to call get_creds(config) and build(api, version, ...) on each
invocation: the token file was re-read and the discovery document parsed again for
every tool call and every bulk worker.

api_client() keeps one client per (config, api, version) and reuses it, so a running
server builds the Drive client once. The cache belongs to the Config *object*: a
process has one Config for its lifetime and gets the cache for free, while a test (or
a second server with other settings) that creates a new Config starts clean and cannot
inherit a client built under a different token, scope set or mock. Entries are dropped
when the Config is collected.

Credentials are cached the same way. They stay valid because google-auth refreshes an
expired credential before a request; reset() drops everything after a failed refresh
or when the token file changed on disk.
"""

from __future__ import annotations

import threading
import weakref
from typing import Any, Dict, Optional, Tuple

from googleapiclient import discovery

from . import auth as auth_module
from .config import Config

_LOCK = threading.RLock()
_SERVICES: Dict[int, Tuple[weakref.ref, Dict[Tuple[str, str], Any]]] = {}
_CREDS: Dict[int, Tuple[weakref.ref, Any]] = {}


def _forget(key: int, reference: weakref.ref) -> None:
    with _LOCK:
        for table in (_SERVICES, _CREDS):
            entry = table.get(key)
            if entry is not None and entry[0] is reference:
                table.pop(key, None)


def _slot(config: Config) -> int:
    """Identity slot for config, reset when the object was replaced."""
    key = id(config)
    with _LOCK:
        entry = _SERVICES.get(key)
        if entry is not None and entry[0]() is not config:
            _SERVICES.pop(key, None)
        if key not in _SERVICES:
            _SERVICES[key] = (
                weakref.ref(config, lambda ref, k=key: _forget(k, ref)),  # type: ignore[misc]
                {},
            )
    return key


def credentials(config: Config):
    """OAuth credentials for config, read from disk once."""
    key = id(config)
    with _LOCK:
        entry = _CREDS.get(key)
        if entry is not None and entry[0]() is not config:
            _CREDS.pop(key, None)
            entry = None
        cached = entry[1] if entry else None
    if cached is not None:
        if not cached.expired:
            return cached
        if cached.expired and cached.refresh_token:
            try:
                from google.auth.transport.requests import Request

                cached.refresh(Request())
                return cached
            except Exception:  # noqa: BLE001 - fall back to a fresh get_creds
                pass

    # Resolved through the module so tests that patch
    # workspace_operator.auth.get_creds keep working.
    creds = auth_module.get_creds(config)
    with _LOCK:
        _CREDS[key] = (
            weakref.ref(config, lambda ref, k=key: _forget(k, ref)),  # type: ignore[misc]
            creds,
        )
    return creds


def api_client(config: Config, api: str, version: str, **kwargs: Any):
    """Return a cached client for api/version."""
    key = _slot(config)
    with _LOCK:
        client = _SERVICES[key][1].get((api, version))
    if client is not None:
        return client

    client = discovery.build(
        api,
        version,
        credentials=credentials(config),
        cache_discovery=kwargs.pop("cache_discovery", False),
        **kwargs,
    )
    with _LOCK:
        _SERVICES[key][1][(api, version)] = client
    return client


def reset(config: Optional[Config] = None) -> None:
    """Forget cached clients; all of them when config is None."""
    with _LOCK:
        if config is None:
            _SERVICES.clear()
            _CREDS.clear()
        else:
            _SERVICES.pop(id(config), None)
            _CREDS.pop(id(config), None)


def cached_service_count(config: Config) -> int:
    """Diagnostics: how many clients are cached for one configuration."""
    with _LOCK:
        entry = _SERVICES.get(id(config))
        return len(entry[1]) if entry else 0
