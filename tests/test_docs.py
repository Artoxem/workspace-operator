"""Documentation must stay in sync with the code.

These tests fail when a tool is added but not documented, when counts drift,
when a legacy name sneaks back, or when a relative link breaks.
"""

import json
import re
import unittest
from pathlib import Path

import yaml

from workspace_operator.profiles import resolve_profile
from workspace_operator.server import _tools

ROOT = Path(__file__).resolve().parents[1]
TOOLS = _tools()
TOOL_NAMES = [tool.name for tool in TOOLS]
TOTAL = len(TOOLS)
READ_WRITE = len(resolve_profile("read-write").filter(TOOLS))
READ_ONLY = len(resolve_profile("read-only").filter(TOOLS))

# Release notes and specs describe past versions on purpose.
HISTORICAL = ("docs/RELEASE_", "docs/SPEC_")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def markdown_files():
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        yield path


class ToolCatalogTests(unittest.TestCase):
    def test_readme_lists_every_tool(self):
        for rel in ("README.md", "README.ru.md"):
            text = read(rel)
            missing = [
                name
                for name in TOOL_NAMES
                if not re.search(rf"`{re.escape(name)}[`(]", text)
            ]
            with self.subTest(file=rel):
                self.assertEqual(missing, [], f"undocumented in {rel}: {missing}")

    def test_reference_lists_every_tool(self):
        for rel in ("docs/TOOLS_REFERENCE.md", "docs/ru/TOOLS_REFERENCE.md"):
            text = read(rel)
            missing = [
                name
                for name in TOOL_NAMES
                if not re.search(rf"`{re.escape(name)}[`(]", text)
            ]
            with self.subTest(file=rel):
                self.assertEqual(missing, [], f"missing in {rel}: {missing}")

    def test_readme_tool_count(self):
        self.assertIn(f"**{TOTAL} tools", read("README.md"))
        self.assertIn(f"**{TOTAL} инструментов", read("README.ru.md"))
        self.assertIn(f"tools-{TOTAL}-informational", read("README.md"))


class ProfileCountTests(unittest.TestCase):
    def test_readme_profile_table(self):
        text = read("README.md")
        for label, value in (("full", TOTAL), ("read-write", READ_WRITE), ("read-only", READ_ONLY)):
            self.assertIn(f"| `{label}` | {value} |", text)

    def test_russian_readme_profile_table(self):
        text = read("README.ru.md")
        for label, value in (("full", TOTAL), ("read-write", READ_WRITE), ("read-only", READ_ONLY)):
            self.assertIn(f"| `{label}` | {value} |", text)

    def test_security_docs(self):
        for rel in ("docs/SECURITY.md", "docs/ru/SECURITY.md"):
            text = read(rel)
            for label, value in (("full", TOTAL), ("read-write", READ_WRITE), ("read-only", READ_ONLY)):
                with self.subTest(file=rel, profile=label):
                    self.assertIn(f"| `{label}` | {value} |", text)

    def test_tools_reference_docs(self):
        for rel in ("docs/TOOLS_REFERENCE.md", "docs/ru/TOOLS_REFERENCE.md"):
            text = read(rel)
            with self.subTest(file=rel):
                self.assertIn(f"| `read-write` | {READ_WRITE} |", text)
                self.assertIn(f"| `read-only` | {READ_ONLY} |", text)

    def test_antigravity_guide(self):
        text = read("antigravity/README.md")
        self.assertIn(f"| `read-only` | {READ_ONLY} read tools", text)
        self.assertIn(f"| `read-write` | {READ_WRITE} tools", text)
        self.assertIn(f"| `full` | all {TOTAL} tools", text)


class LegacyNameTests(unittest.TestCase):
    def test_no_legacy_package_or_server_name(self):
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix not in {".py", ".md", ".json", ".toml", ".yaml"}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(HISTORICAL) or rel == "tests/test_docs.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in ("mcp_google", "My Google Tools"):
                if needle in text:
                    offenders.append(f"{rel}: {needle}")
        self.assertEqual(offenders, [])


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for path in markdown_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for target in re.findall(r"\]\(([^)#][^)]*)\)", text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if not (path.parent / target.split("#")[0]).resolve().exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])


class ConfigExampleTests(unittest.TestCase):
    def test_antigravity_example(self):
        data = json.loads(read("antigravity/mcp_config.example.json"))
        server = data["mcpServers"]["workspace-operator"]
        self.assertTrue(server["args"][0].endswith("server.py"))
        self.assertIn("MCP_AUTH_TOKEN", server["env"])

    def test_config_example_runtime_keys(self):
        data = yaml.safe_load(read("config.example.yaml"))
        for key in ("tool_profile", "dry_run", "audit_log", "retry_attempts"):
            with self.subTest(key=key):
                self.assertIn(key, data)

    def test_readme_documents_operations(self):
        for rel in ("README.md", "README.ru.md"):
            text = read(rel)
            with self.subTest(file=rel):
                self.assertIn("python -m workspace_operator doctor", text)
                self.assertIn("MCP_DRY_RUN", text)
                self.assertIn("MCP_AUDIT_LOG", text)

    def test_config_example_scopes(self):
        data = yaml.safe_load(read("config.example.yaml"))
        self.assertIn("tool_profile", data)
        self.assertIn(
            "https://www.googleapis.com/auth/presentations", data["scopes"]
        )


if __name__ == "__main__":
    unittest.main()
