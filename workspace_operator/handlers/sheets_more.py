"""Sheets: columns and sorting."""

import logging
from typing import Any, Dict, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from .formatting import _grid_range, _resolve_sheet, _sheet_lookup, parse_a1_range
from .sheets_structure import _dimension_request


def _sheets(config: Config):
    return build("sheets", "v4", credentials=get_creds(config))


def _properties(service, spreadsheet_id: str):
    meta = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title,gridProperties))",
        )
        .execute()
    )
    return _sheet_lookup(meta)


def insert_columns_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    start_column: int = 1,
    count: int = 1,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."
        if count < 1:
            return "Error: count must be at least 1."
        if start_column < 1:
            return "Error: start_column is 1-based and must be at least 1."

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, None
        )
        start = start_column - 1
        request = _dimension_request(
            sheet["sheetId"], "COLUMNS", start, start + count, insert=True
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        return (
            f"Inserted {count} column(s) into '{sheet.get('title')}' "
            f"before column {start_column}."
        )
    except Exception as e:
        return f"Error inserting columns: {str(e)}"


def delete_columns_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    start_column: int = 1,
    count: int = 1,
    confirm: bool = False,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."
        if count < 1:
            return "Error: count must be at least 1."
        if start_column < 1:
            return "Error: start_column is 1-based and must be at least 1."

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, None
        )
        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Delete {count} column(s) from '{sheet.get('title')}', "
                f"starting at column {start_column}.\n"
                "Values in these columns are lost; columns to the right shift left.\n"
                "Call again with confirm=true to proceed."
            )

        start = start_column - 1
        request = _dimension_request(
            sheet["sheetId"], "COLUMNS", start, start + count, insert=False
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        return f"Deleted {count} column(s) from '{sheet.get('title')}'."
    except Exception as e:
        return f"Error deleting columns: {str(e)}"


def sort_range_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    column: int = 1,
    ascending: bool = True,
    sheet_name: Optional[str] = None,
) -> str:
    """Sort a range by a 1-based column inside that range."""
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."
        if column < 1:
            return "Error: column is 1-based and must be at least 1."

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, range_name
        )
        grid = _grid_range(sheet["sheetId"], parse_a1_range(range_name))
        start_col = grid.get("startColumnIndex", 0)
        end_col = grid.get("endColumnIndex")
        if end_col is None:
            return "Error: the range must name explicit columns."
        dimension_index = start_col + column - 1
        if dimension_index >= end_col:
            return "Error: column is outside the range."

        request: Dict[str, Any] = {
            "sortRange": {
                "range": grid,
                "sortSpecs": [
                    {
                        "dimensionIndex": dimension_index,
                        "sortOrder": "ASCENDING" if ascending else "DESCENDING",
                    }
                ],
            }
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": [request]}
        ).execute()
        logger.info("Sorted %s by column %s", range_name, column)
        return (
            f"Sorted {range_name} by column {column} "
            f"({'ascending' if ascending else 'descending'})."
        )
    except Exception as e:
        return f"Error sorting range: {str(e)}"
