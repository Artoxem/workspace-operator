"""The tool/prompt definitions are data files; pin them and their packaging."""

import json
import os
import re
import unittest
from importlib import resources
from pathlib import Path

from mcp import types

from workspace_operator import definitions
from workspace_operator.definitions import load_prompts, load_tools

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).parent / "data" / "definitions_golden.json"
HINT = (
    "If this change is intentional (a tool was added, renamed or re-described), regenerate "
    "tests/data/definitions_golden.json: UPDATE_GOLDEN=1 python -m pytest tests/test_definitions.py"
)


def _dump(obj):
    return obj.model_dump(mode="json", by_alias=False, exclude_none=False)


class DefinitionsSnapshotTests(unittest.TestCase):
    """The snapshot comes from the Python definitions that preceded the JSON files."""

    @classmethod
    def setUpClass(cls):
        if os.environ.get("UPDATE_GOLDEN"):
            snapshot = {
                "tools": [_dump(tool) for tool in load_tools()],
                "prompts": [_dump(prompt) for prompt in load_prompts()],
            }
            GOLDEN.write_text(
                json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        cls.golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    def test_tools_match_snapshot_including_order(self):
        loaded = [_dump(tool) for tool in load_tools()]
        self.assertEqual(
            [t["name"] for t in loaded], [t["name"] for t in self.golden["tools"]], HINT
        )
        for got, want in zip(loaded, self.golden["tools"], strict=True):
            self.assertEqual(got, want, f"definition changed for {want['name']}. {HINT}")

    def test_prompts_match_snapshot(self):
        self.assertEqual([_dump(p) for p in load_prompts()], self.golden["prompts"], HINT)

    def test_counts(self):
        self.assertEqual(len(load_tools()), 103, HINT)
        self.assertEqual(len(load_prompts()), 7, HINT)


class DefinitionsShapeTests(unittest.TestCase):
    def test_every_tool_has_a_valid_object_schema_and_description(self):
        for tool in load_tools():
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.description.strip())
                schema = tool.input_schema
                self.assertEqual(schema.get("type"), "object")
                properties = schema.get("properties", {})
                for required in schema.get("required", []):
                    self.assertIn(required, properties, f"{tool.name}: required '{required}' is not a property")

    def test_names_are_unique(self):
        names = [tool.name for tool in load_tools()]
        self.assertEqual(len(names), len(set(names)))

    def test_safety_hints_are_consistent(self):
        for tool in load_tools():
            hints = tool.annotations
            with self.subTest(tool=tool.name):
                self.assertIsNotNone(hints)
                self.assertFalse(hints.read_only_hint and hints.destructive_hint)

    def test_loaders_return_fresh_objects(self):
        first, second = load_tools(), load_tools()
        first[0].annotations.read_only_hint = not first[0].annotations.read_only_hint
        self.assertNotEqual(first[0].annotations.read_only_hint, second[0].annotations.read_only_hint)

    def test_prompts_are_prompts(self):
        for prompt in load_prompts():
            self.assertIsInstance(prompt, types.Prompt)


class DefinitionsFilesTests(unittest.TestCase):
    def test_every_json_file_is_loaded(self):
        """A new definitions/*.json that is not wired into the loader would be dead data."""
        on_disk = {
            entry.name for entry in resources.files(definitions).iterdir()
            if entry.name.endswith(".json")
        }
        wired = {f"{name}.json" for name in definitions._DOMAIN_FILES} | {"order.json", "prompts.json"}
        self.assertEqual(on_disk, wired)

    def test_order_lists_exactly_the_defined_tools(self):
        order = json.loads(resources.files(definitions).joinpath("order.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(order), sorted(tool.name for tool in load_tools()))
        self.assertEqual(len(order), len(set(order)))


class PackagingTests(unittest.TestCase):
    """JSON files are not packaged by default; a wheel without them cannot start."""

    def test_package_data_covers_the_definition_files(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'\[tool\.setuptools\.package-data\](.*?)(?=\n\[|\Z)', text, re.S)
        self.assertIsNotNone(match, "pyproject.toml needs [tool.setuptools.package-data]")
        self.assertIn('"workspace_operator.definitions"', match.group(1))
        self.assertIn("*.json", match.group(1))

    def test_dockerfile_copies_the_package_directory(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY workspace_operator ./workspace_operator", dockerfile)


if __name__ == "__main__":
    unittest.main()
