"""Tool profiles — decide which MCP tools this server exposes.

A profile is a local, server-side guardrail. It complements, but never
replaces, two other layers:

* OAuth scopes — what Google actually lets the token do.
* Client-side permissions — Antigravity ``mcp(server/tool)`` policies,
  confirmations, and the ``readOnlyHint`` / ``destructiveHint`` annotations.

Three profiles are available:

``full``
    Every tool. The default, and the behaviour of every release before 1.1.0.

``read-write``
    Everything except tools annotated ``destructiveHint=True``.

``read-only``
    Only tools annotated ``readOnlyHint=True``.

Explicit ``allowed_tools`` / ``denied_tools`` lists are applied on top of the
profile, so one deployment can expose exactly the surface it needs: for
example ``profile: read-write`` plus ``denied_tools: [send_email, share_file]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, TypeVar

PROFILE_FULL = "full"
PROFILE_CORE = "core"
PROFILE_READ_WRITE = "read-write"
PROFILE_READ_ONLY = "read-only"

VALID_PROFILES = (PROFILE_CORE, PROFILE_FULL, PROFILE_READ_WRITE, PROFILE_READ_ONLY)

T = TypeVar("T")


class ProfileError(ValueError):
    """Raised when a profile name or a tool list is invalid."""


def _annotations(tool: object) -> object:
    return getattr(tool, "annotations", None)


def _hint(annotations: object, snake: str, camel: str) -> bool:
    """Read an annotation across MCP SDK 1.x (camelCase) and 2.x (snake_case)."""
    value = getattr(annotations, snake, None)
    if value is None:
        value = getattr(annotations, camel, None)
    return bool(value)


def is_read_only(tool: object) -> bool:
    return _hint(_annotations(tool), "read_only_hint", "readOnlyHint")


def is_destructive(tool: object) -> bool:
    return _hint(_annotations(tool), "destructive_hint", "destructiveHint")


def _normalize(names: Optional[Sequence[str]]) -> Optional[frozenset]:
    if names is None:
        return None
    cleaned = {str(name).strip() for name in names if str(name).strip()}
    return frozenset(cleaned)


@dataclass(frozen=True)
class ToolProfile:
    """An immutable filter over MCP tools."""

    name: str
    allowed: Optional[frozenset] = None
    denied: frozenset = frozenset()

    def allows(self, tool: object) -> bool:
        """Return True when ``tool`` passes the profile.

        Pass a tool object (anything with ``name`` and optional
        ``annotations``) so annotation-based profiles can be evaluated. A bare
        tool name is only enough for allow/deny lists: with ``read-only`` an
        unknown name is rejected, because the annotation cannot be checked.
        Use :meth:`allowed_names` to pre-compute the callable surface.
        """
        tool_name = getattr(tool, "name", tool)
        if not isinstance(tool_name, str):  # pragma: no cover - defensive
            return False

        if self.allowed is not None and tool_name not in self.allowed:
            return False
        if tool_name in self.denied:
            return False

        if self.name == PROFILE_READ_ONLY:
            return is_read_only(tool)
        if self.name == PROFILE_READ_WRITE:
            return not is_destructive(tool)
        return True

    def filter(self, tools: Iterable[T]) -> List[T]:
        """Return the tools this profile exposes, preserving order."""
        return [tool for tool in tools if self.allows(tool)]

    def allowed_names(self, tools: Iterable[T]) -> frozenset:
        """Return the names of the tools this profile exposes."""
        return frozenset(getattr(tool, "name", tool) for tool in self.filter(tools))

    def describe(self) -> str:
        parts = [f"profile={self.name}"]
        if self.allowed is not None:
            parts.append(f"allowed={len(self.allowed)}")
        if self.denied:
            parts.append(f"denied={len(self.denied)}")
        return " ".join(parts)


def resolve_profile(
    name: Optional[str] = None,
    allowed_tools: Optional[Sequence[str]] = None,
    denied_tools: Optional[Sequence[str]] = None,
) -> ToolProfile:
    """Build a :class:`ToolProfile` from configuration values.

    Args:
        name: One of ``core``, ``full``, ``read-write``, ``read-only``.
            ``None`` or an empty string means ``full``.
        allowed_tools: Optional allow-list applied on top of the profile.
        denied_tools: Optional deny-list applied last.

    Raises:
        ProfileError: If the profile name is unknown.
    """
    profile_name = (name or PROFILE_FULL).strip().lower()
    if profile_name not in VALID_PROFILES:
        raise ProfileError(
            f"Unknown tool profile {profile_name!r}. "
            f"Valid values: {', '.join(VALID_PROFILES)}."
        )

    allowed = _normalize(allowed_tools)
    if profile_name == PROFILE_CORE:
        from .toolset.catalog import CORE_TOOL_NAMES

        allowed = CORE_TOOL_NAMES if allowed is None else allowed & CORE_TOOL_NAMES
    denied = _normalize(denied_tools) or frozenset()

    if allowed is not None and denied:
        both = allowed & denied
        if both:
            # Deny wins; spelling it out avoids a silent surprise at runtime.
            allowed = frozenset(allowed - both)

    return ToolProfile(name=profile_name, allowed=allowed, denied=denied)
