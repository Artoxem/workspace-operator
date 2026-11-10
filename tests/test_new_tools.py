"""Tests for the v1.14 batch: new tools, conditions, charts, previews."""

import logging
import unittest

from workspace_operator.handlers.doc_edit import _excerpt
from workspace_operator.handlers.sheets_extra import (
    CHART_TYPES,
    _condition,
    add_chart_handler,
)
from workspace_operator.profiles import resolve_profile
from workspace_operator.server import _tools

LOGGER = logging.getLogger("test")
BY_NAME = {tool.name: tool for tool in _tools()}

NEW_TOOLS = [
    "drive_get_metadata",
    "drive_rename_file",
    "drive_delete_file",
    "drive_restore_file",
    "drive_remove_permission",
    "drive_list_comments",
    "drive_create_comment",
    "drive_reply_comment",
    "drive_resolve_comment",
    "doc_replace_text",
    "sheet_conditional_format",
    "sheet_add_chart",
    "slides_delete_slide",
]


class CatalogTests(unittest.TestCase):
    def test_new_tools_are_registered(self):
        self.assertEqual(len(_tools()), 80)
        for name in NEW_TOOLS:
            with self.subTest(tool=name):
                self.assertIn(name, BY_NAME)

    def test_destructive_tools_are_marked(self):
        for name in (
            "drive_delete_file",
            "drive_remove_permission",
            "doc_replace_text",
            "slides_delete_slide",
        ):
            with self.subTest(tool=name):
                self.assertTrue(BY_NAME[name].annotations.destructiveHint)

    def test_read_tools_are_marked_read_only(self):
        for name in (
            "drive_get_metadata",
            "drive_list_comments",
        ):
            with self.subTest(tool=name):
                self.assertTrue(BY_NAME[name].annotations.readOnlyHint)

    def test_profiles_hide_destructive_batch(self):
        read_write = {
            tool.name for tool in resolve_profile("read-write").filter(_tools())
        }
        read_only = {
            tool.name for tool in resolve_profile("read-only").filter(_tools())
        }
        for name in ("drive_delete_file", "doc_replace_text", "slides_delete_slide"):
            self.assertNotIn(name, read_write)
            self.assertNotIn(name, read_only)
        self.assertIn("drive_get_metadata", read_only)
        self.assertEqual(len(read_write), 68)
        self.assertEqual(len(read_only), 23)


class ConditionTests(unittest.TestCase):
    def test_text_condition(self):
        rule = _condition("TEXT_CONTAINS", "urgent", None)
        self.assertEqual(rule["type"], "TEXT_CONTAINS")
        self.assertEqual(rule["values"][0]["userEnteredValue"], "urgent")

    def test_alias_is_resolved(self):
        self.assertEqual(_condition("contains", "x", None)["type"], "TEXT_CONTAINS")
        self.assertEqual(_condition("greater", 5, None)["type"], "NUMBER_GREATER")

    def test_number_between_needs_two_values(self):
        rule = _condition("NUMBER_BETWEEN", 10, 20)
        self.assertEqual(len(rule["values"]), 2)
        with self.assertRaises(ValueError):
            _condition("NUMBER_BETWEEN", 10, None)

    def test_empty_conditions_take_no_value(self):
        self.assertEqual(_condition("IS_EMPTY", None, None), {"type": "IS_EMPTY"})
        self.assertEqual(_condition("blank", None, None), {"type": "IS_EMPTY"})

    def test_unknown_condition_is_rejected(self):
        with self.assertRaises(ValueError):
            _condition("MAGIC", "x", None)

    def test_text_condition_requires_value(self):
        with self.assertRaises(ValueError):
            _condition("TEXT_CONTAINS", None, None)


class ChartTests(unittest.TestCase):
    def test_supported_types(self):
        self.assertIn("COLUMN", CHART_TYPES)
        self.assertIn("PIE", CHART_TYPES)

    def test_unknown_type_is_rejected_before_any_api_call(self):
        message = add_chart_handler(
            config=None,  # validation happens before the service is built
            logger=LOGGER,
            spreadsheet_id="sheet-id",
            range_name="A1:B5",
            chart_type="DONUT",
        )
        self.assertTrue(message.startswith("Error: chart_type"))

    def test_missing_range_is_rejected(self):
        message = add_chart_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", range_name="", chart_type="LINE"
        )
        self.assertTrue(message.startswith("Error:"))


class ExcerptTests(unittest.TestCase):
    def test_excerpt_is_centred_on_the_match(self):
        text = "x" * 100 + "NEEDLE" + "y" * 100
        excerpt = _excerpt(text, "needle", match_case=False)
        self.assertIn("NEEDLE", excerpt)
        self.assertLess(len(excerpt), 200)

    def test_missing_match_returns_empty(self):
        self.assertEqual(_excerpt("hello", "absent", match_case=False), "")


if __name__ == "__main__":
    unittest.main()
