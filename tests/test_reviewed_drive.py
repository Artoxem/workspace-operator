"""Read the Drive review through HTTP before allowing real MCP routing."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from workspace_operator import server
from workspace_operator.approvals import ApprovalStore
from workspace_operator.bulk import store
from workspace_operator.bulk.models import Plan
from workspace_operator.config import Config
from workspace_operator.http_transport import HttpOptions, build_asgi_app

BASE = "http://127.0.0.1:8765"
LOGGER = logging.getLogger(__name__)


def move_plan():
    return Plan(
        "bp_move", "drive", "move",
        {"target_folder_id": "target", "move_destination": {"id": "target", "name": "Archive", "driveId": None}},
        {}, "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00",
        [{"id": f"file_{i}", "name": f"<Report> {i}", "parents": ["source"], "driveId": None,
          "mimeType": "text/plain", "sources": [{"id": "source", "name": "Incoming"}]} for i in range(25)],
    )


def config_for(tmp_path, *, wait=0):
    return Config("x", "x", str(tmp_path), None, "t", [], approval_dir=str(tmp_path), bulk_dir=str(tmp_path),
                  approval_browser_wait=wait, scope_routing=False, tool_profile="full", approval_url=None)


def make_client(config, queue):
    return TestClient(build_asgi_app(server.create_server(config, LOGGER), HttpOptions(tokens={"default": "t"}),
                                     "test", approval_store=queue), base_url=BASE)


def call(client, name, arguments):
    response = client.post("/mcp", headers={"Authorization": "Bearer t", "Accept": "application/json, text/event-stream"},
                           json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200
    return response.json()["result"]


def browser_review(client, queue, *, check, action):
    record, = queue.list_pending()
    url = urlsplit(queue.browser_link(record, BASE))
    page = client.get(f"{url.path}?{url.query}")
    assert page.status_code == 200
    for text in (*check, "APPROVE", "DENY"):
        assert text in page.text
    if action:
        posted = client.post(f"{url.path}/{action}", data={"k": parse_qs(url.query)["k"][0]},
                             headers={"Origin": BASE}, follow_redirects=False)
        assert posted.status_code == 303
    return record["id"]


@pytest.mark.parametrize("operation", ["move", "upload"])
@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_reviewed_drive_call_waits_for_browser(tmp_path, operation, decision):
    config = config_for(tmp_path, wait=8)
    queue = ApprovalStore(config)
    requested = Event()
    original_request = ApprovalStore.request

    def signal_request(self, *args, **kwargs):
        record = original_request(self, *args, **kwargs)
        requested.set()
        return record

    snapshot = move_plan()
    store.save_plan(config, snapshot)
    upload = {"operation": "upload", "destination": {"id": "target", "name": "Archive"},
              "items": [{"id": "local-id", "name": "local.txt", "sources": [{"name": "source", "id": "local.txt"}],
                         "size_bytes": 4, "mime_type": "text/plain"}]}
    name, args, check = (
        ("bulk_run", {"plan_id": snapshot.id}, ("Archive", "Incoming", "and 15 more")) if operation == "move"
        else ("drive_write", {"action": "upload", "local_path": "local.txt"}, ("Archive", "local.txt", "4 B"))
    )
    with (make_client(config, queue) as client, ThreadPoolExecutor() as pool,
          mock.patch.object(ApprovalStore, "request", signal_request),
          mock.patch.object(server, "bulk_run_handler", return_value="MOVED") as move,
          mock.patch("workspace_operator.handlers.files.prepare_drive_upload", return_value=upload),
          mock.patch("workspace_operator.handlers.files.execute_prepared_drive_upload", return_value="UPLOADED") as execute):
        waiting = pool.submit(call, client, name, {**args, "confirm": True})
        assert requested.wait(5)
        move.assert_not_called()
        execute.assert_not_called()
        rid = browser_review(client, queue, check=check, action=decision)
        result = waiting.result(timeout=10)
        assert queue.get(rid)["status"] == ("used" if decision == "approve" else "denied")
        if decision == "deny":
            assert "denied" in result["content"][0]["text"]
            move.assert_not_called()
            execute.assert_not_called()
        elif operation == "move":
            move.assert_called_once()
            assert move.call_args.kwargs["plan_snapshot"] == snapshot
        else:
            execute.assert_called_once_with(config, mock.ANY, upload)


def test_restart_retry_rejects_modified_move_plan_and_old_route(tmp_path):
    config = config_for(tmp_path)
    queue = ApprovalStore(config)
    plan = move_plan()
    store.save_plan(config, plan)
    with make_client(config, queue) as client, mock.patch.object(server, "bulk_run_handler") as handler:
        for name, args in (("drive_write", {"action": "move"}), ("move_file", {})):
            retired = call(client, name, args)
            assert retired["isError"] and "No files were moved" in retired["content"][0]["text"]
        args = {"plan_id": plan.id, "confirm": True}
        call(client, "bulk_run", args)
        rid = browser_review(client, queue, check=("Incoming", "Archive"), action="approve")
        # Alter an execution field after approval. A valid-looking plan with the
        # same ID must still not use the previous decision.
        plan.items.pop()
        store.save_plan(config, plan)
        rejected = call(client, "bulk_run", {**args, "approval_id": rid})
        assert "changed after approval" in rejected["content"][0]["text"]
        handler.assert_not_called()


def test_reviewed_approval_is_only_consumed_once_across_store_instances(tmp_path):
    config = config_for(tmp_path)
    store1, store2 = ApprovalStore(config), ApprovalStore(config)
    review = {"operation": "upload", "destination": {"id": "target", "name": "Private"}, "items": []}
    record = store1.request("drive_write", "upload", {}, review=review)
    store1.approve(record["id"])
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda queue: queue.consume(record["id"], "drive_write", "upload", {}, review=review),
                                (store1, store2)))
    assert sum(ok for ok, _ in results) == 1


def test_draft_deletion_review_reaches_the_page(tmp_path):
    config = config_for(tmp_path, wait=8)
    queue = ApprovalStore(config)
    review = {
        "operation": "trash",
        "destination": {"id": "trash", "name": "Trash · recoverable 30 days"},
        "items": [{"id": "D1", "name": "Draft: quarterly plan", "mime_type": "message/rfc822",
                   "sources": [{"id": "drafts", "name": "Drafts"}]}],
    }
    requested = Event()
    original_request = ApprovalStore.request

    def signal_request(self, *args, **kwargs):
        record = original_request(self, *args, **kwargs)
        requested.set()
        return record

    with (make_client(config, queue) as client, ThreadPoolExecutor() as pool,
          mock.patch.object(ApprovalStore, "request", signal_request),
          mock.patch("workspace_operator.tool_router.prepare_review", return_value=(review, None)),
          mock.patch.object(server, "delete_draft_tool", return_value="DELETED") as handler):
        waiting = pool.submit(call, client, "gmail_delete", {"action": "draft", "draft_id": "D1"})
        assert requested.wait(5)
        handler.assert_not_called()
        rid = browser_review(client, queue, check=("quarterly plan", "Drafts", "Trash"), action="approve")
        waiting.result(timeout=10)
        assert queue.get(rid)["status"] == "used"
        handler.assert_called_once()


def test_signed_review_cannot_be_edited_on_disk(tmp_path):
    queue = ApprovalStore(config_for(tmp_path))
    review = {"operation": "upload", "destination": {"id": "target", "name": "Private"}, "items": []}
    record = queue.request("drive_write", "upload", {}, review=review)
    path = tmp_path / f"{record['id']}.json"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["review"]["destination"]["name"] = "Misleading title"
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert not queue.list_pending()
