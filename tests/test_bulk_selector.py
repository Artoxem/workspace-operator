"""Selector and service-facade tests with fake Drive/Gmail clients (no network)."""

import json
import logging
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from googleapiclient.errors import HttpError

from workspace_operator.bulk import move, selector, service, store
from workspace_operator.bulk.models import BulkError, Job
from workspace_operator.config import Config

LOGGER = logging.getLogger("test.bulk.selector")


class Req:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def execute(self):
        if self.error:
            raise self.error
        return self.value


def http_error(status=404):
    class Resp:
        pass

    resp = Resp()
    resp.status = status
    resp.reason = "x"
    return HttpError(resp, b"{}")


def meta(i, **extra):
    data = {"id": f"id{i}", "name": f"file{i}.txt", "parents": ["root"], "size": str(i),
            "mimeType": "text/plain", "trashed": False}
    data.update(extra)
    return data


class FakeDriveFiles:
    """list() serves pre-baked pages; get() serves metadata by id."""

    def __init__(self, pages=None, by_id=None):
        self.pages = list(pages or [])
        self.by_id = by_id or {}
        self.list_calls = []
        self.get_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        index = 0 if kwargs.get("pageToken") is None else int(kwargs["pageToken"])
        page = self.pages[index] if index < len(self.pages) else {"files": []}
        return Req(page)

    def get(self, fileId, **kwargs):  # noqa: N803
        self.get_calls.append((fileId, kwargs))
        if fileId in self.by_id:
            return Req(self.by_id[fileId])
        return Req(error=http_error(404))


class FakeDrive:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def resolve(files, selector_dict, max_items=10, **kwargs):
    with mock.patch.object(selector, "build", return_value=FakeDrive(files)):
        return selector.resolve_drive(
            object(), selector_dict, max_items=max_items, allow_shared_drives=False,
            logger=LOGGER, **kwargs
        )


class ResolveDriveTests(unittest.TestCase):
    def test_pagination_collects_all_pages(self):
        files = FakeDriveFiles(pages=[
            {"files": [meta(1), meta(2)], "nextPageToken": "1"},
            {"files": [meta(3)]},
        ])
        result = resolve(files, {"query": "name contains 'x'"})
        self.assertEqual([i["id"] for i in result["items"]], ["id1", "id2", "id3"])
        self.assertFalse(result["truncated"])
        self.assertEqual(len(files.list_calls), 2)

    def test_truncates_above_cap_and_warns(self):
        files = FakeDriveFiles(pages=[{"files": [meta(i) for i in range(1, 8)]}])
        result = resolve(files, {}, max_items=3)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(any("More than 3" in w for w in result["warnings"]))

    def test_protected_ids_and_patterns_are_skipped_and_reported(self):
        files = FakeDriveFiles(pages=[{"files": [
            meta(1), meta(2), meta(3, name="Contract-FINAL.pdf"), meta(4, name="tax.XLSX"),
        ]}])
        result = resolve(files, {}, protected_ids=["id1"], protected_patterns=["contract-*", "*.xlsx"])
        self.assertEqual([i["id"] for i in result["items"]], ["id2"])
        self.assertTrue(any("3 file(s) are protected" in w for w in result["warnings"]))

    def test_exclude_ids_and_duplicates(self):
        files = FakeDriveFiles(pages=[{"files": [meta(1), meta(1), meta(2)]}])
        result = resolve(files, {"exclude_ids": ["id2"]})
        self.assertEqual([i["id"] for i in result["items"]], ["id1"])

    def test_trashed_files_dropped_unless_requested(self):
        page = {"files": [meta(1), meta(2, trashed=True)]}
        self.assertEqual(len(resolve(FakeDriveFiles(pages=[page]), {})["items"]), 1)
        both = resolve(FakeDriveFiles(pages=[page]), {"include_trashed": True})
        self.assertEqual(len(both["items"]), 2)

    def test_explicit_ids_report_missing(self):
        files = FakeDriveFiles(by_id={"a": meta(1, id="a")})
        result = resolve(files, {"ids": ["a", "ghost"]})
        self.assertEqual([i["id"] for i in result["items"]], ["a"])
        self.assertTrue(any("1 id(s) could not be read" in w for w in result["warnings"]))

    def test_no_match_warns(self):
        result = resolve(FakeDriveFiles(pages=[{"files": []}]), {})
        self.assertTrue(any("No files matched" in w for w in result["warnings"]))

    def test_folder_scope_builds_parent_query(self):
        files = FakeDriveFiles(pages=[{"files": [meta(1)]}])
        resolve(files, {"folder_id": "F1"})
        self.assertIn("'F1' in parents", files.list_calls[0]["q"])

    def test_recursive_folder_tree_is_walked(self):
        class Tree(FakeDriveFiles):
            def list(self, **kwargs):
                q = kwargs.get("q", "")
                if "mimeType = 'application/vnd.google-apps.folder'" in q and "'root' in parents" in q:
                    return Req({"files": [{"id": "child"}]})
                if "mimeType = 'application/vnd.google-apps.folder'" in q:
                    return Req({"files": []})
                self.list_calls.append(kwargs)
                return Req({"files": [meta(1)]})

        files = Tree()
        resolve(files, {"folder_id": "root", "recursive": True})
        self.assertIn("'child' in parents", files.list_calls[0]["q"])
        self.assertIn("'root' in parents", files.list_calls[0]["q"])

    def test_item_from_handles_bad_size(self):
        self.assertEqual(selector._item_from({"id": "a", "size": "n/a"})["size"], 0)
        self.assertEqual(selector._item_from({"id": "a"})["size"], 0)


