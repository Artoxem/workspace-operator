"""Composite tool: turn a spreadsheet range into a Google Doc report.

One call does what an agent would otherwise do in six: read the values, compute
column statistics, render a readable report and create the document.

The analysis and rendering are pure functions, so the interesting behaviour is
unit-testable without credentials.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

MAX_STATS_ROWS = 2000
PREVIEW_ROWS = 25
CELL_LIMIT = 40


def to_number(value: str) -> Optional[float]:
    """Parse a formatted cell into a float, or return None for non-numbers."""
    text = clean_text(value).replace("\u00a0", " ").strip()
    if not text:
        return None
    text = text.replace(" ", "").replace("€", "").replace("$", "").replace("%", "")
    if text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def summarise_columns(rows: Sequence[Sequence[str]]) -> Dict[str, Any]:
    """Describe a table: header, column kinds and numeric aggregates."""
    if not rows:
        return {"header": [], "rows": 0, "columns": []}

    header = [clean_text(cell) for cell in rows[0]]
    data = [list(row) for row in rows[1:]]
    width = max([len(header)] + [len(row) for row in data]) if data else len(header)
    header += [f"column {index + 1}" for index in range(len(header), width)]

    columns: List[Dict[str, Any]] = []
    for index in range(width):
        values = [row[index] for row in data if index < len(row)]
        non_empty = [clean_text(value) for value in values if clean_text(value)]
        numbers = [number for number in (to_number(value) for value in non_empty) if number is not None]
        numeric = bool(non_empty) and len(numbers) >= max(1, len(non_empty) * 0.5)

        column: Dict[str, Any] = {
            "name": header[index],
            "kind": "number" if numeric else "text",
            "non_empty": len(non_empty),
            "unique": len(set(non_empty)),
        }
        if numeric and numbers:
            column.update(
                {
                    "sum": sum(numbers),
                    "avg": sum(numbers) / len(numbers),
                    "min": min(numbers),
                    "max": max(numbers),
                }
            )
        columns.append(column)

    return {"header": header, "rows": len(data), "columns": columns}


def _pad(value: str, width: int) -> str:
    text = clean_text(value)
    if len(text) > width:
        text = text[: width - 1] + "…"
    return text.ljust(width)


def render_table(rows: Sequence[Sequence[str]], limit: Optional[int] = None) -> str:
    """Render rows as a fixed-width text table."""
    selected = list(rows[:limit]) if limit else list(rows)
    if not selected:
        return "(no data)"

    columns = max(len(row) for row in selected)
    widths = []
    for index in range(columns):
        widths.append(
            min(
                CELL_LIMIT,
                max(len(clean_text(row[index])) if index < len(row) else 0 for row in selected) or 1,
            )
        )

    header = selected[0]
    lines = [
        " | ".join(
            _pad(header[i] if i < len(header) else "", widths[i]) for i in range(columns)
        )
    ]
    lines.append("-+-".join("-" * width for width in widths))
    for row in selected[1:]:
        lines.append(" | ".join(_pad(row[i] if i < len(row) else "", widths[i]) for i in range(columns)))
    return "\n".join(lines)


def render_report(
    title: str,
    source: str,
    range_name: str,
    rows: Sequence[Sequence[str]],
    max_rows: int = PREVIEW_ROWS,
) -> str:
    summary = summarise_columns(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        title,
        "",
        f"Source: {source}",
        f"Range: {range_name}",
        f"Generated: {stamp}",
        "",
        "Summary",
        f"  rows: {summary['rows']}",
        f"  columns: {len(summary['columns'])}",
        "",
        "| Column | Type | Non-empty | Unique | Sum | Avg | Min | Max |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for column in summary["columns"]:
        if column["kind"] == "number":
            cells = [
                column["name"],
                "number",
                str(column["non_empty"]),
                str(column["unique"]),
                f"{column['sum']:.2f}",
                f"{column['avg']:.2f}",
                f"{column['min']:.2f}",
                f"{column['max']:.2f}",
            ]
        else:
            cells = [
                column["name"],
                "text",
                str(column["non_empty"]),
                str(column["unique"]),
                "—",
                "—",
                "—",
                "—",
            ]
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "Data", ""]
    lines.append(render_table(rows, limit=max_rows))
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more row(s) not shown")

    return "\n".join(lines)


def _first_sheet_range(service, spreadsheet_id: str) -> str:
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
        .execute()
    )
    sheets = meta.get("sheets", [])
    if not sheets:
        raise ValueError("the spreadsheet has no sheets")
    return sheets[0]["properties"]["title"]


def report_from_sheet_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_name: Optional[str] = None,
    doc_title: Optional[str] = None,
    max_rows: int = PREVIEW_ROWS,
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."

        creds = get_creds(config)
        sheets = build("sheets", "v4", credentials=creds)
        docs = build("docs", "v1", credentials=creds)

        target_range = range_name or _first_sheet_range(sheets, spreadsheet_id)
        values = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=target_range)
            .execute()
            .get("values", [])
        )
        if not values:
            return f"Error: range '{target_range}' is empty — nothing to report."

        title = doc_title or f"Report {target_range} {datetime.now(timezone.utc):%Y-%m-%d}"
        content = render_report(
            title=title,
            source=spreadsheet_id,
            range_name=target_range,
            rows=values[: MAX_STATS_ROWS + 1],
            max_rows=int(max_rows),
        )

        document = docs.documents().create(body={"title": title}).execute()
        document_id = document.get("documentId")
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

        summary = summarise_columns(values[: MAX_STATS_ROWS + 1])
        logger.info(
            "Report created: sheet=%s range=%s doc=%s rows=%s",
            spreadsheet_id,
            target_range,
            document_id,
            summary["rows"],
        )
        return (
            f"Report created: {title}\n"
            f"Document ID: {document_id}\n"
            f"URL: https://docs.google.com/document/d/{document_id}/edit\n"
            f"Rows: {summary['rows']} | columns: {len(summary['columns'])}"
        )
    except Exception as e:
        return f"Error building report: {str(e)}"
