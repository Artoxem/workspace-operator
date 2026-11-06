"""Sheet formatting: one tool for the formatting work agents actually need.

`sheet_format` applies cell formatting (bold, italic, size, number format,
colours, alignment, wrap), column widths, row heights and frozen panes in a
single `spreadsheets.batchUpdate` call.

All request building lives in pure helpers so it can be unit-tested without
credentials or network.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config

_CELL = re.compile(r"^([A-Za-z]*)(\d*)$")
_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

ALIGNMENTS = {"LEFT", "CENTER", "RIGHT"}
WRAP_STRATEGIES = {"OVERFLOW_CELL", "CLIP", "WRAP"}


def column_to_index(letters: str) -> int:
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def parse_a1_range(value: str) -> Dict[str, Optional[int]]:
    """Parse ``A1:C10``, ``A:C`` or ``1:10`` into grid indexes (end-exclusive).

    Returns ``startRow``/``endRow``/``startCol``/``endCol`` where a missing
    dimension is ``None`` (whole sheet).
    """
    text = str(value or "").replace("$", "").strip()
    if "!" in text:
        text = text.split("!", 1)[1]
    if not text:
        raise ValueError("empty range")

    parts = text.split(":")
    if len(parts) > 2:
        raise ValueError(f"invalid range: {value}")

    endpoints = [part.strip() for part in parts]
    parsed = []
    for endpoint in endpoints:
        match = _CELL.match(endpoint)
        if not match:
            raise ValueError(f"invalid range endpoint: {endpoint!r}")
        letters, digits = match.groups()
        parsed.append((letters, digits))

    if len(parsed) == 1:
        letters, digits = parsed[0]
        parsed = [(letters, digits), (letters, digits)]

    (start_letters, start_digits), (end_letters, end_digits) = parsed
    kind = ("columns" if start_letters and not start_digits else "rows" if start_digits and not start_letters else "cells")
    if kind == "columns":
        if not (end_letters and not end_digits):
            raise ValueError(f"mixed range types: {value}")
        return {
            "startRow": None,
            "endRow": None,
            "startCol": column_to_index(start_letters),
            "endCol": column_to_index(end_letters) + 1,
        }
    if kind == "rows":
        if not (end_digits and not end_letters):
            raise ValueError(f"mixed range types: {value}")
        return {
            "startRow": int(start_digits) - 1,
            "endRow": int(end_digits),
            "startCol": None,
            "endCol": None,
        }

    return {
        "startRow": int(start_digits) - 1,
        "endRow": int(end_digits),
        "startCol": column_to_index(start_letters),
        "endCol": column_to_index(end_letters) + 1,
    }


def hex_to_color(value: str) -> Dict[str, float]:
    """Convert ``#RRGGBB`` / ``#RGB`` into the Sheets colour object."""
    match = _HEX.match(str(value).strip())
    if not match:
        raise ValueError(f"invalid colour {value!r}; use #RRGGBB")

    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    return {
        "red": int(digits[0:2], 16) / 255,
        "green": int(digits[2:4], 16) / 255,
        "blue": int(digits[4:6], 16) / 255,
    }


def build_cell_format(
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    font_size: Optional[float] = None,
    number_format: Optional[str] = None,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    horizontal_alignment: Optional[str] = None,
    wrap: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the ``userEnteredFormat`` object from tool arguments."""
    cell_format: Dict[str, Any] = {}

    text_format: Dict[str, Any] = {}
    if bold is not None:
        text_format["bold"] = bool(bold)
    if italic is not None:
        text_format["italic"] = bool(italic)
    if font_size is not None:
        text_format["fontSize"] = float(font_size)
    if text_color is not None:
        text_format["foregroundColorStyle"] = {
            "rgbColor": hex_to_color(text_color)
        }
    if text_format:
        cell_format["textFormat"] = text_format

    if number_format:
        cell_format["numberFormat"] = {"type": "NUMBER", "pattern": number_format}
    if background_color is not None:
        cell_format["backgroundColorStyle"] = {
            "rgbColor": hex_to_color(background_color)
        }
    if horizontal_alignment is not None:
        alignment = str(horizontal_alignment).upper()
        if alignment not in ALIGNMENTS:
            raise ValueError(
                f"invalid alignment {horizontal_alignment!r}; "
                f"use {', '.join(sorted(ALIGNMENTS))}"
            )
        cell_format["horizontalAlignment"] = alignment
    if wrap is not None:
        strategy = str(wrap).upper()
        if strategy not in WRAP_STRATEGIES:
            raise ValueError(
                f"invalid wrap {wrap!r}; use {', '.join(sorted(WRAP_STRATEGIES))}"
            )
        cell_format["wrapStrategy"] = strategy

    return cell_format


def build_requests(
    sheet_id: int,
    grid_range: Dict[str, Optional[int]],
    cell_format: Optional[Dict[str, Any]] = None,
    column_width: Optional[float] = None,
    row_height: Optional[float] = None,
    freeze_rows: Optional[int] = None,
    freeze_cols: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Assemble the batchUpdate request list."""
    requests: List[Dict[str, Any]] = []
    prefix = {"sheetId": sheet_id}

    if cell_format:
        grid = _grid_range(sheet_id, grid_range)
        requests.append(
            {
                "repeatCell": {
                    "range": grid,
                    "cell": {"userEnteredFormat": cell_format},
                    "fields": "userEnteredFormat",
                }
            }
        )

    if column_width is not None:
        start = grid_range.get("startCol") or 0
        end = grid_range.get("endCol")
        if end is None:
            raise ValueError("column_width requires a range with columns (e.g. A:C)")
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        **prefix,
                        "dimension": "COLUMNS",
                        "startIndex": start,
                        "endIndex": end,
                    },
                    "properties": {"pixelSize": int(column_width)},
                    "fields": "pixelSize",
                }
            }
        )

    if row_height is not None:
        start = grid_range.get("startRow") or 0
        end = grid_range.get("endRow")
        if end is None:
            raise ValueError("row_height requires a range with rows (e.g. 1:10)")
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        **prefix,
                        "dimension": "ROWS",
                        "startIndex": start,
                        "endIndex": end,
                    },
                    "properties": {"pixelSize": int(row_height)},
                    "fields": "pixelSize",
                }
            }
        )

    if freeze_rows is not None or freeze_cols is not None:
        grid_properties: Dict[str, int] = {}
        if freeze_rows is not None:
            grid_properties["frozenRowCount"] = int(freeze_rows)
        if freeze_cols is not None:
            grid_properties["frozenColumnCount"] = int(freeze_cols)
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {**prefix, "gridProperties": grid_properties},
                    "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
                }
            }
        )

    return requests



