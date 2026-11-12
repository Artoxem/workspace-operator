"""Google Tasks handlers."""

import logging
from typing import Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config


def _service(config: Config):
    return build("tasks", "v1", credentials=get_creds(config), cache_discovery=False)


def tasks_list_lists_handler(config: Config, logger: logging.Logger) -> str:
    try:
        service = _service(config)
        response = service.tasklists().list(maxResults=100).execute()
        items = response.get("items", [])
        if not items:
            return "No task lists found."
        lines = ["Task lists:"]
        for item in items:
            lines.append(f"- {item.get('title', '(untitled)')} (ID: {item.get('id')})")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("tasks_list_lists failed: %s", exc)
        return f"Error: cannot list task lists: {exc}"


def tasks_list_handler(
    config: Config,
    logger: logging.Logger,
    tasklist_id: str = "@default",
    show_completed: bool = False,
    max_results: int = 50,
) -> str:
    try:
        service = _service(config)
        response = (
            service.tasks()
            .list(
                tasklist=tasklist_id or "@default",
                showCompleted=bool(show_completed),
                maxResults=max(1, min(int(max_results or 50), 100)),
            )
            .execute()
        )
        items = response.get("items", [])
        if not items:
            return "No tasks found."
        lines = [f"Tasks in {tasklist_id or '@default'}:"]
        for item in items:
            status = "x" if item.get("status") == "completed" else " "
            due = item.get("due")
            due_text = f" — due {due[:10]}" if isinstance(due, str) else ""
            lines.append(
                f"- [{status}] {item.get('title', '(untitled)')}{due_text} (ID: {item.get('id')})"
            )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("tasks_list failed: %s", exc)
        return f"Error: cannot list tasks: {exc}"


def tasks_create_handler(
    config: Config,
    logger: logging.Logger,
    title: str,
    notes: Optional[str] = None,
    due: Optional[str] = None,
    tasklist_id: str = "@default",
) -> str:
    try:
        if not title or not str(title).strip():
            return "Error: title is required."
        body = {"title": str(title).strip()}
        if notes:
            body["notes"] = str(notes)
        if due:
            body["due"] = str(due)
        service = _service(config)
        task = (
            service.tasks()
            .insert(tasklist=tasklist_id or "@default", body=body)
            .execute()
        )
        return (
            f"Task created: {task.get('title')} (ID: {task.get('id')}) "
            f"in {tasklist_id or '@default'}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("tasks_create failed: %s", exc)
        return f"Error: cannot create task: {exc}"


def tasks_complete_handler(
    config: Config,
    logger: logging.Logger,
    task_id: str,
    tasklist_id: str = "@default",
) -> str:
    try:
        if not task_id:
            return "Error: task_id is required."
        service = _service(config)
        task = (
            service.tasks()
            .patch(
                tasklist=tasklist_id or "@default",
                task=task_id,
                body={"status": "completed"},
            )
            .execute()
        )
        return f"Task completed: {task.get('title')} (ID: {task.get('id')})"
    except Exception as exc:  # noqa: BLE001
        logger.error("tasks_complete failed: %s", exc)
        return f"Error: cannot complete task: {exc}"
