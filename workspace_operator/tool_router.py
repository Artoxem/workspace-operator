"""Tool-call pipeline: resolve, validate, approve, execute, report.

``ToolRouter.handle`` is the body of the MCP ``tools/call`` request. It used to be
a single 270-line closure inside ``create_server``; the steps are methods now and
share their state through the instance. Each step either returns a finished
``CallToolResult`` (an early exit) or ``None`` to continue, so the order of the
checks, the messages and the audit records are exactly the ones the closure had.
``tests/test_call_tool_branches.py`` pins them.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from datetime import datetime
from types import ModuleType
from typing import Any, Dict, Mapping, Optional, Tuple

import mcp.types as types

from .approvals import ApprovalError, ApprovalStore, challenge_text, summarize
from .bulk import service as bulk_service
from .bulk import store as bulk_store
from .bulk.models import BulkError, Plan
from .config import Config
from .dispatch import build_handlers
from .handlers import files as drive_files
from .operations import BinaryResult
from .results import ToolError, ToolResult, is_error_text
from .review import prepare_review
from .runtime import AuditLog, call_with_retry
from .security import require_token_configured
from .text import humanize_http_error
from .toolset import REMOVED_ALIAS_NAMES, RoutingError, resolve_call
from .toolset.models import CallPlan, Safety, ToolSpec


def _error(text: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], is_error=True
    )


def _message(text: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


class ToolRouter:
    """State and steps of one server's tool-call path."""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        *,
        tool_index: Mapping[str, ToolSpec],
        aliases: Mapping[str, Tuple[str, Optional[str]]],
        audit: AuditLog,
        approvals: ApprovalStore,
        profile_name: str,
        handler_module: ModuleType,
    ) -> None:
        self.config = config
        self.logger = logger
        self.tool_index = tool_index
        self.aliases = aliases
        self.audit = audit
        self.approvals = approvals
        self.profile_name = profile_name
        # Handlers are looked up by name in this module at call time, so tests that
        # patch a handler there keep working (see dispatch.build_handlers).
        self.handler_module = handler_module

    # ------------------------------------------------------------------ steps

    def _announce_to_operator(self, record: Dict[str, Any]) -> None:
        """Show the operator how to decide, in the server log only.

        The link carries the secret. It is written to the server's own log (the
        operator's console), never into the tool result the agent reads.
        """
        if self.config.approval_browser_wait:
            self.logger.info("APPROVAL PENDING %s (browser mode)", record["id"])
            return
        try:
            link = self.approvals.human_link(
                record["id"], getattr(self.config, "approval_url", None)
            )
        except Exception:  # noqa: BLE001 - announcing must never break a call
            link = None
        target = link or f"workspace-operator approvals link {record['id']}"
        self.logger.warning(
            "APPROVAL PENDING %s: %s — decide in your browser: %s",
            record["id"],
            record.get("summary", ""),
            target,
        )

    async def _elicit_approval(
        self, ctx: Any, name: str, plan: CallPlan, argument_names: Tuple[str, ...]
    ) -> Optional[str]:
        """Ask the human in the client UI when the client supports elicitation."""
        if ctx is None:
            return None
        try:
            capabilities = getattr(ctx.session, "client_capabilities", None)
            elicitation = getattr(capabilities, "elicitation", None)
            if getattr(elicitation, "form", None) is None:
                return None
            summary = summarize(name, plan.action, plan.arguments)
            result = await ctx.session.elicit_form(
                message=(
                    "Approve this destructive Workspace Operator action?\n\n"
                    f"{summary}\n\n"
                    "The action will run once and is bound to these arguments."
                ),
                requested_schema={
                    "type": "object",
                    "properties": {
                        "approve": {
                            "type": "boolean",
                            "title": "Approve",
                            "description": "Run this exact destructive action.",
                        }
                    },
                    "required": ["approve"],
                },
                related_request_id=getattr(ctx, "request_id", None),
            )
            if result.action == "accept" and (result.content or {}).get("approve") is True:
                return "approved"
            if result.action == "accept":
                return "declined"
            return "declined" if result.action == "decline" else "cancelled"
        except Exception as exc:  # noqa: BLE001 - fallback must never break a call
            self.logger.warning(
                "Elicitation unavailable, falling back to approval_id: %s", exc
            )
            return None

    def _find_spec(
        self, name: str, arguments: Dict[str, Any]
    ) -> Tuple[Optional[ToolSpec], Dict[str, Any], Optional[types.CallToolResult]]:
        """Map a name to a tool spec, following legacy aliases.

        Returns ``(spec, arguments, early_result)``; ``early_result`` is set when the
        call must stop here (hidden by the profile, removed, or unknown).
        """
        spec = self.tool_index.get(name)
        if spec is None and name in self.aliases:
            target, action = self.aliases[name]
            spec = self.tool_index.get(target)
            if spec is None:
                return None, arguments, _error(
                    f"Tool '{name}' maps to '{target}', which is hidden by "
                    f"the active profile ({self.profile_name}) or by scope routing."
                )
            if action:
                arguments = dict(arguments or {})
                arguments["action"] = action
            self.logger.info(
                "Legacy alias %s -> %s%s", name, target, f":{action}" if action else ""
            )
        if spec is None:
            if name in REMOVED_ALIAS_NAMES:
                return None, arguments, _error(
                    f"Tool '{name}' was removed in Workspace Operator 2.0. "
                    "See docs/MIGRATION_2.0.md for the replacement."
                )
            self.logger.warning("Blocked tool call outside profile: %s", name)
            return None, arguments, _error(
                f"Tool '{name}' is disabled by the active tool profile "
                f"({self.profile_name}). Adjust tool_profile, allowed_tools or "
                "denied_tools in config.yaml to enable it."
            )
        return spec, arguments, None

    def _dry_run(
        self, name: str, argument_names: Tuple[str, ...]
    ) -> types.CallToolResult:
        self.logger.info("Dry run: %s was not executed", name)
        self.audit.record(name, self.profile_name, "dry-run", 0, argument_names)
        return _message(
            f"DRY RUN: '{name}' was not executed. "
            f"Arguments: {sorted(argument_names)}. "
            "Unset dry_run / MCP_DRY_RUN to apply changes."
        )

    async def _authorise(
        self,
        ctx: Any,
        name: str,
        plan: CallPlan,
        argument_names: Tuple[str, ...],
        *, review: Optional[Dict[str, Any]] = None, snapshot_digest: Optional[str] = None,
    ) -> Optional[types.CallToolResult]:
        """Human approval for a destructive call; ``None`` means "approved, go on"."""
        audit, profile_name, approvals = self.audit, self.profile_name, self.approvals
        browser_wait = self.config.approval_browser_wait
        # Compact elicitation has no full preview; reviewed operations use the queue.
        elicitation = None if browser_wait or review is not None or snapshot_digest is not None else await self._elicit_approval(
            ctx, name, plan, argument_names
        )
        if elicitation == "approved":
            plan.arguments["confirm"] = True
            audit.record(name, profile_name, "approved-in-chat", 0, argument_names)
            return None
        if elicitation in ("declined", "cancelled"):
            audit.record(name, profile_name, f"approval-{elicitation}", 0, argument_names)
            return _message(
                "The user did not approve this action; nothing was "
                "changed. Do not retry unless the user asks."
            )
        try:
            approval_id = plan.arguments.get("approval_id")
            if not approval_id:
                record = approvals.request(
                    name, plan.action, plan.arguments, review=review, snapshot_digest=snapshot_digest
                )
                audit.record(
                    name,
                    profile_name,
                    "approval-required",
                    0,
                    argument_names + ("approval_id",),
                )
                self._announce_to_operator(record)
                if browser_wait:
                    deadline = time.monotonic() + browser_wait
                    while True:
                        status = approvals.get(record["id"])["status"]
                        if status == "approved":
                            approval_id = record["id"]
                            break
                        if status != "pending":
                            return _message(
                                f"Approval is {status}. This call did not run. Do not retry."
                            )
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        await asyncio.sleep(min(0.25, remaining))
                if not approval_id:
                    message = challenge_text(record)
                    if browser_wait:
                        message += " If no browser tab opened, the operator's browser helper may not be running."
                    return _message(message)
            ok, reason = approvals.consume(
                str(approval_id), name, plan.action, plan.arguments,
                review=review, snapshot_digest=snapshot_digest,
            )
            if not ok:
                audit.record(
                    name,
                    profile_name,
                    "approval-rejected",
                    0,
                    argument_names,
                    error=reason,
                )
                if browser_wait:
                    return _message(f"Approval could not be used: {reason} The action did not run.")
                record = approvals.request(
                    name, plan.action, plan.arguments, review=review, snapshot_digest=snapshot_digest
                )
                self._announce_to_operator(record)
                return _message(
                    f"Approval could not be used: {reason}\n\n"
                    + challenge_text(record)
                )
            plan.arguments["confirm"] = True
            return None
        except ApprovalError as exc:
            audit.record(
                name, profile_name, "approval-error", 0, argument_names, error=str(exc)
            )
            return _error(f"Approval error: {exc}. The action was not executed.")

    def _record_bulk_finish(self, tool_name: str, job: Any) -> None:
        try:
            start = datetime.fromisoformat(job.started_at).timestamp()
            end = (
                datetime.fromisoformat(job.finished_at).timestamp()
                if job.finished_at
                else time.time()
            )
            duration = max(0, int((end - start) * 1000))
        except Exception:  # noqa: BLE001 - audit must never break a job
            duration = 0
        status = (
            "ok"
            if job.state == "completed"
            else ("cancelled" if job.state == "cancelled" else "error")
        )
        self.audit.record(
            tool_name,
            self.profile_name,
            status,
            duration,
            ("plan_id", "confirm", "job_id"),
            error=job.error,
        )

    async def _execute(
        self,
        name: str,
        plan: CallPlan,
        argument_names: Tuple[str, ...],
        started: float,
        *, upload_review: Optional[Dict[str, Any]] = None, bulk_snapshot: Optional[Plan] = None,
    ) -> types.CallToolResult:
        config, logger = self.config, self.logger
        try:
            require_token_configured(config.mcp_auth_token)

            handlers = build_handlers(
                self.handler_module,
                config,
                logger,
                {
                    "_on_bulk_finish": lambda job: self._record_bulk_finish("bulk_run", job),
                    "_on_undo_finish": lambda job: self._record_bulk_finish("bulk_undo", job),
                },
            )

            if upload_review is not None:
                # A Drive create is not idempotent; do not retry the whole approval.
                result = await asyncio.to_thread(
                    drive_files.execute_prepared_drive_upload, config, logger, upload_review
                )
            elif bulk_snapshot is not None:
                result = await asyncio.to_thread(
                    self.handler_module.bulk_run_handler, config, logger, bulk_snapshot.id,
                    True, lambda job: self._record_bulk_finish("bulk_run", job),
                    plan.arguments.get("job_id"), plan_snapshot=bulk_snapshot,
                )
            else:
                if plan.legacy_name not in handlers or plan.legacy_name == "bulk_run":
                    raise ValueError(f"Unknown or unprepared tool: {plan.legacy_name}")
                result = await asyncio.to_thread(
                    call_with_retry,
                    lambda: handlers[plan.legacy_name](plan.arguments),
                    config.retry_attempts,
                    logger=logger,
                )

            if isinstance(result, BinaryResult):
                return types.CallToolResult(
                    content=[
                        types.EmbeddedResource(
                            type="resource",
                            resource=types.BlobResourceContents(
                                uri=result.uri,
                                mime_type=result.mime_type,
                                blob=base64.b64encode(result.data).decode(),
                            ),
                        )
                    ]
                )

            if isinstance(result, ToolResult):
                text, is_error = result.text, result.is_error
            else:
                text = str(result)
                # Legacy handlers report recoverable failures as "Error ..." strings;
                # turn those into a protocol-level isError so clients can react to
                # them, and strip googleapiclient's raw <HttpError ...> dumps.
                is_error = is_error_text(text)
            if is_error:
                text = humanize_http_error(text)
            self.audit.record(
                name,
                self.profile_name,
                "error" if is_error else "ok",
                int((time.perf_counter() - started) * 1000),
                argument_names,
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                is_error=is_error,
            )

        except ToolError as e:
            # A deliberate, user-facing failure: the message is the output.
            self.audit.record(
                name,
                self.profile_name,
                "error",
                int((time.perf_counter() - started) * 1000),
                argument_names,
                error=str(e),
            )
            return _error(str(e))

        except Exception as e:
            self.audit.record(
                name,
                self.profile_name,
                "exception",
                int((time.perf_counter() - started) * 1000),
                argument_names,
                error=str(e),
            )
            logger.exception("Tool call error [%s]: %s", name, e)
            return _error(f"Error: {humanize_http_error(e)}")

    # ------------------------------------------------------------------ entry

    async def handle(
        self, name: str, arguments: Optional[Dict[str, Any]], ctx: Any = None
    ) -> types.CallToolResult:
        if not arguments:
            arguments = {}
        if name == "move_file" or (name == "drive_write" and arguments.get("action") == "move"):
            return _error(
                "Direct Drive move was removed. Use bulk_plan(domain='drive', action='move', "
                "selector={'ids': [...]}, options={'target_folder_id': '…'}), then bulk_run. "
                "No files were moved."
            )

        spec, arguments, early = self._find_spec(name, arguments)
        if early is not None:
            return early
        if spec is None:  # pragma: no cover - _find_spec returns an early result
            return _error(f"Tool '{name}' is not available in this profile.")

        try:
            plan = resolve_call(
                spec,
                arguments,
                require_confirm=not self.config.dry_run
                and spec.safety is not Safety.DESTRUCTIVE,
            )
        except RoutingError as exc:
            self.audit.record(
                name,
                self.profile_name,
                "invalid",
                0,
                tuple((arguments or {}).keys()),
                error=str(exc),
            )
            return _error(str(exc))

        is_read_only = spec.safety is Safety.READ
        argument_names = tuple(plan.arguments.keys())
        if plan.action:
            argument_names = argument_names + ("action",)
        started = time.perf_counter()

        if self.config.dry_run and not is_read_only:
            return self._dry_run(name, argument_names)

        review: Optional[Dict[str, Any]] = None
        snapshot: Optional[Plan] = None
        digest: Optional[str] = None
        reviewed_upload = plan.legacy_name == "drive_upload"
        try:
            if reviewed_upload or plan.legacy_name == "bulk_run":
                require_token_configured(self.config.mcp_auth_token)
            if reviewed_upload:
                review = await asyncio.to_thread(
                    drive_files.prepare_drive_upload,
                    self.config, plan.arguments["local_path"],
                    **{key: plan.arguments.get(key) for key in ("name", "parent_id", "mime_type", "convert_to")},
                )
            elif plan.legacy_name == "bulk_run":
                plan_id = plan.arguments.get("plan_id")
                if not isinstance(plan_id, str) or not plan_id:
                    raise BulkError("bulk_run needs a valid plan_id. Run bulk_plan first.")
                snapshot = await asyncio.to_thread(bulk_store.load_plan, self.config, plan_id)
                digest = bulk_store.plan_digest(snapshot)
                if snapshot.domain == "drive" and snapshot.action == "move":
                    review = bulk_service.move_review(snapshot)
            else:
                review, _ = await asyncio.to_thread(
                    prepare_review, self.config, plan.legacy_name, plan.arguments, self.logger
                )
        except Exception as exc:  # metadata reads and local validation precede all approval/execution
            reason = humanize_http_error(exc)
            self.audit.record(name, self.profile_name, "preview-error", 0, argument_names, error=reason)
            return _error(f"Could not prepare the operation: {reason}")

        if spec.safety is Safety.DESTRUCTIVE or review is not None or snapshot is not None:
            denied = await self._authorise(ctx, name, plan, argument_names, review=review, snapshot_digest=digest)
            if denied is not None:
                return denied

        return await self._execute(
            name, plan, argument_names, started, upload_review=review if reviewed_upload else None,
            bulk_snapshot=snapshot,
        )
