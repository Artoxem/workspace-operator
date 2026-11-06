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


def doc_fill_template_handler(
    config: Config,
    logger: logging.Logger,
    document_id: str,
    replacements: Dict[str, str],
    confirm: bool = False,
) -> str:
    """Fill a Google Doc template by replacing placeholders."""
    try:
        if not replacements:
            return "Error: replacements map is required."

        # Two-step safety: confirm before writing
        if not confirm:
            keys = ", ".join(list(replacements.keys())[:20])
            return (
                "⚠️ CONFIRMATION REQUIRED\n\n"
                f"This will replace placeholders in document {document_id}.\n"
                f"Keys: {keys}\n"
                "To proceed, call again with confirm=True."
            )

        creds = get_creds(config)
        service = build("docs", "v1", credentials=creds)

        requests = []
        for key, value in replacements.items():
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {"text": key, "matchCase": True},
                        "replaceText": str(value),
                    }
                }
            )

        service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()

        logger.info("Doc template filled: %s keys=%s", document_id, len(replacements))
        return f"✅ Document updated: {len(replacements)} placeholders replaced."
    except Exception as e:
        logger.error("Error filling template %s: %s", document_id, str(e))
        return f"Error filling template: {str(e)}"


def doc_export_pdf_handler(
    config: Config, logger: logging.Logger, document_id: str
) -> Union[BinaryResult, str]:
    """Export a Google Doc to PDF and return it as binary content."""
    try:
        creds = get_creds(config)
        drive = build("drive", "v3", credentials=creds)

        data: bytes = drive.files().export(
            fileId=document_id, mimeType="application/pdf"
        ).execute()

        logger.info("Doc exported to PDF: %s bytes=%s", document_id, len(data))
        return BinaryResult(
            uri=f"gdocs://{document_id}/export.pdf",
            mime_type="application/pdf",
            data=data,
            description=f"PDF export of document {document_id} ({len(data):,} bytes)",
        )
    except Exception as e:
        logger.error("Error exporting PDF %s: %s", document_id, str(e))
        return f"Error exporting PDF: {str(e)}"
