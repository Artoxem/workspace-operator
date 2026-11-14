"""Core data model for the tool surface."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from mcp import types


class Safety(str, Enum):
    """How a tool behaves for profiles and annotations."""

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ScopeMode(str, Enum):
    """How ``required_scopes`` are matched against granted scopes."""

    ANY = "any"
    ALL = "all"


@dataclass(frozen=True)
class ActionSpec:
    """One action inside a consolidated tool.

    ``legacy`` is the handler name that implements the action. Action-specific
    validation lives in the router, so the JSON schema can stay compact.
    """

    name: str
    legacy: str
    summary: str = ""
    required: Tuple[str, ...] = ()
    params: Tuple[str, ...] = ()
    confirm: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """A tool exposed through ``tools/list``.

    A spec is either *direct* (``legacy`` set, no actions) or *consolidated*
    (``actions`` set, ``legacy`` unset). Direct specs exist for high-frequency
    tools and for tools with a single operation.
    """

    name: str
    description: str
    input_schema: Mapping[str, Any]
    annotations: types.ToolAnnotations
    domain: str
    safety: Safety
    actions: Tuple[ActionSpec, ...] = ()
    legacy: Optional[str] = None
    required_scopes: frozenset[str] = frozenset()
    scope_mode: ScopeMode = ScopeMode.ALL
    requires_confirm: bool = False

    @property
    def is_direct(self) -> bool:
        return self.legacy is not None and not self.actions

    @property
    def action_names(self) -> Tuple[str, ...]:
        return tuple(action.name for action in self.actions)

    def action(self, name: str) -> ActionSpec:
        for action in self.actions:
            if action.name == name:
                return action
        raise KeyError(name)

    def to_mcp(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            inputSchema=dict(self.input_schema),
            annotations=self.annotations,
        )

    def schema_chars(self) -> int:
        return len(json.dumps(dict(self.input_schema), ensure_ascii=False))


@dataclass(frozen=True)
class CallPlan:
    """Resolved call: which handler to invoke and with which arguments."""

    tool: ToolSpec
    legacy_name: str
    arguments: Dict[str, Any]
    action: Optional[str] = None

    @property
    def audit_action(self) -> Optional[str]:
        return self.action


@dataclass(frozen=True)
class Surface:
    """The visible tools for one profile/scope combination."""

    tools: Tuple[ToolSpec, ...]
    profile: str = "legacy"

    def __len__(self) -> int:
        return len(self.tools)

    def __iter__(self):
        return iter(self.tools)

    @property
    def by_name(self) -> Dict[str, ToolSpec]:
        return {tool.name: tool for tool in self.tools}

    def get(self, name: str) -> Optional[ToolSpec]:
        return self.by_name.get(name)

    def mcp_tools(self) -> list[types.Tool]:
        return [tool.to_mcp() for tool in self.tools]

    def schema_chars(self) -> int:
        return sum(tool.schema_chars() for tool in self.tools)

    def estimated_tokens(self) -> int:
        """Rough token estimate used by budget tests (chars / 4)."""
        return (self.schema_chars() + sum(len(t.description) for t in self.tools)) // 4


def safety_from_annotations(annotations: types.ToolAnnotations) -> Safety:
    """Map MCP annotations to the safety class used by profiles."""
    if getattr(annotations, "readOnlyHint", False):
        return Safety.READ
    if getattr(annotations, "destructiveHint", False):
        return Safety.DESTRUCTIVE
    return Safety.WRITE


def annotations_for(safety: Safety) -> types.ToolAnnotations:
    if safety is Safety.READ:
        return types.ToolAnnotations(readOnlyHint=True, destructiveHint=False)
    if safety is Safety.DESTRUCTIVE:
        return types.ToolAnnotations(readOnlyHint=False, destructiveHint=True)
    return types.ToolAnnotations(readOnlyHint=False, destructiveHint=False)


def iter_names(tools: Iterable[ToolSpec]) -> Iterable[str]:
    for tool in tools:
        yield tool.name
