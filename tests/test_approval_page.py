"""The approval page: compact review, full list, CSV manifest."""

import csv
import io

import pytest
from starlette.testclient import TestClient

from workspace_operator import server
from workspace_operator.approvals import ApprovalStore
from workspace_operator.config import Config
from workspace_operator.http_transport import HttpOptions, build_asgi_app

BASE = "http://127.0.0.1:8765"


def make_config(folder):
    return Config("x", "x", folder, None, "t", [], approval_dir=folder, scope_routing=False, tool_profile="full")


def move_review(count):
    groups = (("Inbox", 320), ("Scans 2025", 112), ("Loose", 68))
    items, index = [], 0
    for name, amount in groups:
        for _ in range(min(amount, count - index)):
            items.append(
                {
                    "id": f"ID-FILE-{index:04d}",
                    "name": f"File {index} — report.pdf",
                    "sources": [{"id": "SRC-" + name.replace(" ", "-"), "name": name}],
                    "size": 2048,
                }
            )
            index += 1
    items += [
        {"id": f"ID-FILE-{i:04d}", "name": f"File {i} — report.pdf",
         "sources": [{"id": "SRC-Loose", "name": "Loose"}], "size": 2048}
        for i in range(index, count)
    ]
    return {"operation": "move", "destination": {"id": "DEST", "name": "Archive 2026"}, "items": items}


@pytest.fixture()
def page(tmp_path):
    config = make_config(str(tmp_path))
    queue = ApprovalStore(config)
    app = build_asgi_app(server.create_server(config, __import__("logging").getLogger(__name__)),
                         HttpOptions(tokens={"default": "t"}), "test", approval_store=queue)
    with TestClient(app, base_url=BASE) as client:
        yield client, queue, config


def request_page(client, queue, record, query=""):
    link = queue.browser_link(record, BASE)
    secret = link.split("?k=", 1)[1]
    response = client.get(f"/approvals/{record['id']}?k={secret}{query}")
    assert response.status_code == 200
    return response, secret


def test_large_review_is_grouped_and_stays_small(page):
    client, queue, _ = page
    record = queue.request("bulk_run", None, {"plan_id": "bp_x"}, review=move_review(500))
    response, _ = request_page(client, queue, record)
    text = response.text
    assert "320 file(s) from <bdi>Inbox</bdi>" in text
    assert "and 310 more" in text
    assert "show all 500 files" in text
    assert len(text) < 20000, f"compact page grew to {len(text)} bytes"
    assert "ID-FILE-" not in text, "file ids must stay out of the page"
    assert "fingerprint" in text


def test_small_review_is_expanded(page):
    client, queue, _ = page
    review = move_review(1)
    record = queue.request("bulk_run", None, {"plan_id": "bp_x"}, review=review)
    response, _ = request_page(client, queue, record)
    assert "<details open>" in response.text


def test_full_list_is_paginated(page):
    client, queue, _ = page
    record = queue.request("bulk_run", None, {"plan_id": "bp_x"}, review=move_review(500))
    first, _ = request_page(client, queue, record, "&all=1")
    assert first.text.count("<tr><td class='name'>") == 100
    assert "page 1 / 5" in first.text
    last, _ = request_page(client, queue, record, "&all=1&page=5")
    assert last.text.count("<tr><td class='name'>") == 100
    assert "page 5 / 5" in last.text


def test_csv_manifest_has_every_row_and_needs_the_secret(page):
    client, queue, _ = page
    record = queue.request("bulk_run", None, {"plan_id": "bp_x"}, review=move_review(500))
    _, secret = request_page(client, queue, record)
    response = client.get(f"/approvals/{record['id']}/manifest.csv?k={secret}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 500
    assert rows[0]["id"] == "ID-FILE-0000"
    assert rows[0]["source_folders"] == "Inbox"
    assert rows[0]["destination"] == "Archive 2026"
    assert rows[0]["fingerprint"] == rows[-1]["fingerprint"]
    assert client.get(f"/approvals/{record['id']}/manifest.csv").status_code == 404
    assert client.get(f"/approvals/{record['id']}/manifest.csv?k=wrong").status_code == 404


def test_upload_review_shows_size_and_type_without_ids(page):
    client, queue, _ = page
    review = {
        "operation": "upload",
        "destination": {"id": "DEST", "name": "Inbox"},
        "items": [{
            "id": "/home/app/report.pdf", "name": "report.pdf",
            "sources": [{"id": "/home/app/report.pdf", "name": "report.pdf"}],
            "size_bytes": 4096, "mime_type": "application/pdf",
        }],
    }
    record = queue.request("drive_write", "upload", {}, review=review)
    response, _ = request_page(client, queue, record)
    assert "4 KB" in response.text
    assert "application/pdf" in response.text
    assert "/home/app/report.pdf" not in response.text
