"""Characterisation tests for MCP resources and prompts (fake Google clients).

Every resource URI and every prompt is called through the real MCP dispatcher with
``googleapiclient.discovery.build`` replaced by a recorder. The text a client gets
and the API calls that produced it are compared with a snapshot taken from the
code before it was split out of server.py, so the move cannot change behaviour.

Regenerate the snapshot after an intentional change with:
    UPDATE_GOLDEN=1 python -m pytest tests/test_resources_prompts.py
"""

import asyncio
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

import workspace_operator.prompts as prompts_module
import workspace_operator.resources as resources_module
import workspace_operator.server as server_module
from workspace_operator.config import Config

LOGGER = logging.getLogger("test.resources")
GOLDEN = Path(__file__).parent / "data" / "resources_prompts.json"


class Request:
    def __init__(self, record, name, kwargs, result):
        self._record, self._name, self._kwargs, self._result = record, name, kwargs, result

    def execute(self):
        self._record.append([self._name, _plain(self._kwargs)])
        return self._result(self._kwargs) if callable(self._result) else self._result


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


class Node:
    """A tiny fake of a Google API resource tree: any attribute path is callable."""

    def __init__(self, record, path, responses):
        self._record, self._path, self._responses = record, path, responses

    def __getattr__(self, name):
        return Node(self._record, self._path + (name,), self._responses)

    def __call__(self, *args, **kwargs):
        path = ".".join(self._path)
        if path in self._responses:
            return Request(self._record, path, kwargs, self._responses[path])
        return Node(self._record, self._path, self._responses)


def _fixtures():
    return {
        "files.list": {"files": [
            {"id": "f1", "name": "Plan.docx", "mimeType": "application/msword",
             "modifiedTime": "2026-01-02T10:00:00Z", "owners": [{"emailAddress": "a@x.com"}],
             "webViewLink": "https://x/f1"},
            {"id": "f2", "name": "NoOwner", "modifiedTime": "2026-01-03T10:00:00Z"},
        ]},
        "files.get": {"id": "f1", "name": "Plan.docx", "mimeType": "t", "size": "2048",
                      "createdTime": "2026-01-01T00:00:00Z", "modifiedTime": "2026-01-02T00:00:00Z",
                      "owners": [{"emailAddress": "a@x.com"}], "webViewLink": "https://x/f1"},
        "users.messages.list": {"messages": [{"id": "m1"}, {"id": "m2"}]},
        "users.messages.get": {"snippet": "  hello   world ", "payload": {"headers": [
            {"name": "From", "value": "Bob <bob@x.com>"}, {"name": "Subject", "value": "Hi"},
            {"name": "Date", "value": "Tue, 06 Jan 2026 09:30:00 +0000"}]}},
        "events.list": {"items": [
            {"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-01-07T09:00:00Z"},
             "end": {"dateTime": "2026-01-07T09:15:00Z"}, "attendees": [{"email": "a@x.com"}]},
            {"id": "e2", "start": {"date": "2026-01-08"}, "end": {"date": "2026-01-09"}},
        ]},
        "spreadsheets.get": {"properties": {"title": "Budget"}},
        "spreadsheets.values.get": {"values": [["a", "b"], [1, 2], ["x"]]},
        "documents.get": {"title": "Notes", "body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "Hello doc\n"}}]}}]}},
    }


def _big_sheet():
    """250 rows: more than the 200 the analyze prompt keeps."""
    fixtures = _fixtures()
    fixtures["spreadsheets.values.get"] = {"values": [[f"r{i}", i] for i in range(250)]}
    return fixtures


def _empty():
    return {key: {} for key in _fixtures()}


# (kind, name/uri, arguments)
CASES = [
    ("resource", "gdrive://recent", None),
    ("resource", "gmail://inbox", None),
    ("resource", "gcalendar://upcoming", None),
    ("resource", "gdrive://file/f1", None),
    ("resource", "gsheets://SHEET1/Data!A1:B3", None),
    ("resource", "gsheets://SHEET1", None),
    ("resource", "gdocs://DOC1", None),
    ("resource", "gdrive://file/", None),
    ("resource", "gsheets:///Sheet1", None),
    ("resource", "gdocs://", None),
    ("resource", "nope://x", None),
    ("prompt", "summarize_inbox", None),
    ("prompt", "summarize_inbox", {"query": "from:boss", "max_results": "500"}),
    ("prompt", "analyze_spreadsheet", {"spreadsheet_id": "S1", "range": "A1:B2"}),
    ("prompt", "analyze_spreadsheet", {"spreadsheet_id": "S1"}),
    ("prompt", "analyze_spreadsheet", {}),
    ("prompt", "plan_week", None),
    ("prompt", "plan_week", {"days_ahead": "3"}),
    ("prompt", "search_drive", {"query": "name contains 'x'", "limit": "999"}),
    ("prompt", "search_drive", {}),
    ("prompt", "weekly_review", None),
    ("prompt", "weekly_review", {"days_back": "0"}),
    ("prompt", "weekly_review", {"days_back": "3"}),
    ("prompt", "inbox_triage", None),
    ("prompt", "inbox_triage", {"query": "label:x", "max_results": "5"}),
    ("prompt", "compare_brief", {"spreadsheet_id": "S", "range_a": "A1:B2", "range_b": "D1:E2"}),
    ("prompt", "compare_brief", {"spreadsheet_id": "S", "range_a": "A1:B2"}),
    ("prompt", "nope", None),
]
BIG_CASES = [
    ("prompt", "analyze_spreadsheet", {"spreadsheet_id": "S1", "range": "A1:B250"}),
    ("resource", "gsheets://SHEET1/Data!A1:B250", None),
]
EMPTY_CASES = [c for c in CASES if c[1] in (
    "gdrive://recent", "gmail://inbox", "gcalendar://upcoming", "gsheets://SHEET1",
    "summarize_inbox", "analyze_spreadsheet", "plan_week", "search_drive")]


