"""Tests for the v1.14 batch: new tools, conditions, charts, previews."""

import logging
import unittest

from workspace_operator.handlers.doc_edit import _excerpt
from workspace_operator.handlers.gmail_labels import modify_messages_handler
from workspace_operator.handlers.sheets_extra import (
    CHART_TYPES,
    _condition,
    add_chart_handler,
)
from workspace_operator.handlers.sheets_structure import (
    _dimension_request,
    merge_cells_handler,
)
from workspace_operator.profiles import is_destructive, is_read_only, resolve_profile
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
    "sheet_delete_sheet",
    "sheet_insert_rows",
    "sheet_delete_rows",
    "sheet_merge_cells",
    "slides_move_slide",
    "slides_set_notes",
    "gmail_list_labels",
    "gmail_create_label",
    "drive_empty_trash",
    "sheet_insert_columns",
    "sheet_delete_columns",
    "sheet_sort_range",
    "slides_add_table",
    "docs_insert_image",
    "calendar_list_calendars",
    "drive_transfer_ownership",
    "gmail_send_with_attachments",
    "script_list_deployments",
    "sheet_add_pivot_table",
    "docs_format_text",
    "gmail_list_drafts",
    "gmail_delete_draft",
    "calendar_move_event",
    "slides_list_layouts",
    "script_create_deployment",
    "drive_create_shortcut",
    "sheet_set_data_validation",
    "sheet_protect_range",
    "sheet_set_borders",
    "gmail_list_filters",
    "gmail_create_filter",
    "gmail_update_draft",
    "slides_add_shape",
    "calendar_set_event_color",
    "script_update_deployment",
]


class CatalogTests(unittest.TestCase):
    def test_new_tools_are_registered(self):
        self.assertEqual(len(_tools()), 121)
        for name in NEW_TOOLS:
            with self.subTest(tool=name):
                self.assertIn(name, BY_NAME)

    def test_destructive_tools_are_marked(self):
        for name in (
            "drive_delete_file",
            "drive_remove_permission",
            "doc_replace_text",
            "slides_delete_slide",
            "sheet_delete_sheet",
            "sheet_delete_rows",
            "drive_empty_trash",
            "sheet_delete_columns",
            "drive_transfer_ownership",
            "docs_format_text",
            "gmail_delete_draft",
        ):
            with self.subTest(tool=name):
                self.assertTrue(is_destructive(BY_NAME[name]))

    def test_read_tools_are_marked_read_only(self):
        for name in (
            "drive_get_metadata",
            "drive_list_comments",
            "gmail_list_labels",
            "calendar_list_calendars",
            "script_list_deployments",
            "gmail_list_drafts",
            "slides_list_layouts",
            "gmail_list_filters",
        ):
            with self.subTest(tool=name):
                self.assertTrue(is_read_only(BY_NAME[name]))

    def test_profiles_hide_destructive_batch(self):
        read_write = {
            tool.name for tool in resolve_profile("read-write").filter(_tools())
        }
        read_only = {
            tool.name for tool in resolve_profile("read-only").filter(_tools())
        }
        for name in (
            "drive_delete_file",
            "doc_replace_text",
            "slides_delete_slide",
            "sheet_delete_sheet",
            "drive_empty_trash",
            "sheet_delete_columns",
            "drive_transfer_ownership",
            "docs_format_text",
            "gmail_delete_draft",
        ):
            self.assertNotIn(name, read_write)
            self.assertNotIn(name, read_only)
        self.assertIn("drive_get_metadata", read_only)
        self.assertEqual(len(read_write), 102)
        self.assertEqual(len(read_only), 33)


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


class StructureTests(unittest.TestCase):
    def test_dimension_request_shape(self):
        insert = _dimension_request(7, "ROWS", 1, 3, insert=True)
        self.assertEqual(
            insert["insertDimension"]["range"],
            {"sheetId": 7, "dimension": "ROWS", "startIndex": 1, "endIndex": 3},
        )
        delete = _dimension_request(7, "ROWS", 1, 3, insert=False)
        self.assertIn("deleteDimension", delete)

    def test_unknown_merge_type_is_rejected_before_the_api(self):
        message = merge_cells_handler(
            config=None,
            logger=LOGGER,
            spreadsheet_id="id",
            range_name="A1:B2",
            merge_type="SPLAT",
        )
        self.assertTrue(message.startswith("Error: merge_type"))

    def test_modify_messages_dry_run_needs_no_api(self):
        message = modify_messages_handler(
            config=None,
            logger=LOGGER,
            message_ids=["m1", "m2"],
            add_labels=["STARRED"],
            dry_run=True,
        )
        self.assertIn("DRY RUN", message)
        self.assertIn("2 message(s)", message)

    def test_modify_messages_requires_a_change(self):
        message = modify_messages_handler(
            config=None, logger=LOGGER, message_ids=["m1"], dry_run=True
        )
        self.assertTrue(message.startswith("Error:"))


