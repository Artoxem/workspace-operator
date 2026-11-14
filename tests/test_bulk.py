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
from workspace_operator.bulk.service import _undo_spec
from workspace_operator.bulk.engine import _gmail_label_changes, _rename
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


class GmailActionTests(unittest.TestCase):
    def test_archive_removes_inbox(self):
        self.assertEqual(_gmail_label_changes("archive", {}), ([], ["INBOX"]))

    def test_trash_and_restore(self):
        self.assertEqual(_gmail_label_changes("trash", {}), (["TRASH"], []))
        self.assertEqual(_gmail_label_changes("restore", {}), ([], ["TRASH"]))

    def test_read_state(self):
        self.assertEqual(_gmail_label_changes("mark_read", {}), ([], ["UNREAD"]))
        self.assertEqual(_gmail_label_changes("mark_unread", {}), (["UNREAD"], []))

    def test_label_uses_resolved_ids(self):
        self.assertEqual(
            _gmail_label_changes(
                "label", {"add_label_ids": ["Label_1"], "remove_label_ids": ["Label_2"]}
            ),
            (["Label_1"], ["Label_2"]),
        )

    def test_plan_gmail_archive(self):
        fake = {
            "items": [
                {"id": "m1", "name": "", "size": 0, "mimeType": "message/rfc822"},
                {"id": "m2", "name": "", "size": 0, "mimeType": "message/rfc822"},
            ],
            "sample": [{"id": "m1", "subject": "smoke", "from": "a@b.c", "date": ""}],
            "truncated": False,
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            with mock.patch.object(service, "get_creds", return_value=None), mock.patch.object(
                service.selector_module, "resolve_gmail", return_value=fake
            ):
                payload = json.loads(
                    service.plan_bulk(
                        config,
                        LOGGER,
                        "gmail",
                        "archive",
                        selector={"query": "subject:bulk-smoke"},
                    )
                )
            self.assertTrue(payload["ok"], payload)
            self.assertEqual(payload["matched"], 2)
            self.assertEqual(payload["sample"][0]["subject"], "smoke")

    def test_gmail_action_cross_domain_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            payload = json.loads(service.plan_bulk(config, LOGGER, "gmail", "move"))
            self.assertFalse(payload["ok"])


class ShareValidationTests(unittest.TestCase):
    def test_anyone_requires_allow_public(self):
        with self.assertRaises(Exception):
            service._validate_options(
                "drive",
                "share",
                {"role": "reader", "type": "anyone"},
                make_config("."),
                LOGGER,
            )

    def test_user_requires_email(self):
        with self.assertRaises(Exception):
            service._validate_options(
                "drive",
                "share",
                {"role": "reader", "type": "user", "email_address": "not-an-email"},
                make_config("."),
                LOGGER,
            )

    def test_valid_share(self):
        service._validate_options(
            "drive",
            "share",
            {"role": "writer", "type": "user", "email_address": "a@example.com"},
            make_config("."),
            LOGGER,
        )


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


class UndoTests(unittest.TestCase):
    def test_move_undo_spec(self):
        job = Job(id="bj_1", plan_id="bp_1", domain="drive", action="move", total=1)
        records = [
            {
                "id": "a",
                "name": "a.txt",
                "status": "ok",
                "previous_parents": ["old"],
            }
        ]
        action, items = _undo_spec(job, records)
        self.assertEqual(action, "move_back")
        self.assertEqual(items[0]["previous_parents"], ["old"])

    def test_rename_undo_spec(self):
        job = Job(id="bj_2", plan_id="bp_2", domain="drive", action="rename", total=1)
        records = [{"id": "a", "name": "new.txt", "status": "ok", "previous_name": "old.txt"}]
        action, items = _undo_spec(job, records)
        self.assertEqual(action, "rename_back")
        self.assertEqual(items[0]["previous_name"], "old.txt")

    def test_trash_undo_spec(self):
        job = Job(id="bj_3", plan_id="bp_3", domain="drive", action="trash", total=1)
        records = [{"id": "a", "name": "a.txt", "status": "ok"}]
        action, items = _undo_spec(job, records)
        self.assertEqual(action, "restore")
        self.assertTrue(items[0]["trashed"])

    def test_gmail_undo_is_rejected(self):
        job = Job(id="bj_4", plan_id="bp_4", domain="gmail", action="archive", total=1)
        with self.assertRaises(Exception):
            _undo_spec(job, [{"id": "m1", "status": "ok"}])

    def test_undo_requires_confirm_and_saved_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            job = Job(
                id="bj_undo",
                plan_id="bp_src",
                domain="drive",
                action="move",
                state="completed",
                total=1,
                done=1,
                ok=1,
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            store.save_job(config, job)
            store.append_result(
                config,
                "bj_undo",
                {
                    "id": "a",
                    "name": "a.txt",
                    "status": "ok",
                    "previous_parents": ["old"],
                },
            )
            refused = json.loads(service.undo_bulk(config, LOGGER, "bj_undo", confirm=False))
            self.assertFalse(refused["ok"])
            fake_job = Job(
                id="bj_new",
                plan_id="bp_undo",
                domain="drive",
                action="move_back",
                total=1,
            )
            with mock.patch.object(service.engine, "start_job", return_value=fake_job):
                started = json.loads(
                    service.undo_bulk(config, LOGGER, "bj_undo", confirm=True)
                )
            self.assertTrue(started["ok"])
            self.assertEqual(started["action"], "move_back")



class TextDomainTests(unittest.TestCase):
    def _fake(self):
        return {
            "items": [
                {"id": "f1", "name": "doc one", "size": 0, "mimeType": "", "trashed": False}
            ],
            "sample": [{"id": "f1", "name": "doc one", "size": 0, "mimeType": ""}],
            "truncated": False,
            "warnings": [],
        }

    def test_docs_replace_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            with mock.patch.object(service, "get_creds", return_value=None), mock.patch.object(
                service.selector_module, "resolve_drive", return_value=self._fake()
            ):
                payload = json.loads(
                    service.plan_bulk(
                        config,
                        LOGGER,
                        "docs",
                        "replace_text",
                        selector={"ids": ["f1"]},
                        options={"find": "old", "replace": "new"},
                    )
                )
            self.assertTrue(payload["ok"], payload)
            self.assertEqual(payload["matched"], 1)

    def test_text_action_requires_find(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            payload = json.loads(
                service.plan_bulk(
                    config,
                    LOGGER,
                    "docs",
                    "replace_text",
                    selector={"ids": ["f1"]},
                    options={"replace": "new"},
                )
            )
            self.assertFalse(payload["ok"])

    def test_sheets_rejects_non_integer_sheet_id(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(directory)
            payload = json.loads(
                service.plan_bulk(
                    config,
                    LOGGER,
                    "sheets",
                    "find_replace",
                    selector={"ids": ["f1"]},
                    options={"find": "a", "sheet_id": "not-a-number"},
                )
            )
            self.assertFalse(payload["ok"])



if __name__ == "__main__":
    unittest.main()
