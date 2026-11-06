"""Tests for shared text hygiene helpers."""

import unittest

from mcp_google.handlers.docs import document_to_text
from mcp_google.text import (
    clean_text,
    format_timestamp,
    html_to_text,
    humanize_http_error,
    parse_email_date,
    shorten_links,
)


class CleanTextTests(unittest.TestCase):
    def test_unescapes_html_entities(self):
        self.assertEqual(clean_text("I&#39;ve &amp; you&#39;ll"), "I've & you'll")

    def test_drops_invisible_characters(self):
        dirty = "hello\u200b \u034fworld\ufeff"
        self.assertEqual(clean_text(dirty), "hello world")

    def test_collapses_spaces_and_blank_lines(self):
        self.assertEqual(clean_text("a   b\n\n\n\nc"), "a b\n\nc")

    def test_normalises_crlf_before_collapsing(self):
        self.assertEqual(clean_text("a\r\n\r\n\r\n\r\nb"), "a\n\nb")

    def test_limit_adds_ellipsis(self):
        self.assertEqual(clean_text("abcdef", limit=3), "abc…")

    def test_none_is_empty(self):
        self.assertEqual(clean_text(None), "")

    def test_single_line_flattens_newlines(self):
        self.assertEqual(clean_text("a\nb\n\nc", single_line=True), "a b c")

    def test_shorten_links_replaces_tracking_urls(self):
        long_url = "https://example.com/" + "x" * 200
        text = shorten_links(f"see {long_url} end")
        self.assertEqual(text, "see [long link] end")

    def test_shorten_links_keeps_normal_urls(self):
        text = "https://docs.google.com/spreadsheets/d/abc"
        self.assertEqual(shorten_links(text), text)


class HtmlToTextTests(unittest.TestCase):
    def test_strips_tags_and_breaks(self):
        markup = "<p>Hello <b>world</b></p><p>Second&#39;s line</p>"
        self.assertEqual(html_to_text(markup), "Hello world\nSecond's line")

    def test_drops_script_and_style(self):
        markup = "<style>.a{}</style><script>alert(1)</script><div>ok</div>"
        self.assertEqual(html_to_text(markup), "ok")


class HumanizeErrorTests(unittest.TestCase):
    def test_extracts_403_reason(self):
        raw = (
            '<HttpError 403 when requesting https://example.com/x returned '
            '"The user does not have sufficient permissions for this file.". '
            'Details: "[{\'reason\': \'insufficientFilePermissions\'}]">'
        )
        message = humanize_http_error(raw)
        self.assertIn("Google API 403", message)
        self.assertIn("does not have sufficient permissions", message)
        self.assertIn("check that the account can access this resource", message)
        self.assertNotIn("http", message)

    def test_unknown_status(self):
        raw = '<HttpError 418 when requesting https://x returned "teapot".'
        self.assertIn("Google API 418", humanize_http_error(raw))

    def test_keeps_handler_prefix(self):
        raw = (
            'Error reading sheet: <HttpError 404 when requesting https://x returned '
            '"Requested entity was not found.". Details: "Requested entity was not found.">'
        )
        message = humanize_http_error(raw)
        self.assertTrue(message.startswith("Error reading sheet:"))
        self.assertIn("Google API 404", message)

    def test_plain_text_passes_through(self):
        self.assertEqual(humanize_http_error("Error: boom"), "Error: boom")


class DateTests(unittest.TestCase):
    def test_normalizes_rfc_date(self):
        self.assertEqual(
            parse_email_date("Fri, 6 Nov 2026 17:09:11 +0000 (GMT)"),
            "2026-11-06 17:09",
        )

    def test_handles_garbage(self):
        self.assertEqual(parse_email_date("not a date"), "not a date")
        self.assertEqual(parse_email_date(""), "unknown date")

    def test_formats_drive_timestamp(self):
        self.assertEqual(format_timestamp("2026-09-16T08:28:52.006Z"), "2026-09-16 08:28")

    def test_formats_timestamp_with_offset(self):
        self.assertEqual(format_timestamp("2026-11-07T10:00:00+03:00"), "2026-11-07 07:00")

    def test_timestamp_fallbacks(self):
        self.assertEqual(format_timestamp(""), "unknown")
        self.assertEqual(format_timestamp("yesterday"), "yesterday")


class DocumentToTextTests(unittest.TestCase):
    def test_renders_paragraphs_and_tables(self):
        document = {
            "body": {
                "content": [
                    {"paragraph": {"elements": [{"textRun": {"content": "Title"}}]}},
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "A"}}]}}]},
                                        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "B"}}]}}]},
                                    ]
                                },
                                {
                                    "tableCells": [
                                        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "1"}}]}}]},
                                        {"content": [{"paragraph": {"elements": [{"textRun": {"content": "2"}}]}}]},
                                    ]
                                },
                            ]
                        }
                    },
                ]
            }
        }
        text = document_to_text(document)
        self.assertIn("Title", text)
        self.assertIn("| A | B |", text)
        self.assertIn("| 1 | 2 |", text)


if __name__ == "__main__":
    unittest.main()