class BatchThreeTests(unittest.TestCase):
    def test_create_event_takes_recurrence(self):
        schema = BY_NAME["create_event"].input_schema
        self.assertIn("recurrence", schema["properties"])

    def test_insert_columns_validates_count(self):
        from workspace_operator.handlers.sheets_more import insert_columns_handler

        message = insert_columns_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", count=0
        )
        self.assertTrue(message.startswith("Error: count"))

    def test_sort_range_validates_column(self):
        from workspace_operator.handlers.sheets_more import sort_range_handler

        message = sort_range_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", range_name="A1:B5", column=0
        )
        self.assertTrue(message.startswith("Error: column"))

    def test_attachment_requires_an_existing_file(self):
        from workspace_operator.handlers.gmail import _create_message_with_attachments

        with self.assertRaises(FileNotFoundError):
            _create_message_with_attachments(
                "a@example.com", "s", "b", ["/definitely/missing.txt"]
            )

    def test_slides_table_validates_shape(self):
        from workspace_operator.handlers.slides import add_table_handler

        message = add_table_handler(
            config=None,
            logger=LOGGER,
            presentation_id="id",
            slide_id="slide",
            rows=0,
            columns=2,
        )
        self.assertTrue(message.startswith("Error: rows"))


class BatchFourTests(unittest.TestCase):
    def test_find_ranges_maps_offsets(self):
        from workspace_operator.handlers.doc_format import find_ranges

        document = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"startIndex": 1, "textRun": {"content": "Hello "}},
                                {"startIndex": 7, "textRun": {"content": "world hello"}},
                            ]
                        }
                    }
                ]
            }
        }
        ranges = find_ranges(document, "hello")
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0], (1, 6))
        self.assertEqual(ranges[1], (13, 18))

    def test_absolute_falls_back_to_end(self):
        from workspace_operator.handlers.doc_format import _absolute

        self.assertEqual(_absolute([(1, "abc")], 10), 4)

    def test_pivot_aggregation_is_validated(self):
        from workspace_operator.handlers.sheets_pivot import add_pivot_table_handler

        message = add_pivot_table_handler(
            config=None,
            logger=LOGGER,
            spreadsheet_id="id",
            source_range="A1:C10",
            rows=[1],
            values=[3],
            aggregation="MEDIAN",
        )
        self.assertTrue(message.startswith("Error: aggregation"))

    def test_pivot_requires_rows_and_values(self):
        from workspace_operator.handlers.sheets_pivot import add_pivot_table_handler

        message = add_pivot_table_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", source_range="A1:C10",
            rows=[], values=[2],
        )
        self.assertTrue(message.startswith("Error: rows"))


class BatchFiveTests(unittest.TestCase):
    def test_borders_style_is_validated(self):
        from workspace_operator.handlers.sheets_validate import set_borders_handler

        message = set_borders_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", range_name="A1:B2", style="WAVY"
        )
        self.assertTrue(message.startswith("Error: style"))

    def test_validation_needs_values_or_bounds(self):
        from workspace_operator.handlers.sheets_validate import set_data_validation_handler

        message = set_data_validation_handler(
            config=None, logger=LOGGER, spreadsheet_id="id", range_name="A1:A5"
        )
        self.assertTrue(message.startswith("Error: pass values"))

    def test_filter_requires_criteria(self):
        from workspace_operator.handlers.gmail_filters import create_filter_handler

        message = create_filter_handler(
            config=None, logger=LOGGER, add_labels=["Label_1"]
        )
        self.assertTrue(message.startswith("Error: pass at least one"))

    def test_event_color_range(self):
        from workspace_operator.handlers.calendar import set_event_color_handler

        message = set_event_color_handler(
            config=None, logger=LOGGER, event_id="id", color_id="42"
        )
        self.assertTrue(message.startswith("Error: color_id"))

    def test_shape_type_is_validated(self):
        from workspace_operator.handlers.slides import add_shape_handler

        message = add_shape_handler(
            config=None,
            logger=LOGGER,
            presentation_id="id",
            slide_id="slide",
            shape_type="STAR",
        )
        self.assertTrue(message.startswith("Error: shape_type"))


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
