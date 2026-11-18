"""Every place that states the package version must agree.

server.json carries the version twice (the server and its PyPI package); a bump that
replaces only the first occurrence once left the registry entry one release behind.
"""

import json
import re
import unittest
from pathlib import Path

from workspace_operator import __version__

ROOT = Path(__file__).resolve().parent.parent


class VersionSyncTests(unittest.TestCase):
    def test_pyproject_matches_package(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        self.assertEqual(match.group(1), __version__)

    def test_server_json_versions_match_package(self):
        data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], __version__)
        for package in data["packages"]:
            self.assertEqual(package["version"], __version__, package["identifier"])

    def test_skill_version_matches_package(self):
        text = (ROOT / "skills" / "google-workspace" / "SKILL.md").read_text(encoding="utf-8")
        # the version sits under "metadata:" in the front matter, hence the indent
        match = re.search(r'^\s+version:\s*"([^"]+)"', text, re.M)
        self.assertIsNotNone(match, "no version in the skill front matter")
        self.assertEqual(match.group(1), __version__)

    def test_version_history_names_the_current_release(self):
        text = (ROOT / "docs" / "VERSIONS.md").read_text(encoding="utf-8")
        self.assertIn(f"Current release: **{__version__}**", text)
        self.assertIn(f"| **{__version__}** |", text)


if __name__ == "__main__":
    unittest.main()
