"""Safe handling of files that hold secrets (OAuth token, approvals, keys).

* ``write_private`` writes atomically (temp file + replace) and restricts the file
  to the current user: mode 0600 on POSIX, an owner-only ACL on Windows.
* ``file_lock`` serialises token refreshes across threads and processes.
* ``protected_paths`` is the single list of locations an agent-driven file
  operation (for example ``drive_upload``) must never read.
* ``audit_permissions`` reports secret files that other users can read.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

_THREAD_LOCKS: dict = {}
_THREAD_LOCKS_GUARD = threading.Lock()

SECRET_FILE_NAMES = frozenset(
    {
        "token.json",
        "token.pickle",
        "oauth.keys.json",
        "credentials.json",
        "client_secret.json",
        "service-account.json",
        "service_account.json",
        ".env",
        "id_rsa",
        "id_ed25519",
    }
)
SECRET_NAME_PREFIXES = (".env", "token.json.", "client_secret")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_BROAD_GROUPS = ("everyone", "builtin\\users", "authenticated users", "\\users:")


def restrict_to_owner(path: Path) -> None:
    """Best effort: make ``path`` readable and writable by the current user only."""
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME")
            if not user:
                return
            # Drop inherited ACEs, then grant only the current user.
            subprocess.run(  # noqa: S603 - fixed argument list, no shell
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],  # noqa: S607
                check=False,
                capture_output=True,
                timeout=15,
            )
        else:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
    except (OSError, subprocess.SubprocessError):
        pass


def write_private(path: Path | str, text: str) -> None:
    """Atomically write ``text`` to ``path``, readable by the owner only."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(temporary), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        restrict_to_owner(temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            with contextlib.suppress(OSError):
                temporary.unlink()


@contextlib.contextmanager
def file_lock(path: Path | str, timeout: float = 30.0) -> Iterator[None]:
    """Exclusive lock for ``path`` across threads and processes (lock file based)."""
    lock_path = Path(str(path) + ".lock")
    key = str(lock_path.resolve())
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(timeout=timeout):
        raise TimeoutError(f"Timed out waiting for {lock_path}")
    fd: Optional[int] = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                # A crashed process must not block refreshes forever.
                with contextlib.suppress(OSError):
                    if time.time() - lock_path.stat().st_mtime > timeout * 2:
                        lock_path.unlink()
                        continue
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Timed out waiting for {lock_path}") from None
                time.sleep(0.05)
        yield
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                lock_path.unlink()
        thread_lock.release()


def protected_paths(config: object = None) -> List[Path]:
    """Locations that must never be read or exported by agent-driven file tools."""
    home = Path.home()
    paths = [home / ".google", home / ".ssh", home / ".aws", home / ".gnupg", home / ".config" / "gcloud"]
    if config is not None:
        for attr in (
            "token_file",
            "client_secrets_file",
            "backup_dir",
            "approval_dir",
            "bulk_dir",
            "audit_log",
            "log_file",
        ):
            value = getattr(config, attr, None)
            if value:
                paths.append(Path(str(value)).expanduser())
        from .approvals import approval_root  # local import: avoid a cycle

        with contextlib.suppress(Exception):
            paths.append(approval_root(config))  # type: ignore[arg-type]
    return paths


def looks_like_secret_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SECRET_FILE_NAMES
        or name.startswith(SECRET_NAME_PREFIXES)
        or name.endswith(SECRET_SUFFIXES)
    )


def is_protected(path: Path, config: object = None) -> bool:
    """True when ``path`` is a secret file or lives inside a protected location."""
    try:
        resolved = path.resolve()
    except OSError:
        return True
    if looks_like_secret_file(resolved):
        return True
    for entry in protected_paths(config):
        try:
            root = entry.resolve()
        except OSError:
            continue
        if resolved == root or resolved.is_relative_to(root):
            return True
    return False


def audit_permissions(paths: Iterable[Path]) -> List[str]:
    """Return human-readable warnings for secret files other users can read."""
    warnings: List[str] = []
    for path in paths:
        if not path.exists():
            continue
        if os.name == "nt":
            try:
                result = subprocess.run(  # noqa: S603
                    ["icacls", str(path)],  # noqa: S607
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            for line in result.stdout.splitlines():
                lowered = line.lower()
                if any(group in lowered for group in _BROAD_GROUPS):
                    warnings.append(
                        f"{path}: readable by a broad group ({line.strip()[:80]})"
                    )
                    break
        else:
            mode = path.stat().st_mode & 0o077
            if mode:
                warnings.append(f"{path}: permissions {oct(path.stat().st_mode & 0o777)} allow other users")
    return warnings


def mask(value: Optional[str], keep: int = 4) -> str:
    """Show only the tail of a secret, for diagnostics."""
    if not value:
        return "(not set)"
    return "*" * max(0, len(value) - keep) + value[-keep:]


__all__ = [
    "audit_permissions",
    "file_lock",
    "is_protected",
    "looks_like_secret_file",
    "mask",
    "protected_paths",
    "restrict_to_owner",
    "write_private",
]
