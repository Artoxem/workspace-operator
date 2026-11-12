"""Unit tests for the Tasks, Forms and Postmaster handlers."""

import logging
import unittest
from unittest import mock

from workspace_operator.config import Config
from workspace_operator.handlers import forms as forms_module
from workspace_operator.handlers import postmaster as postmaster_module
from workspace_operator.handlers import tasks as tasks_module

LOGGER = logging.getLogger("test.services")
CONFIG = Config(
    client_secrets_file="secrets.json",
    token_file="token.json",
    backup_dir="backups",
    log_file=None,
    mcp_auth_token="token",
    scopes=[],
)


class TaskTests(unittest.TestCase):
    def test_list_lists(self):
        service = mock.MagicMock()
        service.tasklists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "list1", "title": "Work"}]
        }
        with mock.patch.object(tasks_module, "_service", return_value=service):
            text = tasks_module.tasks_list_lists_handler(CONFIG, LOGGER)
        self.assertIn("Work", text)
        self.assertIn("list1", text)

    def test_create_sends_due_and_notes(self):
        service = mock.MagicMock()
        service.tasks.return_value.insert.return_value.execute.return_value = {
            "id": "t1",
            "title": "Call",
        }
        with mock.patch.object(tasks_module, "_service", return_value=service):
            text = tasks_module.tasks_create_handler(
                CONFIG,
                LOGGER,
                "Call",
                notes="details",
                due="2026-11-20T00:00:00.000Z",
                tasklist_id="@default",
            )
        body = service.tasks.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["notes"], "details")
        self.assertEqual(body["due"], "2026-11-20T00:00:00.000Z")
        self.assertIn("t1", text)

    def test_complete_patches_status(self):
        service = mock.MagicMock()
        service.tasks.return_value.patch.return_value.execute.return_value = {
            "id": "t1",
            "title": "Call",
        }
        with mock.patch.object(tasks_module, "_service", return_value=service):
            tasks_module.tasks_complete_handler(CONFIG, LOGGER, "t1")
        body = service.tasks.return_value.patch.call_args.kwargs["body"]
        self.assertEqual(body["status"], "completed")


class FormTests(unittest.TestCase):
    def test_question_requests(self):
        requests = forms_module._question_requests(
            [{"title": "Name", "required": True}, {"title": "City"}], 3
        )
        self.assertEqual(requests[0]["createItem"]["location"]["index"], 3)
        self.assertEqual(requests[1]["createItem"]["location"]["index"], 4)
        self.assertTrue(
            requests[0]["createItem"]["item"]["questionItem"]["question"]["required"]
        )

    def test_answer_values(self):
        answer = {"textAnswers": {"answers": [{"value": "A"}, {"value": "B"}]}}
        self.assertEqual(forms_module._answer_values(answer), ["A", "B"])

    def test_list_responses_maps_question_titles(self):
        service = mock.MagicMock()
        service.forms.return_value.get.return_value.execute.return_value = {
            "items": [
                {
                    "title": "Name",
                    "questionItem": {"question": {"questionId": "q1"}},
                }
            ]
        }
        service.forms.return_value.responses.return_value.list.return_value.execute.return_value = {
            "responses": [
                {
                    "createTime": "2026-11-12T10:00:00Z",
                    "responseId": "r1",
                    "answers": {"q1": {"textAnswers": {"answers": [{"value": "Eugene"}]}}},
                }
            ]
        }
        with mock.patch.object(forms_module, "_service", return_value=service):
            text = forms_module.forms_list_responses_handler(CONFIG, LOGGER, "form1")
        self.assertIn("Name: Eugene", text)


class PostmasterTests(unittest.TestCase):
    def test_normalize_domain(self):
        self.assertEqual(
            postmaster_module._normalize_domain("domains/Example.COM"), "example.com"
        )

    def test_percent_and_date(self):
        self.assertEqual(postmaster_module._percent(0.0123), "1.23%")
        self.assertEqual(postmaster_module._percent(99.5), "99.50%")
        self.assertEqual(postmaster_module._percent(None), "n/a")
        self.assertEqual(
            postmaster_module._date_label(
                {"date": {"year": 2026, "month": 11, "day": 12}}
            ),
            "2026-11-12",
        )

    def test_stat_value(self):
        self.assertEqual(
            postmaster_module._stat_value({"value": {"doubleValue": 0.5}}), 0.5
        )
        self.assertEqual(
            postmaster_module._stat_value({"value": {"intValue": "7"}}), 7
        )


if __name__ == "__main__":
    unittest.main()
