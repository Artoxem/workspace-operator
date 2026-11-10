"""Sheets extras: conditional formatting and charts."""

import logging
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from .formatting import (
    _grid_range,
    _resolve_sheet,
    _sheet_lookup,
    hex_to_color,
    parse_a1_range,
)

TEXT_CONDITIONS = {
    "TEXT_CONTAINS",
    "TEXT_NOT_CONTAINS",
    "TEXT_STARTS_WITH",
    "TEXT_ENDS_WITH",
    "TEXT_EQ",
}
NUMBER_CONDITIONS = {
    "NUMBER_GREATER",
    "NUMBER_GREATER_THAN_EQ",
    "NUMBER_LESS",
    "NUMBER_LESS_THAN_EQ",
    "NUMBER_EQ",
    "NUMBER_NOT_EQ",
    "NUMBER_BETWEEN",
}
NO_VALUE_CONDITIONS = {"IS_EMPTY", "IS_NOT_EMPTY", "BLANK", "NOT_BLANK"}

ALIASES = {
    "CONTAINS": "TEXT_CONTAINS",
    "NOT_CONTAINS": "TEXT_NOT_CONTAINS",
    "STARTS_WITH": "TEXT_STARTS_WITH",
    "ENDS_WITH": "TEXT_ENDS_WITH",
    "GREATER": "NUMBER_GREATER",
    "GREATER_THAN": "NUMBER_GREATER",
    "LESS": "NUMBER_LESS",
    "LESS_THAN": "NUMBER_LESS",
    "EQUAL": "NUMBER_EQ",
    "NOT_EQUAL": "NUMBER_NOT_EQ",
    "EMPTY": "IS_EMPTY",
    "NOT_EMPTY": "IS_NOT_EMPTY",
}

CHART_TYPES = {
    "COLUMN",
    "BAR",
    "LINE",
    "AREA",
    "SCATTER",
    "COMBO",
    "STEPPED_AREA",
    "PIE",
}


def _sheets(config: Config):
    return build("sheets", "v4", credentials=get_creds(config))


def _meta(service, spreadsheet_id: str) -> List[Dict[str, Any]]:
    meta = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title,gridProperties))",
        )
        .execute()
    )
    return _sheet_lookup(meta)


def _condition(
    condition: str, value: Optional[str], value2: Optional[str]
) -> Dict[str, Any]:
    kind = ALIASES.get(condition.upper(), condition.upper())
    if kind in TEXT_CONDITIONS:
        if value is None:
            raise ValueError(f"{kind} needs a value")
        return {
            "type": kind,
            "values": [{"userEnteredValue": str(value)}],
        }
    if kind in NUMBER_CONDITIONS:
        if value is None:
            raise ValueError(f"{kind} needs a value")
        if kind == "NUMBER_BETWEEN":
            if value2 is None:
                raise ValueError("NUMBER_BETWEEN needs value and value2")
            return {
                "type": kind,
                "values": [
                    {"userEnteredValue": str(value)},
                    {"userEnteredValue": str(value2)},
                ],
            }
        return {"type": kind, "values": [{"userEnteredValue": str(value)}]}
    if kind in NO_VALUE_CONDITIONS:
        mapped = {
            "BLANK": "IS_EMPTY",
            "NOT_BLANK": "IS_NOT_EMPTY",
        }.get(kind, kind)
        return {"type": mapped}
    raise ValueError(
        "unsupported condition; use one of: "
        + ", ".join(sorted(TEXT_CONDITIONS | NUMBER_CONDITIONS | NO_VALUE_CONDITIONS))
    )


