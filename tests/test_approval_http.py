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

    def test_page_shows_summary_and_approves(self):
        page = self.client.get(f"/approvals/{self.record['id']}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("drive_trash", page.text)
        self.assertIn("Approve", page.text)

        response = self.client.post(
            f"/approvals/{self.record['id']}/approve", follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.store.get(self.record["id"])["status"], "approved")

    def test_page_denies(self):
        self.client.post(f"/approvals/{self.record['id']}/deny", follow_redirects=False)
        self.assertEqual(self.store.get(self.record["id"])["status"], "denied")

    def test_unknown_page(self):
        self.assertEqual(self.client.get("/approvals/apr_missing").status_code, 404)


if __name__ == "__main__":
    unittest.main()
