"""Tool-facing facade: plan, run, status, cancel, results, list.

Every public function returns a compact JSON string. The model never receives
a 10,000-row list: plans carry a five-item sample, results are paged, and the
full artifact lives on disk.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..auth import get_creds
from ..config import Config
from ..security import validate_email
from . import engine, selector as selector_module, store
from .models import (
    ACTIONS,
    DOMAIN_MIME,
    DOMAINS,
    DOCS_ACTIONS,
    DRIVE_ACTIONS,
    GMAIL_ACTIONS,
    SHEETS_ACTIONS,
    BulkError,
    Job,
    Plan,
)


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _cap(config: Config, allow_large: bool) -> int:
    default = int(getattr(config, "bulk_max_items", 300) or 300)
    hard = int(getattr(config, "bulk_hard_limit", 10000) or 10000)
    return hard if allow_large else default


def _validate_options(
    domain: str,
    action: str,
    options: Dict[str, Any],
    config: Config,
    logger: logging.Logger,
) -> None:
    if domain == "gmail":
        if action == "label":
            add = [str(item) for item in options.get("add_labels") or [] if str(item).strip()]
            remove = [
                str(item) for item in options.get("remove_labels") or [] if str(item).strip()
            ]
            if not add and not remove:
                raise BulkError("label needs options.add_labels or options.remove_labels")
            creds = get_creds(config)
            options["add_label_ids"] = selector_module.resolve_gmail_labels(
                creds, add, logger
            )
            options["remove_label_ids"] = selector_module.resolve_gmail_labels(
                creds, remove, logger
            )
        return

    if domain in ("docs", "sheets"):
        find = options.get("find")
        if not isinstance(find, str) or find == "":
            raise BulkError(f"{domain} needs options.find")
        replace = options.get("replace")
        if replace is not None and not isinstance(replace, str):
            raise BulkError("options.replace must be a string")
        if domain == "sheets" and options.get("sheet_id") is not None:
            try:
                int(options["sheet_id"])
            except (TypeError, ValueError) as exc:
                raise BulkError("options.sheet_id must be an integer") from exc
        return

    if action == "move":
        target = options.get("target_folder_id")
        if not isinstance(target, str) or not target.strip():
            raise BulkError("move needs options.target_folder_id")
        try:
            meta = (
                build("drive", "v3", credentials=get_creds(config), cache_discovery=False)
                .files()
                .get(fileId=target.strip(), fields="id,mimeType", supportsAllDrives=False)
                .execute()
            )
        except HttpError as exc:
            raise BulkError(f"target folder cannot be read: {exc}") from exc
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            raise BulkError("options.target_folder_id must point at a folder")
    elif action == "rename":
        pattern = options.get("pattern")
        find = options.get("find")
        if not (isinstance(pattern, str) and pattern.strip()) and not (
            isinstance(find, str) and find
        ):
            raise BulkError("rename needs options.pattern or options.find")
    elif action == "share":
        role = str(options.get("role") or "").strip().lower()
        if role not in ("reader", "commenter", "writer"):
            raise BulkError("share needs options.role = reader | commenter | writer")
        permission_type = str(options.get("type") or "user").strip().lower()
        if permission_type not in ("user", "group", "domain", "anyone"):
            raise BulkError("share needs options.type = user | group | domain | anyone")
        if permission_type in ("user", "group"):
            email = str(options.get("email_address") or "").strip()
            if not validate_email(email):
                raise BulkError("share to a user/group needs a valid email_address")
        elif permission_type == "domain":
            if not str(options.get("domain") or "").strip():
                raise BulkError("share to a domain needs options.domain")
        elif not options.get("allow_public"):
            raise BulkError("share to anyone needs allow_public=true")
    elif action == "revoke_public":
        # No options: remove every type=anyone permission per file.
        pass


def plan_bulk(
    config: Config,
    logger: logging.Logger,
    domain: str,
    action: str,
    selector: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
    allow_large: bool = False,
    sample: int = 5,
) -> str:
    selector = selector or {}
    options = options or {}
    domain = (domain or "drive").strip().lower()
    action = (action or "").strip().lower()
    if domain not in DOMAINS:
        return _json({"ok": False, "error": f"unsupported domain '{domain}'"})
    valid_actions = {
        "drive": DRIVE_ACTIONS,
        "gmail": GMAIL_ACTIONS,
        "docs": DOCS_ACTIONS,
        "sheets": SHEETS_ACTIONS,
    }[domain]
    if action not in valid_actions:
        return _json(
            {
                "ok": False,
                "error": f"unsupported action '{action}' for domain '{domain}'",
            }
        )

    try:
        _validate_options(domain, action, options, config, logger)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})

    explicit = [str(value) for value in selector.get("ids") or [] if str(value).strip()]
    if explicit and selector.get("query"):
        return _json(
            {"ok": False, "error": "selector.ids cannot be combined with selector.query"}
        )

    cap = _cap(config, allow_large)
    requested_limit = selector.get("limit")
    if requested_limit is not None:
        try:
            requested_limit = int(requested_limit)
        except (TypeError, ValueError):
            return _json({"ok": False, "error": "selector.limit must be an integer"})
        if requested_limit < 1:
            return _json({"ok": False, "error": "selector.limit must be positive"})
        if requested_limit > cap:
            hint = (
                "raise it with allow_large=true"
                if not allow_large
                else f"the hard cap is {cap}"
            )
            return _json(
                {
                    "ok": False,
                    "error": f"selector.limit {requested_limit} exceeds the cap of {cap}; {hint}",
                }
            )
        cap = requested_limit

    if (
        domain == "drive"
        and selector.get("include_trashed")
        and action in ("trash", "move", "rename", "share", "revoke_public")
    ):
        return _json(
            {"ok": False, "error": "include_trashed is only valid for restore"}
        )

    store.cleanup_plans(config)
    try:
        if domain == "gmail":
            resolved = selector_module.resolve_gmail(
                get_creds(config),
                selector,
                max_items=cap,
                logger=logger,
            )
        else:
            drive_selector = dict(selector)
            if domain in DOMAIN_MIME:
                drive_selector["mime_types"] = [DOMAIN_MIME[domain]]
            resolved = selector_module.resolve_drive(
                get_creds(config),
                drive_selector,
                max_items=cap,
                allow_shared_drives=bool(getattr(config, "bulk_allow_shared_drives", False)),
                protected_ids=getattr(config, "bulk_protected_ids", None),
                protected_patterns=getattr(config, "bulk_protected_patterns", None),
                logger=logger,
            )
    except BulkError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface Google errors compactly
        logger.exception("bulk plan resolution failed")
        return _json({"ok": False, "error": f"cannot resolve selector: {exc}"})

    items = resolved["items"]
    warnings = list(resolved["warnings"])
    if len(items) > cap:
        if not allow_large:
            return _json(
                {
                    "ok": False,
                    "error": (
                        f"more than {cap} files matched; narrow the selector or pass "
                        "allow_large=true"
                    ),
                    "warnings": warnings,
                }
            )
        items = items[:cap]
        warnings.append(f"Plan truncated to the configured hard cap of {cap}.")

    if resolved["truncated"] and not allow_large:
        return _json(
            {
                "ok": False,
                "error": (
                    f"more than {cap} files matched; narrow the selector or pass "
                    "allow_large=true"
                ),
                "warnings": warnings,
            }
        )

    sample_size = max(1, min(int(sample or 5), 20))
    if resolved.get("sample"):
        sample_items = resolved["sample"][:sample_size]
    else:
        sample_items = [
            {
                "id": item["id"],
                "name": item["name"],
                "mimeType": item["mimeType"],
                "size": item["size"],
            }
            for item in items[:sample_size]
        ]
    created = _now()
    ttl = int(getattr(config, "bulk_plan_ttl", 900) or 900)
    plan = Plan(
        id=f"bp_{uuid4().hex[:10]}",
        domain=domain,
        action=action,
        options=options,
        selector=selector,
        created_at=created.isoformat(timespec="seconds"),
        expires_at=(created + timedelta(seconds=ttl)).isoformat(timespec="seconds"),
        items=items,
        warnings=warnings,
    )
    store.save_plan(config, plan)
    total_bytes = sum(int(item.get("size") or 0) for item in items)
    return _json(
        {
            "ok": True,
            "plan_id": plan.id,
            "domain": domain,
            "action": action,
            "matched": len(items),
            "estimated_bytes": total_bytes,
            "sample": sample_items,
            "warnings": warnings,
            "expires_in_seconds": ttl,
            "next": f"bulk_run(plan_id='{plan.id}', confirm=true)",
        }
    )


def run_bulk(
    config: Config,
    logger: logging.Logger,
    plan_id: str,
    confirm: bool = False,
    on_finish: Optional[Callable[[Job], None]] = None,
    job_id: Optional[str] = None,
) -> str:
    if getattr(config, "dry_run", False):
        return _json(
            {"ok": False, "error": "server dry_run is enabled; bulk_run refuses to start"}
        )
    if not confirm:
        return _json(
            {
                "ok": False,
                "error": "confirmation required",
                "message": "Review the plan, then call bulk_run again with confirm=true.",
            }
        )
    try:
        plan = store.load_plan(config, plan_id)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})

    expires = _parse_time(plan.expires_at)
    if expires is None or expires < _now():
        return _json(
            {"ok": False, "error": "plan expired; run bulk_plan again for a fresh snapshot"}
        )

    if not plan.items:
        return _json(
            {"ok": False, "error": "plan is empty; run bulk_plan with a broader selector"}
        )

    if job_id and job_id == plan.id:
        return _json({"ok": False, "error": "job_id must be a bulk job id, not a plan id"})

    try:
        job = engine.start_job(
            config,
            plan,
            logger,
            on_finish=on_finish,
            resume_job_id=job_id or None,
        )
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})
    return _json(
        {
            "ok": True,
            "job_id": job.id,
            "plan_id": plan.id,
            "action": plan.action,
            "total": job.total,
            "state": job.state,
            "next": f"bulk_status(job_id='{job.id}')",
        }
    )


def _undo_spec(job: Job, records: List[Dict[str, Any]]):
    """Build inverse items from a finished job's result records."""
    done = [record for record in records if record.get("status") == "ok"]
    if not done:
        raise BulkError("nothing to undo: the job has no successful items")
    if job.action == "trash":
        items = [
            {
                "id": record["id"],
                "name": record.get("name", ""),
                "size": 0,
                "mimeType": "",
                "trashed": True,
            }
            for record in done
        ]
        return "restore", items
    if job.action == "move":
        items = []
        for record in done:
            parents = record.get("previous_parents")
            if not parents:
                raise BulkError(
                    "this move job has no saved parents; it predates undo support"
                )
            items.append(
                {
                    "id": record["id"],
                    "name": record.get("name", ""),
                    "previous_parents": list(parents),
                    "size": 0,
                    "mimeType": "",
                    "trashed": False,
                }
            )
        return "move_back", items
    if job.action == "rename":
        items = []
        for record in done:
            previous = record.get("previous_name")
            if not previous:
                raise BulkError(
                    "this rename job has no saved names; it predates undo support"
                )
            items.append(
                {
                    "id": record["id"],
                    "name": record.get("name", ""),
                    "previous_name": previous,
                    "size": 0,
                    "mimeType": "",
                    "trashed": False,
                }
            )
        return "rename_back", items
    raise BulkError(f"undo is not supported for '{job.action}' jobs")


