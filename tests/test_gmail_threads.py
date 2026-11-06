"""Tests for Gmail thread/reply helpers (no network)."""

import unittest

from workspace_operator.handlers.gmail_threads import (
    attachment_catalog,
    match_attachment,
    reply_recipients,
    reply_reference,
    reply_subject,
)

ATTACHMENTS = [
    {"filename": "invoice.pdf", "attachment_id": "a1"},
    {"filename": "Report-Final.XLSX", "attachment_id": "a2"},
]


class SubjectTests(unittest.TestCase):
    def test_adds_prefix(self):
        self.assertEqual(reply_subject("Quarterly report"), "Re: Quarterly report")

    def test_keeps_existing_prefix(self):
        self.assertEqual(reply_subject("RE: Hello"), "RE: Hello")

    def test_empty_subject(self):
        self.assertEqual(reply_subject(None), "Re:")


class RecipientTests(unittest.TestCase):
    HEADERS = {
        "From": "Alice <alice@example.com>",
        "To": '"Me" <me@example.com>, Bob <bob@example.com>',
        "Cc": "carol@example.com",
    }

    def test_reply_to_sender_only(self):
        self.assertEqual(
            reply_recipients(self.HEADERS, "me@example.com"), "alice@example.com"
        )

    def test_reply_all_includes_to_and_cc(self):
        recipients = reply_recipients(self.HEADERS, "me@example.com", reply_all=True)
        self.assertIn("alice@example.com", recipients)
        self.assertIn("bob@example.com", recipients)
        self.assertIn("carol@example.com", recipients)
        self.assertNotIn("me@example.com", recipients)

    def test_no_duplicates(self):
        headers = {
            "From": "alice@example.com",
            "To": "alice@example.com, bob@example.com",
        }
        self.assertEqual(
            reply_recipients(headers, "me@example.com", reply_all=True),
            "alice@example.com, bob@example.com",
        )

    def test_missing_from(self):
        self.assertEqual(reply_recipients({}, "me@example.com"), "")


class ReferenceTests(unittest.TestCase):
    def test_combines_existing_references_and_message_id(self):
        headers = {"References": "<a@x> <b@x>", "Message-ID": "<c@x>"}
        self.assertEqual(reply_reference(headers), "<a@x> <b@x> <c@x>")

    def test_message_id_only(self):
        self.assertEqual(reply_reference({"Message-ID": "<c@x>"}), "<c@x>")

    def test_empty(self):
        self.assertEqual(reply_reference({}), "")


class AttachmentMatchTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(match_attachment(ATTACHMENTS, "invoice.pdf")["attachment_id"], "a1")

    def test_case_insensitive(self):
        self.assertEqual(
            match_attachment(ATTACHMENTS, "report-final.xlsx")["attachment_id"], "a2"
        )

    def test_substring(self):
        self.assertEqual(match_attachment(ATTACHMENTS, "report")["attachment_id"], "a2")

    def test_single_attachment_is_implicit(self):
        self.assertEqual(match_attachment([ATTACHMENTS[0]], None)["attachment_id"], "a1")

    def test_ambiguous_without_name(self):
        self.assertIsNone(match_attachment(ATTACHMENTS, None))

    def test_missing(self):
        self.assertIsNone(match_attachment(ATTACHMENTS, "nope.txt"))
        self.assertIsNone(match_attachment([], "a.txt"))

    def test_catalog(self):
        self.assertEqual(
            attachment_catalog(ATTACHMENTS), "invoice.pdf, Report-Final.XLSX"
        )


if __name__ == "__main__":
    unittest.main()
