"""Google Forms handlers."""

import logging
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build

from ..auth import get_creds
from ..config import Config


def _service(config: Config):
    return build("forms", "v1", credentials=get_creds(config), cache_discovery=False)


def _question_requests(questions: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
    requests = []
    for offset, question in enumerate(questions):
        if not isinstance(question, dict):
            raise ValueError("each question must be an object")
        title = str(question.get("title") or "").strip()
        if not title:
            raise ValueError("each question needs a title")
        item: Dict[str, Any] = {
            "title": title,
            "questionItem": {
                "question": {
                    "required": bool(question.get("required")),
                    "textQuestion": {},
                }
            },
        }
        description = question.get("description")
        if description:
            item["description"] = str(description)
        requests.append(
            {
                "createItem": {
                    "item": item,
                    "location": {"index": start_index + offset},
                }
            }
        )
    return requests


def forms_create_handler(
    config: Config,
    logger: logging.Logger,
    title: str,
    description: Optional[str] = None,
) -> str:
    try:
        if not title or not str(title).strip():
            return "Error: title is required."
        service = _service(config)
        form = (
            service.forms()
            .create(body={"info": {"title": str(title).strip()}})
            .execute()
        )
        form_id = form.get("formId")
        if description:
            service.forms().batchUpdate(
                formId=form_id,
                body={
                    "requests": [
                        {
                            "updateFormInfo": {
                                "info": {"description": str(description)},
                                "updateMask": "description",
                            }
                        }
                    ]
                },
            ).execute()
        return (
            f"Form created: {title} (ID: {form_id})\n"
            f"Open: {form.get('responderUri', '')}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("forms_create failed: %s", exc)
        return f"Error: cannot create form: {exc}"


def forms_add_questions_handler(
    config: Config,
    logger: logging.Logger,
    form_id: str,
    questions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    try:
        questions = questions or []
        if not form_id:
            return "Error: form_id is required."
        if not questions:
            return "Error: questions is required."
        service = _service(config)
        form = service.forms().get(formId=form_id).execute()
        start = len(form.get("items", []))
        requests = _question_requests(questions, start)
        service.forms().batchUpdate(
            formId=form_id, body={"requests": requests}
        ).execute()
        return f"Added {len(requests)} question(s) to form {form_id}."
    except Exception as exc:  # noqa: BLE001
        logger.error("forms_add_questions failed: %s", exc)
        return f"Error: cannot add questions: {exc}"


def forms_get_handler(config: Config, logger: logging.Logger, form_id: str) -> str:
    try:
        if not form_id:
            return "Error: form_id is required."
        service = _service(config)
        form = service.forms().get(formId=form_id).execute()
        info = form.get("info", {})
        lines = [
            f"Form: {info.get('title', '(untitled)')} (ID: {form.get('formId')})",
            f"Responder link: {form.get('responderUri', '')}",
        ]
        if info.get("description"):
            lines.append(f"Description: {info['description']}")
        items = form.get("items", [])
        if not items:
            lines.append("No questions yet.")
        for index, item in enumerate(items, start=1):
            question = (item.get("questionItem") or {}).get("question") or {}
            required = " (required)" if question.get("required") else ""
            question_id = question.get("questionId", "")
            lines.append(
                f"{index}. {item.get('title', '(untitled)')}{required} [questionId: {question_id}]"
            )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("forms_get failed: %s", exc)
        return f"Error: cannot read form: {exc}"


def _answer_values(answer: Dict[str, Any]) -> List[str]:
    text = (answer.get("textAnswers") or {}).get("answers") or []
    values = [str(entry.get("value", "")) for entry in text if entry.get("value") is not None]
    if values:
        return values
    file_upload = answer.get("fileUploadAnswers") or {}
    files = file_upload.get("answers") or []
    return [str(entry.get("fileId", "")) for entry in files if entry.get("fileId")]


def forms_list_responses_handler(
    config: Config,
    logger: logging.Logger,
    form_id: str,
    max_results: int = 50,
) -> str:
    try:
        if not form_id:
            return "Error: form_id is required."
        service = _service(config)
        form = service.forms().get(formId=form_id).execute()
        titles = {}
        for item in form.get("items", []):
            question = (item.get("questionItem") or {}).get("question") or {}
            if question.get("questionId"):
                titles[question["questionId"]] = item.get("title", "")
        response = (
            service.forms()
            .responses()
            .list(formId=form_id, pageSize=max(1, min(int(max_results or 50), 100)))
            .execute()
        )
        responses = response.get("responses", [])
        if not responses:
            return "No responses yet."
        lines = [f"Responses for form {form_id}: {len(responses)}"]
        for entry in responses:
            lines.append(
                f"- {entry.get('createTime', '')} (response {entry.get('responseId', '')})"
            )
            for question_id, answer in (entry.get("answers") or {}).items():
                values = _answer_values(answer)
                if values:
                    lines.append(
                        f"    {titles.get(question_id, question_id)}: {', '.join(values)}"
                    )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.error("forms_list_responses failed: %s", exc)
        return f"Error: cannot list responses: {exc}"
