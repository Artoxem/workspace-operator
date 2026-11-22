import hashlib
import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from workspace_operator.handlers import files


class PreparedDriveUploadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.source = self.base / "report.txt"
        self.original = b"reviewed report\n"
        self.source.write_bytes(self.original)
        self.config = SimpleNamespace(upload_roots=[self.base], bulk_allow_shared_drives=False)
        self.logger = logging.getLogger(__name__)
        self.folder = {
            "id": "actual-folder-id",
            "name": "My Drive",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": True},
        }
        api_patcher = patch.object(files, "api_client")
        self.addCleanup(api_patcher.stop)
        api = api_patcher.start()
        self.drive = api.return_value.files.return_value
        self.drive.get.return_value.execute.return_value = self.folder
        self.drive.create.return_value.execute.return_value = {
            "id": "created-id", "name": "report.txt", "mimeType": "text/plain",
        }

    def prepare(self, **kwargs):
        # Round-trip through the same plain serialization used by approvals.
        review = files.prepare_drive_upload(self.config, str(self.source), **kwargs)
        return json.loads(json.dumps(review))

    def execute(self, review):
        return files.execute_prepared_drive_upload(self.config, self.logger, review)

    def test_default_root_and_source_fingerprint_are_reviewed(self):
        review = self.prepare()

        self.assertEqual(review["operation"], "upload")
        self.assertEqual(review["destination"], {"id": "actual-folder-id", "name": "My Drive"})
        self.assertEqual(review["items"], [{
            "id": str(self.source),
            "name": "report.txt",
            "sources": [{"id": str(self.source), "name": "report.txt"}],
            "size_bytes": len(self.original),
            "sha256": hashlib.sha256(self.original).hexdigest(),
            "mime_type": "text/plain",
            "conversion_mime_type": None,
        }])
        self.assertEqual(self.drive.get.call_args.kwargs["fileId"], "root")
        self.assertFalse(self.drive.get.call_args.kwargs["supportsAllDrives"])
        self.drive.create.assert_not_called()

    def test_shared_drive_upload_requires_explicit_policy_at_both_stages(self):
        self.folder.update(name="Shared reports", driveId="shared-drive-id")
        with self.assertRaisesRegex(ValueError, "bulk_allow_shared_drives"):
            self.prepare(parent_id="actual-folder-id")
        self.config.bulk_allow_shared_drives = True
        review = self.prepare(parent_id="actual-folder-id")
        self.config.bulk_allow_shared_drives = False
        self.assertIn("bulk_allow_shared_drives", self.execute(review))
        self.drive.create.assert_not_called()

    def test_shared_drive_and_conversion_use_the_reviewed_snapshot(self):
        self.config.bulk_allow_shared_drives = True
        self.folder.update(name="Shared reports", driveId="shared-drive-id")
        review = self.prepare(parent_id="actual-folder-id", name="Approved title", convert_to="docs")
        self.assertEqual(review["destination"]["drive_id"], "shared-drive-id")

        def create(**kwargs):
            # This occurs after the executor has verified the bytes, but before
            # the upload API reads them. Reopening the local path now is unsafe.
            self.source.write_bytes(b"changed after validation")
            media = kwargs["media_body"]
            self.assertEqual(media.getbytes(0, media.size()), self.original)
            self.assertEqual(media.mimetype(), "text/plain")
            self.assertFalse(media.resumable())
            return Mock(execute=Mock(return_value={"id": "created-id", "name": "Approved title"}))

        self.drive.create.side_effect = create
        self.assertIn("Uploaded Approved title", self.execute(review))
        self.assertTrue(self.drive.get.call_args.kwargs["supportsAllDrives"])
        self.assertEqual(self.drive.get.call_args.kwargs["fileId"], "actual-folder-id")
        self.assertTrue(self.drive.create.call_args.kwargs["supportsAllDrives"])
        self.assertEqual(self.drive.create.call_args.kwargs["body"], {
            "name": "Approved title",
            "parents": ["actual-folder-id"],
            "mimeType": "application/vnd.google-apps.document",
        })

    def test_content_changes_of_the_same_size_require_new_approval(self):
        review = self.prepare()
        self.source.write_bytes(b"x" * len(self.original))
        self.assertIn("Request a new upload approval", self.execute(review))
        self.drive.create.assert_not_called()

    def test_revoked_local_path_access_is_rechecked_at_execution(self):
        review = self.prepare()
        self.config.upload_roots = [self.base / "other"]
        self.assertIn("upload_roots", self.execute(review))
        self.drive.create.assert_not_called()

    def test_changed_destination_requires_new_approval(self):
        review = self.prepare()
        self.folder["name"] = "A different title"
        self.assertIn("Drive destination changed", self.execute(review))
        self.assertEqual(self.drive.get.call_args.kwargs["fileId"], "actual-folder-id")
        self.drive.create.assert_not_called()

    def test_rejects_nonfolder_trashed_and_nonwritable_destinations(self):
        cases = [
            ({"mimeType": "text/plain"}, "non-trashed folder"),
            ({"trashed": True}, "non-trashed folder"),
            ({"capabilities": {"canAddChildren": False}}, "permission"),
        ]
        for change, message in cases:
            with self.subTest(change=change):
                self.drive.get.return_value.execute.return_value = {**self.folder, **change}
                with self.assertRaisesRegex(ValueError, message):
                    self.prepare()
        self.drive.create.assert_not_called()

    def test_secrets_and_size_limit_rejected_before_destination_lookup(self):
        self.config.token_file = str(self.source)
        with self.assertRaisesRegex(ValueError, "secrets file"):
            self.prepare()
        self.config.token_file = ""
        with patch.object(files, "MAX_TRANSFER_BYTES", len(self.original) - 1):
            with self.assertRaisesRegex(ValueError, "limit"):
                self.prepare()
        self.drive.get.assert_not_called()

    def test_larger_upload_uses_resumable_media_from_bounded_snapshot(self):
        with patch.object(files, "_RESUMABLE_UPLOAD_ABOVE_BYTES", len(self.original) - 1):
            review = self.prepare()

            def create(**kwargs):
                media = kwargs["media_body"]
                self.assertTrue(media.resumable())
                self.assertEqual(media.getbytes(0, media.size()), self.original)
                return Mock(execute=Mock(return_value={"id": "created-id", "name": "report.txt"}))

            self.drive.create.side_effect = create
            self.assertIn("Uploaded report.txt", self.execute(review))


if __name__ == "__main__":
    unittest.main()
