"""Tests for the human approval queue."""

import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workspace_operator.approvals import (
    ApprovalError,
    ApprovalStore,
    approval_root,
    arguments_hash,
    challenge_text,
)
from workspace_operator.config import Config


def make_config(directory: str, ttl: int = 900) -> Config:
    return Config(
        client_secrets_file="x",
        token_file="x",
        backup_dir="x",
        log_file=None,
        mcp_auth_token="t",
        scopes=[],
        approval_dir=directory,
        approval_ttl=ttl,
    )


class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ApprovalStore(make_config(self.tmp.name))

    def test_request_approve_consume(self):
        args = {"file_id": "f1", "confirm": True}
        record = self.store.request("drive_trash", None, args)
        self.assertEqual(record["status"], "pending")
        self.store.approve(record["id"])
        ok, reason = self.store.consume(record["id"], "drive_trash", None, args)
        self.assertTrue(ok, reason)
        ok, reason = self.store.consume(record["id"], "drive_trash", None, args)
        self.assertFalse(ok)
        self.assertIn("already used", reason)

    def test_args_hash_ignores_approval_and_confirm(self):
        a = {"file_id": "f1", "confirm": False, "approval_id": "apr_old"}
        b = {"file_id": "f1", "confirm": True, "approval_id": "apr_new"}
        self.assertEqual(
            arguments_hash("drive_trash", None, a),
            arguments_hash("drive_trash", None, b),
        )

    def test_mismatched_arguments_rejected(self):
        record = self.store.request("drive_trash", None, {"file_id": "f1"})
        self.store.approve(record["id"])
        ok, reason = self.store.consume(
            record["id"], "drive_trash", None, {"file_id": "f2"}
        )
        self.assertFalse(ok)
        self.assertIn("changed", reason)

    def test_denied(self):
        record = self.store.request("drive_trash", None, {"file_id": "f1"})
        self.store.deny(record["id"])
        with self.assertRaises(ApprovalError):
            self.store.approve(record["id"])

    def test_expired(self):
        record = self.store.request("drive_trash", None, {"file_id": "f1"})
        self.store.approve(record["id"])
        # Expire through the store's own writer so the seal stays valid.
        data = self.store.get(record["id"])
        data["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.store._write(data)
        ok, reason = self.store.consume(
            record["id"], "drive_trash", None, {"file_id": "f1"}
        )
        self.assertFalse(ok)
        self.assertIn("expired", reason)

    def test_agent_cannot_forge_approval_in_file(self):
        """Editing status to 'approved' on disk must not release the action."""
        args = {"file_id": "f1"}
        record = self.store.request("drive_trash", None, args)
        path = Path(self.tmp.name) / f"{record['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "approved"
        path.write_text(json.dumps(data), encoding="utf-8")
        ok, reason = self.store.consume(record["id"], "drive_trash", None, args)
        self.assertFalse(ok)
        self.assertIn("integrity", reason)

    def test_key_file_is_created_once_and_reused(self):
        self.store.request("drive_trash", None, {"file_id": "f1"})
        key_path = Path(self.tmp.name) / "approval.key"
        first = key_path.read_text(encoding="utf-8")
        again = ApprovalStore(make_config(self.tmp.name))
        again.request("drive_trash", None, {"file_id": "f2"})
        self.assertEqual(key_path.read_text(encoding="utf-8"), first)

    def test_challenge_is_machine_readable(self):
        record = self.store.request("drive_trash", None, {"file_id": "f1"})
        text = challenge_text(record, f"http://127.0.0.1:8765/approvals/{record['id']}")
        self.assertIn("APPROVAL REQUIRED", text)
        self.assertIn(record["id"], text)
        # The agent must not learn how to decide: no links, no CLI commands.
        self.assertNotIn("/approvals/", text)
        self.assertNotIn("?k=", text)
        self.assertNotIn("approvals link", text)
        self.assertNotIn("approvals approve", text)
        self.assertNotIn("approvals deny", text)


def bare_config() -> Config:
    """A config without approval_dir, so the default location applies."""
    return Config(
        client_secrets_file="x",
        token_file="x",
        backup_dir="x",
        log_file=None,
        mcp_auth_token="t",
        scopes=[],
    )


class ApprovalLocationTests(unittest.TestCase):
    """The queue resolves to one place, whatever folder the server starts from."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.saved_env = os.environ.pop("MCP_APPROVAL_DIR", None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self.cwd)
        if self.saved_env is not None:
            os.environ["MCP_APPROVAL_DIR"] = self.saved_env

    def test_default_is_the_credentials_folder_from_any_directory(self):
        roots = set()
        for _ in range(2):
            with tempfile.TemporaryDirectory() as folder:
                os.chdir(folder)
                try:
                    roots.add(approval_root(bare_config()))
                finally:
                    os.chdir(self.cwd)
        expected = (Path(os.path.expanduser("~")) / ".google" / "approvals").resolve()
        self.assertEqual(roots, {expected})

    def test_explicit_directory_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as explicit:
            self.assertEqual(approval_root(make_config(explicit)), Path(explicit).resolve())

    def test_example_configs_do_not_pin_a_relative_approval_dir(self):
        """A relative approval_dir would bring back the working-directory dependency."""
        root = Path(__file__).resolve().parents[1]
        for name in ("config.example.yaml", "config.docker.yaml"):
            for line in (root / name).read_text(encoding="utf-8").splitlines():
                match = re.match(r'approval_dir:\s*"?([^"\s#]+)', line)
                if match:
                    with self.subTest(file=name):
                        self.assertTrue(match.group(1).startswith(("/", "~")), line)


if __name__ == "__main__":
    unittest.main()
