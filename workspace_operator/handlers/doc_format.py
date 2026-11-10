"""Google Docs: style matched text (bold, italic, size, heading)."""

import logging
from typing import Dict, List, Tuple

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text
from .docs import document_to_text

HEADINGS = {
    "NORMAL_TEXT",
    "HEADING_1",
    "HEADING_2",
    "HEADING_3",
    "HEADING_4",
    "HEADING_5",
    "HEADING_6",
    "TITLE",
    "SUBTITLE",
}


def _runs(paragraph: dict) -> List[Tuple[int, str]]:
    runs = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            runs.append((element.get("startIndex", 0), text_run.get("content", "")))
    return runs


def _absolute(runs: List[Tuple[int, str]], offset: int) -> int:
    consumed = 0
    for start, content in runs:
        if offset < consumed + len(content):
            return start + (offset - consumed)
        consumed += len(content)
    last_start, last_content = runs[-1]
    return last_start + len(last_content)


def find_ranges(
    document: dict, find: str, match_case: bool = False, limit: int = 200
) -> List[Tuple[int, int]]:
    """Map every match to absolute document indices."""
    ranges: List[Tuple[int, int]] = []
    needle = find if match_case else find.lower()
    for item in (document.get("body") or {}).get("content", []):
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        runs = _runs(paragraph)
        if not runs:
            continue
        text = "".join(content for _, content in runs)
        haystack = text if match_case else text.lower()
        start = 0
        while True:
            position = haystack.find(needle, start)
            if position == -1:
                break
            begin = _absolute(runs, position)
            end = _absolute(runs, position + len(find))
            ranges.append((begin, end))
            start = position + len(find)
            if len(ranges) >= limit:
                return ranges
    return ranges


def _paragraph_spans(document: dict, ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    spans = []
    for item in (document.get("body") or {}).get("content", []):
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        begin = item.get("startIndex", 0)
        end = item.get("endIndex", begin)
        if any(begin <= start < end for start, _ in ranges):
            spans.append((begin, end))
    return spans


def format_text_handler(
    config: Config,
    logger: logging.Logger,
    document_id: str,
    find: str,
    bold: bool = False,
    italic: bool = False,
    font_size: float = 0,
    heading: str = "",
    match_case: bool = False,
    confirm: bool = False,
) -> str:
    try:
        if not document_id or not find:
            return "Error: document_id and find are required."
        style = heading.upper()
        if style and style not in HEADINGS:
            return "Error: heading must be one of " + ", ".join(sorted(HEADINGS))
        if not (bold or italic or font_size or style):
            return "Error: pass bold, italic, font_size and/or heading."

        service = build("docs", "v1", credentials=get_creds(config))
        document = service.documents().get(documentId=document_id).execute()
        ranges = find_ranges(document, find, match_case)
        if not ranges:
            return f"No matches for “{find}” — nothing to style."

        if not confirm:
            excerpt = clean_text(document_to_text(document), single_line=True)[:160]
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Would style {len(ranges)} occurrence(s) of “{find}”"
                + (f" as {style}" if style else "")
                + (f", bold={bold}" if bold else "")
                + (f", italic={italic}" if italic else "")
                + (f", size={font_size}" if font_size else "")
                + f".\nDocument starts: …{excerpt}…\n\n"
                "Call again with confirm=true to apply."
            )

        requests: List[Dict] = []
        text_style: Dict[str, object] = {}
        fields: List[str] = []
        if bold:
            text_style["bold"] = True
            fields.append("bold")
        if italic:
            text_style["italic"] = True
            fields.append("italic")
        if font_size:
            text_style["fontSize"] = {"magnitude": float(font_size), "unit": "PT"}
            fields.append("fontSize")

        if text_style:
            for start, end in ranges:
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": start, "endIndex": end},
                            "textStyle": text_style,
                            "fields": ",".join(fields),
                        }
                    }
                )
        if style:
            for start, end in _paragraph_spans(document, ranges):
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": start, "endIndex": end},
                            "paragraphStyle": {"namedStyleType": style},
                            "fields": "namedStyleType",
                        }
                    }
                )

        service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()
        logger.info("Styled %s occurrence(s) in %s", len(ranges), document_id)
        return f"Styled {len(ranges)} occurrence(s) of “{find}” in document {document_id}."
    except Exception as e:
        return f"Error styling text: {str(e)}"
