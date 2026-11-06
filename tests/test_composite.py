"""Tests for composite helpers: digest, template clone, table diff (no network)."""

import unittest

from workspace_operator.handlers.compare import diff_tables, render_diff
from workspace_operator.handlers.digest import parse_sources, render_digest
from workspace_operator.handlers.template import (
    count_occurrences,
    replacement_requests,
)


class DigestSourceTests(unittest.TestCase):
    def test_default_is_all(self):
        self.assertEqual(parse_sources(None), ["gmail", "calendar", "drive"])

    def test_subset_order_preserved(self):
        self.assertEqual(parse_sources("drive, gmail"), ["drive", "gmail"])

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            parse_sources("gmail,telegram")

    def test_empty_falls_back_to_all(self):
        self.assertEqual(parse_sources("  "), ["gmail", "calendar", "drive"])


class DigestRenderTests(unittest.TestCase):
    def test_sections_and_total(self):
        text = render_digest(
            "Digest",
            24,
            {
                "gmail": [{"title": "Hello", "meta": "2026-11-06 · a@b.c"}],
                "calendar": [],
                "drive": [{"title": "Budget", "meta": "2026-11-06 · sheet"}],
            },
            10,
        )
        self.assertIn("## Email (1)", text)
        self.assertIn("- Hello", text)
        self.assertIn("## Agenda (0)", text)
        self.assertIn("- nothing", text)
        self.assertIn("## Changed files (1)", text)
        self.assertIn("Total items: 2", text)

    def test_limit_is_applied(self):
        items = [{"title": f"mail {index}"} for index in range(5)]
        text = render_digest("D", 1, {"gmail": items}, 2)
        self.assertIn("mail 0", text)
        self.assertNotIn("mail 3", text)

    def test_window_is_visible(self):
        self.assertIn("last 6h", render_digest("D", 6, {}, 10))


class TemplateRequestTests(unittest.TestCase):
    def test_document_requests(self):
        requests = replacement_requests("document", {"{{A}}": "1"})
        self.assertEqual(requests[0]["replaceAllText"]["containsText"]["text"], "{{A}}")
        self.assertEqual(requests[0]["replaceAllText"]["replaceText"], "1")

    def test_presentation_uses_same_shape(self):
        requests = replacement_requests("presentation", {"{{B}}": "2"})
        self.assertIn("replaceAllText", requests[0])

    def test_spreadsheet_uses_find_replace(self):
        requests = replacement_requests("spreadsheet", {"{{C}}": "3"})
        find = requests[0]["findReplace"]
        self.assertEqual(find["find"], "{{C}}")
        self.assertTrue(find["allSheets"])

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            replacement_requests("pdf", {"a": "b"})

    def test_count_occurrences(self):
        replies = [
            {"replaceAllText": {"occurrencesChanged": 2}},
            {"findReplace": {"occurrencesChanged": 3}},
            {},
        ]
        self.assertEqual(count_occurrences(replies), 5)


A = [
    ["SKU", "Name", "Price"],
    ["1", "Chair", "100"],
    ["2", "Table", "300"],
    ["3", "Shelf", "150"],
]
B = [
    ["SKU", "Name", "Price"],
    ["1", "Chair", "120"],
    ["3", "Shelf", "150"],
    ["4", "Lamp", "80"],
]


class DiffTests(unittest.TestCase):
    def test_counts(self):
        diff = diff_tables(A, B, key_column="SKU")
        self.assertEqual(diff["added"], ["4"])
        self.assertEqual(diff["removed"], ["2"])
        self.assertEqual(len(diff["changed"]), 1)
        self.assertEqual(diff["unchanged"], 1)

    def test_changed_details(self):
        diff = diff_tables(A, B, key_column="SKU")
        change = diff["changed"][0]
        self.assertEqual(change["key"], "1")
        self.assertEqual(change["changes"][0]["column"], "Price")
        self.assertEqual(change["changes"][0]["before"], "100")
        self.assertEqual(change["changes"][0]["after"], "120")

    def test_key_by_index(self):
        diff = diff_tables(A, B, key_column="1")
        self.assertEqual(diff["key"], "SKU")

    def test_without_header(self):
        diff = diff_tables(A[1:], B[1:], key_column="1", header=False)
        self.assertEqual(diff["added"], ["4"])
        self.assertEqual(diff["removed"], ["2"])

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            diff_tables(A, B, key_column="ID")

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            diff_tables([], B)

    def test_render(self):
        text = render_diff(diff_tables(A, B, key_column="SKU"))
        for marker in ("Compare by 'SKU'", "Added (1)", "Removed (1)", "Changed (1)"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
