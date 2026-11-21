"""Config lookup: explicit path, current directory, per-user directory, defaults."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

from workspace_operator.cli import build_parser, check_config, main
from workspace_operator.config import Config, ConfigFileError, load_config

ENV_KEYS = (
    "MCP_CONFIG_FILE",
    "MCP_TOOL_PROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CONFIG_HOME",
)


def write_config(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class ConfigLookupTests(unittest.TestCase):
    def setUp(self):
        if sys.platform == "darwin":
            self.skipTest("the macOS config directory is not env-driven")
        self.cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        # Registered before the chdir cleanup, so the test leaves the temporary
        # directory before it is removed (Windows cannot delete a busy cwd).
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, self.cwd)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        # Keep the per-user lookup inside the temporary directory.
        self.user_base = self.root / "appdata"
        os.environ["APPDATA"] = str(self.user_base)  # Windows
        os.environ["XDG_CONFIG_HOME"] = str(self.user_base)  # POSIX
        self.empty = self.root / "empty"
        self.empty.mkdir()

    # -- explicit ---------------------------------------------------------

    def test_explicit_path_wins_and_is_reported(self):
        path = write_config(self.root / "custom.yaml", {"tool_profile": "full"})
        config = load_config(config_path=str(path))
        self.assertEqual(config.tool_profile, "full")
        self.assertEqual(config.config_source, "explicit")
        self.assertEqual(config.config_file, str(path))

    def test_explicit_env_variable_is_honoured(self):
        path = write_config(self.root / "custom.yaml", {"tool_profile": "read-only"})
        os.environ["MCP_CONFIG_FILE"] = str(path)
        self.assertEqual(load_config().tool_profile, "read-only")

    def test_explicit_missing_path_is_an_error(self):
        missing = str(self.root / "nope.yaml")
        with self.assertRaises(ConfigFileError) as ctx:
            load_config(config_path=missing)
        self.assertIn("Config file not found", str(ctx.exception))
        self.assertIn("nope.yaml", str(ctx.exception))

    def test_explicit_env_missing_path_is_an_error(self):
        os.environ["MCP_CONFIG_FILE"] = str(self.root / "nope.yaml")
        with self.assertRaises(ConfigFileError):
            load_config()

    # -- lookup -----------------------------------------------------------

    def test_local_config_is_discovered(self):
        os.chdir(self.empty)
        path = write_config(self.empty / "config.yaml", {"tool_profile": "full"})
        config = load_config()
        self.assertEqual(config.tool_profile, "full")
        self.assertEqual(config.config_source, "local")
        self.assertEqual(config.config_file, str(path))

    def test_json_local_config_is_discovered(self):
        os.chdir(self.empty)
        (self.empty / "config.json").write_text('{"tool_profile": "read-write"}', encoding="utf-8")
        self.assertEqual(load_config().tool_profile, "read-write")

    def test_user_config_is_discovered(self):
        os.chdir(self.empty)
        path = write_config(
            self.user_base / "workspace-operator" / "config.yaml",
            {"tool_profile": "read-only"},
        )
        config = load_config()
        self.assertEqual(config.tool_profile, "read-only")
        self.assertEqual(config.config_source, "user")
        self.assertEqual(config.config_file, str(path))

    def test_local_wins_over_user(self):
        os.chdir(self.empty)
        write_config(
            self.user_base / "workspace-operator" / "config.yaml",
            {"tool_profile": "read-only"},
        )
        write_config(self.empty / "config.yaml", {"tool_profile": "full"})
        config = load_config()
        self.assertEqual(config.tool_profile, "full")
        self.assertEqual(config.config_source, "local")

    def test_defaults_when_no_file_exists(self):
        os.chdir(self.empty)
        config = load_config()
        self.assertEqual(config.tool_profile, "core")
        self.assertIsNone(config.config_file)
        self.assertEqual(config.config_source, "defaults")

    # -- precedence inside a file ----------------------------------------

    def test_environment_overrides_the_file(self):
        os.chdir(self.empty)
        write_config(self.empty / "config.yaml", {"tool_profile": "read-only"})
        os.environ["MCP_TOOL_PROFILE"] = "full"
        self.assertEqual(load_config().tool_profile, "full")

    def test_profile_argument_wins_over_everything(self):
        os.chdir(self.empty)
        write_config(self.empty / "config.yaml", {"tool_profile": "read-only"})
        os.environ["MCP_TOOL_PROFILE"] = "full"
        self.assertEqual(load_config(tool_profile="core").tool_profile, "core")

    # -- command line -----------------------------------------------------

    def test_parser_accepts_config_and_serve_profile(self):
        args = build_parser().parse_args(
            ["--config", "x.yaml", "serve", "--http", "--profile", "full"]
        )
        self.assertEqual(args.config, "x.yaml")
        self.assertEqual(args.profile, "full")
        self.assertIsNone(build_parser().parse_args(["version"]).config)

    def test_main_reports_a_missing_explicit_config(self):
        missing = str(self.root / "nope.yaml")
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--config", missing, "approvals", "list"])
        self.assertEqual(code, 2)
        self.assertIn("Config file not found", out.getvalue())

    def test_doctor_reports_the_config_source(self):
        config = Config(
            client_secrets_file=str(self.root / "s.json"),
            token_file=str(self.root / "t.json"),
            backup_dir=str(self.root / "b"),
            log_file=None,
            mcp_auth_token=None,
            scopes=[],
            config_file=str(self.empty / "config.yaml"),
            config_source="local",
        )
        checks = check_config(config)
        by_name = {check.name: check for check in checks}
        self.assertIn("config file", by_name)
        self.assertIn("local", by_name["config file"].detail)
        self.assertIn(str(self.empty), by_name["config file"].detail)


if __name__ == "__main__":
    unittest.main()
