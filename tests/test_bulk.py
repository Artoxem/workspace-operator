"""Unit tests for the bulk planner, store and safety gates."""

import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest import mock

from workspace_operator.bulk import service, store
from workspace_operator.bulk.engine import _rename
from workspace_operator.bulk.models import Job, Plan
from workspace_operator.bulk.selector import build_query, escape_query
from workspace_operator.config import Config

LOGGER = logging.getLogger("test.bulk")


def make_config(directory: str, **overrides) -> Config:
    base = Config(
        client_secrets_file="secrets.json",
        token_file="token.json",
        backup_dir=os.path.join(directory, "backups"),
        log_file=None,
        mcp_auth_token="token",
        scopes=[],
        bulk_dir=directory,
        bulk_max_items=2,
        bulk_hard_limit=10,
        bulk_concurrency=2,
        bulk_plan_ttl=900,
    )
    return replace(base, **overrides)


def fake_resolved(count: int, **extra):
    items = [
        {
            "id": f"id{index}",
            "name": f"file-{index}.txt",
            "parents": ["root"],
            "size": 10 * index,
            "mimeType": "text/plain",
            "trashed": False,
        }
        for index in range(count)
    ]
    payload = {"items": items, "truncated": False, "warnings": []}
    payload.update(extra)
    return payload


class QueryTests(unittest.TestCase):
    def test_escapes_single_quotes(self):
        self.assertEqual(escape_query("O'Brien"), "O\\'Brien")

    def test_builds_combined_filter(self):
        query = build_query(
            {
                "query": "name contains 'IMG'",
                "mime_types": ["image/jpeg", "image/png"],
                "name_contains": "photo",
                "modified": {"after": "2025-01-01"},
            }
        )
        self.assertIn("trashed = false", query)
        self.assertIn("(name contains 'IMG')", query)
        self.assertIn("mimeType = 'image/jpeg'", query)
        self.assertIn("name contains 'photo'", query)
        self.assertIn("modifiedTime > '2025-01-01'", query)

    def test_include_trashed_drops_clause(self):
        self.assertNotIn("trashed = false", build_query({"include_trashed": True}))


class RenameTests(unittest.TestCase):
    def test_pattern_tokens(self):
        item = {"name": "IMG_0001.jpg"}
        result = _rename(item, {"pattern": "trip_{index}{ext}"}, 7)
        self.assertEqual(result, "trip_7.jpg")

    def test_find_replace(self):
        item = {"name": "draft-report.txt"}
        self.assertEqual(
            _rename(item, {"find": "draft-", "replace": "final-"}, 1),
            "final-report.txt",
        )

    def test_rejects_path_separator(self):
        with self.assertRaises(Exception):
            _rename({"name": "a.txt"}, {"pattern": "x/y.txt"}, 1)


class StoreTests(unittest.TestCase):
    def test_plan_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            plan = Plan(
                id="bp_test",
                domain="drive",
                action="trash",
                options={},
                selector={},
                created_at=datetime.now(timezone.utc).isoformat(),
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                items=[{"id": "a", "name": "a.txt"}],
            )
            store.save_plan(config, plan)
            loaded = store.load_plan(config, "bp_test")
            self.assertEqual(loaded.id, "bp_test")
            self.assertEqual(loaded.items[0]["id"], "a")

    def test_expired_plans_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            plan = Plan(
                id="bp_old",
                domain="drive",
                action="trash",
                options={},
                selector={},
                created_at=past,
                expires_at=past,
            )
            store.save_plan(config, plan)
            self.assertEqual(store.cleanup_plans(config), 1)
            with self.assertRaises(Exception):
                store.load_plan(config, "bp_old")

    def test_completed_ids_skip_only_terminal_successes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            store.append_result(config, "bj_x", {"id": "a", "status": "ok"})
            store.append_result(config, "bj_x", {"id": "b", "status": "skipped"})
            store.append_result(config, "bj_x", {"id": "c", "status": "failed"})
            self.assertEqual(store.completed_ids(config, "bj_x"), {"a", "b"})
            self.assertEqual(len(store.read_results(config, "bj_x")), 3)


class PlanServiceTests(unittest.TestCase):
    def test_cap_refuses_without_allow_large(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            with mock.patch.object(service, "get_creds", return_value=None), mock.patch.object(
                service.selector_module, "resolve_drive", return_value=fake_resolved(3)
            ):
                payload = json.loads(
                    service.plan_bulk(config, LOGGER, "drive", "trash")
                )
            self.assertFalse(payload["ok"])
            self.assertIn("more than 2", payload["error"])

    def test_allow_large_accepts_more(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            with mock.patch.object(service, "get_creds", return_value=None), mock.patch.object(
                service.selector_module, "resolve_drive", return_value=fake_resolved(3)
            ):
                payload = json.loads(
                    service.plan_bulk(
                        config, LOGGER, "drive", "trash", allow_large=True
                    )
                )
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["matched"], 3)
            self.assertEqual(len(payload["sample"]), 3)

    def test_plan_refuses_ids_with_query(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            payload = json.loads(
                service.plan_bulk(
                    config,
                    LOGGER,
                    "drive",
                    "trash",
                    selector={"ids": ["a"], "query": "name contains 'x'"},
                )
            )
            self.assertFalse(payload["ok"])

    def test_plan_rejects_unsupported_action(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            payload = json.loads(
                service.plan_bulk(config, LOGGER, "drive", "explode")
            )
            self.assertFalse(payload["ok"])


class RunServiceTests(unittest.TestCase):
    def _plan(self, config: Config) -> Plan:
        plan = Plan(
            id="bp_run",
            domain="drive",
            action="trash",
            options={},
            selector={},
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            items=[{"id": "a", "name": "a.txt"}],
        )
        store.save_plan(config, plan)
        return plan

    def test_run_requires_confirm(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            self._plan(config)
            payload = json.loads(
                service.run_bulk(config, LOGGER, "bp_run", confirm=False)
            )
            self.assertFalse(payload["ok"])
            self.assertIn("confirmation", payload["error"])

    def test_run_refuses_global_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory, dry_run=True)
            self._plan(config)
            payload = json.loads(
                service.run_bulk(config, LOGGER, "bp_run", confirm=True)
            )
            self.assertFalse(payload["ok"])
            self.assertIn("dry_run", payload["error"])

    def test_run_starts_job(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            self._plan(config)
            job = Job(
                id="bj_test",
                plan_id="bp_run",
                domain="drive",
                action="trash",
                total=1,
            )
            finished = []
            with mock.patch.object(service.engine, "start_job", return_value=job):
                payload = json.loads(
                    service.run_bulk(
                        config, LOGGER, "bp_run", confirm=True, on_finish=finished.append
                    )
                )
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["job_id"], "bj_test")

    def test_expired_plan_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            plan = Plan(
                id="bp_expired",
                domain="drive",
                action="trash",
                options={},
                selector={},
                created_at=past,
                expires_at=past,
            )
            store.save_plan(config, plan)
            payload = json.loads(
                service.run_bulk(config, LOGGER, "bp_expired", confirm=True)
            )
            self.assertFalse(payload["ok"])
            self.assertIn("expired", payload["error"])


if __name__ == "__main__":
    unittest.main()
