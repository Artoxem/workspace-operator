"""Engine tests for bulk jobs with a fake Google client (no network)."""

import logging
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from unittest import mock

from googleapiclient.errors import HttpError

from workspace_operator.bulk import engine, move, store
from workspace_operator.bulk.models import BulkError, Job, Plan
from workspace_operator.config import Config

LOGGER = logging.getLogger("test.bulk.engine")


class FakeRequest:
    def __init__(self, func):
        self._func = func

    def execute(self):
        return self._func()


class FakeFiles:
    """Records Drive file updates; optionally fails for chosen ids."""

    def __init__(self, fail_ids=(), delay=0.0, by_id=None):
        self.updates = []
        self.gets = []
        self.fail_ids = set(fail_ids)
        self.delay = delay
        self.by_id = by_id or {}
        self._lock = threading.Lock()

    def update(self, fileId, **kwargs):  # noqa: N803 - Google API naming
        def run():
            if self.delay:
                time.sleep(self.delay)
            if fileId in self.fail_ids:
                raise engine.BulkError("boom " + fileId)
            with self._lock:
                self.updates.append((fileId, kwargs))
            return {"id": fileId}

        return FakeRequest(run)

    def get(self, fileId, **kwargs):  # noqa: N803
        self.gets.append((fileId, kwargs))
        return FakeRequest(lambda: self.by_id[fileId])


class FakeDrive:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def make_config(directory: str, **overrides) -> Config:
    base = Config(
        client_secrets_file="secrets.json",
        token_file="token.json",
        backup_dir=os.path.join(directory, "backups"),
        log_file=None,
        mcp_auth_token="token",
        scopes=[],
        bulk_dir=directory,
        bulk_concurrency=2,
    )
    return replace(base, **overrides)


def make_plan(action="trash", count=3, domain="drive", options=None) -> Plan:
    return Plan(
        id="bp_test",
        domain=domain,
        action=action,
        options=options or {},
        selector={},
        created_at="2026-01-01T00:00:00+00:00",
        expires_at="2999-01-01T00:00:00+00:00",
        items=[
            {"id": f"id{i}", "name": f"f{i}.txt", "parents": ["root"], "trashed": False}
            for i in range(count)
        ],
    )


