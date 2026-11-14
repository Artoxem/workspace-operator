"""Tests for the prompt catalog (metadata only, no network)."""

import unittest

from workspace_operator.server import _prompts

EXPECTED = {
    "summarize_inbox",
    "analyze_spreadsheet",
    "plan_week",
    "search_drive",
    "weekly_review",
    "inbox_triage",
    
    "compare_brief",
}


class PromptCatalogTests(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(_prompts()), 7)

    def test_names_unique_and_expected(self):
        names = [prompt.name for prompt in _prompts()]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), EXPECTED)

    def test_every_prompt_has_a_description(self):
        for prompt in _prompts():
            with self.subTest(prompt=prompt.name):
                self.assertTrue((prompt.description or "").strip())

    def test_required_arguments(self):
        by_name = {prompt.name: prompt for prompt in _prompts()}

        def required(name):
            return [arg.name for arg in by_name[name].arguments if arg.required]

        
        self.assertEqual(required("compare_brief"), ["spreadsheet_id", "range_a", "range_b"])
        self.assertEqual(required("weekly_review"), [])
        self.assertEqual(required("inbox_triage"), [])

    def test_optional_arguments_have_defaults_in_description(self):
        by_name = {prompt.name: prompt for prompt in _prompts()}
        days = [arg for arg in by_name["weekly_review"].arguments if arg.name == "days_back"][0]
        self.assertIn("default", days.description.lower())


if __name__ == "__main__":
    unittest.main()
