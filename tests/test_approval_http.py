"""Tests for the browser approval page (no Google calls)."""

import tempfile
import unittest

from mcp.server import Server
from starlette.testclient import TestClient

from workspace_operator.approvals import ApprovalStore
from workspace_operator.config import Config
from workspace_operator.http_transport import HttpOptions, build_asgi_app


class ApprovalPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = Config(
            client_secrets_file="x",
            token_file="x",
            backup_dir="x",
            log_file=None,
            mcp_auth_token="t",
            scopes=[],
            approval_dir=self.tmp.name,
        )
        self.store = ApprovalStore(config)
        self.record = self.store.request("drive_trash", None, {"file_id": "f1"})
        app = build_asgi_app(
            Server("test"),
            HttpOptions(tokens={"default": "t"}),
            "test",
            approval_store=self.store,
            approval_url="http://127.0.0.1:8765",
        )
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def _k(self):
        # The human obtains the secret through the link; rotating mints a fresh one.
        link = self.store.human_link(self.record["id"], "http://127.0.0.1:8765")
        return link.split("?k=", 1)[1]

    def test_page_shows_summary_and_approves(self):
        rid, k = self.record["id"], self._k()
        page = self.client.get(f"/approvals/{rid}?k={k}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("drive_trash", page.text)
        self.assertIn("Approve", page.text)
        self.assertEqual(page.headers["referrer-policy"], "no-referrer")

        response = self.client.post(
            f"/approvals/{rid}/approve", data={"k": k}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.store.get(rid)["status"], "approved")

    def test_page_denies(self):
        rid = self.record["id"]
        self.client.post(
            f"/approvals/{rid}/deny", data={"k": self._k()}, follow_redirects=False
        )
        self.assertEqual(self.store.get(rid)["status"], "denied")

    def test_page_without_secret_is_hidden(self):
        rid = self.record["id"]
        self.assertEqual(self.client.get(f"/approvals/{rid}").status_code, 404)
        self.assertEqual(self.client.get(f"/approvals/{rid}?k=wrong").status_code, 404)

    def test_post_without_secret_is_rejected(self):
        rid = self.record["id"]
        for data in ({}, {"k": "wrong"}):
            response = self.client.post(
                f"/approvals/{rid}/approve", data=data, follow_redirects=False
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store.get(rid)["status"], "pending")

    def test_cross_origin_post_is_rejected(self):
        rid = self.record["id"]
        response = self.client.post(
            f"/approvals/{rid}/approve",
            data={"k": self._k()},
            headers={"Origin": "http://evil.example"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store.get(rid)["status"], "pending")

    def test_unknown_page(self):
        self.assertEqual(self.client.get("/approvals/apr_missing?k=x").status_code, 404)

    def test_secret_not_in_agent_challenge(self):
        from workspace_operator.approvals import challenge_text

        k = self._k()
        text = challenge_text(self.store.get(self.record["id"]), "http://127.0.0.1:8765")
        self.assertNotIn(k, text)

    def test_human_link_rotation_invalidates_old_link(self):
        rid = self.record["id"]
        old = self._k()
        new = self._k()
        self.assertNotEqual(old, new)
        self.assertEqual(self.client.get(f"/approvals/{rid}?k={old}").status_code, 404)
        self.assertEqual(self.client.get(f"/approvals/{rid}?k={new}").status_code, 200)

    def test_forged_status_in_file_is_rejected(self):
        import json
        from pathlib import Path

        rid = self.record["id"]
        path = Path(self.tmp.name) / f"{rid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "approved"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(Exception):
            self.store.get(rid)
        self.assertEqual(self.client.get(f"/approvals/{rid}?k=x").status_code, 404)


if __name__ == "__main__":
    unittest.main()
