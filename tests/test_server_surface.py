"""End-to-end surface tests over the MCP in-memory transport."""

import asyncio
import json
import logging
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import ClientSession, types
from mcp.shared.memory import create_client_server_memory_streams

import workspace_operator.server as server_module
from workspace_operator.approvals import ApprovalStore
from workspace_operator.config import Config
from workspace_operator.server import create_server

LOGGER = logging.getLogger("test.server")


def config(profile: str, token_file: str = "missing-token.json", scope_routing: bool = False, approval_dir: str = "data/approvals-test") -> Config:
    return Config(
        client_secrets_file="missing-secrets.json",
        token_file=token_file,
        backup_dir="missing-backups",
        log_file=None,
        mcp_auth_token="test-token",
        scopes=[],
        tool_profile=profile,
        scope_routing=scope_routing,
        approval_dir=approval_dir,
    )


class SurfaceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    async def _with_server(
        self,
        profile: str,
        assertions,
        token_file: str = "missing-token.json",
        scope_routing: bool = False,
        elicitation_callback=None,
    ):
        server = create_server(
            config(profile, token_file, scope_routing, self.tmp.name), LOGGER
        )
        async with create_client_server_memory_streams() as (client, srv):
            task = asyncio.create_task(
                server.run(
                    srv[0],
                    srv[1],
                    server.create_initialization_options(),
                    raise_exceptions=False,
                )
            )
            try:
                async with ClientSession(
                    client[0], client[1], elicitation_callback=elicitation_callback
                ) as session:
                    await session.initialize()
                    await assertions(session)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_core_lists_compact_surface(self):
        async def check(session):
            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            self.assertEqual(len(tools), 20)
            self.assertIn("workspace_search", names)
            self.assertNotIn("slides_create", names)
            self.assertNotIn("docs_edit", names)

        await self._with_server("core", check)

    async def test_scope_routing_hides_unfunded_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token.json"
            token.write_text(
                json.dumps(
                    {
                        "scopes": [
                            "https://www.googleapis.com/auth/drive",
                            "https://www.googleapis.com/auth/spreadsheets",
                        ]
                    }
                ),
                encoding="utf-8",
            )

            async def check(session):
                tools = (await session.list_tools()).tools
                names = {tool.name for tool in tools}
                self.assertIn("drive_read", names)
                self.assertIn("sheets_read", names)
                self.assertNotIn("gmail_read", names)
                self.assertNotIn("calendar_read", names)
                self.assertIn("bulk_plan", names)

            await self._with_server(
                "full", check, token_file=str(token), scope_routing=True
            )


    async def test_full_lists_consolidated_surface(self):
        async def check(session):
            tools = (await session.list_tools()).tools
            names = {tool.name for tool in tools}
            self.assertEqual(len(tools), 39)
            self.assertNotIn("drive_empty_trash", names)
            self.assertNotIn("drive_transfer_ownership", names)
            self.assertNotIn("drive_list_comments", names)

        await self._with_server("full", check)

    async def test_destructive_returns_approval_challenge(self):
        async def check(session):
            result = await session.call_tool(
                "docs_edit", {"action": "replace", "document_id": "d", "find": "x", "replace": "y"}
            )
            self.assertFalse(result.is_error)
            self.assertIn("APPROVAL REQUIRED", result.content[0].text)
            self.assertIn("approval_id", result.content[0].text)

        await self._with_server("full", check)

    async def test_direct_destructive_returns_approval_challenge(self):
        async def check(session):
            result = await session.call_tool("drive_trash", {"file_id": "f"})
            self.assertFalse(result.is_error)
            self.assertIn("APPROVAL REQUIRED", result.content[0].text)

        await self._with_server("core", check)

    async def test_legacy_alias_to_destructive_returns_challenge(self):
        async def check(session):
            result = await session.call_tool("drive_delete_file", {"file_id": "f"})
            self.assertFalse(result.is_error)
            self.assertIn("APPROVAL REQUIRED", result.content[0].text)

        await self._with_server("full", check)

    async def test_approved_call_executes_and_is_one_time(self):
        cfg = config("core", approval_dir=self.tmp.name)

        async def check(session):
            first = await session.call_tool("drive_trash", {"file_id": "f"})
            match = re.search(r"apr_[0-9a-f]+", first.content[0].text)
            self.assertIsNotNone(match)
            approval_id = match.group(0)
            ApprovalStore(cfg).approve(approval_id)
            with mock.patch.object(
                server_module, "delete_file_handler", return_value="DELETED"
            ):
                executed = await session.call_tool(
                    "drive_trash", {"file_id": "f", "approval_id": approval_id}
                )
                self.assertFalse(executed.is_error)
                self.assertIn("DELETED", executed.content[0].text)
                reused = await session.call_tool(
                    "drive_trash", {"file_id": "f", "approval_id": approval_id}
                )
                self.assertFalse(reused.is_error)
                self.assertIn("already used", reused.content[0].text.lower())

        await self._with_server("core", check)


    async def test_elicitation_accept_executes(self):
        seen = {}

        async def approve(_context, params):
            seen["message"] = params.message
            return types.ElicitResult(action="accept", content={"approve": True})

        async def check(session):
            with mock.patch.object(
                server_module, "delete_file_handler", return_value="DELETED"
            ) as handler:
                result = await session.call_tool("drive_trash", {"file_id": "f"})
                self.assertFalse(result.is_error)
                self.assertIn("DELETED", result.content[0].text)
                self.assertTrue(handler.called)
            self.assertIn("Approve", seen["message"])

        await self._with_server("core", check, elicitation_callback=approve)

    async def test_elicitation_decline_blocks(self):
        async def decline(_context, params):
            return types.ElicitResult(action="decline")

        async def check(session):
            with mock.patch.object(server_module, "delete_file_handler") as handler:
                result = await session.call_tool("drive_trash", {"file_id": "f"})
                self.assertFalse(result.is_error)
                self.assertIn("did not approve", result.content[0].text)
                handler.assert_not_called()

        await self._with_server("core", check, elicitation_callback=decline)

    async def test_approval_is_bound_to_arguments(self):
        cfg = config("core", approval_dir=self.tmp.name)

        async def check(session):
            first = await session.call_tool("drive_trash", {"file_id": "f1"})
            match = re.search(r"apr_[0-9a-f]+", first.content[0].text)
            self.assertIsNotNone(match)
            approval_id = match.group(0)
            ApprovalStore(cfg).approve(approval_id)
            changed = await session.call_tool(
                "drive_trash", {"file_id": "f2", "approval_id": approval_id}
            )
            self.assertFalse(changed.is_error)
            self.assertIn("changed", changed.content[0].text.lower())

        await self._with_server("core", check)

    async def test_legacy_alias_hidden_by_profile(self):
        async def check(session):
            result = await session.call_tool(
                "drive_remove_permission", {"file_id": "f", "permission_id": "p"}
            )
            self.assertTrue(result.is_error)
            self.assertIn("hidden", result.content[0].text.lower())

        await self._with_server("core", check)

    async def test_removed_tool_has_migration_error(self):
        async def check(session):
            result = await session.call_tool("slides_create", {"title": "x"})
            self.assertTrue(result.is_error)
            self.assertIn("removed", result.content[0].text.lower())

        await self._with_server("full", check)


    async def test_unknown_action_is_reported(self):
        async def check(session):
            result = await session.call_tool("drive_read", {"action": "explode"})
            self.assertTrue(result.is_error)
            self.assertIn("Unknown action", result.content[0].text)

        await self._with_server("core", check)


if __name__ == "__main__":
    unittest.main()
