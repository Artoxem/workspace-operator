"""Files that tests and the package need must actually be in the repository.

A bare ``data/`` rule in .gitignore once matched ``tests/data/`` as well, so every
golden snapshot passed locally and was missing from a fresh clone (CI failed).
These checks ask git itself, so they also catch a future ignore rule.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git")


def _git(*args):
    return subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [GIT, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


@unittest.skipUnless(GIT and (ROOT / ".git").exists(), "needs a git checkout")
class RepositoryFilesTests(unittest.TestCase):
    def _must_not_be_ignored(self, paths):
        ignored = [
            path for path in paths
            # --no-index: judge the rules alone. Without it git reports a file that is
            # already staged or tracked as "not ignored", which hides the very mistake
            # this test exists to catch.
            if _git("check-ignore", "--quiet", "--no-index", path).returncode == 0
        ]
        self.assertEqual(ignored, [], f"git would ignore files the project needs: {ignored}")

    def test_golden_snapshots_are_not_ignored(self):
        files = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "tests" / "data").glob("*"))
        self.assertTrue(files, "tests/data is empty")
        self._must_not_be_ignored(files)

    def test_package_data_files_are_not_ignored(self):
        files = sorted(
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in (ROOT / "workspace_operator" / "definitions").glob("*.json")
        )
        self.assertTrue(files)
        self._must_not_be_ignored(files)

    def test_runtime_state_stays_ignored(self):
        """The top-level data/ holds audit logs and approvals and must never be committed."""
        for path in ("data/audit.jsonl", "data/approvals/apr_1.json", "data/bulk/jobs/x.json"):
            with self.subTest(path=path):
                self.assertEqual(
                    _git("check-ignore", "--quiet", "--no-index", path).returncode, 0, path
                )

    def test_secrets_stay_ignored(self):
        for path in (".env", "config.yaml", "token.json"):
            with self.subTest(path=path):
                self.assertEqual(
                    _git("check-ignore", "--quiet", "--no-index", path).returncode, 0, path
                )

    def test_every_snapshot_a_test_reads_is_tracked(self):
        """Tracked, not just present: git ls-files is what a clone receives."""
        tracked = set(_git("ls-files", "tests/data").stdout.split())
        on_disk = {f"tests/data/{p.name}" for p in (ROOT / "tests" / "data").glob("*")}
        # files staged for the next commit count as tracked
        staged = set(_git("diff", "--cached", "--name-only").stdout.split())
        self.assertEqual(on_disk - tracked - staged, set(), "snapshot files missing from git")


if __name__ == "__main__":
    unittest.main()
