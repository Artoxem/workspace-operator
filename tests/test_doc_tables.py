"""Tests for native Docs table helpers (no network)."""

import unittest

from workspace_operator.handlers.doc_tables import (
    MAX_COLUMNS,
    cell_layout,
    fill_requests,
    header_style_requests,
    normalise_rows,
    table_dimensions,
)


def fake_table(rows, columns, start=10, step=5):
    table_rows = []
    index = start
    for _ in range(rows):
        cells = []
        for _ in range(columns):
            cells.append({"content": [{"startIndex": index, "endIndex": index + step - 1}]})
            index += step
        table_rows.append({"tableCells": cells})
    return {"tableRows": table_rows}


class NormaliseTests(unittest.TestCase):
    def test_pads_rows(self):
        rows = normalise_rows([["a"], ["b", "c", "d"]])
        self.assertEqual(rows, [["a", "", ""], ["b", "c", "d"]])

    def test_limits_columns(self):
        rows = normalise_rows([list("abcdef")], columns=3)
        self.assertEqual(rows, [["a", "b", "c"]])

    def test_never_wider_than_max(self):
        rows = normalise_rows([["x"] * 50])
        self.assertEqual(len(rows[0]), MAX_COLUMNS)

    def test_cleans_text(self):
        rows = normalise_rows([["  a&nbsp;b "]])
        self.assertEqual(rows[0][0], "a b")


class DimensionTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(table_dimensions([["a", "b"], ["c", "d"]]), (2, 2))

    def test_empty_rows_still_valid(self):
        self.assertEqual(table_dimensions([]), (1, 1))


class LayoutTests(unittest.TestCase):
    def test_layout_covers_every_cell(self):
        layout = cell_layout(fake_table(2, 3))
        self.assertEqual(len(layout), 6)
        self.assertEqual(layout[0], {"row": 0, "column": 0, "start": 10, "end": 14})
        self.assertEqual(layout[-1]["row"], 1)
        self.assertEqual(layout[-1]["column"], 2)


class FillTests(unittest.TestCase):
    ROWS = [["Name", "Price"], ["Chair", "100"], ["Table", ""]]

    def test_requests_are_descending(self):
        requests = fill_requests(cell_layout(fake_table(3, 2)), self.ROWS)
        indexes = [request["insertText"]["location"]["index"] for request in requests]
        self.assertEqual(indexes, sorted(indexes, reverse=True))

    def test_empty_cells_are_skipped(self):
        requests = fill_requests(cell_layout(fake_table(3, 2)), self.ROWS)
        texts = [request["insertText"]["text"] for request in requests]
        self.assertNotIn("", texts)
        self.assertEqual(len(requests), 5)

    def test_values_are_cleaned(self):
        requests = fill_requests(cell_layout(fake_table(1, 1)), [["  x  "]])
        self.assertEqual(requests[0]["insertText"]["text"], "x")


class HeaderStyleTests(unittest.TestCase):
    def test_only_first_row_is_bold(self):
        layout = cell_layout(fake_table(2, 2))
        requests = header_style_requests(layout, [["A", "B"], ["1", "2"]])
        self.assertEqual(len(requests), 2)
        ranges = [request["updateTextStyle"]["range"] for request in requests]
        self.assertEqual(ranges[0], {"startIndex": 10, "endIndex": 11})
        self.assertTrue(all(request["updateTextStyle"]["textStyle"]["bold"] for request in requests))

    def test_empty_header_cells_skipped(self):
        layout = cell_layout(fake_table(1, 2))
        requests = header_style_requests(layout, [["", "B"]])
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
