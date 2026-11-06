"""Tests for the runtime layer: retry, audit log, parsing helpers."""

import json
import tempfile
import unittest
from pathlib import Path

from workspace_operator.runtime import (
    AuditLog,
    call_with_retry,
    is_transient,
    parse_bool,
    status_code,
)


class FakeError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = type("Resp", (), {"status": status})()


class RetryTests(unittest.TestCase):
    def test_status_code_from_resp(self):
        self.assertEqual(status_code(FakeError(429)), 429)

    def test_status_code_missing(self):
        self.assertIsNone(status_code(ValueError("nope")))

    def test_transient_detection(self):
        self.assertTrue(is_transient(FakeError(503)))
        self.assertFalse(is_transient(FakeError(404)))

    def test_retries_then_succeeds(self):
        attempts = {"count": 0}

        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise FakeError(503)
            return "ok"

        self.assertEqual(call_with_retry(flaky, attempts=3, base_delay=0.0), "ok")
        self.assertEqual(attempts["count"], 3)

    def test_gives_up_after_attempts(self):
        def always():
            raise FakeError(500)

        with self.assertRaises(FakeError):
            call_with_retry(always, attempts=2, base_delay=0.0)

    def test_non_transient_is_not_retried(self):
        attempts = {"count": 0}

        def broken():
            attempts["count"] += 1
            raise FakeError(404)

        with self.assertRaises(FakeError):
            call_with_retry(broken, attempts=3, base_delay=0.0)
        self.assertEqual(attempts["count"], 1)


class AuditTests(unittest.TestCase):
    def test_disabled_writes_nothing(self):
        audit = AuditLog(None)
        self.assertFalse(audit.enabled)
        audit.record("tool", "full", "ok", 1)  # must not raise

    def test_writes_jsonl_without_argument_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            audit = AuditLog(str(path))
            audit.record("find_files", "read-only", "ok", 12, ["query"])
            audit.record("send_email", "full", "error", 34, ["to"], error="boom")

            lines = path.read_text(encoding="utf-8").strip().splitlines()
            first = json.loads(lines[0])
            self.assertEqual(first["tool"], "find_files")
            self.assertEqual(first["arguments"], ["query"])
            self.assertNotIn("secret", lines[0])

            second = json.loads(lines[1])
            self.assertEqual(second["status"], "error")
            self.assertEqual(second["error"], "boom")


class ParseTests(unittest.TestCase):
    def test_truthy(self):
        for value in ("1", "true", "YES", "on", True):
            self.assertTrue(parse_bool(value))

    def test_falsey(self):
        for value in ("0", "false", "no", "", None, False):
            self.assertFalse(parse_bool(value))


if __name__ == "__main__":
    unittest.main()
