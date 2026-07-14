"""Lifecycle tracking for every decision-facing plan simulation execution."""

from __future__ import annotations

import inspect
from contextvars import ContextVar
from functools import wraps
from typing import Any, Awaitable, Callable

current_simulation_run_id: ContextVar[str | None] = ContextVar(
    "current_simulation_run_id",
    default=None,
)


async def execute_tracked_simulation(
    *,
    workspace: Any,
    plan_id: str,
    source: str,
    input_payload: dict[str, Any],
    operation: Callable[[], Awaitable[Any]],
) -> Any:
    run = workspace.start_simulation_run(
        plan_id,
        source=source,
        input_payload=input_payload,
    )
    run_id = str(run["id"])
    token = current_simulation_run_id.set(run_id)
    try:
        result = await operation()
        result_payload = _json_payload(result)
        result_payload["simulation_run_id"] = run_id
        workspace.finish_simulation_run(
            plan_id,
            run_id,
            status="completed",
            result_payload=result_payload,
        )
        if hasattr(result, "model_copy"):
            return result.model_copy(update={"simulation_run_id": run_id})
        if isinstance(result, dict):
            return {**result, "simulation_run_id": run_id}
        return result
    except Exception as exc:
        workspace.finish_simulation_run(
            plan_id,
            run_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        current_simulation_run_id.reset(token)


def _json_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def track_simulation_run(source: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Track an async route as a complete synchronous Simulation Run."""

    def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        signature = inspect.signature(fn)

        @wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind_partial(*args, **kwargs)
            plan_id = str(bound.arguments.get("plan_id") or "").strip()
            services = bound.arguments.get("services")
            request = bound.arguments.get("request")
            workspace = getattr(services, "plan_workspace", None)
            if not plan_id or workspace is None:
                return await fn(*args, **kwargs)

            return await execute_tracked_simulation(
                workspace=workspace,
                plan_id=plan_id,
                source=source,
                input_payload=_json_payload(request),
                operation=lambda: fn(*args, **kwargs),
            )

        return wrapped

    return decorate