def _grid_range(sheet_id: int, parsed: Dict[str, Optional[int]]) -> Dict[str, int]:
    """Translate parsed A1 indexes into the API GridRange shape."""
    grid: Dict[str, int] = {"sheetId": sheet_id}
    mapping = {
        "startRow": "startRowIndex",
        "endRow": "endRowIndex",
        "startCol": "startColumnIndex",
        "endCol": "endColumnIndex",
    }
    for internal, api_name in mapping.items():
        value = parsed.get(internal)
        if value is not None:
            grid[api_name] = value
    return grid


def _sheet_lookup(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [sheet["properties"] for sheet in meta.get("sheets", [])]


def _resolve_sheet(
    properties: List[Dict[str, Any]], sheet_name: Optional[str], range_value: Optional[str]
) -> Dict[str, Any]:
    wanted = sheet_name
    if not wanted and range_value and "!" in range_value:
        wanted = range_value.split("!", 1)[0]

    if wanted:
        for prop in properties:
            if prop.get("title") == wanted:
                return prop
        raise ValueError(f"sheet not found: {wanted}")

    if not properties:
        raise ValueError("the spreadsheet has no sheets")
    return properties[0]


def format_sheet_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    range_name: Optional[str] = None,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    font_size: Optional[float] = None,
    number_format: Optional[str] = None,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    horizontal_alignment: Optional[str] = None,
    wrap: Optional[str] = None,
    column_width: Optional[float] = None,
    row_height: Optional[float] = None,
    freeze_rows: Optional[int] = None,
    freeze_cols: Optional[int] = None,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."

        creds = get_creds(config)
        service = build("sheets", "v4", credentials=creds)

        meta = (
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,gridProperties))",
            )
            .execute()
        )
        properties = _sheet_lookup(meta)
        sheet = _resolve_sheet(properties, sheet_name, range_name)

        sheet_id = sheet["sheetId"]
        grid = sheet.get("gridProperties", {})

        parsed: Dict[str, Optional[int]] = {
            "startRow": 0,
            "endRow": grid.get("rowCount"),
            "startCol": 0,
            "endCol": grid.get("columnCount"),
        }
        if range_name:
            parsed = parse_a1_range(range_name)

        cell_format = build_cell_format(
            bold=bold,
            italic=italic,
            font_size=font_size,
            number_format=number_format,
            background_color=background_color,
            text_color=text_color,
            horizontal_alignment=horizontal_alignment,
            wrap=wrap,
        )

        if not cell_format and not any(
            value is not None
            for value in (column_width, row_height, freeze_rows, freeze_cols)
        ):
            return "Error: nothing to format — pass at least one formatting option."

        requests = build_requests(
            sheet_id,
            parsed,
            cell_format=cell_format,
            column_width=column_width,
            row_height=row_height,
            freeze_rows=freeze_rows,
            freeze_cols=freeze_cols,
        )

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

        applied = []
        if cell_format:
            applied.append(", ".join(sorted(cell_format)))
        if column_width is not None:
            applied.append(f"column width {int(column_width)}px")
        if row_height is not None:
            applied.append(f"row height {int(row_height)}px")
        if freeze_rows is not None:
            applied.append(f"freeze {freeze_rows} row(s)")
        if freeze_cols is not None:
            applied.append(f"freeze {freeze_cols} column(s)")

        area = range_name or "the whole sheet"
        logger.info("Formatted %s!%s: %s", sheet.get("title"), area, "; ".join(applied))
        return f"Formatted '{sheet.get('title')}' {area}: " + "; ".join(applied) + "."
    except Exception as e:
        return f"Error formatting sheet: {str(e)}"
