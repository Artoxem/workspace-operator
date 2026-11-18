"""Tool and prompt definitions, stored as data.

The JSON files next to this module describe every legacy tool (name,
description, JSON input schema, safety) grouped by domain, plus the scenario
prompts. ``order.json`` fixes the order clients see in ``tools/list``.

``safety`` is one of ``read``, ``write``, ``destructive`` and expands to the
matching MCP annotation preset; a tool with unusual hints carries an explicit
``annotations`` object instead. ``tests/test_definitions.py`` pins the loaded
result against a snapshot of the pre-extraction definitions.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List

from mcp import types

_PRESETS = {
    "read": types.ToolAnnotations(read_only_hint=True, destructive_hint=False),
    "write": types.ToolAnnotations(read_only_hint=False, destructive_hint=False),
    "destructive": types.ToolAnnotations(read_only_hint=False, destructive_hint=True),
}

_DOMAIN_FILES = (
    "discovery",
    "drive",
    "docs",
    "sheets",
    "gmail",
    "calendar",
    "tasks",
    "forms",
    "postmaster",
    "script",
    "bulk",
)


def _read(name: str) -> Any:
    text = resources.files(__package__).joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def _annotations(entry: Dict[str, Any]) -> types.ToolAnnotations:
    if "safety" in entry:
        return _PRESETS[entry["safety"]].model_copy()
    return types.ToolAnnotations(**entry["annotations"])


def _tool(entry: Dict[str, Any]) -> types.Tool:
    extra = {
        key: entry[key]
        for key in ("title", "icons", "meta", "execution", "output_schema")
        if key in entry
    }
    return types.Tool(
        name=entry["name"],
        description=entry["description"],
        input_schema=entry["input_schema"],
        annotations=_annotations(entry),
        **extra,
    )


@lru_cache(maxsize=1)
def _raw_tools() -> Dict[str, Dict[str, Any]]:
    entries: Dict[str, Dict[str, Any]] = {}
    for domain in _DOMAIN_FILES:
        for entry in _read(f"{domain}.json"):
            if entry["name"] in entries:
                raise ValueError(f"duplicate tool definition: {entry['name']}")
            entries[entry["name"]] = entry
    order: List[str] = _read("order.json")
    if sorted(order) != sorted(entries):
        missing = sorted(set(entries) ^ set(order))
        raise ValueError(f"order.json and the domain files disagree: {missing}")
    return {name: entries[name] for name in order}


def load_tools() -> List[types.Tool]:
    """Return fresh ``Tool`` objects in client-visible order."""
    return [_tool(entry) for entry in _raw_tools().values()]


def load_prompts() -> List[types.Prompt]:
    """Return fresh ``Prompt`` objects."""
    return [types.Prompt.model_validate(entry) for entry in _read("prompts.json")]
