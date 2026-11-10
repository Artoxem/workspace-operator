"""Sheets structure: delete a tab, insert/delete rows, merge cells."""

import logging
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from .formatting import (
    _grid_range,
    _resolve_sheet,
    _sheet_lookup,
    parse_a1_range,
)

MERGE_TYPES = {"MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS", "UNMERGE"}


def _sheets(config: Config):
    return build("sheets", "v4", credentials=get_creds(config))


def _properties(service, spreadsheet_id: str) -> List[Dict[str, Any]]:
    meta = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title,gridProperties))",
        )
        .execute()
    )
    return _sheet_lookup(meta)


def delete_sheet_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: str,
    confirm: bool = False,
) -> str:
    try:
        if not spreadsheet_id or not sheet_name:
            return "Error: spreadsheet_id and sheet_name are required."

        service = _sheets(config)
        properties = _properties(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, None)

        if len(properties) <= 1:
            return "Error: a spreadsheet must keep at least one sheet."

        title = sheet.get("title")
        if not confirm:
            cells = sheet.get("gridProperties", {})
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Delete sheet '{title}' "
                f"({cells.get('rowCount', '?')} rows × {cells.get('columnCount', '?')} columns).\n"
                "All values and formatting on this tab are removed; other tabs stay.\n"
                "Call again with confirm=true to proceed."
            )

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": sheet["sheetId"]}}]},
        ).execute()
        logger.info("Deleted sheet %s from %s", title, spreadsheet_id)
        return f"Sheet '{title}' deleted from {spreadsheet_id}."
    except Exception as e:
        return f"Error deleting sheet: {str(e)}"


def _dimension_request(
    sheet_id: int, dimension: str, start_index: int, end_index: int, insert: bool
) -> Dict[str, Any]:
    grid = {
        "sheetId": sheet_id,
        "dimension": dimension,
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if insert:
        return {"insertDimension": {"range": grid, "inheritFromBefore": False}}
    return {"deleteDimension": {"range": grid}}


def insert_rows_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    start_row: int = 1,
    count: int = 1,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."
        if count < 1:
            return "Error: count must be at least 1."
        if start_row < 1:
            return "Error: start_row is 1-based and must be at least 1."

        service = _sheets(config)
        properties = _properties(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, None)
        start = start_row - 1
        request = _dimension_request(
            sheet["sheetId"], "ROWS", start, start + count, insert=True
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        return (
            f"Inserted {count} row(s) into '{sheet.get('title')}' "
            f"before row {start_row}."
        )
    except Exception as e:
        return f"Error inserting rows: {str(e)}"


def delete_rows_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    start_row: int = 1,
    count: int = 1,
    confirm: bool = False,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."
        if count < 1:
            return "Error: count must be at least 1."
        if start_row < 1:
            return "Error: start_row is 1-based and must be at least 1."

        service = _sheets(config)
        properties = _properties(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, None)
        start = start_row - 1

        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Delete {count} row(s) from '{sheet.get('title')}', "
                f"starting at row {start_row}.\n"
                "Values in these rows are lost; rows below shift up.\n"
                "Call again with confirm=true to proceed."
            )

        request = _dimension_request(
            sheet["sheetId"], "ROWS", start, start + count, insert=False
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        logger.info("Deleted %s rows from %s", count, spreadsheet_id)
        return f"Deleted {count} row(s) from '{sheet.get('title')}'."
    except Exception as e:
        return f"Error deleting rows: {str(e)}"


def merge_cells_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    merge_type: str = "MERGE_ALL",
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        kind = merge_type.upper()
        if kind not in MERGE_TYPES:
            return "Error: merge_type must be one of " + ", ".join(sorted(MERGE_TYPES))

        service = _sheets(config)
        properties = _properties(service, spreadsheet_id)
        sheet = _resolve_sheet(properties, sheet_name, range_name)
        grid = _grid_range(sheet["sheetId"], parse_a1_range(range_name))

        if kind == "UNMERGE":
            request: Dict[str, Any] = {"unmergeCells": {"range": grid}}
        else:
            request = {"mergeCells": {"range": grid, "mergeType": kind}}

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        return f"{kind.replace('_', ' ').title()} applied to {range_name}."
    except Exception as e:
        return f"Error merging cells: {str(e)}"
