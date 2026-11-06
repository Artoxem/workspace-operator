"""Composite tool: diff two tables by a key column.

Useful for reconciliation of any two sheets — price lists, catalogues, inventories,
exports before and after a change. Sources are two ranges, possibly in
different spreadsheets; the diff is a pure function over plain rows.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text
from .doc_tables import create_document_with_blocks

MAX_DIFF_ROWS = 400
DEFAULT_KEY = "1"


def _resolve_key(header: List[str], key_column: str, width: int) -> int:
    raw = str(key_column).strip()
    if raw.isdigit():
        index = int(raw) - 1
        if not 0 <= index < width:
            raise ValueError(f"key_column index out of range: {key_column}")
        return index
    lowered = raw.lower()
    for index, name in enumerate(header):
        if name.lower() == lowered:
            return index
    raise ValueError(f"unknown key column: {key_column}")


def diff_tables(
    rows_a: Sequence[Sequence[str]],
    rows_b: Sequence[Sequence[str]],
    key_column: str = DEFAULT_KEY,
    header: bool = True,
) -> Dict[str, Any]:
    """Compare two tables by a key column.

    Returns counts plus ``added``/``removed``/``changed`` lists. Columns are
    matched by header name; if either side has no header, positions are used.
    """
    a = [list(row) for row in rows_a]
    b = [list(row) for row in rows_b]
    if not a or not b:
        raise ValueError("both tables must contain at least a header row")

    width = max(max(len(row) for row in a), max(len(row) for row in b))
    names_a = [clean_text(cell) for cell in a[0]] if header else []
    names_b = [clean_text(cell) for cell in b[0]] if header else []
    header_names = (names_a or names_b) + [
        f"column {index + 1}" for index in range(width)
    ]
    header_names = header_names[:width]

    key_index = _resolve_key(header_names, key_column, width)
    key_name = header_names[key_index]

    def to_map(rows: List[List[str]]) -> Dict[str, List[str]]:
        data = rows[1:] if header else rows
        mapping: Dict[str, List[str]] = {}
        for row in data:
            padded = row + [""] * (width - len(row))
            key = clean_text(padded[key_index])
            if not key:
                continue
            mapping.setdefault(key, [clean_text(cell) for cell in padded])
        return mapping

    map_a = to_map(a)
    map_b = to_map(b)

    columns = [index for index in range(width) if index != key_index]
    added = [key for key in map_b if key not in map_a]
    removed = [key for key in map_a if key not in map_b]

    changed: List[Dict[str, Any]] = []
    for key in map_a:
        if key not in map_b:
            continue
        before = map_a[key]
        after = map_b[key]
        differences = []
        for index in columns:
            old = before[index] if index < len(before) else ""
            new = after[index] if index < len(after) else ""
            if old != new:
                differences.append(
                    {
                        "column": header_names[index],
                        "before": old,
                        "after": new,
                    }
                )
        if differences:
            changed.append({"key": key, "changes": differences})

    return {
        "key": key_name,
        "columns": [header_names[index] for index in columns],
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len([key for key in map_a if key in map_b]) - len(changed),
        "rows_a": len(map_a),
        "rows_b": len(map_b),
    }


def render_diff(diff: Dict[str, Any], limit: int = MAX_DIFF_ROWS) -> str:
    lines = [
        f"Compare by '{diff['key']}': {diff['rows_a']} row(s) vs {diff['rows_b']}",
        f"added: {len(diff['added'])} | removed: {len(diff['removed'])} | "
        f"changed: {len(diff['changed'])} | unchanged: {diff['unchanged']}",
        "",
    ]

    def bullet(title: str, items: List[str]) -> None:
        lines.append(f"{title} ({len(items)})")
        if not items:
            lines.append("- none")
        for item in items[:limit]:
            lines.append(f"- {item}")
        if len(items) > limit:
            lines.append(f"... {len(items) - limit} more")
        lines.append("")

    bullet("Added", diff["added"])
    bullet("Removed", diff["removed"])

    lines.append(f"Changed ({len(diff['changed'])})")
    if not diff["changed"]:
        lines.append("- none")
    for entry in diff["changed"][:limit]:
        details = "; ".join(
            f"{change['column']}: {change['before']} → {change['after']}"
            for change in entry["changes"][:5]
        )
        if len(entry["changes"]) > 5:
            details += f"; +{len(entry['changes']) - 5} more"
        lines.append(f"- {entry['key']}: {details}")
    if len(diff["changed"]) > limit:
        lines.append(f"... {len(diff['changed']) - limit} more")

    return "\n".join(lines)


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


def compare_tables_handler(
    config: Config,
    logger: logging.Logger,
    spreadsheet_id: str,
    range_a: str,
    range_b: str,
    other_spreadsheet_id: Optional[str] = None,
    key_column: str = DEFAULT_KEY,
    header: bool = True,
    output: str = "text",
    doc_title: Optional[str] = None,
) -> str:
    try:
        if not spreadsheet_id or not range_a or not range_b:
            return "Error: spreadsheet_id, range_a and range_b are required."

        mode = str(output or "text").lower()
        if mode not in {"text", "doc"}:
            return "Error: output must be 'text' or 'doc'."

        creds = get_creds(config)
        sheets = build("sheets", "v4", credentials=creds)

        rows_a = _read_range(sheets, spreadsheet_id, range_a)
        rows_b = _read_range(sheets, other_spreadsheet_id or spreadsheet_id, range_b)
        if not rows_a or not rows_b:
            return "Error: one of the ranges is empty — nothing to compare."

        diff = diff_tables(rows_a, rows_b, key_column=key_column, header=header)
        content = render_diff(diff)

        stats = (
            f"added {len(diff['added'])}, removed {len(diff['removed'])}, "
            f"changed {len(diff['changed'])}"
        )
        if mode == "text":
            logger.info("Tables compared: sheet=%s %s", spreadsheet_id, stats)
            return content

        title = doc_title or f"Diff {range_a} vs {range_b} {datetime.now(timezone.utc):%Y-%m-%d}"

        added_rows = [["Added"], *[[key] for key in diff["added"][:MAX_DIFF_ROWS]]]
        removed_rows = [["Removed"], *[[key] for key in diff["removed"][:MAX_DIFF_ROWS]]]
        changed_rows = [["Key", "Column", "Before", "After"]]
        for entry in diff["changed"][:MAX_DIFF_ROWS]:
            for change in entry["changes"]:
                changed_rows.append(
                    [entry["key"], change["column"], change["before"], change["after"]]
                )

        blocks = [
            (
                "text",
                f"{title}\n\nCompared by '{diff['key']}': "
                f"{diff['rows_a']} vs {diff['rows_b']} row(s).\n"
                f"added {len(diff['added'])}, removed {len(diff['removed'])}, "
                f"changed {len(diff['changed'])}, unchanged {diff['unchanged']}\n",
            ),
            ("text", "Added"),
            ("table", added_rows),
            ("text", "Removed"),
            ("table", removed_rows),
            ("text", "Changed"),
            ("table", changed_rows),
        ]
        document_id = create_document_with_blocks(config, logger, title, blocks)
        return (
            f"Diff document created: {title}\n"
            f"Document ID: {document_id}\n"
            f"URL: https://docs.google.com/document/d/{document_id}/edit\n{stats}"
        )
    except Exception as e:
        return f"Error comparing tables: {str(e)}"
