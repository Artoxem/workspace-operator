"""Composite tool: turn a spreadsheet range into an analysis + document.

Design goals (universality first):

* no assumptions about the owner's data — every column, header and number format
  is handled generically;
* the interesting parts are pure functions (parsing, statistics, rendering), so
  the whole pipeline is unit-testable without Google;
* the tool can return plain text (``output="text"``) instead of creating a file,
  which makes it usable for a quick look without side effects.

Parameters exist for the cases where defaults are wrong: ``header``, ``decimal``,
``columns`` and ``aggregates``.
"""

import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text

MAX_STATS_ROWS = 5000
PREVIEW_ROWS = 25
CELL_LIMIT = 40
DEFAULT_AGGREGATES = ("sum", "avg", "min", "max")


def to_number(value: str, decimal: str = "auto") -> Optional[float]:
    """Parse a formatted cell into a float.

    ``decimal``: ``auto`` accepts both ``1,234.50`` and ``1 234,50``; ``comma``
    treats a lone comma as the decimal separator; ``dot`` strips commas as
    thousands separators.
    """
    text = clean_text(value).replace("\u00a0", " ").strip()
    if not text:
        return None

    text = text.replace(" ", "").replace("€", "").replace("$", "").replace("%", "")
    if not text:
        return None

    if decimal == "comma":
        text = text.replace(".", "").replace(",", ".")
    elif decimal == "dot":
        text = text.replace(",", "")
    else:  # auto
        if text.count(",") == 1 and "." not in text:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def _select_columns(
    header: List[str], rows: List[List[str]], columns: Optional[Sequence[str]]
) -> tuple[List[str], List[List[str]]]:
    """Subset table by column names or 1-based indexes."""
    if not columns:
        return header, rows

    indexes: List[int] = []
    for selector in columns:
        raw = str(selector).strip()
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(header):
                indexes.append(index)
                continue
            raise ValueError(f"column index out of range: {selector}")
        lowered = raw.lower()
        for index, name in enumerate(header):
            if name.lower() == lowered:
                indexes.append(index)
                break
        else:
            raise ValueError(f"unknown column: {selector}")

    return (
        [header[index] for index in indexes],
        [[row[index] if index < len(row) else "" for index in indexes] for row in rows],
    )


def summarise_columns(
    rows: Sequence[Sequence[str]],
    header: bool = True,
    decimal: str = "auto",
    columns: Optional[Sequence[str]] = None,
    aggregates: Sequence[str] = DEFAULT_AGGREGATES,
) -> Dict[str, Any]:
    """Describe a table: header, column kinds and numeric aggregates."""
    if not rows:
        return {"header": [], "rows": 0, "columns": [], "aggregates": list(aggregates)}

    raw = [list(row) for row in rows]
    names = [clean_text(cell) for cell in raw[0]] if header else []
    data = raw[1:] if header else raw

    width = max([len(names)] + [len(row) for row in data]) if data else len(names)
    names += [f"column {index + 1}" for index in range(len(names), width)]
    data = [row + [""] * (width - len(row)) for row in data]

    names, data = _select_columns(names, data, columns)

    described: List[Dict[str, Any]] = []
    for index, name in enumerate(names):
        values = [clean_text(row[index]) for row in data]
        non_empty = [value for value in values if value]
        numbers = [
            number
            for number in (to_number(value, decimal) for value in non_empty)
            if number is not None
        ]
        numeric = bool(non_empty) and len(numbers) >= max(1, len(non_empty) * 0.5)

        column: Dict[str, Any] = {
            "name": name,
            "kind": "number" if numeric else "text",
            "non_empty": len(non_empty),
            "unique": len(set(non_empty)),
        }
        if numeric and numbers:
            stats = {
                "sum": sum(numbers),
                "avg": sum(numbers) / len(numbers),
                "min": min(numbers),
                "max": max(numbers),
                "median": statistics.median(numbers),
                "count": float(len(numbers)),
            }
            for aggregate in aggregates:
                if aggregate in stats:
                    column[aggregate] = stats[aggregate]
        described.append(column)

    return {
        "header": names,
        "rows": len(data),
        "columns": described,
        "aggregates": list(aggregates),
    }


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
                max(
                    len(clean_text(row[index])) if index < len(row) else 0
                    for row in selected
                )
                or 1,
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
        lines.append(
            " | ".join(
                _pad(row[i] if i < len(row) else "", widths[i]) for i in range(columns)
            )
        )
    return "\n".join(lines)


def render_report(
    title: str,
    source: str,
    range_name: str,
    rows: Sequence[Sequence[str]],
    max_rows: int = PREVIEW_ROWS,
    header: bool = True,
    decimal: str = "auto",
    columns: Optional[Sequence[str]] = None,
    aggregates: Sequence[str] = DEFAULT_AGGREGATES,
) -> str:
    summary = summarise_columns(rows, header, decimal, columns, aggregates)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    aggregate_headers = [name.capitalize() for name in aggregates]
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
        "| Column | Type | Non-empty | Unique | " + " | ".join(aggregate_headers) + " |",
        "|---|---|---:|---:|" + "---:|" * len(aggregates),
    ]

    for column in summary["columns"]:
        cells = [
            column["name"],
            column["kind"],
            str(column["non_empty"]),
            str(column["unique"]),
        ]
        for aggregate in aggregates:
            value = column.get(aggregate)
            cells.append(f"{value:.2f}" if isinstance(value, float) else "—")
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "Data", ""]
    preview = rows if header else rows
    lines.append(render_table(preview, limit=max_rows))
    if len(preview) > max_rows:
        lines.append(f"... {len(preview) - max_rows} more row(s) not shown")

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
    header: bool = True,
    decimal: str = "auto",
    columns: Optional[Sequence[str]] = None,
    aggregates: Optional[Sequence[str]] = None,
    output: str = "doc",
) -> str:
    try:
        if not spreadsheet_id:
            return "Error: spreadsheet_id is required."

        chosen_aggregates = [str(item).lower() for item in (aggregates or DEFAULT_AGGREGATES)]
        mode = str(output or "doc").lower()
        if mode not in {"doc", "text"}:
            return "Error: output must be 'doc' or 'text'."

        creds = get_creds(config)
        sheets = build("sheets", "v4", credentials=creds)

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
            header=header,
            decimal=decimal,
            columns=columns,
            aggregates=chosen_aggregates,
        )

        summary = summarise_columns(
            values[: MAX_STATS_ROWS + 1], header, decimal, columns, chosen_aggregates
        )
        stats = f"Rows: {summary['rows']} | columns: {len(summary['columns'])}"

        if mode == "text":
            logger.info("Report rendered as text: sheet=%s rows=%s", spreadsheet_id, summary["rows"])
            return f"{content}\n\n{stats} (text mode, no document created)"

        docs = build("docs", "v1", credentials=creds)
        document = docs.documents().create(body={"title": title}).execute()
        document_id = document.get("documentId")
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

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
            f"{stats}"
        )
    except Exception as e:
        return f"Error building report: {str(e)}"
