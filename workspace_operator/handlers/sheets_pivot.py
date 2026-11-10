"""Sheets: create a pivot table from a range."""

import logging
from typing import List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from .formatting import _grid_range, _resolve_sheet, _sheet_lookup, parse_a1_range

SUMMARIES = {"SUM", "COUNT", "AVERAGE", "MIN", "MAX"}


def _sheets(config: Config):
    return build("sheets", "v4", credentials=get_creds(config))


def add_pivot_table_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    source_range: str,
    rows: List[int],
    values: List[int],
    columns: Optional[List[int]] = None,
    aggregation: str = "SUM",
    target_sheet_name: str = "Pivot",
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not source_range:
            return "Error: spreadsheet_id and source_range are required."
        if not rows or not values:
            return "Error: rows and values must each list at least one column."
        summary = aggregation.upper()
        if summary not in SUMMARIES:
            return "Error: aggregation must be one of " + ", ".join(sorted(SUMMARIES))

        service = _sheets(config)
        meta = (
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,gridProperties))",
            )
            .execute()
        )
        properties = _sheet_lookup(meta)
        source = _resolve_sheet(properties, sheet_name, source_range)
        source_grid = _grid_range(source["sheetId"], parse_a1_range(source_range))
        width = source_grid.get("endColumnIndex", 0) - source_grid.get("startColumnIndex", 0)

        def offset(column: int) -> int:
            if column < 1 or column > width:
                raise ValueError(
                    f"column {column} is outside the source range (1..{width})"
                )
            return column - 1

        pivot_rows = [
            {"sourceColumnOffset": offset(column), "showTotals": True, "sortOrder": "ASCENDING"}
            for column in rows
        ]
        pivot_columns = [
            {"sourceColumnOffset": offset(column), "showTotals": True, "sortOrder": "ASCENDING"}
            for column in (columns or [])
        ]
        pivot_values = [
            {"sourceColumnOffset": offset(column), "summarizeFunction": summary}
            for column in values
        ]

        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"addSheet": {"properties": {"title": target_sheet_name}}},
                ]
            },
        ).execute()
        target_sheet_id = (
            (result.get("replies") or [{}])[0]
            .get("addSheet", {})
            .get("properties", {})
            .get("sheetId")
        )
        if target_sheet_id is None:
            return "Error: could not create the pivot sheet."

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateCells": {
                            "range": {
                                "sheetId": target_sheet_id,
                                "startRowIndex": 0,
                                "startColumnIndex": 0,
                            },
                            "rows": [
                                {
                                    "values": [
                                        {
                                            "pivotTable": {
                                                "source": source_grid,
                                                "rows": pivot_rows,
                                                "columns": pivot_columns,
                                                "values": pivot_values,
                                                "valueLayout": "HORIZONTAL",
                                            }
                                        }
                                    ]
                                }
                            ],
                            "fields": "pivotTable",
                        }
                    }
                ]
            },
        ).execute()
        logger.info("Pivot table created in %s", spreadsheet_id)
        return (
            f"Pivot table created on sheet '{target_sheet_name}': "
            f"{len(pivot_rows)} row field(s), {len(pivot_columns)} column field(s), "
            f"{len(pivot_values)} value field(s) with {summary}."
        )
    except Exception as e:
        return f"Error creating pivot table: {str(e)}"
