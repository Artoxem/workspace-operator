"""Drive comments: read, create, reply and resolve threads.

The Drive comments API works for Google Docs, Sheets and Slides.
"""

import logging
from typing import Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config
from ..text import clean_text, format_timestamp

COMMENT_FIELDS = (
    "comments(id,content,author(displayName,emailAddress),createdTime,modifiedTime,"
    "resolved,quotedFileContent(value),"
    "replies(id,content,author(displayName,emailAddress),createdTime,action))"
)


def _drive(config: Config):
    return build("drive", "v3", credentials=get_creds(config))


def _author(node: dict) -> str:
    author = node.get("author") or {}
    return author.get("displayName") or author.get("emailAddress") or "unknown"


def list_comments_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    include_resolved: bool = True,
) -> str:
    try:
        if not file_id:
            return "Error: file_id is required."

        result = (
            _drive(config)
            .comments()
            .list(
                fileId=file_id,
                fields=COMMENT_FIELDS,
                pageSize=100,
                includeDeleted=False,
            )
            .execute()
        )
        comments = result.get("comments", [])
        if not include_resolved:
            comments = [item for item in comments if not item.get("resolved")]

        if not comments:
            return "No comments on this file."

        blocks = [f"Comments ({len(comments)}):"]
        for item in comments:
            state = " [resolved]" if item.get("resolved") else ""
            quoted = (item.get("quotedFileContent") or {}).get("value")
            blocks.append(
                f"\n- {_author(item)} · {format_timestamp(item.get('createdTime'))}{state}\n"
                f"  {clean_text(item.get('content') or '')[:400]}"
                + (f"\n  quoted: “{clean_text(quoted)[:120]}”" if quoted else "")
            )
            for reply in item.get("replies", []):
                action = reply.get("action")
                marker = "resolved" if action == "resolve" else "reply"
                blocks.append(
                    f"    ↳ {_author(reply)} ({marker}): "
                    f"{clean_text(reply.get('content') or '')[:300]}"
                )
        return "\n".join(blocks)
    except Exception as e:
        return f"Error listing comments: {str(e)}"


def create_comment_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    content: str,
    quoted_text: Optional[str] = None,
) -> str:
    try:
        if not file_id or not content:
            return "Error: file_id and content are required."

        body = {"content": content}
        if quoted_text:
            body["quotedFileContent"] = {"value": quoted_text}

        created = (
            _drive(config)
            .comments()
            .create(fileId=file_id, body=body, fields="id,content,createdTime")
            .execute()
        )
        logger.info("Created comment %s on %s", created.get("id"), file_id)
        return (
            f"Comment created (ID: {created.get('id')})\n"
            f"{clean_text(created.get('content') or '')[:300]}"
        )
    except Exception as e:
        return f"Error creating comment: {str(e)}"


def reply_comment_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    comment_id: str,
    content: str,
) -> str:
    try:
        if not (file_id and comment_id and content):
            return "Error: file_id, comment_id and content are required."

        reply = (
            _drive(config)
            .replies()
            .create(
                fileId=file_id,
                commentId=comment_id,
                body={"content": content},
                fields="id,content,createdTime",
            )
            .execute()
        )
        return (
            f"Reply added to comment {comment_id} (ID: {reply.get('id')})\n"
            f"{clean_text(reply.get('content') or '')[:300]}"
        )
    except Exception as e:
        return f"Error replying to comment: {str(e)}"


def resolve_comment_handler(
    config: Config,
    logger: logging.Logger,
    file_id: str,
    comment_id: str,
    confirm: bool = False,
) -> str:
    try:
        if not (file_id and comment_id):
            return "Error: file_id and comment_id are required."

        if not confirm:
            return (
                "CONFIRMATION REQUIRED\n\n"
                f"Resolve comment {comment_id} on file {file_id}.\n"
                "The thread stays visible but is marked resolved.\n"
                "Call again with confirm=true to proceed."
            )

        drive = _drive(config)
        # The API replaces the resource, so keep the original content.
        current = (
            drive.comments()
            .get(fileId=file_id, commentId=comment_id, fields="content")
            .execute()
        )
        drive.comments().update(
            fileId=file_id,
            commentId=comment_id,
            body={"content": current.get("content") or "", "resolved": True},
            fields="id,resolved",
        ).execute()
        return f"Comment {comment_id} resolved."
    except Exception as e:
        return f"Error resolving comment: {str(e)}"
