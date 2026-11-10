"""Gmail labels and bulk message flags."""

import logging
from typing import List

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config

LABEL_FIELDS = "labels(id,name,type,messageListVisibility,labelListVisibility,messagesTotal)"


def _gmail(config: Config):
    return build("gmail", "v1", credentials=get_creds(config))


def list_labels_handler(config: Config, logger: logging.Logger) -> str:
    try:
        result = _gmail(config).users().labels().list(userId="me").execute()
        labels = result.get("labels", [])
        if not labels:
            return "No labels found."

        system = [item for item in labels if item.get("type") == "system"]
        user = [item for item in labels if item.get("type") != "system"]
        lines = [f"Labels ({len(labels)}):"]
        if user:
            lines.append("\nUser labels:")
            lines.extend(f"- {item.get('name')} (ID: {item.get('id')})" for item in user)
        if system:
            lines.append("\nSystem labels:")
            lines.extend(f"- {item.get('name')} (ID: {item.get('id')})" for item in system)
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing labels: {str(e)}"


def create_label_handler(
    config: Config,
    logger: logging.Logger,
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
) -> str:
    try:
        if not name:
            return "Error: name is required."

        body = {
            "name": name,
            "labelListVisibility": label_list_visibility,
            "messageListVisibility": message_list_visibility,
        }
        created = (
            _gmail(config)
            .users()
            .labels()
            .create(userId="me", body=body)
            .execute()
        )
        logger.info("Created Gmail label %s", name)
        return (
            f"Label created: {created.get('name')} (ID: {created.get('id')})\n"
            "Apply it with gmail_label_apply."
        )
    except Exception as e:
        return f"Error creating label: {str(e)}"


def modify_messages_handler(
    config: Config,
    logger: logging.Logger,
    message_ids: List[str],
    add_labels: List[str] = None,
    remove_labels: List[str] = None,
    dry_run: bool = True,
) -> str:
    """Apply or remove labels (system labels cover read/unread and star)."""
    try:
        if not message_ids:
            return "Error: message_ids is required."
        if not add_labels and not remove_labels:
            return "Error: pass add_labels and/or remove_labels."

        add = [str(item) for item in (add_labels or [])]
        remove = [str(item) for item in (remove_labels or [])]

        if dry_run:
            return (
                f"DRY RUN — {len(message_ids)} message(s) would change.\n"
                f"add: {', '.join(add) or '—'}\n"
                f"remove: {', '.join(remove) or '—'}\n\n"
                "Call again with dry_run=false to apply."
            )

        _gmail(config).users().messages().batchModify(
            userId="me",
            body={
                "ids": [str(item) for item in message_ids],
                "addLabelIds": add,
                "removeLabelIds": remove,
            },
        ).execute()
        logger.info(
            "Modified %s messages (add=%s remove=%s)",
            len(message_ids),
            len(add),
            len(remove),
        )
        return (
            f"Updated {len(message_ids)} message(s): "
            f"added {len(add)} label(s), removed {len(remove)}."
        )
    except Exception as e:
        return f"Error modifying messages: {str(e)}"
