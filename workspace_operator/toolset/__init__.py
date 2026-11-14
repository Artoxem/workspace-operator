"""Typed tool surface used by the MCP server.

The module is intentionally transport-free: it describes tools, their actions,
safety class and scope requirements, and can build the visible surface for a
profile. The server remains responsible for MCP wiring and handler dispatch.
"""

from .models import ActionSpec, CallPlan, Safety, ScopeMode, Surface, ToolSpec
from .catalog import CORE_TOOL_NAMES, REMOVED_ALIAS_NAMES, build_aliases, build_catalog
from .surface import build_legacy_surface, build_surface, filter_by_scopes
from .routing import RoutingError, resolve_call

__all__ = [
    "ActionSpec",
    "CORE_TOOL_NAMES",
    "REMOVED_ALIAS_NAMES",
    "CallPlan",
    "RoutingError",
    "Safety",
    "ScopeMode",
    "Surface",
    "ToolSpec",
    "build_aliases",
    "build_catalog",
    "build_legacy_surface",
    "build_surface",
    "filter_by_scopes",
    "resolve_call",
]
