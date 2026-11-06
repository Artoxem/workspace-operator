"""Native Google Docs tables.

Building a document with tables through the Docs API is a two-phase process:

1. insert all blocks (text and empty tables) from the end of the body;
2. re-read the document, compute every cell's ``startIndex`` and fill the cells
   in **descending** index order so earlier indices never shift.

The index arithmetic is pure and unit-tested; only ``create_document_with_blocks``
talks to Google.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

MAX_ROWS = 200
MAX_COLUMNS = 20


def normalise_rows(rows: Sequence[Sequence[Any]], columns: int = 0) -> List[List[str]]:
    """Rectangular table with string cells and at least one column."""
    cleaned = [[clean_text(cell) for cell in row] for row in rows]
    width = columns or max((len(row) for row in cleaned), default=1)
    width = max(1, min(width, MAX_COLUMNS))
    return [row[:width] + [""] * (width - len(row)) for row in cleaned]


def table_dimensions(rows: Sequence[Sequence[str]]) -> Tuple[int, int]:
    height = max(1, min(len(rows), MAX_ROWS))
    width = max(1, min(len(rows[0]) if rows else 1, MAX_COLUMNS))
    return height, width


def cell_layout(table: Dict[str, Any]) -> List[Dict[str, int]]:
    """Return ``[{"row", "column", "start", "end"}]`` for every cell."""
    layout: List[Dict[str, int]] = []
    for row_index, row in enumerate(table.get("tableRows", [])):
        for column_index, cell in enumerate(row.get("tableCells", [])):
            content = cell.get("content") or [{}]
            start = content[0].get("startIndex")
            end = content[0].get("endIndex")
            if isinstance(start, int):
                layout.append(
                    {
                        "row": row_index,
                        "column": column_index,
                        "start": start,
                        "end": end if isinstance(end, int) else start,
                    }
                )
    return layout


def fill_requests(layout: Sequence[Dict[str, int]], rows: Sequence[Sequence[str]]) -> List[Dict[str, Any]]:
    """InsertText requests for non-empty cells, in descending index order."""
    entries: List[Tuple[int, str]] = []
    for cell in layout:
        row, column = cell["row"], cell["column"]
        if row >= len(rows) or column >= len(rows[row]):
            continue
        value = clean_text(rows[row][column])
        if value:
            entries.append((cell["start"], value))

    entries.sort(key=lambda item: item[0], reverse=True)
    return [
        {"insertText": {"location": {"index": index}, "text": value}}
        for index, value in entries
    ]


def header_style_requests(
    layout: Sequence[Dict[str, int]], rows: Sequence[Sequence[str]]
) -> List[Dict[str, Any]]:
    """Bold the first row after the cells are filled."""
    requests: List[Dict[str, Any]] = []
    for cell in layout:
        if cell["row"] != 0:
            continue
        column = cell["column"]
        if not rows or column >= len(rows[0]):
            continue
        text = rows[0][column]
        if not text:
            continue
        requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": cell["start"], "endIndex": cell["start"] + len(text)},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            }
        )
    return requests


def empty_paragraph_index(document: Dict[str, Any]) -> Optional[int]:
    """Index of the trailing empty paragraph, if the body ends with one."""
    content = document.get("body", {}).get("content", [])
    if not content:
        return None
    last = content[-1]
    if "paragraph" not in last:
        return None
    start, end = last.get("startIndex"), last.get("endIndex")
    if isinstance(start, int) and isinstance(end, int) and end - start == 1:
        return start
    return None


def _body_end(document: Dict[str, Any]) -> int:
    content = document.get("body", {}).get("content", [])
    if not content:
        raise ValueError("document body is empty")
    return int(content[-1]["endIndex"]) - 1


def _tables(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        element["table"]
        for element in document.get("body", {}).get("content", [])
        if "table" in element
    ]


def create_document_with_blocks(
    config: Config,
    logger: logging.Logger,
    title: str,
    blocks: Iterable[Any],
) -> str:
    """Create a document from ``("text", str)`` and ``("table", rows)`` blocks.

    Returns the new document id.
    """
    creds = get_creds(config)
    docs = build("docs", "v1", credentials=creds)

    document = docs.documents().create(body={"title": title}).execute()
    document_id = document.get("documentId")

    table_rows: List[List[List[str]]] = []

    for block in blocks:
        kind, payload = block
        current = docs.documents().get(documentId=document_id).execute()
        index = _body_end(current)

        if kind == "text":
            text = str(payload)
            if not text:
                continue
            if not text.endswith("\n"):
                text += "\n"
            request = {"insertText": {"location": {"index": index}, "text": text}}
        elif kind == "table":
            rows = normalise_rows(payload)
            height, width = table_dimensions(rows)
            table_rows.append(rows)

            # Insert into the trailing empty paragraph: the paragraph is split and
            # the remainder stays after the table, so later blocks remain possible.
            paragraph_index = empty_paragraph_index(current)
            if paragraph_index is None:
                docs.documents().batchUpdate(
                    documentId=document_id,
                    body={
                        "requests": [
                            {"insertText": {"location": {"index": index}, "text": "\n"}}
                        ]
                    },
                ).execute()
                current = docs.documents().get(documentId=document_id).execute()
                paragraph_index = empty_paragraph_index(current)
            if paragraph_index is None:
                raise RuntimeError("could not create a paragraph for the table")

            docs.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "insertTable": {
                                "rows": height,
                                "columns": width,
                                "location": {"index": paragraph_index},
                            }
                        }
                    ]
                },
            ).execute()
            continue
        else:
            raise ValueError(f"unknown block kind: {kind}")

        docs.documents().batchUpdate(
            documentId=document_id, body={"requests": [request]}
        ).execute()

    if table_rows:
        for table_index in range(len(table_rows)):
            rows = table_rows[table_index]
            current = docs.documents().get(documentId=document_id).execute()
            tables = _tables(current)
            if table_index >= len(tables):
                logger.warning("Table %s is missing from the document", table_index)
                break

            layout = cell_layout(tables[table_index])
            requests = fill_requests(layout, rows)
            if not requests:
                continue

            try:
                docs.documents().batchUpdate(
                    documentId=document_id, body={"requests": requests}
                ).execute()
            except Exception as exc:  # noqa: BLE001 - fall back to single inserts
                logger.warning("Batch fill failed for table %s: %s", table_index, exc)
                for request in requests:
                    try:
                        docs.documents().batchUpdate(
                            documentId=document_id, body={"requests": [request]}
                        ).execute()
                    except Exception as single_exc:  # noqa: BLE001
                        logger.warning("Cell insert skipped: %s", single_exc)

        current = docs.documents().get(documentId=document_id).execute()
        tables = _tables(current)
        style: List[Dict[str, Any]] = []
        for table, rows in zip(tables, table_rows):
            style.extend(header_style_requests(cell_layout(table), rows))
        if style:
            docs.documents().batchUpdate(
                documentId=document_id, body={"requests": style}
            ).execute()

    logger.info("Document with tables created: %s (%s tables)", document_id, len(table_rows))
    return document_id
