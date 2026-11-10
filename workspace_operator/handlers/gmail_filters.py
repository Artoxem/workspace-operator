"""Gmail filters: list and create."""

import logging
from typing import List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config


def _gmail(config: Config):
    return build("gmail", "v1", credentials=get_creds(config))


def list_filters_handler(config: Config, logger: logging.Logger) -> str:
    try:
        result = _gmail(config).users().settings().filters().list(userId="me").execute()
        filters = result.get("filter", []) or result.get("filters", [])
        if not filters:
            return "No filters configured."

        lines = [f"Filters ({len(filters)}):"]
        for item in filters:
            criteria = item.get("criteria") or {}
            action = item.get("action") or {}
            conditions = ", ".join(
                f"{key}={value}" for key, value in criteria.items() if value
            ) or "—"
            changes = ", ".join(
                f"{key}={value}" for key, value in action.items() if value
            ) or "—"
            lines.append(f"- {item.get('id')} · if {conditions} → {changes}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing filters: {str(e)}"


def create_filter_handler(
    config: Config,
    logger: logging.Logger,
    from_address: str = "",
    subject: str = "",
    query: str = "",
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> str:
    try:
        criteria = {}
        if from_address:
            criteria["from"] = from_address
        if subject:
            criteria["subject"] = subject
        if query:
            criteria["query"] = query
        if not criteria:
            return "Error: pass at least one of from_address, subject or query."

        action = {}
        if add_labels:
            action["addLabelIds"] = [str(item) for item in add_labels]
        if remove_labels:
            action["removeLabelIds"] = [str(item) for item in remove_labels]
        if not action:
            return "Error: pass add_labels and/or remove_labels."

        created = (
            _gmail(config)
            .users()
            .settings()
            .filters()
            .create(userId="me", body={"criteria": criteria, "action": action})
            .execute()
        )
        logger.info("Gmail filter created: %s", created.get("id"))
        return (
            f"Filter created (ID: {created.get('id')})\n"
            f"Criteria: {criteria}\nAction: {action}"
        )
    except Exception as e:
        return f"Error creating filter: {str(e)}"
