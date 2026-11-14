"""End-to-end surface tests over the MCP in-memory transport."""

import asyncio
import json
import logging
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from workspace_operator.config import Config
from workspace_operator.server import create_server

LOGGER = logging.getLogger("test.server")


def config(profile: str, token_file: str = "missing-token.json", scope_routing: bool = False) -> Config:
    return Config(
        client_secrets_file="missing-secrets.json",
        token_file=token_file,
        backup_dir="missing-backups",
        log_file=None,
        mcp_auth_token="test-token",
        scopes=[],
        tool_profile=profile,
        scope_routing=scope_routing,
    )


class SurfaceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def _with_server(self, profile: str, assertions, token_file: str = "missing-token.json", scope_routing: bool = False):
        server = create_server(config(profile, token_file, scope_routing), LOGGER)
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
                async with ClientSession(client[0], client[1]) as session:
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

    async def test_confirmation_error_is_protocol_error(self):
        async def check(session):
            result = await session.call_tool(
                "docs_edit", {"action": "replace", "document_id": "d", "find": "x", "replace": "y"}
            )
            self.assertTrue(result.is_error)
            self.assertIn("confirm", result.content[0].text.lower())

        await self._with_server("full", check)

    async def test_direct_destructive_requires_confirm(self):
        async def check(session):
            result = await session.call_tool("drive_trash", {"file_id": "f"})
            self.assertTrue(result.is_error)
            self.assertIn("confirm", result.content[0].text.lower())

        await self._with_server("core", check)


    async def test_unknown_action_is_reported(self):
        async def check(session):
            result = await session.call_tool("drive_read", {"action": "explode"})
            self.assertTrue(result.is_error)
            self.assertIn("Unknown action", result.content[0].text)

        await self._with_server("core", check)


if __name__ == "__main__":
    unittest.main()
