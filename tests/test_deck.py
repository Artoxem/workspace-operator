"""Tests for the table → presentation helpers (no network)."""

import unittest

from workspace_operator.handlers.deck import (
    MAX_ROWS_PER_SLIDE,
    chunk_rows,
    format_row,
    slide_requests,
    title_slide_requests,
)

HEADER = ["Region", "Channel", "Spend"]


class ChunkTests(unittest.TestCase):
    def test_even_split(self):
        rows = [["a"], ["b"], ["c"], ["d"]]
        self.assertEqual(len(chunk_rows(rows, 2)), 2)

    def test_remainder_chunk(self):
        chunks = chunk_rows([["a"], ["b"], ["c"]], 2)
        self.assertEqual([len(chunk) for chunk in chunks], [2, 1])

    def test_size_is_clamped(self):
        rows = [["x"] for _ in range(30)]
        chunks = chunk_rows(rows, 999)
        self.assertLessEqual(len(chunks[0]), MAX_ROWS_PER_SLIDE)

    def test_zero_size_falls_back(self):
        chunks = chunk_rows([["a"], ["b"]], 0)
        self.assertEqual(len(chunks), 1)


class FormatTests(unittest.TestCase):
    def test_pairs_header_and_values(self):
        self.assertEqual(
            format_row(HEADER, ["EMEA", "Search", "100"]),
            "Region: EMEA · Channel: Search · Spend: 100",
        )

    def test_skips_empty_cells(self):
        self.assertEqual(
            format_row(HEADER, ["EMEA", "", "100"]),
            "Region: EMEA · Spend: 100",
        )

    def test_without_header(self):
        self.assertEqual(format_row([], ["a", "b"]), "a · b")

    def test_empty_row(self):
        self.assertEqual(format_row(HEADER, []), "(empty row)")

    def test_truncates_long_line(self):
        line = format_row(HEADER, ["x" * 500, "y", "z"])
        self.assertTrue(line.endswith("…"))
        self.assertLessEqual(len(line), 180)


class SlideRequestTests(unittest.TestCase):
    def test_structure(self):
        requests = slide_requests("slide_1", "Rows 1–3", ["a", "b"])
        kinds = [next(iter(request)) for request in requests]
        self.assertEqual(
            kinds,
            ["createSlide", "createShape", "insertText", "updateTextStyle",
             "createShape", "insertText", "updateTextStyle"],
        )

    def test_shapes_belong_to_the_slide(self):
        requests = slide_requests("slide_7", "Title", ["line"])
        shapes = [r["createShape"] for r in requests if "createShape" in r]
        self.assertTrue(all(shape["elementProperties"]["pageObjectId"] == "slide_7" for shape in shapes))

    def test_body_text_is_newline_joined(self):
        requests = slide_requests("s", "T", ["one", "two"])
        texts = [r["insertText"]["text"] for r in requests if "insertText" in r]
        self.assertIn("one\ntwo", texts)

    def test_title_is_bold(self):
        requests = slide_requests("s", "T", ["one"])
        styles = [r["updateTextStyle"] for r in requests if "updateTextStyle" in r]
        self.assertTrue(styles[0]["style"]["bold"])
        self.assertEqual(styles[0]["style"]["fontSize"]["unit"], "PT")


class TitleSlideTests(unittest.TestCase):
    def test_has_title_and_subtitle(self):
        requests = title_slide_requests("title_slide", "My deck", "12 rows")
        self.assertEqual(sum("insertText" in request for request in requests), 2)
        texts = [r["insertText"]["text"] for r in requests if "insertText" in r]
        self.assertIn("My deck", texts)
        self.assertIn("12 rows", texts)


if __name__ == "__main__":
    unittest.main()
