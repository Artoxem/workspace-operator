"""Resolve a tool call to a legacy handler and validated arguments."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .models import CallPlan, Safety, ToolSpec


class RoutingError(ValueError):
    """A call that cannot be routed safely."""

    def __init__(self, message: str, *, code: str = "invalid_call") -> None:
        super().__init__(message)
        self.code = code


class ConfirmationRequired(RoutingError):
    """A destructive call without explicit confirmation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="confirmation_required")


def resolve_call(
    tool: ToolSpec,
    arguments: Mapping[str, Any] | None,
    *,
    require_confirm: bool = True,
) -> CallPlan:
    """Validate ``arguments`` and return the handler call plan.

    Direct specs pass their arguments through unchanged. Consolidated specs
    require an ``action``, enforce action-level ``confirm`` and keep the
    original argument mapping (handlers ignore unrelated keys).
    """
    args: Dict[str, Any] = dict(arguments or {})

    if tool.is_direct:
        if (
            require_confirm
            and tool.requires_confirm
            and args.get("confirm") is not True
        ):
            raise ConfirmationRequired(
                f"Tool '{tool.name}' changes data. Call it again with confirm=true."
            )
        return CallPlan(tool=tool, legacy_name=tool.legacy or tool.name, arguments=args)

    action_name = args.pop("action", None)
    if not action_name or not isinstance(action_name, str):
        raise RoutingError(
            f"Tool '{tool.name}' requires an 'action'. "
            f"Available actions: {', '.join(tool.action_names)}.",
            code="missing_action",
        )

    try:
        action = tool.action(action_name)
    except KeyError:
        raise RoutingError(
            f"Unknown action '{action_name}' for '{tool.name}'. "
            f"Available actions: {', '.join(tool.action_names)}.",
            code="unknown_action",
        ) from None

    missing = [name for name in action.required if name not in args]
    if missing:
        raise RoutingError(
            f"Action '{action_name}' requires: {', '.join(missing)}.",
            code="missing_argument",
        )

    requires_confirm = action.confirm or tool.safety is Safety.DESTRUCTIVE
    if require_confirm and requires_confirm and args.get("confirm") is not True:
        raise ConfirmationRequired(
            f"Action '{action_name}' changes data. Call it again with "
            "confirm=true after reviewing the scope."
        )

    return CallPlan(
        tool=tool,
        legacy_name=action.legacy,
        arguments=args,
        action=action.name,
    )
