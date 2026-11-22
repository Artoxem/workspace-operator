"""Characterisation of every branch of the tool-call path (handle_call_tool).

Each scenario goes through the real MCP dispatcher and records what the client
sees (text, is_error) and what the audit log, the handler and the approval queue
saw. The snapshot was taken from the code before it was split into smaller
pieces, so the split cannot change behaviour.

Regenerate after an intentional change with:
    UPDATE_GOLDEN=1 python -m pytest tests/test_call_tool_branches.py
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import ClientSession, types
from mcp.shared.memory import create_client_server_memory_streams

import workspace_operator.server as server_module
from workspace_operator.approvals import ApprovalStore
from workspace_operator.bulk import store
from workspace_operator.bulk.models import Job, Plan
from workspace_operator.config import Config
from workspace_operator.operations import BinaryResult
from workspace_operator.results import ToolError, ToolResult

LOGGER = logging.getLogger("test.branches")
GOLDEN = Path(__file__).parent / "data" / "call_tool_branches.json"


def _config(tmp, **overrides):
    values = dict(
        client_secrets_file="s", token_file="t", backup_dir=tmp, log_file=None,
        mcp_auth_token="x", scopes=[], tool_profile="full", scope_routing=False,
        approval_dir=tmp, bulk_dir=tmp, retry_attempts=1, audit_log=str(Path(tmp) / "audit.jsonl"),
        approval_url="http://127.0.0.1:8765",
    )
    values.update(overrides)
    return Config(**values)


def _audit(tmp):
    path = Path(tmp) / "audit.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row.pop("ts", None)
        row["duration_ms"] = "int" if isinstance(row.get("duration_ms"), int) else row.get("duration_ms")
        rows.append(row)
    return rows


def _normalise(text):
    """Make ids and timestamps stable."""
    text = re.sub(r"apr_[0-9a-f]+", "apr_ID", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:+]+", "TIMESTAMP", text)
    return text


class _Transient(Exception):
    """A transient Google error: status 503, which call_with_retry retries."""

    status_code = 503


def _save_bulk_plan(config, plan_id):
    store.save_plan(config, Plan(plan_id, "drive", "trash", {}, {},
                                "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))


async def _call(tool, arguments, *, profile="full", config_overrides=None, handler=None,
                elicitation=None, binary=False, raises=None, flaky=0, approve_first=False):
    tmp = tempfile.mkdtemp()
    cfg = _config(tmp, tool_profile=profile, **(config_overrides or {}))
    if tool == "bulk_run":
        _save_bulk_plan(cfg, arguments["plan_id"])
    calls = []
    attempts = {"n": 0}

    def default_handler(config, logger, *args):
        calls.append(list(args))
        if flaky:
            attempts["n"] += 1
            if attempts["n"] <= flaky:
                raise _Transient()
        if raises:
            raise raises
        if binary:
            return BinaryResult(uri="x://pdf", mime_type="application/pdf", data=b"%PDF-1.4 data")
        return handler if handler is not None else "OK-RESULT"

    patches = [mock.patch.object(server_module, name, default_handler) for name in (
        "delete_file_handler", "get_metadata_handler", "drive_search_advanced_handler",
        "calendar_delete_event_handler", "list_emails_handler",
    )]
    for patch in patches:
        patch.start()
    try:
        server = server_module.create_server(cfg, LOGGER)
        async with create_client_server_memory_streams() as (client, srv):
            task = asyncio.create_task(
                server.run(srv[0], srv[1], server.create_initialization_options(), raise_exceptions=False)
            )
            try:
                async with ClientSession(client[0], client[1], elicitation_callback=elicitation) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments)
                    if approve_first:
                        record_id = re.search(r"apr_[0-9a-f]+", result.content[0].text).group(0)
                        ApprovalStore(cfg).approve(record_id)
                        result = await session.call_tool(tool, dict(arguments, approval_id=record_id))
                    outcome = {
                        "is_error": bool(result.is_error),
                        "content": [
                            _normalise(c.text) if getattr(c, "type", "") == "text"
                            else {"type": c.type, "mime": c.resource.mime_type, "blob": c.resource.blob}
                            for c in result.content
                        ],
                        "audit": _audit(tmp),
                        "handler_calls": calls,
                        "approvals_created": len(list(Path(tmp).glob("apr_*.json"))),
                    }
                    return outcome
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    finally:
        for patch in patches:
            patch.stop()


async def _accept(_context, params):
    return types.ElicitResult(action="accept", content={"approve": True})


async def _decline(_context, params):
    return types.ElicitResult(action="decline")


async def _cancel(_context, params):
    return types.ElicitResult(action="cancel")


async def _accept_without_flag(_context, params):
    return types.ElicitResult(action="accept", content={"approve": False})


SCENARIOS = {
    "ok_direct_tool": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}),
    "ok_default_profile_core": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, profile="core"),
    "no_arguments_at_all": dict(tool="drive_read", arguments=None),
    "missing_required_argument": dict(tool="drive_read", arguments={"action": "metadata"}),
    "unknown_action": dict(tool="drive_read", arguments={"action": "explode"}),
    "missing_action": dict(tool="drive_read", arguments={"file_id": "F"}),
    "legacy_alias_with_action": dict(tool="drive_get_metadata", arguments={"file_id": "F"}),
    "legacy_alias_direct_target": dict(tool="drive_search_advanced", arguments={"query": "x"}),
    "legacy_alias_hidden_by_profile": dict(tool="drive_remove_permission", arguments={"file_id": "f", "permission_id": "p"}, profile="core"),
    "removed_tool": dict(tool="slides_create", arguments={"title": "x"}),
    "outside_profile_unknown": dict(tool="totally_unknown", arguments={}),
    "outside_profile_read_only": dict(tool="drive_write", arguments={"action": "rename", "file_id": "f", "name": "n"}, profile="read-only"),
    "dry_run_read_runs": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, config_overrides={"dry_run": True}),
    "dry_run_write_is_preview": dict(tool="drive_write", arguments={"action": "rename", "file_id": "f", "name": "n"}, config_overrides={"dry_run": True}),
    "dry_run_destructive_is_preview": dict(tool="drive_trash", arguments={"file_id": "f"}, config_overrides={"dry_run": True}),
    # A non-destructive write needs no approval; it reaches the handler, which here fails on
    # missing credentials. Pins that the unconfigured-client error is reported as an error.
    "write_reaches_handler_without_credentials": dict(tool="drive_write", arguments={"action": "rename", "file_id": "f", "name": "n"}),
    "destructive_challenge": dict(tool="drive_trash", arguments={"file_id": "f"}),
    "destructive_challenge_no_url": dict(tool="drive_trash", arguments={"file_id": "f"}, config_overrides={"approval_url": None}),
    "destructive_wrong_approval_id": dict(tool="drive_trash", arguments={"file_id": "f", "approval_id": "apr_missing"}),
    "elicitation_accept": dict(tool="drive_trash", arguments={"file_id": "f"}, elicitation=_accept),
    "elicitation_decline": dict(tool="drive_trash", arguments={"file_id": "f"}, elicitation=_decline),
    "elicitation_cancel": dict(tool="drive_trash", arguments={"file_id": "f"}, elicitation=_cancel),
    "elicitation_accept_unchecked": dict(tool="drive_trash", arguments={"file_id": "f"}, elicitation=_accept_without_flag),
    "approved_by_id_runs_handler_with_confirm": dict(tool="drive_trash", arguments={"file_id": "f"}, approve_first=True),
    "retries_transient_errors_then_succeeds": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, config_overrides={"retry_attempts": 3}, flaky=2),
    "gives_up_after_configured_attempts": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, config_overrides={"retry_attempts": 2}, flaky=5),
    "bulk_run_challenge": dict(tool="bulk_run", arguments={"plan_id": "bp_x", "confirm": True}),
    "calendar_delete_challenge": dict(tool="calendar_delete", arguments={"event_id": "e"}),
    "handler_error_string": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler="Error reading file: <HttpError 404 when requesting x returned \"Not Found\">"),
    "handler_error_string_indented": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler="  Error: quota"),
    "handler_text_starting_with_error_word": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler="Errors found: 0"),
    "handler_binary_result": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, binary=True),
    "handler_raises": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, raises=RuntimeError("boom")),
    # New contract: explicit signals instead of guessing from the text.
    "handler_raises_tool_error": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, raises=ToolError("Quota exceeded for today.")),
    "handler_result_marked_error": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler=ToolResult("boom", is_error=True)),
    "handler_result_success_despite_error_word": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler=ToolResult("Error codes: none. All good.", is_error=False)),
    "handler_non_string_result": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, handler=12345),
    "missing_auth_token": dict(tool="drive_read", arguments={"action": "metadata", "file_id": "F"}, config_overrides={"mcp_auth_token": None}),
}


def snapshot():
    out = {}
    for name, spec in SCENARIOS.items():
        spec = dict(spec)
        out[name] = asyncio.run(_call(spec.pop("tool"), spec.pop("arguments"), **spec))
    return out


class CallToolBranchTests(unittest.TestCase):
    def test_every_branch_matches_snapshot(self):
        current = snapshot()
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(current, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(sorted(current), sorted(expected))
        for name in sorted(expected):
            self.assertEqual(
                json.loads(json.dumps(current[name], sort_keys=True)), expected[name],
                f"behaviour changed for scenario '{name}'",
            )


class BulkAuditCallbackTests(unittest.TestCase):
    """The bulk finish callbacks write a duration and a status to the audit log."""

    def _callbacks(self, tmp):
        captured = {}

        def fake_bulk_run(config, logger, plan_id, confirm, on_finish, job_id, *, plan_snapshot):
            if plan_snapshot.id != plan_id or not confirm:
                raise ValueError("Missing approved snapshot")
            captured["run"] = on_finish
            return "{}"

        def fake_bulk_undo(config, logger, job_id, confirm, on_finish):
            captured["undo"] = on_finish
            return "{}"

        async def go():
            cfg = _config(tmp)
            _save_bulk_plan(cfg, "bp_x")
            with mock.patch.object(server_module, "bulk_run_handler", fake_bulk_run), mock.patch.object(
                server_module, "bulk_undo_handler", fake_bulk_undo
            ):
                server = server_module.create_server(cfg, LOGGER)
                async with create_client_server_memory_streams() as (client, srv):
                    task = asyncio.create_task(
                        server.run(srv[0], srv[1], server.create_initialization_options(), raise_exceptions=False)
                    )
                    try:
                        async with ClientSession(client[0], client[1], elicitation_callback=_accept) as session:
                            await session.initialize()
                            args = {"plan_id": "bp_x", "confirm": True}
                            challenge = await session.call_tool("bulk_run", args)
                            record_id = re.search(r"apr_[0-9a-f]+", challenge.content[0].text).group(0)
                            ApprovalStore(cfg).approve(record_id)
                            await session.call_tool("bulk_run", dict(args, approval_id=record_id))
                            await session.call_tool("bulk_undo", {"job_id": "bj", "confirm": True})
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

        asyncio.run(go())
        return captured

    def _job(self, state, started="2026-01-01T00:00:00+00:00", finished="2026-01-01T00:00:02+00:00", error=None):
        return Job(id="bj", plan_id="bp", domain="drive", action="trash", state=state,
                   started_at=started, finished_at=finished, error=error)

    def test_callbacks_record_status_duration_and_tool_name(self):
        tmp = tempfile.mkdtemp()
        callbacks = self._callbacks(tmp)
        before = len(_audit(tmp))  # the two tool calls themselves are audited too
        callbacks["run"](self._job("completed"))
        callbacks["run"](self._job("cancelled"))
        callbacks["undo"](self._job("failed", error="x"))
        callbacks["run"](self._job("completed", started="not-a-date", finished=None))
        raw = [
            json.loads(line)
            for line in (Path(tmp) / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        ][before:]
        self.assertEqual(
            [(r["tool"], r["status"], r.get("error")) for r in raw],
            [
                ("bulk_run", "ok", None),
                ("bulk_run", "cancelled", None),
                ("bulk_undo", "error", "x"),
                ("bulk_run", "ok", None),
            ],
        )
        self.assertEqual(raw[0]["duration_ms"], 2000)
        self.assertEqual(raw[3]["duration_ms"], 0)  # unparseable start time -> 0, never an exception
        self.assertEqual(sorted(raw[0]["arguments"]), ["confirm", "job_id", "plan_id"])


if __name__ == "__main__":
    unittest.main()