def wait_for(config, job_id, states=("completed", "failed", "cancelled"), timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.load_job(config, job_id)
        if job.state in states:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish: {store.load_job(config, job_id).state}")


class ApplyItemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    def _apply(self, files, item, action, options=None, domain="drive"):
        with mock.patch.object(engine, "_service", return_value=FakeDrive(files)):
            return engine._apply_item(self.config, item, action, options or {}, 1, LOGGER, domain)

    def test_trash_skips_already_trashed(self):
        files = FakeFiles()
        record = self._apply(files, {"id": "a", "name": "x", "trashed": True}, "trash")
        self.assertEqual(record["status"], "skipped")
        self.assertEqual(files.updates, [])

    def test_trash_updates_file(self):
        files = FakeFiles()
        record = self._apply(files, {"id": "a", "name": "x"}, "trash")
        self.assertEqual(record["status"], "ok")
        self.assertEqual(files.updates[0][1]["body"], {"trashed": True})

    def test_restore_only_when_trashed(self):
        files = FakeFiles()
        self.assertEqual(
            self._apply(files, {"id": "a", "name": "x", "trashed": False}, "restore")["status"],
            "skipped",
        )
        self.assertEqual(
            self._apply(files, {"id": "a", "name": "x", "trashed": True}, "restore")["status"],
            "ok",
        )

    def _move_context(self, parents, drive_id=None):
        destination = {"id": "dest", "name": "Target", "driveId": drive_id}
        item = {"id": "a", "name": "x", "parents": parents, "mimeType": "text/plain",
                "driveId": drive_id, "capabilities": {"canMoveItemWithinDrive": True}}
        options = {"target_folder_id": "dest", "move_destination": destination}
        files = FakeFiles(by_id={
            "a": dict(item),
            "dest": {**destination, "mimeType": move.FOLDER_MIME,
                     "capabilities": {"canAddChildren": True}},
        })
        return files, item, options

    def test_move_records_previous_parents_and_compares_without_order(self):
        files, item, options = self._move_context(["p1", "p2"])
        files.by_id["a"]["parents"] = ["p2", "p1"]
        record = self._apply(files, item, "move", options)
        self.assertEqual(record["previous_parents"], ["p1", "p2"])
        kwargs = files.updates[0][1]
        self.assertEqual(kwargs["addParents"], "dest")
        self.assertEqual(kwargs["removeParents"], "p1,p2")
        self.assertFalse(kwargs["supportsAllDrives"])

    def test_move_into_current_parent_is_skipped_only_after_live_checks(self):
        files, item, options = self._move_context(["dest"])
        self.assertEqual(self._apply(files, item, "move", options)["status"], "skipped")
        files.by_id["a"]["parents"] = ["unreviewed"]
        with self.assertRaisesRegex(BulkError, "source parent folders changed"):
            self._apply(files, item, "move", options)
        self.assertEqual(files.updates, [])

    def test_move_rejects_new_source_or_renamed_destination(self):
        files, item, options = self._move_context(["p1"])
        files.by_id["a"]["parents"] = ["p1", "p2"]
        with self.assertRaisesRegex(BulkError, "source parent folders changed"):
            self._apply(files, item, "move", options)
        files.by_id["dest"]["name"] = "Renamed target"
        with self.assertRaisesRegex(BulkError, "destination folder changed"):
            self._apply(files, item, "move", options)
        self.assertEqual(files.updates, [])

    def test_same_shared_drive_update_requires_opt_in(self):
        files, item, options = self._move_context(["p1"], "shared")
        with self.assertRaisesRegex(BulkError, "require bulk_allow_shared_drives"):
            self._apply(files, item, "move", options)
        self.assertEqual(files.updates, [])
        self.config = replace(self.config, bulk_allow_shared_drives=True)
        self.assertEqual(self._apply(files, item, "move", options)["status"], "ok")
        self.assertTrue(all(kwargs["supportsAllDrives"] for _, kwargs in files.gets + files.updates))
        files.by_id["a"]["driveId"] = "other"
        with self.assertRaisesRegex(BulkError, "different Drive locations"):
            self._apply(files, item, "move", options)
        self.assertEqual(len(files.updates), 1)

    def test_move_retry_revalidates_source_before_retrying_mutation(self):
        files, item, options = self._move_context(["p1"])

        def fail_after_source_has_changed(**kwargs):
            files.by_id["a"]["parents"] = ["unreviewed"]
            raise TimeoutError("ambiguous update outcome")

        with mock.patch.object(files, "update", side_effect=fail_after_source_has_changed) as update:
            with mock.patch.object(engine.time, "sleep"), self.assertRaisesRegex(BulkError, "source parent folders changed"):
                self._apply(files, item, "move", options)
        update.assert_called_once()

    def test_move_sends_if_match_when_drive_returns_an_etag(self):
        files, item, options = self._move_context(["p1"])
        get = files.get
        current = FakeRequest(lambda: files.by_id["a"])
        current.add_response_callback = lambda callback: callback({"etag": '"file-version"'})
        update = FakeRequest(lambda: {"id": "a"})
        update.headers = {}
        with mock.patch.object(files, "get", side_effect=lambda fileId, **kw: (
            current if fileId == "a" else get(fileId, **kw)
        )), mock.patch.object(files, "update", return_value=update):
            self.assertEqual(self._apply(files, item, "move", options)["status"], "ok")
        self.assertEqual(update.headers["If-Match"], '"file-version"')

    def test_move_requires_target(self):
        with self.assertRaises(BulkError):
            self._apply(FakeFiles(), {"id": "a", "name": "x"}, "move", {})

    def test_rename_records_previous_name_and_skips_noop(self):
        files = FakeFiles()
        record = self._apply(
            files, {"id": "a", "name": "old.txt"}, "rename", {"find": "old", "replace": "new"}
        )
        self.assertEqual(record["new_name"], "new.txt")
        self.assertEqual(record["previous_name"], "old.txt")
        noop = self._apply(
            files, {"id": "a", "name": "same.txt"}, "rename", {"find": "zzz", "replace": "y"}
        )
        self.assertEqual(noop["status"], "skipped")

    def test_unsupported_action_raises(self):
        with self.assertRaises(BulkError):
            self._apply(FakeFiles(), {"id": "a", "name": "x"}, "explode")

    def test_legacy_move_back_cannot_update_files(self):
        files = FakeFiles()
        with self.assertRaisesRegex(BulkError, "unsupported action"):
            self._apply(files, {"id": "a", "name": "x", "previous_parents": ["p1"]}, "move_back")
        self.assertEqual(files.updates, [])

    def test_rename_back_restores_previous_name(self):
        files = FakeFiles()
        files.get = lambda fileId, **kw: FakeRequest(lambda: {"name": "new.txt"})  # noqa: N803
        record = self._apply(
            files, {"id": "a", "name": "new.txt", "previous_name": "old.txt"}, "rename_back"
        )
        self.assertEqual(record["status"], "ok")
        self.assertEqual(files.updates[0][1]["body"], {"name": "old.txt"})

    def test_rename_back_requires_previous_name(self):
        with self.assertRaises(BulkError):
            self._apply(FakeFiles(), {"id": "a", "name": "x"}, "rename_back")


class WithRetryTests(unittest.TestCase):
    def _http_error(self, status):
        class Resp:
            pass

        resp = Resp()
        resp.status = status
        resp.reason = "x"
        return HttpError(resp, b"{}")

    def test_retries_transient_then_succeeds(self):
        calls = {"n": 0}

        def operation():
            calls["n"] += 1
            if calls["n"] < 3:
                raise self._http_error(503)
            return "ok"

        with mock.patch.object(engine.time, "sleep"):
            self.assertEqual(engine._with_retry(operation, LOGGER, attempts=3), "ok")
        self.assertEqual(calls["n"], 3)

    def test_non_retryable_status_is_raised_immediately(self):
        calls = {"n": 0}

        def operation():
            calls["n"] += 1
            raise self._http_error(404)

        with self.assertRaises(HttpError):
            engine._with_retry(operation, LOGGER, attempts=3)
        self.assertEqual(calls["n"], 1)

    def test_gives_up_after_attempts(self):
        def operation():
            raise self._http_error(500)

        with mock.patch.object(engine.time, "sleep"), self.assertRaises(HttpError):
            engine._with_retry(operation, LOGGER, attempts=2)


class RunJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    def _start(self, plan, files, **kwargs):
        patcher = mock.patch.object(engine, "_service", return_value=FakeDrive(files))
        patcher.start()
        self.addCleanup(patcher.stop)
        return engine.start_job(self.config, plan, LOGGER, **kwargs)

    def test_job_completes_and_counts(self):
        files = FakeFiles()
        job = self._start(make_plan(count=4), files)
        done = wait_for(self.config, job.id)
        self.assertEqual((done.state, done.total, done.done, done.ok, done.failed), ("completed", 4, 4, 4, 0))
        self.assertEqual(len(files.updates), 4)
        self.assertEqual(len(store.read_results(self.config, job.id)), 4)

    def test_one_failure_does_not_stop_the_job(self):
        files = FakeFiles(fail_ids={"id1"})
        job = self._start(make_plan(count=3), files)
        done = wait_for(self.config, job.id)
        self.assertEqual((done.ok, done.failed, done.state), (2, 1, "completed"))
        failed = [r for r in store.read_results(self.config, job.id) if r["status"] == "failed"]
        self.assertEqual([r["id"] for r in failed], ["id1"])
        self.assertIn("boom", failed[0]["error"])

    def test_on_finish_callback_runs_and_errors_are_swallowed(self):
        seen = []

        def callback(job):
            seen.append(job.state)
            raise RuntimeError("audit down")

        job = self._start(make_plan(count=1), FakeFiles(), on_finish=callback)
        wait_for(self.config, job.id)
        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(seen, ["completed"])

    def test_registry_is_cleaned_after_finish(self):
        job = self._start(make_plan(count=1), FakeFiles())
        wait_for(self.config, job.id)
        deadline = time.time() + 5
        while engine.is_live(job.id) and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(engine.is_live(job.id))

    def test_resume_skips_items_that_already_succeeded(self):
        plan = make_plan(count=3)
        job = Job(id="bj_resume", plan_id=plan.id, domain="drive", action="trash", total=3,
                  state="interrupted", started_at="2026-01-01T00:00:00+00:00")
        store.save_job(self.config, job)
        store.append_result(self.config, job.id, {"id": "id0", "name": "f0", "status": "ok"})
        store.append_result(self.config, job.id, {"id": "id1", "name": "f1", "status": "failed"})
        files = FakeFiles()
        resumed = self._start(plan, files, resume_job_id=job.id)
        done = wait_for(self.config, resumed.id)
        touched = sorted(update[0] for update in files.updates)
        # id0 succeeded earlier and must not be repeated; id1 (failed) and id2 are retried.
        self.assertEqual(touched, ["id1", "id2"])
        self.assertEqual(done.state, "completed")
        self.assertEqual(done.total, 3)

    def test_resume_rejects_changed_move_snapshot_even_if_plan_id_matches(self):
        plan = make_plan(action="move", count=1)
        job = Job(id="bj_move_resume", plan_id=plan.id, domain="drive", action="move", total=1,
                  state="interrupted", plan_digest=store.plan_digest(plan))
        store.save_job(self.config, job)
        plan.items[0]["parents"] = ["different-parent"]
        with self.assertRaisesRegex(BulkError, "exact move snapshot"):
            engine.start_job(self.config, plan, LOGGER, resume_job_id=job.id)

    def test_resume_rejects_finished_or_foreign_jobs(self):
        plan = make_plan()
        finished = Job(id="bj_done", plan_id=plan.id, domain="drive", action="trash", state="completed")
        store.save_job(self.config, finished)
        with self.assertRaises(BulkError):
            engine.start_job(self.config, plan, LOGGER, resume_job_id="bj_done")
        foreign = Job(id="bj_other", plan_id="bp_other", domain="drive", action="trash", state="failed")
        store.save_job(self.config, foreign)
        with self.assertRaises(BulkError):
            engine.start_job(self.config, plan, LOGGER, resume_job_id="bj_other")

    def test_cancel_marks_job_and_records_every_started_item(self):
        """Every item whose Google call ran must be in the result file, even on cancel.

        Otherwise resume would repeat it and undo would not know about it.
        """
        files = FakeFiles(delay=0.05)
        job = self._start(make_plan(count=12), files)
        time.sleep(0.12)
        engine.cancel_job(self.config, job.id)
        done = wait_for(self.config, job.id, states=("cancelled", "completed", "failed"))
        # let in-flight pool workers finish
        time.sleep(0.4)
        executed = {update[0] for update in files.updates}
        recorded = {r["id"] for r in store.read_results(self.config, job.id) if r["status"] == "ok"}
        self.assertEqual(done.state, "cancelled")
        self.assertLess(len(executed), 12, "cancel should have prevented some items")
        self.assertEqual(
            executed - recorded,
            set(),
            f"executed but not recorded (lost for resume/undo): {sorted(executed - recorded)}",
        )

    def test_cancel_unknown_or_finished_job(self):
        job = Job(id="bj_fin", plan_id="p", domain="drive", action="trash", state="completed")
        store.save_job(self.config, job)
        with self.assertRaises(BulkError):
            engine.cancel_job(self.config, "bj_fin")

    def test_cancel_marks_orphaned_running_job_interrupted(self):
        job = Job(id="bj_orphan", plan_id="p", domain="drive", action="trash", state="running")
        store.save_job(self.config, job)
        with self.assertRaises(BulkError):
            engine.cancel_job(self.config, "bj_orphan")
        self.assertEqual(store.load_job(self.config, "bj_orphan").state, "interrupted")


class GmailRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    class FakeGmail:
        def __init__(self, fail_first=False):
            self.calls = []
            self.fail_first = fail_first

        def users(self):
            return self

        def messages(self):
            return self

        def batchModify(self, userId, body):  # noqa: N802,N803
            def run():
                self.calls.append(body)
                if self.fail_first and len(self.calls) == 1:
                    raise RuntimeError("gmail down")
                return {}

            return FakeRequest(run)

    def _run(self, gmail, count):
        plan = Plan(
            id="bp_g", domain="gmail", action="archive", options={}, selector={},
            created_at="2026-01-01T00:00:00+00:00", expires_at="2999-01-01T00:00:00+00:00",
            items=[{"id": f"m{i}", "name": ""} for i in range(count)],
        )
        with mock.patch.object(engine, "build", return_value=gmail), mock.patch.object(
            engine, "get_creds", return_value=object()
        ):
            job = engine.start_job(self.config, plan, LOGGER)
            return wait_for(self.config, job.id)

    def test_archive_batches_by_1000(self):
        gmail = self.FakeGmail()
        done = self._run(gmail, 2500)
        self.assertEqual([len(call["ids"]) for call in gmail.calls], [1000, 1000, 500])
        self.assertTrue(all(call["removeLabelIds"] == ["INBOX"] for call in gmail.calls))
        self.assertEqual((done.ok, done.total, done.state), (2500, 2500, "completed"))

    def test_chunk_failure_is_isolated(self):
        gmail = self.FakeGmail(fail_first=True)
        done = self._run(gmail, 1500)
        self.assertEqual((done.failed, done.ok), (1000, 500))
        self.assertEqual(done.state, "completed")


if __name__ == "__main__":
    unittest.main()
