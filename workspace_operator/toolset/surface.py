"""Build the visible tool surface from specs, profiles and OAuth scopes."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from mcp import types

from ..profiles import ToolProfile, resolve_profile
from .catalog import CORE_TOOL_NAMES
from .models import Safety, ScopeMode, Surface, ToolSpec, safety_from_annotations


def _copy_schema(schema) -> dict:
    return dict(schema or {})


def build_legacy_surface(tools: Sequence[types.Tool], domain: str = "legacy") -> Surface:
    """Wrap the current MCP tool definitions without changing their behaviour.

    This keeps the refactor incremental: the server can switch to specs first,
    then replace the legacy definitions with consolidated ones.
    """
    specs = []
    for tool in tools:
        safety = safety_from_annotations(tool.annotations)
        specs.append(
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                input_schema=_copy_schema(tool.input_schema),
                annotations=tool.annotations,
                domain=domain,
                safety=safety,
                legacy=tool.name,
            )
        )
    return Surface(tuple(specs), profile="legacy")


def filter_by_scopes(
    tools: Iterable[ToolSpec],
    granted_scopes: Optional[Iterable[str]],
) -> tuple[ToolSpec, ...]:
    """Return tools whose scope requirements are satisfied.

    An empty/unknown scope set means "do not filter": an incomplete token file
    must not silently hide the whole server. Scope implications (for example
    ``drive`` covering ``drive.readonly``) are encoded in the spec itself.
    """
    granted = frozenset(granted_scopes or ())
    if not granted:
        return tuple(tools)

    visible = []
    for tool in tools:
        required = tool.required_scopes
        if not required:
            visible.append(tool)
            continue
        if tool.scope_mode is ScopeMode.ANY:
            matched = bool(required & granted)
        else:
            matched = required <= granted
        if matched:
            visible.append(tool)
    return tuple(visible)


def build_surface(
    tools: Iterable[ToolSpec],
    profile: str | ToolProfile = "core",
    granted_scopes: Optional[Iterable[str]] = None,
    allowed: Optional[Iterable[str]] = None,
    denied: Optional[Iterable[str]] = None,
) -> Surface:
    """Apply scope routing first, then the named profile."""
    scoped = filter_by_scopes(tools, granted_scopes)
    if profile == "core":
        active = ToolProfile("core", allowed=CORE_TOOL_NAMES)
    else:
        active = profile if isinstance(profile, ToolProfile) else resolve_profile(profile)
    visible = tuple(active.filter(scoped))
    if allowed is not None:
        allowed_set = frozenset(allowed)
        visible = tuple(tool for tool in visible if tool.name in allowed_set)
    if denied:
        denied_set = frozenset(denied)
        visible = tuple(tool for tool in visible if tool.name not in denied_set)
    name = active.name
    return Surface(visible, profile=name)
