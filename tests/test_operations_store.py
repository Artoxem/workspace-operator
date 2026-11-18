"""Staged operations: on-disk store, expiry, atomic claim and the Apps Script flow."""

import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from workspace_operator.config import Config
from workspace_operator.handlers import apps_script as script_module
from workspace_operator.operations import OperationStore, new_operation_id

LOGGER = logging.getLogger("test.operations")


def make_config(directory: str, **overrides) -> Config:
    base = Config(
        client_secrets_file="secrets.json",
        token_file="token.json",
        backup_dir=os.path.join(directory, "backups"),
        log_file=None,
        mcp_auth_token="token",
        scopes=[],
        operation_dir=os.path.join(directory, "operations"),
        operation_ttl=600,
    )
    return replace(base, **overrides)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)
        self.store = OperationStore(self.config)

    def test_create_get_claim_delete(self):
        op_id = self.store.create({"type": "script_update", "script_id": "s1"})
        self.assertRegex(op_id, r"^op_[0-9a-f]+$")
        self.assertEqual(self.store.get(op_id)["script_id"], "s1")
        claimed = self.store.claim(op_id)
        self.assertEqual(claimed["script_id"], "s1")
        self.assertIsNone(self.store.get(op_id), "claim consumes the operation")

    def test_claim_is_exclusive(self):
        op_id = self.store.create({"type": "t"})
        first = self.store.claim(op_id)
        second = self.store.claim(op_id)
        self.assertIsNotNone(first)
        self.assertIsNone(second, "a second claim must not get the same operation")

    def test_two_stores_on_the_same_directory_see_each_other(self):
        op_id = self.store.create({"type": "shared", "script_id": "s2"})
        other_process = OperationStore(self.config)
        self.assertEqual(other_process.get(op_id)["script_id"], "s2")
        self.assertIsNotNone(other_process.claim(op_id))
        self.assertIsNone(self.store.claim(op_id))

    def test_expired_operation_disappears(self):
        op_id = self.store.create({"type": "t"})
        path = Path(self.config.operation_dir) / f"{op_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertIsNone(self.store.get(op_id))
        self.assertFalse(path.exists(), "an expired record is removed on read")

    def test_cleanup_removes_only_expired(self):
        fresh = self.store.create({"type": "fresh"})
        stale = self.store.create({"type": "stale"})
        path = Path(self.config.operation_dir) / f"{stale}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.store.cleanup(), 1)
        self.assertEqual(self.store.list_ids(), [fresh])

    def test_restore_after_failed_execution(self):
        op_id = self.store.create({"type": "t", "script_id": "s3"})
        claimed = self.store.claim(op_id)
        restored = self.store.restore(claimed)
        self.assertEqual(restored, op_id)
        self.assertEqual(self.store.get(op_id)["script_id"], "s3")

    def test_invalid_ids_cannot_escape_the_directory(self):
        for bad in ("../etc/passwd", "op_../../x", "", "op_NOTHEX", "op_123;rm"):
            with self.subTest(op_id=bad):
                self.assertIsNone(self.store.claim(bad))
                self.assertIsNone(self.store.get(bad))
                self.assertFalse(self.store.delete(bad))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_records_are_owner_only(self):
        op_id = self.store.create({"type": "t"})
        path = Path(self.config.operation_dir) / f"{op_id}.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_ttl_comes_from_configuration(self):
        fast = OperationStore(make_config(self.tmp.name, operation_ttl=30))
        self.assertEqual(fast.ttl_seconds, 30)
        defaulted = OperationStore(make_config(self.tmp.name, operation_ttl=0))
        self.assertGreaterEqual(defaulted.ttl_seconds, 30, "TTL is clamped to a sane minimum")


class FakeProjects:
    def __init__(self, content, fail_update=False):
        self._content = content
        self.calls = []
        self.fail_update = fail_update

    def getContent(self, scriptId):  # noqa: N802,N803
        return _Req(self._content)

    def updateContent(self, scriptId, body):  # noqa: N802,N803
        def run():
            self.calls.append({"script_id": scriptId, "files": body["files"]})
            if self.fail_update:
                raise RuntimeError("google said no")
            return {}

        return _Req(None, run)


class _Req:
    def __init__(self, value, func=None):
        self.value, self.func = value, func

    def execute(self):
        return self.func() if self.func else self.value


class FakeScriptService:
    def __init__(self, content, fail_update=False):
        self.projects_obj = FakeProjects(content, fail_update)

    def projects(self):
        return self.projects_obj


CURRENT = {"files": [{"name": "Code.gs", "type": "SERVER_JS", "source": "function a() {}\n"}]}
NEW = [{"name": "Code.gs", "type": "SERVER_JS", "source": "function a() {}\nfunction b() {}\n"}]


class AppsScriptFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)
        self.store = OperationStore(self.config)

    def _prepare(self, service):
        with mock.patch.object(script_module, "api_client", return_value=service):
            return script_module.prepare_script_update_handler(self.config, LOGGER, "s1", NEW)

    def test_prepare_persists_the_operation(self):
        text = self._prepare(FakeScriptService(CURRENT))
        op_id = self.store.list_ids()[0]
        self.assertIn(op_id, text)
        record = self.store.get(op_id)
        self.assertEqual(record["script_id"], "s1")
        self.assertEqual(record["new_files"], NEW)
        self.assertEqual(record["backup"], CURRENT["files"])

    def test_execute_applies_and_consumes(self):
        self._prepare(FakeScriptService(CURRENT))
        op_id = self.store.list_ids()[0]
        service = FakeScriptService(CURRENT)
        with mock.patch.object(script_module, "api_client", return_value=service):
            text = script_module.execute_operation_handler(self.config, LOGGER, op_id)
        self.assertIn("updated successfully", text)
        self.assertEqual(service.projects_obj.calls[0]["files"], NEW)
        self.assertEqual(self.store.list_ids(), [], "an executed operation is gone")
        backup_dir = Path(self.config.backup_dir)
        self.assertTrue(list(backup_dir.glob("backup_script_s1_*.json")), "backup written first")

    def test_execute_is_one_shot(self):
        self._prepare(FakeScriptService(CURRENT))
        op_id = self.store.list_ids()[0]
        with mock.patch.object(script_module, "api_client", return_value=FakeScriptService(CURRENT)):
            script_module.execute_operation_handler(self.config, LOGGER, op_id)
            second = script_module.execute_operation_handler(self.config, LOGGER, op_id)
        self.assertIn("not found or expired", second)

    def test_failed_execute_restores_the_operation(self):
        self._prepare(FakeScriptService(CURRENT))
        op_id = self.store.list_ids()[0]
        with mock.patch.object(
            script_module, "api_client", return_value=FakeScriptService(CURRENT, fail_update=True)
        ):
            text = script_module.execute_operation_handler(self.config, LOGGER, op_id)
        self.assertIn("Error executing operation", text)
        self.assertEqual(self.store.list_ids(), [op_id], "the operation is back for a retry")

    def test_cancel_removes_it(self):
        self._prepare(FakeScriptService(CURRENT))
        op_id = self.store.list_ids()[0]
        self.assertIn("cancelled", script_module.cancel_operation_handler(self.config, LOGGER, op_id))
        self.assertEqual(self.store.list_ids(), [])
        self.assertIn("not found", script_module.cancel_operation_handler(self.config, LOGGER, op_id))

    def test_unknown_operation_id_is_reported(self):
        self.assertIn(
            "not found or expired",
            script_module.execute_operation_handler(self.config, LOGGER, new_operation_id()),
        )


if __name__ == "__main__":
    unittest.main()
