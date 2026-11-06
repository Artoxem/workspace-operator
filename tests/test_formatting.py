"""Tests for the sheet_format request builders (no network)."""

import unittest

from workspace_operator.handlers.formatting import (
    build_cell_format,
    build_requests,
    column_to_index,
    hex_to_color,
    parse_a1_range,
)


class RangeParsingTests(unittest.TestCase):
    def test_cell_range(self):
        self.assertEqual(
            parse_a1_range("A1:C10"),
            {"startRow": 0, "endRow": 10, "startCol": 0, "endCol": 3},
        )

    def test_single_cell(self):
        self.assertEqual(
            parse_a1_range("B2"),
            {"startRow": 1, "endRow": 2, "startCol": 1, "endCol": 2},
        )

    def test_sheet_prefix_and_dollars(self):
        self.assertEqual(
            parse_a1_range("Report!$B$2:$D$5"),
            {"startRow": 1, "endRow": 5, "startCol": 1, "endCol": 4},
        )

    def test_whole_columns(self):
        self.assertEqual(
            parse_a1_range("A:C"),
            {"startRow": None, "endRow": None, "startCol": 0, "endCol": 3},
        )

    def test_whole_rows(self):
        self.assertEqual(
            parse_a1_range("2:5"),
            {"startRow": 1, "endRow": 5, "startCol": None, "endCol": None},
        )

    def test_mixed_range_rejected(self):
        with self.assertRaises(ValueError):
            parse_a1_range("A1:B")

    def test_bad_range_rejected(self):
        with self.assertRaises(ValueError):
            parse_a1_range("A1:B2:C3")


class ColumnTests(unittest.TestCase):
    def test_single_letters(self):
        self.assertEqual((column_to_index("A"), column_to_index("Z")), (0, 25))

    def test_double_letters(self):
        self.assertEqual(column_to_index("AA"), 26)
        self.assertEqual(column_to_index("AB"), 27)


class ColourTests(unittest.TestCase):
    def test_short_hex(self):
        self.assertEqual(hex_to_color("#fff"), {"red": 1.0, "green": 1.0, "blue": 1.0})

    def test_full_hex(self):
        self.assertEqual(
            hex_to_color("#FF0000"), {"red": 1.0, "green": 0.0, "blue": 0.0}
        )

    def test_invalid_colour(self):
        with self.assertRaises(ValueError):
            hex_to_color("red")


class CellFormatTests(unittest.TestCase):
    def test_text_and_number_format(self):
        cell_format = build_cell_format(bold=True, italic=True, font_size=12, number_format="#,##0.00")
        self.assertEqual(cell_format["textFormat"]["bold"], True)
        self.assertEqual(cell_format["textFormat"]["italic"], True)
        self.assertEqual(cell_format["textFormat"]["fontSize"], 12.0)
        self.assertEqual(cell_format["numberFormat"]["pattern"], "#,##0.00")

    def test_colours_and_alignment(self):
        cell_format = build_cell_format(
            background_color="#FFF2CC", text_color="#000", horizontal_alignment="center", wrap="wrap"
        )
        self.assertEqual(cell_format["backgroundColorStyle"]["rgbColor"]["red"], 1.0)
        self.assertEqual(cell_format["horizontalAlignment"], "CENTER")
        self.assertEqual(cell_format["wrapStrategy"], "WRAP")

    def test_empty(self):
        self.assertEqual(build_cell_format(), {})

    def test_invalid_alignment(self):
        with self.assertRaises(ValueError):
            build_cell_format(horizontal_alignment="middle")


class RequestBuildingTests(unittest.TestCase):
    def test_repeat_cell_uses_grid_range(self):
        requests = build_requests(7, parse_a1_range("A1:B2"), cell_format={"textFormat": {"bold": True}})
        self.assertEqual(len(requests), 1)
        repeat = requests[0]["repeatCell"]
        self.assertEqual(
            repeat["range"],
            {"sheetId": 7, "startRowIndex": 0, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 2},
        )
        self.assertEqual(repeat["fields"], "userEnteredFormat")

    def test_column_width_requires_columns(self):
        with self.assertRaises(ValueError):
            build_requests(1, parse_a1_range("1:5"), column_width=100)

    def test_column_width_request(self):
        requests = build_requests(1, parse_a1_range("A:C"), column_width=120)
        dimension = requests[0]["updateDimensionProperties"]
        self.assertEqual(dimension["range"]["dimension"], "COLUMNS")
        self.assertEqual(dimension["range"]["startIndex"], 0)
        self.assertEqual(dimension["range"]["endIndex"], 3)
        self.assertEqual(dimension["properties"]["pixelSize"], 120)

    def test_freeze_request(self):
        requests = build_requests(2, {}, freeze_rows=1, freeze_cols=2)
        update = requests[0]["updateSheetProperties"]
        self.assertEqual(update["properties"]["gridProperties"], {"frozenRowCount": 1, "frozenColumnCount": 2})
        self.assertIn("frozenRowCount", update["fields"])


if __name__ == "__main__":
    unittest.main()
