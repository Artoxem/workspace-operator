"""The legacy "Error ..." convention and the explicit result/error types."""

import unittest

from workspace_operator.results import ToolError, ToolResult, is_error_text


class ErrorTextTests(unittest.TestCase):
    def test_legacy_error_shapes_are_detected(self):
        for text in (
            "Error",
            "Error: quota",
            "Error reading file: nope",
            "Error uploading file: nope",
            "  Error: leading whitespace",
            "\nError: newline first",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_error_text(text))

    def test_words_that_only_start_with_error_are_success(self):
        for text in (
            "Errors found: 0",
            "Errorless run",
            "ERROR: uppercase is not the convention",
            "error: lowercase is not the convention",
            "Result: Error count 0",
            "✅ Done",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_error_text(text))

    def test_tool_result_defaults(self):
        ok = ToolResult("fine")
        self.assertEqual((ok.text, ok.is_error), ("fine", False))
        bad = ToolResult("nope", is_error=True)
        self.assertTrue(bad.is_error)

    def test_tool_error_carries_its_message(self):
        error = ToolError("Quota exceeded")
        self.assertEqual(str(error), "Quota exceeded")
        self.assertIsInstance(error, Exception)


if __name__ == "__main__":
    unittest.main()
