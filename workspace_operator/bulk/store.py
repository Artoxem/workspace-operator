"""On-disk storage for bulk plans, jobs and result artifacts.

Everything is a small JSON document written atomically (temporary file then
``os.replace``) so a killed process never leaves a truncated plan behind.
Results are JSON Lines so a 10,000-item job can be read page by page.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..config import Config
from .models import BulkError, Job, Plan

_IO_LOCK = threading.RLock()
REPLACE_ATTEMPTS = 6


def bulk_root(config: Config) -> Path:
    configured = getattr(config, "bulk_dir", None) or os.environ.get("MCP_BULK_DIR")
    root = Path(configured).expanduser() if configured else Path("data") / "bulk"
    return root.resolve()


def _plans_dir(config: Config) -> Path:
    return bulk_root(config) / "plans"


def _jobs_dir(config: Config) -> Path:
    return bulk_root(config) / "jobs"


def _results_dir(config: Config) -> Path:
    return bulk_root(config) / "results"


def ensure_dirs(config: Config) -> None:
    for directory in (_plans_dir(config), _jobs_dir(config), _results_dir(config)):
        directory.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically, tolerating short-lived readers on Windows."""
    with _IO_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary, path)
                    return
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            if os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    with _IO_LOCK:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None


def plan_path(config: Config, plan_id: str) -> Path:
    return _plans_dir(config) / f"{plan_id}.json"


def save_plan(config: Config, plan: Plan) -> None:
    ensure_dirs(config)
    write_json_atomic(plan_path(config, plan.id), plan.to_dict())


def load_plan(config: Config, plan_id: str) -> Plan:
    data = read_json(plan_path(config, plan_id))
    if data is None:
        raise BulkError(
            f"Unknown or expired plan '{plan_id}'. Run bulk_plan again to build a fresh plan."
        )
    return Plan.from_dict(data)


def job_path(config: Config, job_id: str) -> Path:
    return _jobs_dir(config) / f"{job_id}.json"


def save_job(config: Config, job: Job) -> None:
    ensure_dirs(config)
    job.updated_at = _now_iso()
    write_json_atomic(job_path(config, job.id), job.to_dict())


def load_job(config: Config, job_id: str) -> Job:
    data = read_json(job_path(config, job_id))
    if data is None:
        raise BulkError(f"Unknown job '{job_id}'.")
    return Job.from_dict(data)


def result_path(config: Config, job_id: str) -> Path:
    return _results_dir(config) / f"{job_id}.jsonl"


def append_result(config: Config, job_id: str, record: Dict[str, Any]) -> None:
    ensure_dirs(config)
    with result_path(config, job_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def read_results(config: Config, job_id: str) -> List[Dict[str, Any]]:
    path = result_path(config, job_id)
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return records


def completed_ids(config: Config, job_id: str) -> set:
    """Ids that already reached a terminal per-item state, for resume."""
    done = set()
    for record in read_results(config, job_id):
        if record.get("status") in ("ok", "skipped") and record.get("id"):
            done.add(record["id"])
    return done


def list_jobs(config: Config, limit: int = 10) -> List[Dict[str, Any]]:
    directory = _jobs_dir(config)
    if not directory.exists():
        return []
    entries = []
    for path in directory.glob("*.json"):
        data = read_json(path)
        if data is not None:
            entries.append(data)
    entries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return entries[: max(1, min(limit, 50))]


def cleanup_plans(config: Config, now: Optional[float] = None) -> int:
    """Delete expired plan files; returns how many were removed."""
    directory = _plans_dir(config)
    if not directory.exists():
        return 0
    current = now or time.time()
    removed = 0
    for path in directory.glob("*.json"):
        data = read_json(path)
        if data is None:
            continue
        expires = data.get("expires_at")
        if not isinstance(expires, str):
            continue
        try:
            from datetime import datetime

            moment = datetime.fromisoformat(expires).timestamp()
        except ValueError:
            continue
        if moment < current:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
