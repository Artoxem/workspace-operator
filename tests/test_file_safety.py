import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from workspace_operator.handlers.files import (
    check_upload_allowed,
    resolve_target,
    safe_filename,
)


class SafeFilenameTests(unittest.TestCase):
    def test_strips_directories(self):
        self.assertEqual(safe_filename("../../evil.txt"), "evil.txt")
        self.assertEqual(safe_filename("..\\..\\evil.txt"), "evil.txt")
        self.assertEqual(safe_filename("C:\\Windows\\evil.txt"), "evil.txt")
        self.assertEqual(safe_filename("/etc/passwd"), "passwd")

    def test_invalid_characters_and_empty(self):
        self.assertEqual(safe_filename('a<b>c:d?.txt'), "a_b_c_d_.txt")
        self.assertEqual(safe_filename(""), "download")
        self.assertEqual(safe_filename(".."), "download")
        self.assertEqual(safe_filename(None), "download")

    def test_reserved_windows_names(self):
        self.assertNotEqual(safe_filename("CON.txt").upper(), "CON.TXT")
        self.assertNotEqual(safe_filename("nul"), "nul")

    def test_length_limit(self):
        self.assertLessEqual(len(safe_filename("a" * 500 + ".txt")), 200)


class ResolveTargetTests(unittest.TestCase):
    def test_traversal_stays_in_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            for name in ("../../evil.txt", "..\\evil.txt", "C:\\x\\evil.txt", "/abs/evil.txt"):
                target = resolve_target(str(base) + "/", name)
                self.assertEqual(target.parent.resolve(), base, name)
                self.assertEqual(target.name, "evil.txt")

    def test_default_directory(self):
        target = resolve_target(None, "../../evil.txt")
        self.assertEqual(target.name, "evil.txt")
        self.assertEqual(target.parent.name, "Downloads")

    def test_explicit_file_path_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            wanted = Path(tmp) / "named.pdf"
            self.assertEqual(resolve_target(str(wanted), "ignored.txt"), wanted)


class UploadGuardTests(unittest.TestCase):
    def _config(self, **kwargs):
        defaults = dict(token_file="", client_secrets_file="", backup_dir="", upload_roots=None)
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_token_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "mytoken.json"
            token.write_text("{}")
            error = check_upload_allowed(token, self._config(token_file=str(token)))
            self.assertIn("protected", error)

    def test_secret_names_and_dotenv_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("token.json", ".env", ".env.local", "oauth.keys.json"):
                path = Path(tmp) / name
                path.write_text("x")
                self.assertIsNotNone(check_upload_allowed(path, self._config()), name)

    def test_plain_file_allowed_without_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.txt"
            path.write_text("x")
            self.assertIsNone(check_upload_allowed(path, self._config()))

    def test_upload_roots_enforced(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
            inside = Path(allowed) / "a.txt"
            outside = Path(other) / "b.txt"
            inside.write_text("x")
            outside.write_text("x")
            config = self._config(upload_roots=[allowed])
            self.assertIsNone(check_upload_allowed(inside, config))
            self.assertIn("upload_roots", check_upload_allowed(outside, config))


if __name__ == "__main__":
    unittest.main()