def undo_bulk(
    config: Config,
    logger: logging.Logger,
    job_id: str,
    confirm: bool = False,
    on_finish: Optional[Callable[[Job], None]] = None,
) -> str:
    if getattr(config, "dry_run", False):
        return _json(
            {"ok": False, "error": "server dry_run is enabled; bulk_undo refuses to start"}
        )
    if not confirm:
        return _json(
            {
                "ok": False,
                "error": "confirmation required",
                "message": "Call bulk_undo again with confirm=true to revert the job.",
            }
        )
    try:
        job = store.load_job(config, job_id)
        records = store.read_results(config, job_id)
        action, items = _undo_spec(job, records)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})

    created = _now()
    ttl = int(getattr(config, "bulk_plan_ttl", 900) or 900)
    plan = Plan(
        id=f"bp_{uuid4().hex[:10]}",
        domain=job.domain,
        action=action,
        options={"source_job_id": job.id},
        selector={},
        created_at=created.isoformat(timespec="seconds"),
        expires_at=(created + timedelta(seconds=ttl)).isoformat(timespec="seconds"),
        items=items,
    )
    store.save_plan(config, plan)
    try:
        undo_job = engine.start_job(config, plan, logger, on_finish=on_finish)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})
    return _json(
        {
            "ok": True,
            "job_id": undo_job.id,
            "plan_id": plan.id,
            "source_job_id": job.id,
            "action": action,
            "total": undo_job.total,
            "state": undo_job.state,
            "next": f"bulk_status(job_id='{undo_job.id}')",
        }
    )


