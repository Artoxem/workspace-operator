"""Golden test: how every tool/action reaches its handler.

Each of the 104 handlers is replaced by a recorder and called through the real
MCP dispatcher. The recorded positional arguments are compared to a snapshot
(tests/data/handler_dispatch.json), so the dispatch table can be refactored
without changing what any handler receives.

Regenerate the snapshot after an intentional change with:
    UPDATE_GOLDEN=1 python -m pytest tests/test_handler_dispatch.py

The "minimal" snapshot sends only the required arguments, so defaults and
``or {}`` fallbacks are pinned too.
"""

import asyncio
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import ClientSession, types
from mcp.shared.memory import create_client_server_memory_streams

import workspace_operator.server as server_module
from workspace_operator.config import Config
from workspace_operator.toolset import build_catalog

LOGGER = logging.getLogger("test.dispatch")
GOLDEN = Path(__file__).parent / "data" / "handler_dispatch.json"
GOLDEN_MINIMAL = Path(__file__).parent / "data" / "handler_dispatch_minimal.json"
SENTINEL = "<{key}>"


def _calls():
    """Yield (tool, action, legacy_handler, required, params) for every handler."""
    for spec in build_catalog(server_module._tools()):
        if spec.is_direct:
            yield spec.name, None, spec.legacy
        else:
            for action in spec.actions:
                yield spec.name, action.name, action.legacy


def _schema_keys(spec_name):
    catalog = {spec.name: spec for spec in build_catalog(server_module._tools())}
    return list((catalog[spec_name].input_schema.get("properties") or {}).keys())


def _required():
    """(tool, action) -> argument names the router insists on."""
    result = {}
    for spec in build_catalog(server_module._tools()):
        if spec.is_direct:
            result[(spec.name, None)] = list(spec.input_schema.get("required") or [])
        else:
            for action in spec.actions:
                result[(spec.name, action.name)] = list(action.required)
    return result


def _snapshot(approve: bool = True, minimal: bool = False):
    """Call every tool once and record what each handler received.

    With ``minimal`` only the required arguments are sent, so every default value and
    ``or {}`` fallback in the routing table is exercised.
    With ``approve`` the in-chat elicitation is accepted, so destructive actions run.
    Without it nothing is approved and destructive handlers must not be reached.
    """
    tmp = tempfile.mkdtemp()
    config = Config(
        client_secrets_file="s", token_file="t", backup_dir=tmp, log_file=None,
        mcp_auth_token="x", scopes=[], tool_profile="full", scope_routing=False,
        approval_dir=tmp, bulk_dir=tmp, retry_attempts=1,
    )
    calls = list(_calls())
    required = _required()
    recorded = {}

    def make_recorder(name):
        def recorder(cfg, logger, *args, **kwargs):
            recorded[name] = {
                "args": [a if isinstance(a, (str, int, float, bool, list, dict, type(None))) else "<callable>"
                         for a in args],
                "kwargs": sorted(kwargs),
            }
            return "ok"
        return recorder

    handler_names = {legacy for _, _, legacy in calls}
    # legacy name -> function name in server.py (taken from the dispatch table source)
    table = _handler_functions()
    patches = [mock.patch.object(server_module, table[name], make_recorder(name)) for name in handler_names]

    async def run():
        for patch in patches:
            patch.start()
        try:
            server = server_module.create_server(config, LOGGER)
            async with create_client_server_memory_streams() as (client, srv):
                task = asyncio.create_task(
                    server.run(srv[0], srv[1], server.create_initialization_options(), raise_exceptions=False)
                )
                try:
                    async with ClientSession(
                        client[0], client[1], elicitation_callback=_answer if approve else _decline
                    ) as session:
                        await session.initialize()
                        for tool, action, _legacy in calls:
                            keys = required[(tool, action)] if minimal else _schema_keys(tool)
                            arguments = {key: SENTINEL.format(key=key) for key in keys
                                         if key not in ("action",)}
                            arguments["confirm"] = True
                            arguments["approval_id"] = "apr_test"
                            if action:
                                arguments["action"] = action
                            await session.call_tool(tool, arguments)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            for patch in patches:
                patch.stop()

    asyncio.run(run())
    return recorded


async def _answer(_context, params):
    return types.ElicitResult(action="accept", content={"approve": True})


async def _decline(_context, params):
    return types.ElicitResult(action="decline")


def _handler_functions():
    """legacy handler name -> function name in workspace_operator.server."""
    from workspace_operator.dispatch import ROUTES

    return {name: function for name, (function, _params) in ROUTES.items()}


class HandlerDispatchTests(unittest.TestCase):
    def test_every_handler_is_reachable_and_receives_the_same_arguments(self):
        recorded = _snapshot()
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(sorted(recorded), sorted(expected), "handlers reached differ from the snapshot")
        for name in sorted(expected):
            self.assertEqual(recorded[name], expected[name], f"arguments changed for {name}")

    def test_defaults_and_fallbacks_are_unchanged(self):
        recorded = _snapshot(minimal=True)
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN_MINIMAL.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        expected = json.loads(GOLDEN_MINIMAL.read_text(encoding="utf-8"))
        self.assertEqual(sorted(recorded), sorted(expected))
        for name in sorted(expected):
            self.assertEqual(recorded[name], expected[name], f"default/fallback changed for {name}")

    def test_destructive_handlers_are_not_reached_without_approval(self):
        declined = _snapshot(approve=False)
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        catalog = {spec.name: spec for spec in build_catalog(server_module._tools())}
        destructive = {
            legacy for tool, action, legacy in _calls()
            if catalog[tool].safety.value == "destructive"
        }
        self.assertEqual(len(destructive), 14)
        self.assertEqual(destructive & set(declined), set(), "a destructive handler ran unapproved")
        self.assertEqual(set(declined), set(expected) - destructive, "non-destructive handlers must still run")

    def test_snapshot_covers_every_catalog_handler(self):
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(len(expected), 104)


if __name__ == "__main__":
    unittest.main()
