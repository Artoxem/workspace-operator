"""Execute a bulk plan as a background job.

One process-wide registry tracks cancellation events. Job state and per-item
results are written to disk as the run progresses, so ``bulk_status`` works
from a fresh process and an interrupted job can be resumed.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..auth import get_creds
from ..config import Config
from . import store
from .models import BulkError, Job, Plan

CONTROLS: Dict[str, threading.Event] = {}
THREADS: Dict[str, threading.Thread] = {}
_LOCK = threading.Lock()
_THREAD_LOCAL = threading.local()
RETRYABLE_STATUS = {403, 429, 500, 502, 503, 504}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _api(config: Config, name: str, version: str):
    service = getattr(_THREAD_LOCAL, f"api_{name}_{version}", None)
    if service is None:
        service = build(name, version, credentials=get_creds(config), cache_discovery=False)
        setattr(_THREAD_LOCAL, f"api_{name}_{version}", service)
    return service


def _service(config: Config, allow_shared: bool):
    return _api(config, "drive", "v3")


def _with_retry(operation: Callable[[], Any], logger: logging.Logger, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return operation()
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", 0)
            if status in RETRYABLE_STATUS and attempt < attempts - 1:
                delay = (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning("bulk: retry after HTTP %s in %.1fs", status, delay)
                time.sleep(delay)
                continue
            raise
        except (TimeoutError, ConnectionError) as exc:
            if attempt < attempts - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 0.5))
                continue
            raise exc
    raise BulkError("retry loop exhausted")


def _rename(item: Dict[str, Any], options: Dict[str, Any], index: int) -> str:
    name = item.get("name", "")
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    suffix = f".{extension}" if extension else ""
    pattern = options.get("pattern")
    if isinstance(pattern, str) and pattern.strip():
        candidate = pattern.strip()
        candidate = candidate.replace("{name}", stem)
        candidate = candidate.replace("{ext}", suffix)
        candidate = candidate.replace("{index}", str(index))
        candidate = candidate.replace("{date}", datetime.now().strftime("%Y-%m-%d"))
    else:
        find = options.get("find")
        replace = options.get("replace")
        if not isinstance(find, str) or find == "":
            raise BulkError("rename needs either options.pattern or options.find")
        candidate = name.replace(find, str(replace or ""), 1)
    if "/" in candidate or "\\" in candidate:
        raise BulkError("new name cannot contain path separators")
    if not candidate.strip():
        raise BulkError("new name cannot be empty")
    return candidate


def _apply_item(
    config: Config,
    item: Dict[str, Any],
    action: str,
    options: Dict[str, Any],
    index: int,
    logger: logging.Logger,
    domain: str = "drive",
) -> Dict[str, Any]:
    service = _service(config, allow_shared=False)
    file_id = item["id"]

    if action == "move":
        target = options.get("target_folder_id")
        if not isinstance(target, str) or not target.strip():
            raise BulkError("move needs options.target_folder_id")
        target = target.strip()
        if target in (item.get("parents") or []):
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        parents = ",".join(item.get("parents") or [])
        _with_retry(
            lambda: service.files()
            .update(
                fileId=file_id,
                addParents=target,
                removeParents=parents or None,
                fields="id,parents",
            )
            .execute(),
            logger,
        )
        return {
            "id": file_id,
            "name": item.get("name", ""),
            "previous_parents": list(item.get("parents") or []),
            "status": "ok",
        }

    if action == "trash":
        if item.get("trashed"):
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        _with_retry(
            lambda: service.files()
            .update(fileId=file_id, body={"trashed": True}, fields="id")
            .execute(),
            logger,
        )
        return {"id": file_id, "name": item.get("name", ""), "status": "ok"}

    if action == "restore":
        if not item.get("trashed"):
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        _with_retry(
            lambda: service.files()
            .update(fileId=file_id, body={"trashed": False}, fields="id")
            .execute(),
            logger,
        )
        return {"id": file_id, "name": item.get("name", ""), "status": "ok"}

    if action == "rename":
        new_name = _rename(item, options, index)
        if new_name == item.get("name"):
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        _with_retry(
            lambda: service.files()
            .update(fileId=file_id, body={"name": new_name}, fields="id,name")
            .execute(),
            logger,
        )
        return {
            "id": file_id,
            "name": item.get("name", ""),
            "new_name": new_name,
            "previous_name": item.get("name", ""),
            "status": "ok",
        }

    if action == "move_back":
        previous = list(item.get("previous_parents") or [])
        if not previous:
            raise BulkError("move_back needs previous_parents")
        current = (
            service.files()
            .get(fileId=file_id, fields="parents")
            .execute()
            .get("parents", [])
        )
        if set(current) == set(previous):
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        _with_retry(
            lambda: service.files()
            .update(
                fileId=file_id,
                addParents=",".join(previous),
                removeParents=",".join(current) or None,
                fields="id,parents",
            )
            .execute(),
            logger,
        )
        return {"id": file_id, "name": item.get("name", ""), "status": "ok"}

    if action == "rename_back":
        previous = item.get("previous_name")
        if not previous:
            raise BulkError("rename_back needs previous_name")
        current = (
            service.files()
            .get(fileId=file_id, fields="name")
            .execute()
            .get("name", "")
        )
        if current == previous:
            return {"id": file_id, "name": current, "status": "skipped"}
        _with_retry(
            lambda: service.files()
            .update(fileId=file_id, body={"name": previous}, fields="id,name")
            .execute(),
            logger,
        )
        return {
            "id": file_id,
            "name": current,
            "new_name": previous,
            "previous_name": current,
            "status": "ok",
        }

    if action == "share":
        role = str(options.get("role") or "reader")
        permission_type = str(options.get("type") or "user")
        body: Dict[str, Any] = {"role": role, "type": permission_type}
        if permission_type in ("user", "group"):
            body["emailAddress"] = options.get("email_address")
        elif permission_type == "domain":
            body["domain"] = options.get("domain")
        _with_retry(
            lambda: service.permissions()
            .create(
                fileId=file_id,
                body=body,
                sendNotificationEmail=bool(options.get("send_notification")),
                fields="id",
            )
            .execute(),
            logger,
        )
        return {"id": file_id, "name": item.get("name", ""), "status": "ok"}

    if action == "revoke_public":
        permissions = (
            service.permissions()
            .list(fileId=file_id, fields="permissions(id,type)")
            .execute()
            .get("permissions", [])
        )
        public = [entry for entry in permissions if entry.get("type") == "anyone"]
        if not public:
            return {"id": file_id, "name": item.get("name", ""), "status": "skipped"}
        for entry in public:
            _with_retry(
                lambda permission_id=entry["id"]: service.permissions()
                .delete(fileId=file_id, permissionId=permission_id)
                .execute(),
                logger,
            )
        return {"id": file_id, "name": item.get("name", ""), "status": "ok"}

    if domain in ("docs", "slides") and action == "replace_text":
        find = str(options.get("find") or "")
        replace = str(options.get("replace") or "")
        request = {
            "replaceAllText": {
                "containsText": {
                    "text": find,
                    "matchCase": bool(options.get("match_case")),
                },
                "replaceText": replace,
            }
        }
        if domain == "docs":
            response = _with_retry(
                lambda: _api(config, "docs", "v1")
                .documents()
                .batchUpdate(documentId=file_id, body={"requests": [request]})
                .execute(),
                logger,
            )
        else:
            response = _with_retry(
                lambda: _api(config, "slides", "v1")
                .presentations()
                .batchUpdate(presentationId=file_id, body={"requests": [request]})
                .execute(),
                logger,
            )
        occurrences = sum(
            int(reply.get("replaceAllText", {}).get("occurrencesChanged", 0))
            for reply in response.get("replies", [])
        )
        return {
            "id": file_id,
            "name": item.get("name", ""),
            "occurrences": occurrences,
            "status": "ok",
        }

    if domain == "sheets" and action == "find_replace":
        find = str(options.get("find") or "")
        replace = str(options.get("replace") or "")
        sheet_id = options.get("sheet_id")
        request: Dict[str, Any] = {
            "findReplace": {
                "find": find,
                "replacement": replace,
                "matchCase": bool(options.get("match_case")),
                "allSheets": sheet_id is None,
            }
        }
        if sheet_id is not None:
            request["findReplace"]["sheetId"] = int(sheet_id)
        response = _with_retry(
            lambda: _api(config, "sheets", "v4")
            .spreadsheets()
            .batchUpdate(spreadsheetId=file_id, body={"requests": [request]})
            .execute(),
            logger,
        )
        replies = response.get("replies", [])
        occurrences = int(
            replies[0].get("findReplace", {}).get("occurrencesChanged", 0)
            if replies
            else 0
        )
        return {
            "id": file_id,
            "name": item.get("name", ""),
            "occurrences": occurrences,
            "status": "ok",
        }

    raise BulkError(f"unsupported action '{action}'")


def _gmail_label_changes(action: str, options: Dict[str, Any]):
    if action == "archive":
        return [], ["INBOX"]
    if action == "trash":
        return ["TRASH"], []
    if action == "restore":
        return [], ["TRASH"]
    if action == "mark_read":
        return [], ["UNREAD"]
    if action == "mark_unread":
        return ["UNREAD"], []
    if action == "label":
        return (
            list(options.get("add_label_ids") or []),
            list(options.get("remove_label_ids") or []),
        )
    raise BulkError(f"unsupported Gmail action '{action}'")


def _run_gmail(
    config: Config,
    job: Job,
    plan: Plan,
    logger: logging.Logger,
    on_finish: Optional[Callable[[Job], None]],
) -> None:
    event = CONTROLS.get(job.id)
    skip = store.completed_ids(config, job.id)
    items = [item for item in plan.items if item["id"] not in skip]
    counters = _count_existing(config, job.id)
    job.total = len(plan.items)
    job.done = counters["done"]
    job.ok = counters["ok"]
    job.skipped = counters["skipped"]
    job.failed = counters["failed"]
    store.save_job(config, job)
    add_ids, remove_ids = _gmail_label_changes(plan.action, plan.options)
    cancelled = False
    try:
        service = build("gmail", "v1", credentials=get_creds(config))
        for start in range(0, len(items), 1000):
            if event is not None and event.is_set():
                cancelled = True
                break
            chunk = items[start : start + 1000]
            message_ids = [item["id"] for item in chunk]
            try:
                _with_retry(
                    lambda ids=message_ids: service.users()
                    .messages()
                    .batchModify(
                        userId="me",
                        body={
                            "ids": ids,
                            "addLabelIds": add_ids,
                            "removeLabelIds": remove_ids,
                        },
                    )
                    .execute(),
                    logger,
                )
                records = [
                    {"id": message_id, "name": "", "status": "ok"}
                    for message_id in message_ids
                ]
            except Exception as exc:  # noqa: BLE001 - chunk-level isolation
                logger.warning("bulk Gmail chunk failed: %s", exc)
                records = [
                    {
                        "id": message_id,
                        "name": "",
                        "status": "failed",
                        "error": str(exc),
                    }
                    for message_id in message_ids
                ]
            for record in records:
                store.append_result(config, job.id, record)
                job.done += 1
                if record["status"] == "ok":
                    job.ok += 1
                elif record["status"] == "skipped":
                    job.skipped += 1
                else:
                    job.failed += 1
            store.save_job(config, job)
        job.state = "cancelled" if cancelled else "completed"
        job.finished_at = now_iso()
        store.save_job(config, job)
    except Exception as exc:  # noqa: BLE001 - job-level failure
        logger.exception("bulk Gmail job %s failed: %s", job.id, exc)
        job.state = "failed"
        job.error = str(exc)
        job.finished_at = now_iso()
        store.save_job(config, job)
    finally:
        with _LOCK:
            CONTROLS.pop(job.id, None)
            THREADS.pop(job.id, None)
        if on_finish is not None:
            try:
                on_finish(job)
            except Exception:  # noqa: BLE001
                logger.exception("bulk: finish callback failed")


def _count_existing(config: Config, job_id: str) -> Dict[str, int]:
    counts = {"done": 0, "ok": 0, "skipped": 0, "failed": 0}
    for record in store.read_results(config, job_id):
        counts["done"] += 1
        status = record.get("status")
        if status == "ok":
            counts["ok"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status == "failed":
            counts["failed"] += 1
    return counts


def _run(
    config: Config,
    job: Job,
    plan: Plan,
    logger: logging.Logger,
    on_finish: Optional[Callable[[Job], None]],
) -> None:
    if plan.domain == "gmail":
        return _run_gmail(config, job, plan, logger, on_finish)
    concurrency = max(1, min(int(getattr(config, "bulk_concurrency", 8) or 8), 16))
    event = CONTROLS.get(job.id)
    skip = store.completed_ids(config, job.id)
    items = [item for item in plan.items if item["id"] not in skip]
    counters = _count_existing(config, job.id)
    job.done = counters["done"]
    job.ok = counters["ok"]
    job.skipped = counters["skipped"]
    job.failed = counters["failed"]
    job.total = len(plan.items)
    store.save_job(config, job)

    cancelled = False
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(
                    _apply_item,
                    config,
                    item,
                    plan.action,
                    plan.options,
                    index,
                    logger,
                    plan.domain,
                ): item
                for index, item in enumerate(items, start=1)
            }
            processed = 0
            for future in as_completed(futures):
                if event is not None and event.is_set():
                    cancelled = True
                    for pending in futures:
                        pending.cancel()
                    break
                item = futures[future]
                try:
                    record = future.result()
                except BulkError as exc:
                    record = {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "status": "failed",
                        "error": str(exc),
                    }
                except HttpError as exc:
                    record = {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "status": "failed",
                        "error": f"HTTP {getattr(getattr(exc, 'resp', None), 'status', '?')}: {exc}",
                    }
                except Exception as exc:  # noqa: BLE001 - isolate one bad item
                    record = {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "status": "failed",
                        "error": str(exc),
                    }

                store.append_result(config, job.id, record)
                processed += 1
                job.done += 1
                if record["status"] == "ok":
                    job.ok += 1
                elif record["status"] == "skipped":
                    job.skipped += 1
                else:
                    job.failed += 1
                if processed % 25 == 0:
                    store.save_job(config, job)

        job.state = "cancelled" if cancelled else "completed"
        job.finished_at = now_iso()
        store.save_job(config, job)
    except Exception as exc:  # noqa: BLE001 - job-level failure
        logger.exception("bulk job %s failed: %s", job.id, exc)
        job.state = "failed"
        job.error = str(exc)
        job.finished_at = now_iso()
        store.save_job(config, job)
    finally:
        with _LOCK:
            CONTROLS.pop(job.id, None)
            THREADS.pop(job.id, None)
        if on_finish is not None:
            try:
                on_finish(job)
            except Exception:  # noqa: BLE001 - audit must not break the job
                logger.exception("bulk: finish callback failed")


def start_job(
    config: Config,
    plan: Plan,
    logger: logging.Logger,
    on_finish: Optional[Callable[[Job], None]] = None,
    resume_job_id: Optional[str] = None,
) -> Job:
    if resume_job_id:
        job = store.load_job(config, resume_job_id)
        if job.state not in ("interrupted", "failed", "cancelled"):
            raise BulkError(f"Job '{job.id}' is '{job.state}', nothing to resume.")
        if job.plan_id != plan.id:
            raise BulkError("The resume job does not belong to this plan.")
        job.state = "running"
        job.finished_at = None
        job.error = None
        store.save_job(config, job)
    else:
        job = Job(
            id=f"bj_{uuid4().hex[:10]}",
            plan_id=plan.id,
            domain=plan.domain,
            action=plan.action,
            total=len(plan.items),
            started_at=now_iso(),
        )
        job.result_file = str(store.result_path(config, job.id))
        store.save_job(config, job)

    if not job.result_file:
        job.result_file = str(store.result_path(config, job.id))

    event = threading.Event()
    with _LOCK:
        CONTROLS[job.id] = event
        thread = threading.Thread(
            target=_run,
            args=(config, job, plan, logger, on_finish),
            name=f"bulk-{job.id}",
            daemon=True,
        )
        THREADS[job.id] = thread
    thread.start()
    return job


def cancel_job(config: Config, job_id: str) -> Job:
    job = store.load_job(config, job_id)
    if job.state not in ("running", "cancelling"):
        raise BulkError(f"Job '{job.id}' is '{job.state}' and cannot be cancelled.")
    with _LOCK:
        event = CONTROLS.get(job.id)
    if event is None:
        # The thread is gone (server restarted): mark it interrupted.
        job.state = "interrupted"
        store.save_job(config, job)
        raise BulkError(
            f"Job '{job.id}' is no longer running (interrupted); resume it instead."
        )
    event.set()
    job.state = "cancelling"
    store.save_job(config, job)
    return job


def is_live(job_id: str) -> bool:
    with _LOCK:
        return job_id in CONTROLS