class FakeGmail:
    def __init__(self, pages, labels=None, fail_meta=False):
        self.pages, self.labels, self.fail_meta = pages, labels or [], fail_meta

    def users(self):
        return self

    def messages(self):
        return _Messages(self)

    def labels_api(self):
        return self


class _Messages:
    def __init__(self, gmail):
        self.g = gmail

    def list(self, **kwargs):
        index = 0 if kwargs.get("pageToken") is None else int(kwargs["pageToken"])
        return Req(self.g.pages[index] if index < len(self.g.pages) else {})

    def get(self, **kwargs):
        if self.g.fail_meta:
            return Req(error=http_error(500))
        return Req({"payload": {"headers": [{"name": "Subject", "value": "Hi"}]}})


class ResolveGmailTests(unittest.TestCase):
    def _resolve(self, gmail, selector_dict, max_items=10):
        with mock.patch.object(selector, "build", return_value=gmail):
            return selector.resolve_gmail(object(), selector_dict, max_items=max_items, logger=LOGGER)

    def test_query_pagination_and_sample(self):
        gmail = FakeGmail([{"messages": [{"id": "m1"}, {"id": "m2"}], "nextPageToken": "1"},
                           {"messages": [{"id": "m3"}]}])
        result = self._resolve(gmail, {"query": "from:x"})
        self.assertEqual([i["id"] for i in result["items"]], ["m1", "m2", "m3"])
        self.assertEqual(result["sample"][0]["subject"], "Hi")

    def test_truncation(self):
        gmail = FakeGmail([{"messages": [{"id": f"m{i}"} for i in range(8)]}])
        result = self._resolve(gmail, {}, max_items=3)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["items"]), 3)

    def test_explicit_ids_and_exclusions(self):
        result = self._resolve(FakeGmail([]), {"ids": ["a", "b", "a"], "exclude_ids": ["b"]})
        self.assertEqual([i["id"] for i in result["items"]], ["a"])

    def test_sample_survives_metadata_errors(self):
        gmail = FakeGmail([{"messages": [{"id": "m1"}]}], fail_meta=True)
        result = self._resolve(gmail, {})
        self.assertEqual(result["sample"][0]["subject"], "")

    def test_no_match_warns(self):
        result = self._resolve(FakeGmail([{}]), {})
        self.assertTrue(any("No messages matched" in w for w in result["warnings"]))


class ResolveLabelTests(unittest.TestCase):
    class Service:
        def users(self):
            return self

        def labels(self):
            return self

        def list(self, userId):  # noqa: N803
            return Req({"labels": [{"id": "Label_1", "name": "Invoices"}]})

    def _resolve(self, names):
        with mock.patch.object(selector, "build", return_value=self.Service()):
            return selector.resolve_gmail_labels(object(), names, LOGGER)

    def test_names_ids_and_system_labels(self):
        self.assertEqual(self._resolve(["invoices", "Label_1", "inbox"]), ["Label_1", "Label_1", "INBOX"])

    def test_unknown_label_is_an_error(self):
        with self.assertRaises(BulkError) as ctx:
            self._resolve(["Nope"])
        self.assertIn("Nope", str(ctx.exception))

    def test_empty_makes_no_api_call(self):
        with mock.patch.object(selector, "build", side_effect=AssertionError("no call")):
            self.assertEqual(selector.resolve_gmail_labels(object(), [], LOGGER), [])


