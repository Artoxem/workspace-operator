"""CLI tests for the approval queue (no network)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from workspace_operator.approvals import ApprovalStore
from workspace_operator.cli import main
from workspace_operator.config import load_config


class ApprovalCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_path = Path(self.tmp.name) / "config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "client_secrets_file: missing",
                    "token_file: missing",
                    "backup_dir: missing",
                    f"approval_dir: {self.tmp.name}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.old = os.environ.get("MCP_CONFIG_FILE")
        os.environ["MCP_CONFIG_FILE"] = str(self.config_path)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self.old is None:
            os.environ.pop("MCP_CONFIG_FILE", None)
        else:
            os.environ["MCP_CONFIG_FILE"] = self.old

    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_list_approve_show_deny(self):
        store = ApprovalStore(load_config())
        record = store.request("drive_trash", None, {"file_id": "f1"})

        code, out = self.run_cli("approvals", "list")
        self.assertEqual(code, 0)
        self.assertIn(record["id"], out)

        code, out = self.run_cli("approvals", "approve", record["id"])
        self.assertEqual(code, 0)
        self.assertIn("APPROVED", out)

        code, out = self.run_cli("approvals", "show", record["id"])
        self.assertEqual(code, 0)
        self.assertIn("approved", out)

        second = store.request("drive_trash", None, {"file_id": "f2"})
        code, out = self.run_cli("approvals", "deny", second["id"])
        self.assertEqual(code, 0)
        self.assertIn("DENIED", out)

    def test_unknown_id_returns_error(self):
        code, out = self.run_cli("approvals", "approve", "apr_missing")
        self.assertEqual(code, 1)
        self.assertIn("error", out.lower())


if __name__ == "__main__":
    unittest.main()
