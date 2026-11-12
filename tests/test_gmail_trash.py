"""Tests for the Gmail trash behaviour (no permanent delete with gmail.modify)."""

import logging
import unittest
from unittest import mock

from workspace_operator.config import Config
from workspace_operator.handlers import gmail as gmail_module

LOGGER = logging.getLogger("test.gmail")
CONFIG = Config(
    client_secrets_file="secrets.json",
    token_file="token.json",
    backup_dir="backups",
    log_file=None,
    mcp_auth_token="token",
    scopes=[],
)


def fake_service():
    service = mock.MagicMock()
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "snippet": "test message"
    }
    service.users.return_value.messages.return_value.trash.return_value.execute.return_value = {}
    service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}
    service.users.return_value.messages.return_value.delete.return_value.execute.return_value = {}
    service.users.return_value.messages.return_value.batchDelete.return_value.execute.return_value = {}
    return service


class DeleteEmailTests(unittest.TestCase):
    def test_confirm_required_does_not_touch_mail(self):
        service = fake_service()
        with mock.patch.object(gmail_module, "get_creds", return_value=None), mock.patch.object(
            gmail_module, "build", return_value=service
        ):
            text = gmail_module.delete_email_handler(CONFIG, LOGGER, "m1", confirm=False)
        self.assertIn("CONFIRMATION REQUIRED", text)
        service.users.return_value.messages.return_value.trash.assert_not_called()

    def test_delete_email_moves_to_trash(self):
        service = fake_service()
        with mock.patch.object(gmail_module, "get_creds", return_value=None), mock.patch.object(
            gmail_module, "build", return_value=service
        ):
            text = gmail_module.delete_email_handler(CONFIG, LOGGER, "m1", confirm=True)
        service.users.return_value.messages.return_value.trash.assert_called_once_with(
            userId="me", id="m1"
        )
        service.users.return_value.messages.return_value.delete.assert_not_called()
        self.assertIn("Trash", text)


class BatchDeleteTests(unittest.TestCase):
    def test_dry_run_does_not_modify(self):
        service = fake_service()
        with mock.patch.object(gmail_module, "get_creds", return_value=None), mock.patch.object(
            gmail_module, "build", return_value=service
        ):
            text = gmail_module.batch_delete_emails_handler(
                CONFIG, LOGGER, ["m1", "m2"], dry_run=True
            )
        service.users.return_value.messages.return_value.batchModify.assert_not_called()
        self.assertIn("DRY RUN", text)

    def test_batch_moves_to_trash_in_chunks(self):
        service = fake_service()
        ids = [f"m{index}" for index in range(1001)]
        with mock.patch.object(gmail_module, "get_creds", return_value=None), mock.patch.object(
            gmail_module, "build", return_value=service
        ):
            text = gmail_module.batch_delete_emails_handler(
                CONFIG, LOGGER, ids, dry_run=False
            )
        self.assertEqual(
            service.users.return_value.messages.return_value.batchModify.call_count, 2
        )
        first_body = service.users.return_value.messages.return_value.batchModify.call_args_list[0].kwargs["body"]
        self.assertEqual(first_body["addLabelIds"], ["TRASH"])
        self.assertEqual(len(first_body["ids"]), 1000)
        service.users.return_value.messages.return_value.batchDelete.assert_not_called()
        self.assertIn("1001", text)


if __name__ == "__main__":
    unittest.main()