def make_config(directory, **kw):
    base = Config(client_secrets_file="s", token_file="t", backup_dir=directory, log_file=None,
                  mcp_auth_token="x", scopes=[], bulk_dir=directory, bulk_max_items=5,
                  bulk_hard_limit=20)
    return replace(base, **kw)


class MovePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    @staticmethod
    def folder(folder_id, name, **extra):
        return {"id": folder_id, "name": name, "mimeType": move.FOLDER_MIME,
                "capabilities": {"canAddChildren": True}, **extra}

    def _plan(self, files, *, ids=None, target="dest", query_selector=None):
        with mock.patch.object(service, "get_creds", return_value=object()), mock.patch.object(
            service, "build", return_value=FakeDrive(files)
        ), mock.patch.object(selector, "build", return_value=FakeDrive(files)):
            return json.loads(service.plan_bulk(
                self.config, LOGGER, "drive", "move", {"ids": ids} if ids is not None else query_selector,
                {"target_folder_id": target}, sample=1,
            ))

    def test_full_review_includes_every_file_and_source_beyond_sample(self):
        files = FakeDriveFiles(by_id={
            "dest": self.folder("dest", "Project destination {} 東京"),
            "p1": self.folder("p1", "Spring"), "p2": self.folder("p2", "Summer"),
            "id1": meta(1, parents=["p1", "p2"]), "id2": meta(2, parents=["p2"]),
        })
        result = self._plan(files, ids=["id1", "id2"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["sample"]), 1)
        snapshot = store.load_plan(self.config, result["plan_id"])
        self.assertEqual(service.move_review(snapshot), {
            "operation": "move",
            "destination": {"id": "dest", "name": "Project destination {} 東京"},
            "items": [
                {"id": "id1", "name": "file1.txt", "sources": [
                    {"id": "p1", "name": "Spring"}, {"id": "p2", "name": "Summer"},
                ]},
                {"id": "id2", "name": "file2.txt", "sources": [{"id": "p2", "name": "Summer"}]},
            ],
        })
        self.assertEqual([file_id for file_id, _ in files.get_calls].count("p2"), 1)
        before = store.plan_digest(snapshot)
        snapshot.options = dict(reversed(list(snapshot.options.items())))
        self.assertEqual(store.plan_digest(snapshot), before)
        snapshot.items[1]["sources"][0]["name"] = "Changed"
        self.assertNotEqual(store.plan_digest(snapshot), before)

    def test_move_rejects_implicit_unreviewed_changes_and_uses_only_supplied_snapshot(self):
        files = FakeDriveFiles(by_id={
            "root": self.folder("actual-root", "My Drive"),
            "p1": self.folder("p1", "Source"), "id1": meta(1, parents=["p1"]),
        })
        result = self._plan(files, ids=["id1"], target="root")
        self.assertEqual(result["destination"], {"id": "actual-root", "name": "My Drive"})
        plan_id = result["plan_id"]
        plan = store.load_plan(self.config, plan_id)
        with mock.patch.object(service.engine, "start_job") as start:
            denied = json.loads(service.run_bulk(self.config, LOGGER, plan_id, confirm=True))
            self.assertFalse(denied["ok"], denied)
            self.assertIn("approved move snapshot", denied["error"])
            start.assert_not_called()
        changed = store.load_plan(self.config, plan_id)
        changed.items[0]["name"] = "replacement"
        store.save_plan(self.config, changed)
        job = Job(id="bj_job", plan_id=plan_id, domain="drive", action="move", total=1)
        with mock.patch.object(service.engine, "start_job", return_value=job) as start, mock.patch.object(
            store, "load_plan", side_effect=AssertionError("must not reread the persisted plan")
        ):
            started = json.loads(service.run_bulk(self.config, LOGGER, plan_id, confirm=True, plan_snapshot=plan))
        self.assertTrue(started["ok"], started)
        self.assertIs(start.call_args.args[1], plan)
        self.assertEqual(start.call_args.args[1].items[0]["name"], "file1.txt")

    def test_legacy_move_plan_without_complete_review_is_refused(self):
        files = FakeDriveFiles(by_id={
            "dest": self.folder("dest", "Destination"),
            "p1": self.folder("p1", "Source"), "id1": meta(1, parents=["p1"]),
        })
        result = self._plan(files, ids=["id1"])
        plan = store.load_plan(self.config, result["plan_id"])
        del plan.items[0]["sources"]
        with self.assertRaisesRegex(BulkError, "no valid complete review"):
            service.move_review(plan)

    def test_inaccessible_file_or_source_and_folder_items_fail_closed(self):
        files = FakeDriveFiles(by_id={
            "dest": self.folder("dest", "Destination"),
            "id1": meta(1, parents=["missing-source"]),
            "folder": self.folder("folder", "Folder"),
        })
        for ids, text in ((["id1"], "source folder"), (["id1", "unreadable"], "cannot be read"),
                          (["folder"], "not folders"), ([], "at least one eligible file")):
            with self.subTest(ids=ids):
                result = self._plan(files, ids=ids)
                self.assertFalse(result["ok"], result)
                self.assertIn(text, result["error"])
        self.assertEqual(files.list_calls, [], "explicit empty IDs must not select every file")

    def test_shared_drive_requires_opt_in_verified_context_and_capabilities(self):
        files = FakeDriveFiles(by_id={
            "dest": self.folder("dest", "Destination", driveId="shared"),
            "p1": self.folder("p1", "Source", driveId="shared"),
            "id1": meta(1, parents=["p1"], driveId="shared", capabilities={"canMoveItemWithinDrive": True}),
        })
        result = self._plan(files, ids=["id1"])
        self.assertFalse(result["ok"], result)
        self.assertIn("bulk_allow_shared_drives", result["error"])
        self.config = replace(self.config, bulk_allow_shared_drives=True)
        files.get_calls.clear()
        result = self._plan(files, ids=["id1"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(all(kwargs["supportsAllDrives"] for _, kwargs in files.get_calls))
        files.by_id["p1"]["driveId"] = "other"
        result = self._plan(files, ids=["id1"])
        self.assertIn("source folder is not in the same drive", result["error"])
        files.by_id["p1"]["driveId"] = "shared"
        files.by_id["id1"].pop("capabilities")
        result = self._plan(files, ids=["id1"])
        self.assertIn("does not allow moving", result["error"])
        for other_drive in (None, "other"):
            files.by_id["id1"]["driveId"] = other_drive
            result = self._plan(files, ids=["id1"])
            self.assertIn("different Drive locations", result["error"])
        files.by_id["id1"]["driveId"] = "shared"
        files.by_id["dest"].pop("capabilities")
        result = self._plan(files, ids=["id1"])
        self.assertIn("does not allow adding", result["error"])

    def test_shared_folder_scoped_query_targets_drive_and_excludes_folders(self):
        self.config = replace(self.config, bulk_allow_shared_drives=True)
        files = FakeDriveFiles(
            by_id={"dest": self.folder("dest", "Dest", driveId="d"), "src": self.folder("src", "Source", driveId="d")},
            pages=[{"files": [meta(1, parents=["src"], driveId="d", capabilities={"canMoveItemWithinDrive": True})]}],
        )
        result = self._plan(files, query_selector={"folder_id": "src"})
        self.assertTrue(result["ok"], result)
        scope = files.list_calls[0]
        self.assertEqual((scope["corpora"], scope["driveId"]), ("drive", "d"))
        self.assertIn("mimeType !=", scope["q"])


class FacadeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    def _job(self, state="completed", job_id="bj_x", **kw):
        job = Job(id=job_id, plan_id="bp", domain="drive", action="trash", state=state,
                  total=kw.pop("total", 4), **kw)
        store.save_job(self.config, job)
        return job

    def test_status_marks_orphaned_running_job_interrupted(self):
        self._job(state="running")
        data = json.loads(service.status_bulk(self.config, LOGGER, "bj_x"))
        self.assertEqual((data["state"], data["live"]), ("interrupted", False))
        self.assertEqual(store.load_job(self.config, "bj_x").state, "interrupted")

    def test_status_percent(self):
        self._job(done=1, total=4)
        self.assertEqual(json.loads(service.status_bulk(self.config, LOGGER, "bj_x"))["percent"], 25.0)

    def test_unknown_job_is_an_error_not_an_exception(self):
        for call in (service.status_bulk, service.result_bulk, service.cancel_bulk):
            data = json.loads(call(self.config, LOGGER, "bj_missing"))
            self.assertFalse(data["ok"])

    def test_result_paging(self):
        self._job()
        for i in range(5):
            store.append_result(self.config, "bj_x", {"id": f"i{i}", "status": "ok" if i else "failed"})
        page = json.loads(service.result_bulk(self.config, LOGGER, "bj_x", offset=0, limit=2))
        self.assertEqual((len(page["items"]), page["next_offset"], page["failures"]), (2, 2, 1))
        last = json.loads(service.result_bulk(self.config, LOGGER, "bj_x", offset=4, limit=50))
        self.assertIsNone(last["next_offset"])
        clamped = json.loads(service.result_bulk(self.config, LOGGER, "bj_x", offset=-5, limit=9999))
        self.assertEqual((clamped["offset"], clamped["limit"]), (0, 200))

    def test_list_jobs(self):
        self._job(job_id="bj_a")
        self._job(job_id="bj_b")
        ids = {j["job_id"] for j in json.loads(service.list_bulk(self.config, LOGGER))["jobs"]}
        self.assertEqual(ids, {"bj_a", "bj_b"})

    def test_run_refuses_empty_plan_and_plan_id_as_job_id(self):
        from workspace_operator.bulk.models import Plan

        empty = Plan(id="bp_e", domain="drive", action="trash", options={}, selector={},
                     created_at="2026-01-01T00:00:00+00:00", expires_at="2999-01-01T00:00:00+00:00")
        store.save_plan(self.config, empty)
        data = json.loads(service.run_bulk(self.config, LOGGER, "bp_e", confirm=True))
        self.assertIn("empty", data["error"])
        full = Plan(id="bp_f", domain="drive", action="trash", options={}, selector={},
                    created_at="2026-01-01T00:00:00+00:00", expires_at="2999-01-01T00:00:00+00:00",
                    items=[{"id": "a", "name": "a"}])
        store.save_plan(self.config, full)
        data = json.loads(service.run_bulk(self.config, LOGGER, "bp_f", confirm=True, job_id="bp_f"))
        self.assertIn("job_id must be a bulk job id", data["error"])

    def test_undo_refuses_dry_run_and_missing_confirm(self):
        self._job()
        dry = replace(self.config, dry_run=True)
        self.assertIn("dry_run", json.loads(service.undo_bulk(dry, LOGGER, "bj_x", confirm=True))["error"])
        self.assertIn("confirmation", json.loads(service.undo_bulk(self.config, LOGGER, "bj_x"))["error"])

    def test_plan_include_trashed_only_for_restore(self):
        data = json.loads(service.plan_bulk(self.config, LOGGER, "drive", "trash",
                                             selector={"include_trashed": True}))
        self.assertIn("only valid for restore", data["error"])

    def test_plan_limit_validation(self):
        for bad, text in (("abc", "integer"), (0, "positive"), (999, "exceeds the cap")):
            data = json.loads(service.plan_bulk(self.config, LOGGER, "drive", "trash",
                                                 selector={"limit": bad}))
            self.assertIn(text, data["error"])

    def test_plan_unknown_domain(self):
        self.assertIn("unsupported domain",
                      json.loads(service.plan_bulk(self.config, LOGGER, "nope", "trash"))["error"])

    def test_plan_end_to_end_saves_snapshot_with_sample(self):
        resolved = {"items": [{"id": f"i{n}", "name": f"n{n}", "size": 3, "mimeType": "t"} for n in range(3)],
                    "truncated": False, "warnings": []}
        with mock.patch.object(service, "get_creds", return_value=object()), mock.patch.object(
            service.selector_module, "resolve_drive", return_value=resolved
        ):
            data = json.loads(service.plan_bulk(self.config, LOGGER, "drive", "trash", sample=2))
        self.assertTrue(data["ok"])
        self.assertEqual((data["matched"], data["estimated_bytes"], len(data["sample"])), (3, 9, 2))
        self.assertEqual(len(store.load_plan(self.config, data["plan_id"]).items), 3)

    def test_plan_passes_protection_settings_to_selector(self):
        config = replace(self.config, bulk_protected_ids=["keep"], bulk_protected_patterns=["*.pdf"])
        resolved = {"items": [], "truncated": False, "warnings": []}
        with mock.patch.object(service, "get_creds", return_value=object()), mock.patch.object(
            service.selector_module, "resolve_drive", return_value=resolved
        ) as resolve_mock:
            service.plan_bulk(config, LOGGER, "drive", "trash")
        kwargs = resolve_mock.call_args.kwargs
        self.assertEqual((kwargs["protected_ids"], kwargs["protected_patterns"]), (["keep"], ["*.pdf"]))


if __name__ == "__main__":
    unittest.main()