def _config(tmp):
    return Config(client_secrets_file="s", token_file="t", backup_dir=tmp, log_file=None,
                  mcp_auth_token="x", scopes=[], tool_profile="full", scope_routing=False,
                  approval_dir=tmp, bulk_dir=tmp, retry_attempts=1)


def _outcome(case, fixtures):
    """Run one case; return what the client saw and the API calls made."""
    kind, key, arguments = case
    record = []
    handler_calls = []

    def fake_build(api, version, **kwargs):
        record.append(["build", [api, version]])
        return Node(record, (), fixtures)

    def fake_digest(cfg, logger, *args):
        handler_calls.append(["digest_handler", list(args)])
        return "DIGEST-TEXT"

    def fake_search(cfg, logger, *args):
        handler_calls.append(["gmail_search_and_summarize_handler", list(args)])
        return "SEARCH-TEXT"

    def fake_compare(cfg, logger, *args):
        handler_calls.append(["compare_tables_handler", list(args)])
        return "DIFF-TEXT"

    tmp = tempfile.mkdtemp()

    async def run():
        server = server_module.create_server(_config(tmp), LOGGER)
        async with create_client_server_memory_streams() as (client, srv):
            task = asyncio.create_task(
                server.run(srv[0], srv[1], server.create_initialization_options(), raise_exceptions=False)
            )
            try:
                async with ClientSession(client[0], client[1]) as session:
                    await session.initialize()
                    try:
                        if kind == "resource":
                            result = await session.read_resource(key)
                            return {"ok": [[c.mime_type, getattr(c, "text", None)] for c in result.contents]}
                        result = await session.get_prompt(key, arguments)
                        return {"ok": {
                            "description": result.description,
                            "messages": [[m.role, m.content.text] for m in result.messages],
                        }}
                    except Exception as exc:  # noqa: BLE001 - the error text is part of the contract
                        return {"error": str(exc)}
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    import datetime as real

    class FrozenDatetime(real.datetime):
        @classmethod
        def now(cls, tz=None):
            return real.datetime(2026, 1, 5, 12, 0, tzinfo=real.timezone.utc)

    with mock.patch("googleapiclient.discovery.build", fake_build), mock.patch(
        "workspace_operator.auth.get_creds", lambda cfg: object()
    ), mock.patch.object(prompts_module, "digest_handler", fake_digest), mock.patch.object(
        prompts_module, "gmail_search_and_summarize_handler", fake_search
    ), mock.patch.object(prompts_module, "compare_tables_handler", fake_compare), mock.patch.object(
        prompts_module, "datetime", FrozenDatetime
    ), mock.patch.object(resources_module, "datetime", FrozenDatetime):
        outcome = asyncio.run(run())
    return {"case": [kind, key, arguments], "result": outcome, "api": record, "handlers": handler_calls}


def snapshot():
    full = [_outcome(case, _fixtures()) for case in CASES]
    empty = [_outcome(case, _empty()) for case in EMPTY_CASES]
    big = [_outcome(case, _big_sheet()) for case in BIG_CASES]
    return {"populated": full, "empty": empty, "big": big}


class ResourcesAndPromptsTests(unittest.TestCase):
    def test_behaviour_matches_snapshot(self):
        current = snapshot()
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(current, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for group in ("populated", "empty", "big"):
            self.assertEqual(len(current[group]), len(expected[group]))
            for got, want in zip(current[group], expected[group], strict=True):
                self.assertEqual(got, want, f"{group}: behaviour changed for {want['case']}")

    def test_listings_are_stable(self):
        async def run():
            tmp = tempfile.mkdtemp()
            server = server_module.create_server(_config(tmp), LOGGER)
            async with create_client_server_memory_streams() as (client, srv):
                task = asyncio.create_task(
                    server.run(srv[0], srv[1], server.create_initialization_options(), raise_exceptions=False)
                )
                try:
                    async with ClientSession(client[0], client[1]) as session:
                        await session.initialize()
                        resources = [str(r.uri) for r in (await session.list_resources()).resources]
                        templates = [t.uri_template for t in (await session.list_resource_templates()).resource_templates]
                        prompts = [p.name for p in (await session.list_prompts()).prompts]
                        return resources, templates, prompts
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        resources, templates, prompts = asyncio.run(run())
        self.assertEqual(resources, ["gdrive://recent", "gmail://inbox", "gcalendar://upcoming"])
        self.assertEqual(templates, ["gdrive://file/{file_id}", "gsheets://{spreadsheet_id}/{range}", "gdocs://{document_id}"])
        self.assertEqual(len(prompts), 7)


if __name__ == "__main__":
    unittest.main()
