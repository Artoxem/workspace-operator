"""Tests for the report_from_sheet analysis and rendering (no network)."""

import unittest

from workspace_operator.handlers.report import (
    render_report,
    render_table,
    summarise_columns,
    to_number,
)

ROWS = [
    ["Model", "Price", "Qty"],
    ["Grande", "4 882,50", "2"],
    ["Lusso", "7 602,63", "1"],
    ["Sono", "n/a", "5"],
]


class NumberTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(to_number("42"), 42.0)

    def test_decimal_comma(self):
        self.assertEqual(to_number("4882,50"), 4882.5)

    def test_spaces_and_currency(self):
        self.assertEqual(to_number(" 1 234,50 € "), 1234.5)

    def test_percent(self):
        self.assertEqual(to_number("12,5%"), 12.5)

    def test_thousands_separator(self):
        self.assertEqual(to_number("1,234.50"), 1234.5)

    def test_not_a_number(self):
        self.assertIsNone(to_number("n/a"))
        self.assertIsNone(to_number(""))


class SummaryTests(unittest.TestCase):
    def test_header_and_counts(self):
        summary = summarise_columns(ROWS)
        self.assertEqual(summary["header"], ["Model", "Price", "Qty"])
        self.assertEqual(summary["rows"], 3)

    def test_numeric_column_stats(self):
        price = summarise_columns(ROWS)["columns"][1]
        self.assertEqual(price["kind"], "number")
        self.assertAlmostEqual(price["sum"], 4882.5 + 7602.63, places=2)
        self.assertEqual(price["min"], 4882.5)
        self.assertEqual(price["max"], 7602.63)

    def test_text_column(self):
        model = summarise_columns(ROWS)["columns"][0]
        self.assertEqual(model["kind"], "text")
        self.assertEqual(model["unique"], 3)
        self.assertNotIn("sum", model)

    def test_empty_table(self):
        self.assertEqual(
            summarise_columns([]),
            {
                "header": [],
                "rows": 0,
                "columns": [],
                "aggregates": ["sum", "avg", "min", "max"],
            },
        )

    def test_ragged_rows_are_padded(self):
        summary = summarise_columns([["A", "B"], ["1"], ["2", "3", "extra"]])
        self.assertEqual(len(summary["columns"]), 3)


class TableTests(unittest.TestCase):
    def test_renders_header_and_separator(self):
        table = render_table(ROWS)
        self.assertIn("Model", table)
        self.assertIn("-+-", table)
        self.assertEqual(len(table.splitlines()), len(ROWS) + 1)

    def test_limit(self):
        table = render_table(ROWS, limit=2)
        self.assertEqual(len(table.splitlines()), 3)

    def test_truncates_long_cells(self):
        table = render_table([["x" * 80]])
        self.assertIn("…", table)

    def test_empty(self):
        self.assertEqual(render_table([]), "(no data)")


class ReportTests(unittest.TestCase):
    def test_contains_sections(self):
        report = render_report("Title", "sheet-1", "A1:C4", ROWS)
        for marker in ("Title", "Source: sheet-1", "Range: A1:C4", "Summary", "Data", "| Column |"):
            self.assertIn(marker, report)

    def test_truncation_note(self):
        rows = [["A"]] + [[str(index)] for index in range(30)]
        report = render_report("T", "s", "A1:A31", rows, max_rows=5)
        self.assertIn("more row(s) not shown", report)


class UniversalityTests(unittest.TestCase):
    def test_header_false_treats_first_row_as_data(self):
        summary = summarise_columns([["1", "2"], ["3", "4"]], header=False)
        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["header"], ["column 1", "column 2"])

    def test_decimal_comma_mode(self):
        summary = summarise_columns([["v"], ["1.234,50"]], decimal="comma")
        self.assertAlmostEqual(summary["columns"][0]["sum"], 1234.5)

    def test_decimal_dot_mode(self):
        summary = summarise_columns([["v"], ["1,234.50"]], decimal="dot")
        self.assertAlmostEqual(summary["columns"][0]["sum"], 1234.5)

    def test_column_selection_by_name_and_index(self):
        summary = summarise_columns(ROWS, columns=["Qty"])
        self.assertEqual(summary["header"], ["Qty"])
        summary = summarise_columns(ROWS, columns=["2"])
        self.assertEqual(summary["header"], ["Price"])

    def test_unknown_column_raises(self):
        with self.assertRaises(ValueError):
            summarise_columns(ROWS, columns=["Nope"])

    def test_aggregate_subset(self):
        summary = summarise_columns(ROWS, aggregates=["median"])
        self.assertIn("median", summary["columns"][1])
        self.assertNotIn("sum", summary["columns"][1])

    def test_median(self):
        summary = summarise_columns([["v"], ["1"], ["2"], ["9"]], aggregates=["median"])
        self.assertAlmostEqual(summary["columns"][0]["median"], 2.0)


if __name__ == "__main__":
    unittest.main()
