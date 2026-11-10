"""Sheets: data validation, protected ranges and borders."""

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

BORDER_STYLES = {"SOLID", "DOTTED", "DASHED", "SOLID_MEDIUM", "SOLID_THICK", "NONE"}
SIDES = ("top", "bottom", "left", "right", "innerHorizontal", "innerVertical")


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


def set_data_validation_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    values: Optional[List[str]] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    strict: bool = True,
    input_message: str = "",
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        if values:
            condition: Dict[str, Any] = {
                "type": "ONE_OF_LIST",
                "values": [
                    {"userEnteredValue": str(item)} for item in values
                ],
            }
            label = f"list of {len(values)} value(s)"
        elif minimum is not None and maximum is not None:
            condition = {
                "type": "NUMBER_BETWEEN",
                "values": [
                    {"userEnteredValue": str(minimum)},
                    {"userEnteredValue": str(maximum)},
                ],
            }
            label = f"number between {minimum} and {maximum}"
        else:
            return "Error: pass values (list) or both minimum and maximum."

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, range_name
        )
        grid = _grid_range(sheet["sheetId"], parse_a1_range(range_name))
        rule = {
            "condition": condition,
            "strict": bool(strict),
            "showCustomUi": True,
        }
        if input_message:
            rule["inputMessage"] = input_message

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"setDataValidation": {"range": grid, "rule": rule}}
                ]
            },
        ).execute()
        logger.info("Data validation set on %s", range_name)
        return f"Data validation set on {range_name}: {label} (strict={strict})."
    except Exception as e:
        return f"Error setting data validation: {str(e)}"


def protect_range_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    description: str = "",
    warning_only: bool = True,
    editors: Optional[List[str]] = None,
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, range_name
        )
        grid = _grid_range(sheet["sheetId"], parse_a1_range(range_name))
        protected: Dict[str, Any] = {
            "range": grid,
            "description": description or f"Protected {range_name}",
            "warningOnly": bool(warning_only),
        }
        if editors:
            protected["editors"] = {"users": [str(item) for item in editors]}

        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"addProtectedRange": {"protectedRange": protected}}
                ]
            },
        ).execute()
        protected_id = (
            (result.get("replies") or [{}])[0]
            .get("addProtectedRange", {})
            .get("protectedRange", {})
            .get("protectedRangeId")
        )
        logger.info("Protected range %s", range_name)
        mode = "warning only" if warning_only else "locked"
        return (
            f"Protected {range_name} ({mode}, ID: {protected_id})."
        )
    except Exception as e:
        return f"Error protecting range: {str(e)}"


def set_borders_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: str,
    style: str = "SOLID",
    color: str = "#000000",
    sides: Optional[List[str]] = None,
    sheet_name: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_name:
            return "Error: spreadsheet_id and range_name are required."

        border_style = style.upper()
        if border_style not in BORDER_STYLES:
            return "Error: style must be one of " + ", ".join(sorted(BORDER_STYLES))

        chosen = [side for side in (sides or SIDES) if side in SIDES]
        if not chosen:
            return "Error: sides must contain " + ", ".join(SIDES)

        service = _sheets(config)
        sheet = _resolve_sheet(
            _properties(service, spreadsheet_id), sheet_name, range_name
        )
        grid = _grid_range(sheet["sheetId"], parse_a1_range(range_name))
        border = {"style": border_style}
        if border_style != "NONE":
            border["colorStyle"] = {"rgbColor": hex_to_color(color)}

        request: Dict[str, Any] = {"range": grid}
        for side in chosen:
            request[side] = border

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"updateBorders": request}]},
        ).execute()
        return f"Borders applied to {range_name}: {border_style} on {', '.join(chosen)}."
    except Exception as e:
        return f"Error applying borders: {str(e)}"
