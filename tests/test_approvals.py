"""Tests for the human approval queue."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workspace_operator.approvals import (
    ApprovalError,
    ApprovalStore,
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
        path = Path(self.tmp.name) / f"{record['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        path.write_text(json.dumps(data), encoding="utf-8")
        ok, reason = self.store.consume(
            record["id"], "drive_trash", None, {"file_id": "f1"}
        )
        self.assertFalse(ok)
        self.assertIn("expired", reason)

    def test_challenge_is_machine_readable(self):
        record = self.store.request("drive_trash", None, {"file_id": "f1"})
        text = challenge_text(record)
        self.assertIn("APPROVAL REQUIRED", text)
        self.assertIn(record["id"], text)
        self.assertIn("workspace-operator approvals approve", text)


if __name__ == "__main__":
    unittest.main()
