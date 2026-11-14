"""Integrity and budget tests for the consolidated 2.0 catalog."""

import unittest

from workspace_operator.profiles import resolve_profile
from workspace_operator.server import _tools
from workspace_operator.toolset.catalog import (
    CORE_TOOL_NAMES,
    REMOVED_ALIAS_NAMES,
    build_aliases,
    build_catalog,
)
from workspace_operator.toolset.surface import build_surface

REMOVED_STANDALONE = {
    "slides_create", "slides_get", "slides_add_slide", "slides_delete_slide",
    "slides_move_slide", "slides_list_layouts", "slides_replace_text",
    "slides_add_shape", "slides_add_table", "slides_insert_image",
    "slides_set_notes",
    "drive_create_comment", "drive_list_comments", "drive_reply_comment",
    "drive_resolve_comment",
    "clone_and_fill", "report_from_sheet", "sheet_to_slides",
    "drive_create_shortcut", "drive_download", "drive_empty_trash",
    "drive_transfer_ownership", "doc_fill_template", "calendar_find_free_slots",
    "create_event", "create_draft", "send_draft", "gmail_update_draft",
    "gmail_delete_draft", "gmail_list_drafts", "batch_delete_emails",
    "find_files", "doc_export_pdf",
}


# Draft tools are removed as standalone names but their handlers are reused
# by the gmail_write / gmail_delete actions.
UNCOVERED = REMOVED_STANDALONE - {
    "create_draft", "send_draft", "gmail_update_draft",
    "gmail_delete_draft", "gmail_list_drafts",
}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = _tools()
        cls.catalog = build_catalog(cls.legacy)
        cls.by_name = {tool.name: tool for tool in cls.catalog}

    def test_catalog_shape(self):
        self.assertEqual(len(self.catalog), 39)
        self.assertTrue(CORE_TOOL_NAMES <= set(self.by_name))

    def test_removed_tools_are_absent(self):
        self.assertEqual(set(self.by_name) & REMOVED_STANDALONE, set())

    def test_every_action_references_a_legacy_handler(self):
        legacy_names = {tool.name for tool in self.legacy}
        for tool in self.catalog:
            if tool.legacy:
                self.assertIn(tool.legacy, legacy_names)
            for action in tool.actions:
                self.assertIn(action.legacy, legacy_names)

    def test_no_duplicate_actions(self):
        for tool in self.catalog:
            self.assertEqual(len(tool.action_names), len(set(tool.action_names)))

    def test_required_fields_exist_in_source_schema(self):
        by_legacy = {tool.name: tool for tool in self.legacy}
        for tool in self.catalog:
            for action in tool.actions:
                source = by_legacy[action.legacy].input_schema or {}
                properties = source.get("properties") or {}
                for name in action.required:
                    self.assertIn(name, properties, f"{action.legacy}: {name}")

    def test_retained_legacy_names_have_an_alias(self):
        aliases = build_aliases(self.catalog)
        consolidated = set(self.by_name)
        for tool in self.legacy:
            if tool.name in consolidated:
                continue
            self.assertIn(tool.name, aliases, tool.name)
            target, _ = aliases[tool.name]
            self.assertIn(target, self.by_name)

    def test_removed_names_are_explicit(self):
        self.assertTrue(REMOVED_ALIAS_NAMES)
        self.assertNotIn("drive_delete_file", REMOVED_ALIAS_NAMES)


    def test_context_budgets(self):
        core = build_surface(self.catalog, "core")
        full = build_surface(self.catalog, "full")
        readonly = build_surface(self.catalog, "read-only")
        self.assertLessEqual(len(core), 20)
        self.assertLessEqual(core.estimated_tokens(), 4000)
        self.assertLessEqual(len(full), 39)
        self.assertLessEqual(full.estimated_tokens(), 9000)
        self.assertLessEqual(len(readonly), 17)
        self.assertLessEqual(readonly.estimated_tokens(), 3200)

    def test_destructive_tools_are_annotated(self):
        for name in (
            "drive_trash",
            "drive_permissions",
            "docs_edit",
            "sheets_delete",
            "gmail_delete",
            "calendar_delete",
            "script_run",
            "bulk_run",
            "bulk_undo",
        ):
            self.assertTrue(
                getattr(self.by_name[name].annotations, "destructive_hint", False),
                name,
            )

    def test_no_permanent_drive_trash_tool(self):
        self.assertNotIn("drive_empty_trash", self.by_name)
        self.assertNotIn("drive_transfer_ownership", self.by_name)


class LegacyCoverageTests(unittest.TestCase):
    def test_only_intended_legacy_tools_are_uncovered(self):
        legacy = _tools()
        catalog = build_catalog(legacy)
        used = set()
        for tool in catalog:
            if tool.legacy:
                used.add(tool.legacy)
            for action in tool.actions:
                used.add(action.legacy)
        uncovered = {tool.name for tool in legacy} - used
        self.assertEqual(uncovered, set())


if __name__ == "__main__":
    unittest.main()
