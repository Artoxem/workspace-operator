"""Tests for workspace_search helpers (no network, no credentials)."""

import unittest
from datetime import datetime, timezone

from mcp_google.handlers.search import (
    MAX_LIMIT,
    _clamp_limit,
    _escape_drive_term,
    _format_date,
    _parse_sources,
    _render,
)


class SourceParsingTests(unittest.TestCase):
    def test_default_sources(self):
        self.assertEqual(_parse_sources(None), ["drive", "gmail"])

    def test_comma_separated_string(self):
        self.assertEqual(_parse_sources("drive, calendar"), ["drive", "calendar"])

    def test_duplicates_collapsed_and_order_preserved(self):
        self.assertEqual(_parse_sources(["gmail", "GMAIL", "drive"]), ["gmail", "drive"])

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            _parse_sources("drive,notion")

    def test_empty_string_falls_back_to_default(self):
        self.assertEqual(_parse_sources("  "), ["drive", "gmail"])


class LimitTests(unittest.TestCase):
    def test_clamps_high_and_low(self):
        self.assertEqual(_clamp_limit(1000), MAX_LIMIT)
        self.assertEqual(_clamp_limit(0), 1)
        self.assertEqual(_clamp_limit(-5), 1)

    def test_invalid_value_falls_back_to_ten(self):
        self.assertEqual(_clamp_limit("nonsense"), 10)
        self.assertEqual(_clamp_limit(None), 10)


class FormattingTests(unittest.TestCase):
    def test_drive_term_escapes_quotes(self):
        self.assertEqual(_escape_drive_term("O'Brien"), "O\\'Brien")

    def test_format_date_utc(self):
        value = datetime(2026, 3, 2, 10, 11, tzinfo=timezone.utc)
        self.assertEqual(_format_date(value), "2026-03-02 10:11 UTC")

    def test_format_date_missing(self):
        self.assertEqual(_format_date(None), "unknown date")

    def test_render_empty(self):
        self.assertEqual(_render("budget", [], []), "No results for 'budget'.")

    def test_render_lists_counts_items_and_errors(self):
        items = [
            {
                "source": "drive",
                "title": "Budget 2026",
                "id": "file-1",
                "date": datetime(2026, 3, 2, 10, 11, tzinfo=timezone.utc),
                "detail": "type: spreadsheet",
                "link": "https://docs.google.com/spreadsheets/d/file-1",
            },
            {
                "source": "gmail",
                "title": "Q3 budget approval",
                "id": "msg-1",
                "date": datetime(2026, 2, 27, 9, 14, tzinfo=timezone.utc),
                "detail": "from: cfo@corp.io",
                "link": "",
                "snippet": "Please approve the Q3 budget",
            },
        ]
        rendered = _render("budget", items, ["calendar: boom"])
        self.assertIn("2 result(s)", rendered)
        self.assertIn("drive (1), gmail (1)", rendered)
        self.assertIn("[drive] Budget 2026", rendered)
        self.assertIn("Please approve the Q3 budget", rendered)
        self.assertIn("Partial results", rendered)
        self.assertIn("calendar: boom", rendered)


if __name__ == "__main__":
    unittest.main()
