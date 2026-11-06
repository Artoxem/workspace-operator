"""Tests for Apps Script execution response formatting (no network)."""

import unittest

from workspace_operator.handlers.apps_script import format_script_response


class SuccessTests(unittest.TestCase):
    def test_renders_json_result(self):
        text = format_script_response("doWork", {"result": {"ok": True, "rows": 3}})
        self.assertIn("Executed doWork", text)
        self.assertIn('"ok": true', text)
        self.assertIn('"rows": 3', text)

    def test_no_return_value(self):
        text = format_script_response("doWork", {})
        self.assertIn("(no return value)", text)

    def test_truncates_large_results(self):
        text = format_script_response("doWork", {"result": "x" * 6000})
        self.assertIn("(truncated)", text)
        self.assertLess(len(text), 4200)


class ErrorTests(unittest.TestCase):
    def test_renders_message_and_stack(self):
        response = {
            "error": {
                "message": "ReferenceError: foo is not defined",
                "details": [
                    {
                        "scriptStackTraceElements": [
                            {"function": "doWork", "lineNumber": 12},
                            {"function": "main", "lineNumber": 3},
                        ]
                    }
                ],
            }
        }
        text = format_script_response("doWork", response)
        self.assertTrue(text.startswith("Error: ReferenceError"))
        self.assertIn("at doWork (line 12)", text)
        self.assertIn("at main (line 3)", text)

    def test_error_without_message(self):
        text = format_script_response("doWork", {"error": {}})
        self.assertIn("Apps Script execution failed", text)


if __name__ == "__main__":
    unittest.main()