def conditional_format_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    condition: str,
    value: Optional[str] = None,
    value2: Optional[str] = None,
    background_color: Optional[str] = "#FFF2CC",
    text_color: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        service = _sheets(config)
        properties = _meta(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, range_name)
        sheet_id = sheet["sheetId"]

        grid = _grid_range(sheet_id, parse_a1_range(range_name))
        rule_format: Dict[str, Any] = {}
        if background_color:
            rule_format["backgroundColorStyle"] = {"rgbColor": hex_to_color(background_color)}
        if text_color:
            rule_format["textFormat"] = {"foregroundColorStyle": {"rgbColor": hex_to_color(text_color)}}
        if not rule_format:
            return "Error: pass background_color or text_color."

        rule = {
            "ranges": [grid],
            "booleanRule": {
                "condition": _condition(condition, value, value2),
                "format": rule_format,
            },
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addConditionalFormatRule": {"rule": rule}}]},
        ).execute()

        logger.info("Conditional format %s on %s", condition, range_name)
        return (
            f"Conditional format added to {range_name}: {condition}"
            + (f" “{value}”" if value else "")
            + f" → {background_color or text_color}"
        )
    except Exception as e:
        return f"Error adding conditional format: {str(e)}"


def _source(sheet_id: int, rows: Dict[str, int], column: int) -> Dict[str, int]:
    return {
        "sheetId": sheet_id,
        "startRowIndex": rows["startRow"],
        "endRowIndex": rows["endRow"],
        "startColumnIndex": column,
        "endColumnIndex": column + 1,
    }


def add_chart_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    chart_type: str = "COLUMN",
    title: Optional[str] = None,
    sheet_name: Optional[str] = None,
    header: bool = True,
    anchor_row: int = 0,
    anchor_col: int = 0,
    width: int = 600,
    height: int = 371,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        kind = chart_type.upper()
        if kind not in CHART_TYPES:
            return "Error: chart_type must be one of " + ", ".join(sorted(CHART_TYPES))

        service = _sheets(config)
        properties = _meta(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, range_name)
        sheet_id = sheet["sheetId"]

        parsed = parse_a1_range(range_name)
        grid = _grid_range(sheet_id, parsed)
        start_col = grid.get("startColumnIndex", 0)
        end_col = grid.get("endColumnIndex", start_col + 2)
        start_row = grid.get("startRowIndex", 0)
        end_row = grid.get("endRowIndex", start_row + 10)

        if end_col - start_col < 2:
            return "Error: the range needs at least two columns (labels + values)."

        rows = {"startRow": start_row, "endRow": end_row}
        domain = {"domain": {"sourceRange": {"sources": [_source(sheet_id, rows, start_col)]}}}
        series = [
            {
                "series": {"sourceRange": {"sources": [_source(sheet_id, rows, column)]}},
                "targetAxis": "LEFT_AXIS",
            }
            for column in range(start_col + 1, end_col)
        ]

        title = title or f"{sheet.get('title')} chart"
        if kind == "PIE":
            spec: Dict[str, Any] = {
                "title": title,
                "pieChart": {
                    "legendPosition": "RIGHT_LEGEND",
                    "domain": {"sourceRange": {"sources": [_source(sheet_id, rows, start_col)]}},
                    "series": {"sourceRange": {"sources": [_source(sheet_id, rows, start_col + 1)]}},
                },
            }
        else:
            spec = {
                "title": title,
                "basicChart": {
                    "chartType": kind,
                    "legendPosition": "BOTTOM_LEGEND",
                    "headerCount": 1 if header else 0,
                    "domains": [domain],
                    "series": series,
                },
            }

        request = {
            "addChart": {
                "chart": {
                    "spec": spec,
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": max(0, anchor_row),
                                "columnIndex": max(0, anchor_col),
                            },
                            "widthPixels": width,
                            "heightPixels": height,
                        }
                    },
                }
            }
        }
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        chart_id = (
            (result.get("replies") or [{}])[0].get("addChart", {}).get("chartId")
        )
        logger.info("Added %s chart to %s", kind, spreadsheet_id)
        suffix = f" (ID: {chart_id})" if chart_id is not None else ""
        return f"Chart added: {kind}{suffix} on {range_name}\nTitle: {title}"
    except Exception as e:
        return f"Error adding chart: {str(e)}"
