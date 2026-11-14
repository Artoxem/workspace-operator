"""Tests for the typed tool surface and action router."""

import unittest

from mcp import types

from workspace_operator.server import _tools
from workspace_operator.toolset.catalog import build_catalog
from workspace_operator.toolset import (
    ActionSpec,
    RoutingError,
    Safety,
    ScopeMode,
    ToolSpec,
    build_legacy_surface,
    build_surface,
    filter_by_scopes,
    resolve_call,
)
from workspace_operator.toolset.models import annotations_for


def spec(name: str, scopes=(), mode=ScopeMode.ALL) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=name,
        input_schema={"type": "object", "properties": {}},
        annotations=annotations_for(Safety.READ),
        domain="test",
        safety=Safety.READ,
        required_scopes=frozenset(scopes),
        scope_mode=mode,
    )


def action_tool() -> ToolSpec:
    return ToolSpec(
        name="drive_write",
        description="write actions",
        input_schema={"type": "object", "properties": {"action": {"type": "string"}}},
        annotations=annotations_for(Safety.WRITE),
        domain="drive",
        safety=Safety.WRITE,
        actions=(
            ActionSpec("upload", "drive_upload", required=("local_path",), params=("local_path",)),
            ActionSpec("move", "move_file", required=("file_id", "folder_id")),
        ),
    )


class LegacySurfaceTests(unittest.TestCase):
    def setUp(self):
        self.legacy = _tools()
        self.surface = build_legacy_surface(self.legacy)

    def test_every_retained_legacy_tool_is_preserved(self):
        self.assertEqual(len(self.surface.tools), 104)
        self.assertEqual(
            {tool.name for tool in self.surface.tools},
            {tool.name for tool in self.legacy},
        )

    def test_direct_call_passes_arguments(self):
        plan = resolve_call(self.surface.get("workspace_search"), {"query": "x"})
        self.assertEqual(plan.legacy_name, "workspace_search")
        self.assertEqual(plan.arguments, {"query": "x"})
        self.assertIsNone(plan.action)

    def test_consolidated_profile_counts(self):
        catalog = build_catalog(self.legacy)
        for name, expected in (
            ("core", 20),
            ("full", 39),
            ("read-write", 30),
            ("read-only", 17),
        ):
            with self.subTest(profile=name):
                self.assertEqual(len(build_surface(catalog, profile=name)), expected)


class RoutingTests(unittest.TestCase):
    def test_missing_action(self):
        with self.assertRaises(RoutingError) as ctx:
            resolve_call(action_tool(), {"file_id": "f"})
        self.assertEqual(ctx.exception.code, "missing_action")

    def test_unknown_action(self):
        with self.assertRaises(RoutingError) as ctx:
            resolve_call(action_tool(), {"action": "explode"})
        self.assertEqual(ctx.exception.code, "unknown_action")

    def test_required_argument(self):
        with self.assertRaises(RoutingError) as ctx:
            resolve_call(action_tool(), {"action": "upload"})
        self.assertEqual(ctx.exception.code, "missing_argument")

    def test_consolidated_call(self):
        plan = resolve_call(action_tool(), {"action": "upload", "local_path": "x"})
        self.assertEqual(plan.legacy_name, "drive_upload")
        self.assertEqual(plan.action, "upload")
        self.assertEqual(plan.arguments, {"local_path": "x"})

    def test_destructive_action_requires_confirm(self):
        tool = ToolSpec(
            name="drive_trash",
            description="trash",
            input_schema={"type": "object", "properties": {}},
            annotations=annotations_for(Safety.DESTRUCTIVE),
            domain="drive",
            safety=Safety.DESTRUCTIVE,
            actions=(ActionSpec("delete", "drive_delete_file", required=("file_id",)),),
        )
        with self.assertRaises(RoutingError) as ctx:
            resolve_call(tool, {"action": "delete", "file_id": "f"})
        self.assertEqual(ctx.exception.code, "confirmation_required")
        plan = resolve_call(
            tool, {"action": "delete", "file_id": "f", "confirm": True}
        )
        self.assertEqual(plan.legacy_name, "drive_delete_file")


class ScopeFilterTests(unittest.TestCase):
    def test_unknown_scopes_do_not_hide(self):
        tools = [spec("read", ("drive",))]
        self.assertEqual(len(filter_by_scopes(tools, None)), 1)
        self.assertEqual(len(filter_by_scopes(tools, [])), 1)

    def test_all_mode(self):
        tools = [spec("both", ("drive", "documents"))]
        self.assertEqual(len(filter_by_scopes(tools, ["drive"])), 0)
        self.assertEqual(len(filter_by_scopes(tools, ["drive", "documents"])), 1)

    def test_any_mode(self):
        tools = [spec("any", ("drive", "drive.readonly"), ScopeMode.ANY)]
        self.assertEqual(len(filter_by_scopes(tools, ["drive"])), 1)
        self.assertEqual(len(filter_by_scopes(tools, ["drive.readonly"])), 1)
        self.assertEqual(len(filter_by_scopes(tools, ["gmail.modify"])), 0)

    def test_scope_filter_runs_before_profile(self):
        tools = [spec("r", ("drive",))]
        self.assertEqual(len(build_surface(tools, "full", ["drive"])), 1)
        self.assertEqual(len(build_surface(tools, "full", ["gmail.modify"])), 0)


if __name__ == "__main__":
    unittest.main()
