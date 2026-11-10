"""Editing an existing Google Doc: find and replace with a preview."""

import logging

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text
from .docs import document_to_text


def _docs(config: Config):
    return build("docs", "v1", credentials=get_creds(config))


def _excerpt(text: str, needle: str, match_case: bool) -> str:
    haystack = text if match_case else text.lower()
    position = haystack.find(needle if match_case else needle.lower())
    if position == -1:
        return ""
    start = max(0, position - 60)
    end = min(len(text), position + len(needle) + 60)
    return clean_text(text[start:end], single_line=True)


def replace_text_handler(
    config: Config,
    logger: logging.Logger,
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = False,
    confirm: bool = False,
) -> str:
    try:
        if not document_id or not find:
            return "Error: document_id and find are required."

        service = _docs(config)

        if not confirm:
            document = service.documents().get(documentId=document_id).execute()
            text = document_to_text(document)
            haystack = text if match_case else text.lower()
            needle = find if match_case else find.lower()
            occurrences = haystack.count(needle)
            if not occurrences:
                return (
                    f"No matches for “{find}”"
                    + (" (case-sensitive)" if match_case else "")
                    + " — nothing would change."
                )
            excerpt = _excerpt(text, find, match_case)
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Would replace {occurrences} occurrence(s) of “{find}” with “{replace}”.\n"
                + (f"First match: …{excerpt}…\n" if excerpt else "")
                + "\nCall again with confirm=true to apply."
            )

        result = (
            service.documents()
            .batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {"text": find, "matchCase": match_case},
                                "replaceText": replace,
                            }
                        }
                    ]
                },
            )
            .execute()
        )
        replies = result.get("replies") or [{}]
        changed = (replies[0].get("replaceAllText") or {}).get("occurrencesChanged", 0)
        logger.info("Replaced %s occurrence(s) in %s", changed, document_id)
        return f"Replaced {changed} occurrence(s) in document {document_id}."
    except Exception as e:
        return f"Error replacing text: {str(e)}"