def status_bulk(config: Config, logger: logging.Logger, job_id: str) -> str:
    try:
        job = store.load_job(config, job_id)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})
    live = engine.is_live(job.id)
    if job.state == "running" and not live:
        job.state = "interrupted"
        store.save_job(config, job)
    payload = job.summary()
    payload["ok"] = True
    payload["live"] = live
    return _json(payload)


def cancel_bulk(config: Config, logger: logging.Logger, job_id: str) -> str:
    try:
        job = engine.cancel_job(config, job_id)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})
    payload = job.summary()
    payload["ok"] = True
    payload["message"] = "cancellation requested; in-flight items will finish"
    return _json(payload)


def result_bulk(
    config: Config,
    logger: logging.Logger,
    job_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    try:
        job = store.load_job(config, job_id)
    except BulkError as exc:
        return _json({"ok": False, "error": str(exc)})
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 50), 200))
    records = store.read_results(config, job_id)
    page: List[Dict[str, Any]] = records[offset : offset + limit]
    failures = sum(1 for record in records if record.get("status") == "failed")
    return _json(
        {
            "ok": True,
            "job_id": job.id,
            "state": job.state,
            "total_records": len(records),
            "failures": failures,
            "offset": offset,
            "limit": limit,
            "items": page,
            "result_file": job.result_file,
            "next_offset": offset + len(page) if offset + len(page) < len(records) else None,
        }
    )


def list_bulk(config: Config, logger: logging.Logger, limit: int = 10) -> str:
    jobs = []
    for data in store.list_jobs(config, limit):
        jobs.append(
            {
                "job_id": data.get("id"),
                "plan_id": data.get("plan_id"),
                "action": data.get("action"),
                "state": data.get("state"),
                "done": data.get("done"),
                "total": data.get("total"),
                "failed": data.get("failed"),
                "updated_at": data.get("updated_at"),
            }
        )
    return _json({"ok": True, "jobs": jobs})
