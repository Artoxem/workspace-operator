"""Composite tool: turn a spreadsheet range into a presentation.

No assumption about the data: the first row is treated as a header (optional),
every following row becomes one bullet line «Header: value · Header2: value2»,
and rows are grouped into slides of ``rows_per_slide``.

Slide construction is pure: ``chunk_rows``, ``format_row`` and the request
builders are unit-tested; only the handler talks to Google.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

INCH = 914400
SLIDE_WIDTH = 9144000
SLIDE_HEIGHT = 5143500
MAX_SLIDES = 40
MAX_ROWS_PER_SLIDE = 20
DEFAULT_ROWS_PER_SLIDE = 8
LINE_LIMIT = 180


def chunk_rows(rows: Sequence[Sequence[str]], size: int) -> List[List[List[str]]]:
    """Split data rows into groups of at most ``size`` rows."""
    step = max(1, min(int(size or DEFAULT_ROWS_PER_SLIDE), MAX_ROWS_PER_SLIDE))
    return [list(rows[index : index + step]) for index in range(0, len(rows), step)]


def format_row(header: Sequence[str], row: Sequence[str]) -> str:
    """One bullet line: «Header: value · Header2: value2», skipping empties."""
    parts: List[str] = []
    for index, value in enumerate(row):
        cell = clean_text(value)
        if not cell:
            continue
        name = clean_text(header[index]) if index < len(header) else ""
        parts.append(f"{name}: {cell}" if name else cell)

    line = " · ".join(parts) if parts else "(empty row)"
    if len(line) > LINE_LIMIT:
        line = line[: LINE_LIMIT - 1] + "…"
    return line


def _emu(pixels: float) -> Dict[str, Any]:
    return {"magnitude": int(round(pixels)), "unit": "EMU"}


def _text_box(shape_id: str, slide_id: str, x: int, y: int, w: int, h: int) -> Dict[str, Any]:
    return {
        "createShape": {
            "objectId": shape_id,
            "shapeType": "TEXT_BOX",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {"width": _emu(w), "height": _emu(h)},
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": x,
                    "translateY": y,
                    "unit": "EMU",
                },
            },
        }
    }


def _insert_text(shape_id: str, text: str) -> Dict[str, Any]:
    return {"insertText": {"objectId": shape_id, "insertionIndex": 0, "text": text}}


def _style(shape_id: str, size: int, bold: bool) -> Dict[str, Any]:
    return {
        "updateTextStyle": {
            "objectId": shape_id,
            "textRange": {"type": "ALL"},
            "style": {
                "fontSize": {"magnitude": size, "unit": "PT"},
                "bold": bold,
            },
            "fields": "fontSize,bold",
        }
    }


def slide_requests(
    slide_id: str,
    title: str,
    lines: Sequence[str],
    title_size: int = 26,
    body_size: int = 14,
) -> List[Dict[str, Any]]:
    """Create one slide with a title and a body of bullet lines."""
    title_shape = f"{slide_id}_title"
    body_shape = f"{slide_id}_body"

    return [
        {
            "createSlide": {
                "objectId": slide_id,
                "slideLayoutReference": {"predefinedLayout": "BLANK"},
            }
        },
        _text_box(title_shape, slide_id, INCH // 2, INCH // 2, SLIDE_WIDTH - INCH, INCH),
        _insert_text(title_shape, title),
        _style(title_shape, title_size, True),
        _text_box(
            body_shape,
            slide_id,
            INCH // 2,
            INCH + INCH // 2,
            SLIDE_WIDTH - INCH,
            SLIDE_HEIGHT - 2 * INCH,
        ),
        _insert_text(body_shape, "\n".join(lines)),
        _style(body_shape, body_size, False),
    ]


def title_slide_requests(slide_id: str, title: str, subtitle: str) -> List[Dict[str, Any]]:
    title_shape = f"{slide_id}_title"
    subtitle_shape = f"{slide_id}_subtitle"

    return [
        {
            "createSlide": {
                "objectId": slide_id,
                "slideLayoutReference": {"predefinedLayout": "BLANK"},
            }
        },
        _text_box(title_shape, slide_id, INCH, int(SLIDE_HEIGHT * 0.32), SLIDE_WIDTH - 2 * INCH, int(INCH * 1.4)),
        _insert_text(title_shape, title),
        _style(title_shape, 40, True),
        _text_box(subtitle_shape, slide_id, INCH, int(SLIDE_HEIGHT * 0.55), SLIDE_WIDTH - 2 * INCH, INCH),
        _insert_text(subtitle_shape, subtitle),
        _style(subtitle_shape, 18, False),
    ]


def _read_range(service, spreadsheet_id: str, range_name: Optional[str]) -> List[List[str]]:
    target = range_name
    if not target:
        meta = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
            .execute()
        )
        target = meta["sheets"][0]["properties"]["title"]
    return (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=target)
        .execute()
        .get("values", [])
    )


def sheet_to_slides_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: Optional[str] = None,
    title: Optional[str] = None,
    rows_per_slide: int = DEFAULT_ROWS_PER_SLIDE,
    header: bool = True,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."

        creds = get_creds(config)
        sheets = build("sheets", "v4", credentials=creds)
        slides = build("slides", "v1", credentials=creds)

        values = _read_range(sheets, spreadsheet_id, range_name)
        if not values:
            return "Error: the range is empty — nothing to present."

        header_row = [clean_text(cell) for cell in values[0]] if header else []
        data = [list(row) for row in (values[1:] if header else values)]
        if not data:
            return "Error: the range has a header but no data rows."

        chunks = chunk_rows(data, rows_per_slide)
        if len(chunks) > MAX_SLIDES:
            chunks = chunks[:MAX_SLIDES]

        deck_title = title or f"Table {datetime_stamp()}"
        presentation = slides.presentations().create(body={"title": deck_title}).execute()
        presentation_id = presentation.get("presentationId")

        # A fresh presentation ships with one empty slide — remove it.
        existing = slides.presentations().get(presentationId=presentation_id).execute()
        default_slides = [
            slide["objectId"] for slide in existing.get("slides", [])
        ]
        remove_requests = [
            {"deleteObject": {"objectId": slide_id}} for slide_id in default_slides
        ]

        subtitle = f"{len(data)} row(s) · {len(header_row) or '?'} column(s)"
        slides.presentations().batchUpdate(
            presentationId=presentation_id,
            body={
                "requests": remove_requests
                + title_slide_requests("title_slide", deck_title, subtitle)
            },
        ).execute()

        start = 1
        for index, chunk in enumerate(chunks, start=1):
            lines = [format_row(header_row, row) for row in chunk]
            end = start + len(chunk) - 1
            slides.presentations().batchUpdate(
                presentationId=presentation_id,
                body={
                    "requests": slide_requests(
                        f"slide_{index}", f"Rows {start}–{end}", lines
                    )
                },
            ).execute()
            start = end + 1

        logger.info(
            "Deck created: sheet=%s presentation=%s slides=%s rows=%s",
            spreadsheet_id,
            presentation_id,
            len(chunks) + 1,
            len(data),
        )
        return (
            f"Presentation created: {deck_title}\n"
            f"ID: {presentation_id}\n"
            f"URL: https://docs.google.com/presentation/d/{presentation_id}/edit\n"
            f"Slides: {len(chunks) + 1} | rows: {len(data)}"
        )
    except Exception as e:
        return f"Error building presentation: {str(e)}"


def datetime_stamp() -> str:
    from datetime import datetime, timezone

    return f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M}"
