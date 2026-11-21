"""End-to-end checks that an agent cannot release its own destructive call.

Calls go through a real MCP session (in-memory transport). ``handler_calls`` counts
how many times the destructive handler actually ran.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_call_tool_branches import _call, _config
from workspace_operator.approvals import ApprovalStore

TOOL = "drive_trash"
ARGS = {"file_id": "f1"}


def run(coro):
    return asyncio.run(coro)


class AgentCannotSelfApproveTests(unittest.TestCase):
    def test_first_call_never_runs_the_handler(self):
        outcome = run(_call(TOOL, ARGS))
        self.assertEqual(outcome["handler_calls"], [])
        self.assertEqual(outcome["approvals_created"], 1)
        self.assertIn("APPROVAL REQUIRED", outcome["content"][0])

    def test_agent_retry_with_its_own_id_does_not_run(self):
        """The agent receives an id and retries it itself, without a human approval."""
        outcome = run(_call(TOOL, dict(ARGS, approval_id="apr_0000000000000000")))
        self.assertEqual(outcome["handler_calls"], [])

    def test_approved_call_runs_exactly_once(self):
        outcome = run(_call(TOOL, ARGS, approve_first=True))
        self.assertEqual(len(outcome["handler_calls"]), 1)

    def test_forged_status_on_disk_cannot_release_the_call(self):
        """Agent with file access flips status to 'approved' by hand."""
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        path = Path(tmp) / f"{record['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "approved"
        path.write_text(json.dumps(data), encoding="utf-8")
        ok, reason = store.consume(record["id"], TOOL, None, ARGS)
        self.assertFalse(ok)
        self.assertIn("integrity", reason)

    def test_guessed_seal_does_not_release_the_call(self):
        """Without the on-disk key, a forged record cannot be re-sealed."""
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        path = Path(tmp) / f"{record['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "approved"
        data["seal"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
        ok, _ = store.consume(record["id"], TOOL, None, ARGS)
        self.assertFalse(ok)

    def test_approval_is_bound_to_arguments(self):
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, {"file_id": "f1"})
        store.approve(record["id"])
        ok, reason = store.consume(record["id"], TOOL, None, {"file_id": "f2"})
        self.assertFalse(ok)
        self.assertIn("changed", reason)

    def test_approval_is_one_time(self):
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        store.approve(record["id"])
        self.assertTrue(store.consume(record["id"], TOOL, None, ARGS)[0])
        ok, reason = store.consume(record["id"], TOOL, None, ARGS)
        self.assertFalse(ok)
        self.assertIn("already used", reason)

    def test_denied_call_never_runs(self):
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        store.deny(record["id"])
        ok, reason = store.consume(record["id"], TOOL, None, ARGS)
        self.assertFalse(ok)
        self.assertIn("denied", reason)

    def test_secret_never_reaches_the_agent(self):
        outcome = run(_call(TOOL, ARGS))
        visible = " ".join(str(c) for c in outcome["content"])
        self.assertNotIn("?k=", visible)
        self.assertNotIn("secret", visible.lower())

    def test_agent_result_has_no_decision_path(self):
        """The agent reads a pending result with no way to decide it itself."""
        outcome = run(_call(TOOL, ARGS))
        visible = " ".join(str(c) for c in outcome["content"])
        for forbidden in ("approvals link", "approvals approve", "approvals deny", "/approvals/", "?k="):
            self.assertNotIn(forbidden, visible)

    def test_operator_log_gets_the_link_not_the_agent(self):
        """The decision link is announced to the server log (operator), not returned."""
        import logging

        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        captured = []

        class Capture(logging.Handler):
            def emit(self, rec):
                captured.append(rec.getMessage())

        logger = logging.getLogger("test.operator-announce")
        logger.addHandler(Capture())
        logger.setLevel(logging.WARNING)

        from workspace_operator.tool_router import ToolRouter

        router = ToolRouter.__new__(ToolRouter)
        router.approvals = store
        router.logger = logger
        router.config = _config(tmp, approval_url="http://127.0.0.1:8765")
        router._announce_to_operator(record)

        joined = "\n".join(captured)
        self.assertIn(record["id"], joined)
        self.assertIn("/approvals/", joined)
        self.assertIn("?k=", joined)

    def test_link_rotation_kills_previous_link(self):
        tmp = tempfile.mkdtemp()
        store = ApprovalStore(_config(tmp, tool_profile="full"))
        record = store.request(TOOL, None, ARGS)
        first = store.human_link(record["id"], "http://127.0.0.1:8765").split("?k=")[1]
        second = store.human_link(record["id"], "http://127.0.0.1:8765").split("?k=")[1]
        self.assertFalse(store.verify_secret(record["id"], first))
        self.assertTrue(store.verify_secret(record["id"], second))


if __name__ == "__main__":
    unittest.main()
