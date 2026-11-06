"""Tests for Slides helpers (no network)."""

import unittest

from workspace_operator.handlers.slides import (
    EMU_PER_PIXEL,
    _count_occurrences,
    _emu,
    _slide_text,
)


def _slide(*texts):
    elements = []
    for text in texts:
        elements.append(
            {
                "shape": {
                    "text": {
                        "textElements": [
                            {"textRun": {"content": text}},
                        ]
                    }
                }
            }
        )
    return {"objectId": "slide-1", "pageElements": elements}


class EmuTests(unittest.TestCase):
    def test_96_pixels_is_one_inch(self):
        self.assertEqual(_emu(96), {"magnitude": 914400, "unit": "EMU"})

    def test_rounds_fractional_pixels(self):
        self.assertEqual(_emu(1.5)["magnitude"], round(1.5 * EMU_PER_PIXEL))


class SlideTextTests(unittest.TestCase):
    def test_joins_shapes(self):
        self.assertEqual(_slide_text(_slide("Title", "Body")), "Title / Body")

    def test_ignores_whitespace_only_runs(self):
        self.assertEqual(_slide_text(_slide("Title", "  \n ")), "Title")

    def test_empty_slide(self):
        self.assertEqual(_slide_text({"pageElements": []}), "")

    def test_strips_html_entities(self):
        self.assertEqual(_slide_text(_slide("Q&amp;A")), "Q&A")


class OccurrenceTests(unittest.TestCase):
    def test_counts_across_slides(self):
        presentation = {"slides": [_slide("Hello {{name}}"), _slide("{{name}} again")]}
        counts = _count_occurrences(presentation, ["{{name}}", "missing"])
        self.assertEqual(counts["{{name}}"], 2)
        self.assertEqual(counts["missing"], 0)

    def test_counts_within_a_single_run(self):
        presentation = {"slides": [_slide("x x x")]}
        self.assertEqual(_count_occurrences(presentation, ["x"])["x"], 3)


if __name__ == "__main__":
    unittest.main()
