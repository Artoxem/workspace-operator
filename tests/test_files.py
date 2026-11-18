"""Tests for local ↔ Drive helpers (no network)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from workspace_operator.handlers.files import (
    EXPORT_FORMATS_BY_TYPE,
    EXPORT_MIME,
    conflict_message,
    default_download_dir,
    expand_path,
    resolve_target,
)


class PathTests(unittest.TestCase):
    def test_expands_home(self):
        self.assertEqual(expand_path("~/x.txt"), Path.home() / "x.txt")

    def test_makes_relative_absolute(self):
        self.assertTrue(expand_path("relative.txt").is_absolute())

    def test_expands_environment_variables(self):
        # Use a variable the test sets itself: TEMP exists on Windows only.
        with mock.patch.dict(os.environ, {"WO_TEST_DIR": "exports"}):
            expanded = expand_path("$WO_TEST_DIR/file.txt" if os.name != "nt" else "%WO_TEST_DIR%/file.txt")
        self.assertNotIn("WO_TEST_DIR", str(expanded))
        self.assertEqual(expanded.name, "file.txt")
        self.assertEqual(expanded.parent.name, "exports")


class TargetResolutionTests(unittest.TestCase):
    """Directory/file interpretation of save_to, on the platform's own path syntax."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_default_directory(self):
        self.assertEqual(
            resolve_target(None, "a.txt"), default_download_dir() / "a.txt"
        )

    def test_trailing_separator_means_directory(self):
        target = resolve_target(str(self.root / "exports") + os.sep, "a.txt")
        self.assertEqual(target.name, "a.txt")
        self.assertEqual(target.parent.name, "exports")

    def test_file_name_is_used_as_is(self):
        target = resolve_target(str(self.root / "exports" / "custom.txt"), "a.txt")
        self.assertEqual(target.name, "custom.txt")

    def test_directory_without_suffix_gets_filename(self):
        target = resolve_target(str(self.root / "exports"), "a.txt")
        self.assertEqual(target, self.root / "exports" / "a.txt")

    def test_existing_directory_gets_filename_even_with_a_suffix(self):
        folder = self.root / "release.v2"
        folder.mkdir()
        self.assertEqual(resolve_target(str(folder), "a.txt"), folder / "a.txt")

    @unittest.skipUnless(os.name == "nt", "Windows drive-letter paths")
    def test_windows_drive_paths(self):
        self.assertEqual(
            resolve_target("D:\\exports", "a.txt"), Path("D:\\exports\\a.txt")
        )
        self.assertEqual(resolve_target("D:\\exports\\", "a.txt").parent.name, "exports")
        self.assertEqual(resolve_target("D:\\exports\\custom.txt", "a.txt").name, "custom.txt")


class ConflictTests(unittest.TestCase):
    def test_message_mentions_path_and_flag(self):
        message = conflict_message(Path("D:/x/a.txt"))
        self.assertIn("a.txt", message)
        self.assertIn("overwrite=true", message)


class ExportTableTests(unittest.TestCase):
    def test_every_allowed_format_has_a_mime_type(self):
        for native, formats in EXPORT_FORMATS_BY_TYPE.items():
            with self.subTest(native=native):
                missing = formats - set(EXPORT_MIME)
                self.assertEqual(missing, set())

    def test_common_formats_present(self):
        for fmt in ("pdf", "docx", "xlsx", "csv"):
            self.assertIn(fmt, EXPORT_MIME)


if __name__ == "__main__":
    unittest.main()
