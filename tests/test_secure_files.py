import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from workspace_operator.cli import check_security
from workspace_operator.secure_files import (
    file_lock,
    is_protected,
    looks_like_secret_file,
    mask,
    write_private,
)


class WritePrivateTests(unittest.TestCase):
    def test_atomic_write_replaces_content_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token.json"
            write_private(target, "one")
            write_private(target, "two")
            self.assertEqual(target.read_text(encoding="utf-8"), "two")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["token.json"])

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_posix_mode_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token.json"
            write_private(target, "x")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


class FileLockTests(unittest.TestCase):
    def test_serialises_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "token.json"
            active = []
            overlaps = []

            def worker():
                with file_lock(target, timeout=10):
                    active.append(1)
                    if len(active) > 1:
                        overlaps.append(True)
                    threading.Event().wait(0.02)
                    active.pop()

            threads = [threading.Thread(target=worker) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(overlaps, [])
            self.assertFalse((Path(tmp) / "token.json.lock").exists())


class ProtectedPathTests(unittest.TestCase):
    def test_secret_names(self):
        for name in (
            "token.json", "token.json.bak-1", ".env", ".env.local", "service-account.json",
            "credentials.json", "client_secret_123.json", "server.pem", "id_rsa",
        ):
            self.assertTrue(looks_like_secret_file(Path(name)), name)
        self.assertFalse(looks_like_secret_file(Path("report.txt")))

    def test_configured_directories_are_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            approvals = Path(tmp) / "approvals"
            approvals.mkdir()
            record = approvals / "apr_1.json"
            record.write_text("{}")
            config = SimpleNamespace(
                token_file=str(Path(tmp) / "t.json"),
                client_secrets_file="",
                backup_dir="",
                approval_dir=str(approvals),
                bulk_dir="",
                audit_log="",
                log_file="",
            )
            self.assertTrue(is_protected(record, config))
            other = Path(tmp) / "notes.txt"
            other.write_text("x")
            self.assertFalse(is_protected(other, config))


class DoctorSecurityTests(unittest.TestCase):
    def test_flags_stray_files_and_config_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            google = Path(tmp)
            (google / "token.json").write_text("{}")
            (google / "oauth.keys.json").write_text("{}")
            (google / "service-account.json").write_text("{}")
            (google / "token.json.bak-1").write_text("{}")
            config = SimpleNamespace(
                token_file=str(google / "token.json"),
                client_secrets_file=str(google / "oauth.keys.json"),
                mcp_auth_token="abcdefghijklmnopqrstuvwxyz",
            )
            old = os.environ.pop("MCP_AUTH_TOKEN", None)
            try:
                checks = {c.name: c for c in check_security(config)}
            finally:
                if old is not None:
                    os.environ["MCP_AUTH_TOKEN"] = old
            self.assertFalse(checks["stray secret files"].ok)
            self.assertIn("service-account.json", checks["stray secret files"].detail)
            self.assertFalse(checks["auth token source"].ok)
            self.assertNotIn("abcdefghijklmnopqrstuvw", checks["auth token source"].detail)


class MaskTests(unittest.TestCase):
    def test_mask_keeps_tail_only(self):
        self.assertEqual(mask("abcdefgh"), "****efgh")
        self.assertEqual(mask(None), "(not set)")


if __name__ == "__main__":
    unittest.main()
