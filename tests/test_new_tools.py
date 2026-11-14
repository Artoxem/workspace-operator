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
LOGGER = logging.getLogger("test")



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

    def test_excerpt_is_centred_on_the_match(self):
        text = "x" * 100 + "NEEDLE" + "y" * 100
        excerpt = _excerpt(text, "needle", match_case=False)
        self.assertIn("NEEDLE", excerpt)
        self.assertLess(len(excerpt), 200)

    def test_missing_match_returns_empty(self):
        self.assertEqual(_excerpt("hello", "absent", match_case=False), "")


if __name__ == "__main__":
    unittest.main()
