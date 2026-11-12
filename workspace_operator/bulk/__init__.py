"""Bulk operations: plan, execute, observe.

The public surface is the six ``bulk_*`` MCP tools. This package is internal.
"""

from .models import ACTIONS, DOMAINS, BulkError, Job, Plan
from .service import (
    cancel_bulk,
    list_bulk,
    plan_bulk,
    result_bulk,
    run_bulk,
    status_bulk,
)

__all__ = [
    "ACTIONS",
    "DOMAINS",
    "BulkError",
    "Job",
    "Plan",
    "cancel_bulk",
    "list_bulk",
    "plan_bulk",
    "result_bulk",
    "run_bulk",
    "status_bulk",
]
