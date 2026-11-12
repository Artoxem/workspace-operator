"""Thin handlers for the bulk tools.

The engine lives in :mod:`workspace_operator.bulk`; these wrappers keep the
server dispatch table consistent with the other domains.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from ..bulk import service
from ..bulk.models import Job
from ..config import Config


def bulk_plan_handler(
    config: Config,
    logger: logging.Logger,
    domain: str = "drive",
    action: str = "move",
    selector: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
    allow_large: bool = False,
    sample: int = 5,
) -> str:
    return service.plan_bulk(
        config,
        logger,
        domain=domain,
        action=action,
        selector=selector,
        options=options,
        allow_large=allow_large,
        sample=sample,
    )


def bulk_run_handler(
    config: Config,
    logger: logging.Logger,
    plan_id: str,
    confirm: bool = False,
    on_finish: Optional[Callable[[Job], None]] = None,
    job_id: Optional[str] = None,
) -> str:
    return service.run_bulk(
        config,
        logger,
        plan_id=plan_id,
        confirm=confirm,
        on_finish=on_finish,
        job_id=job_id,
    )


def bulk_status_handler(config: Config, logger: logging.Logger, job_id: str) -> str:
    return service.status_bulk(config, logger, job_id)


def bulk_cancel_handler(config: Config, logger: logging.Logger, job_id: str) -> str:
    return service.cancel_bulk(config, logger, job_id)


def bulk_result_handler(
    config: Config,
    logger: logging.Logger,
    job_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    return service.result_bulk(config, logger, job_id, offset=offset, limit=limit)


def bulk_list_handler(
    config: Config, logger: logging.Logger, limit: int = 10
) -> str:
    return service.list_bulk(config, logger, limit=limit)


def bulk_undo_handler(
    config: Config,
    logger: logging.Logger,
    job_id: str,
    confirm: bool = False,
    on_finish: Optional[Callable[[Job], None]] = None,
) -> str:
    return service.undo_bulk(
        config, logger, job_id=job_id, confirm=confirm, on_finish=on_finish
    )
