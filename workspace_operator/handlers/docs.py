import logging
from typing import Dict, Union

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..operations import BinaryResult
from ..text import clean_text


def _paragraph_text(paragraph: dict) -> str:
    return "".join(
        element.get("textRun", {}).get("content", "")
        for element in paragraph.get("elements", [])
    )


def _table_text(table: dict) -> str:
    """Render a Docs table as markdown-ish rows so cell content is not lost."""
    lines = []
    for row in table.get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            chunks = []
            for item in cell.get("content", []):
                if "paragraph" in item:
                    chunks.append(_paragraph_text(item["paragraph"]))
                elif "table" in item:
                    chunks.append(_table_text(item["table"]))
            cells.append(clean_text(" ".join(chunks)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def document_to_text(document: dict) -> str:
    """Flatten a Google Docs document body, including tables."""
    blocks = []
    for item in document.get("body", {}).get("content", []):
        if "paragraph" in item:
            blocks.append(_paragraph_text(item["paragraph"]))
        elif "table" in item:
            blocks.append(_table_text(item["table"]))
    return clean_text("\n".join(blocks))


def read_doc_handler(config: Config, logger: logging.Logger, document_id: str) -> str:
    try:
        creds = get_creds(config)
        service = build("docs", "v1", credentials=creds)

        document = service.documents().get(documentId=document_id).execute()
        text = document_to_text(document) or "(the document has no readable text)"

        return f"Document Content ({document.get('title')}):\n\n{text}"
    except Exception as e:
        return f"Error reading document: {str(e)}"


def create_doc_handler(config: Config, logger: logging.Logger, title: str) -> str:
    try:
        creds = get_creds(config)
        service = build("docs", "v1", credentials=creds)

        body = {"title": title}
        doc = service.documents().create(body=body).execute()

        return f"Created document: {doc.get('title')} (ID: {doc.get('documentId')})"
    except Exception as e:
        return f"Error creating document: {str(e)}"


def append_to_doc_handler(config: Config, logger: logging.Logger, document_id: str, text: str) -> str:
    try:
        creds = get_creds(config)
        service = build("docs", "v1", credentials=creds)

        requests = [
            {
                "insertText": {
                    "endOfSegmentLocation": {"segmentId": ""},
                    "text": text,
                }
            }
        ]

        service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()

        return "Successfully appended text to document."
    except Exception as e:
        return f"Error appending to document: {str(e)}"




