"""Tests for the CLI: catalog rendering and configuration checks (no network)."""

import json
import tempfile
import unittest
from pathlib import Path

from workspace_operator.cli import (
    Check,
    check_config,
    check_token,
    main,
    render_catalog,
    render_checks,
    tool_catalog,
)
from workspace_operator.config import Config


def make_config(tmp: str, **overrides) -> Config:
    root = Path(tmp)
    payload = {
        "client_secrets_file": str(root / "secrets.json"),
        "token_file": str(root / "token.json"),
        "backup_dir": str(root / "backups"),
        "log_file": str(root / "logs" / "mcp.log"),
        "mcp_auth_token": "token",
        "scopes": ["https://www.googleapis.com/auth/drive"],
    }
    payload.update(overrides)
    return Config(**payload)


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_tool_count(self):
        catalog = tool_catalog("full")
        self.assertGreater(len(catalog), 60)

    def test_profile_filters_catalog(self):
        full = len(tool_catalog("full"))
        readonly = len(tool_catalog("read-only"))
        self.assertLess(readonly, full)

    def test_render_contains_all_names(self):
        catalog = tool_catalog("full")
        text = render_catalog(catalog)
        for item in catalog[:5]:
            self.assertIn(item["name"], text)
        self.assertIn("tool(s)", text)

    def test_kinds(self):
        kinds = {item["kind"] for item in tool_catalog("full")}
        self.assertEqual(kinds, {"read", "write", "destructive"})

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(["tools", "--json", "--profile", "read-only"])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(all("name" in item for item in payload))


class ConfigCheckTests(unittest.TestCase):
    def test_missing_secrets_is_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = check_config(make_config(tmp))
            secrets = next(check for check in checks if check.name == "client secrets")
            self.assertFalse(secrets.ok)
            self.assertTrue(secrets.critical)

    def test_existing_paths_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(tmp)
            Path(config.client_secrets_file).write_text("{}", encoding="utf-8")
            Path(config.token_file).write_text("{}", encoding="utf-8")
            Path(config.backup_dir).mkdir()
            Path(config.log_file).parent.mkdir(parents=True)

            checks = check_config(config)
            statuses = {check.name: check.ok for check in checks}
            self.assertTrue(statuses["client secrets"])
            self.assertTrue(statuses["token file"])
            self.assertTrue(statuses["backup directory"])
            self.assertTrue(statuses["tool profile"])

    def test_bad_profile_is_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = check_config(make_config(tmp, tool_profile="sometimes"))
            profile = next(check for check in checks if check.name == "tool profile")
            self.assertFalse(profile.ok)
            self.assertTrue(profile.critical)


class TokenCheckTests(unittest.TestCase):
    def test_missing_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = check_token(make_config(tmp), refresh=False)
            self.assertFalse(checks[0].ok)

    def test_scope_mismatch_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(tmp)
            Path(config.token_file).write_text(
                json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.modify"]}),
                encoding="utf-8",
            )
            checks = check_token(config, refresh=False)
            scopes = next(check for check in checks if check.name == "scopes")
            self.assertFalse(scopes.ok)
            self.assertIn("drive", scopes.detail)

    def test_scopes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(tmp)
            Path(config.token_file).write_text(
                json.dumps({"scopes": config.scopes}), encoding="utf-8"
            )
            checks = check_token(config, refresh=False)
            scopes = next(check for check in checks if check.name == "scopes")
            self.assertTrue(scopes.ok)


class RenderTests(unittest.TestCase):
    def test_render_checks(self):
        text = render_checks([Check("a", True, "fine"), Check("b", False, "broken")])
        self.assertIn("[ok  ] a: fine", text)
        self.assertIn("[FAIL] b: broken", text)


if __name__ == "__main__":
    unittest.main()
