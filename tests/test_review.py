"""Reviews for deletion: what will go to Trash, from where, with which children."""

from unittest import mock

import pytest

from workspace_operator import review
from workspace_operator.config import Config


def make_config():
    return Config("x", "x", "b", None, "t", [])


def drive_files(meta, children=None, parent_names=None):
    files = mock.MagicMock()

    def get(fileId=None, **kwargs):
        result = mock.MagicMock()
        if fileId == meta["id"]:
            result.execute.return_value = meta
        else:
            result.execute.return_value = {
                "id": fileId,
                "name": (parent_names or {}).get(fileId, fileId),
            }
        return result

    files.get.side_effect = get
    listed = mock.MagicMock()
    listed.execute.return_value = children or {"files": []}
    files.list.return_value = listed
    return files


def patch_api(files=None, gmail=None):
    service = mock.MagicMock()
    if files is not None:
        service.files.return_value = files
    if gmail is not None:
        service.users.return_value.messages.return_value.get.return_value.execute.return_value = gmail
    return mock.patch("workspace_operator.review.api_client", return_value=service)


def test_file_review_names_it_and_its_folder():
    files = drive_files(
        {"id": "F1", "name": "Q3 report.pdf", "mimeType": "application/pdf", "size": "2048",
         "parents": ["P1"], "trashed": False},
        parent_names={"P1": "Reports"},
    )
    with patch_api(files=files):
        result = review.drive_trash_review(make_config(), "F1")
    assert result["operation"] == "trash"
    assert result["destination"]["id"] == "trash"
    item = result["items"][0]
    assert item["name"] == "Q3 report.pdf"
    assert item["sources"] == [{"id": "P1", "name": "Reports"}]
    assert "children" not in item


def test_folder_review_lists_its_children():
    files = drive_files(
        {"id": "D1", "name": "demo", "mimeType": review.FOLDER_MIME, "parents": ["ROOT"], "trashed": False},
        children={"files": [{"name": "a.pdf"}, {"name": "b.pdf"}, {"name": "c.pdf"}]},
        parent_names={"ROOT": "My Drive"},
    )
    with patch_api(files=files):
        item = review.drive_trash_review(make_config(), "D1")["items"][0]
    assert item["children"] == 3
    assert item["children_sample"] == ["a.pdf", "b.pdf", "c.pdf"]
    assert "children_at_least" not in item


def test_trashed_target_is_refused_before_approval():
    files = drive_files({"id": "F1", "name": "x", "mimeType": "text/plain", "trashed": True})
    with patch_api(files=files), pytest.raises(ValueError):
        review.drive_trash_review(make_config(), "F1")


def test_gmail_review_shows_subject_and_sender():
    message = {
        "id": "M1",
        "internalDate": "1700000000000",
        "payload": {"headers": [
            {"name": "Subject", "value": "Invoice 42"},
            {"name": "From", "value": "Acme <billing@acme.test>"},
        ]},
    }
    with patch_api(gmail=message):
        result = review.gmail_trash_review(make_config(), "M1")
    item = result["items"][0]
    assert item["name"] == "Invoice 42"
    assert item["sources"] == [{"id": "inbox", "name": "Acme <billing@acme.test>"}]


def test_prepare_review_routes_only_deletion_tools():
    with mock.patch.object(review, "drive_trash_review", return_value={"operation": "trash"}) as drive:
        assert review.prepare_review(make_config(), "drive_delete_file", {"file_id": "F"}, mock.MagicMock()) == (
            {"operation": "trash"}, None
        )
    drive.assert_called_once()
    with mock.patch.object(review, "gmail_trash_review", return_value={"operation": "trash"}) as gmail:
        review.prepare_review(make_config(), "delete_email", {"message_id": "M"}, mock.MagicMock())
    gmail.assert_called_once()
    assert review.prepare_review(make_config(), "drive_delete_file", {}, mock.MagicMock()) == (None, None)
    assert review.prepare_review(make_config(), "list_emails", {"message_id": "M"}, mock.MagicMock()) == (None, None)
