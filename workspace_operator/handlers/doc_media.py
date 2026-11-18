"""Google Docs media: insert an image at the end of the document."""

import logging
from typing import Optional

from ..config import Config
from ..google_clients import api_client


def insert_image_handler(
    config: Config,
    logger: logging.Logger,
    document_id: str,
    image_url: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
) -> str:
    """Insert an inline image at the end of the document body (PT sizes)."""
    try:
        if not document_id:
            return "Error: document_id is required."
        if not image_url or not str(image_url).startswith(("http://", "https://")):
            return "Error: image_url must be a public http(s) URL."

        service = api_client(config, 'docs', 'v1')
        document = service.documents().get(documentId=document_id).execute()
        content = (document.get("body") or {}).get("content") or []
        if not content:
            return "Error: the document body is empty."

        insertion_index = max(1, content[-1].get("endIndex", 2) - 1)
        request = {
            "insertInlineImage": {
                "location": {"index": insertion_index},
                "uri": image_url,
            }
        }
        size = {}
        if width:
            size["width"] = {"magnitude": float(width), "unit": "PT"}
        if height:
            size["height"] = {"magnitude": float(height), "unit": "PT"}
        if size:
            request["insertInlineImage"]["objectSize"] = size

        result = service.documents().batchUpdate(
            documentId=document_id, body={"requests": [request]}
        ).execute()
        reply = (result.get("replies") or [{}])[0].get("insertInlineImage", {})
        logger.info("Inserted image into %s", document_id)
        return (
            f"Image inserted into document {document_id} "
            f"(at index {insertion_index}, ID: {reply.get('objectId')})."
        )
    except Exception as e:
        return f"Error inserting image: {str(e)}"
