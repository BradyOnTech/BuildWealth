"""Shared calculation policy and degraded-response envelope helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

ENGINE_STATUS_OK: Literal["ok"] = "ok"
ENGINE_STATUS_DEGRADED: Literal["degraded"] = "degraded"

FALLBACK_METHOD_CONTRACT_VERSION_GUARD = "contract_version_guard"
FALLBACK_METHOD_LOCAL_CALCULATION = "local_calculation"


@dataclass(frozen=True)
class EngineCallDisposition:
    use_calculation_adapter: bool
    mode: Literal["use_calculation_adapter", "guarded", "disabled", "adapter_missing", "local_only"]
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    warning: str | None = None


def resolve_engine_call_disposition(
    *,
    engine_label: str,
    calculation_adapter_enabled: bool,
    calculation_adapter: Any | None,
    contract_guard_reason: str | None = None,
    disabled_behavior: Literal["degraded_fallback", "local_ok"] = "degraded_fallback",
    adapter_missing_behavior: Literal["degraded_fallback", "local_ok"] | None = None,
) -> EngineCallDisposition:
    """Resolve whether a service should call an optional calculator or use the local path.

    disabled_behavior and adapter_missing_behavior control whether local mode should be
    treated as normal (`local_ok`) or explicit degraded fallback (`degraded_fallback`).
    """

    adapter_behavior = adapter_missing_behavior or disabled_behavior
    label = str(engine_label or "Engine").strip() or "Engine"

    if contract_guard_reason:
        return EngineCallDisposition(
            use_calculation_adapter=False,
            mode="guarded",
            engine_status=ENGINE_STATUS_DEGRADED,
            fallback_method=FALLBACK_METHOD_CONTRACT_VERSION_GUARD,
            warning=f"{label} calculation skipped: {contract_guard_reason}",
        )

    if not calculation_adapter_enabled:
        if disabled_behavior == "local_ok":
            return EngineCallDisposition(
                use_calculation_adapter=False,
                mode="disabled",
                engine_status=ENGINE_STATUS_OK,
            )
        return EngineCallDisposition(
            use_calculation_adapter=False,
            mode="disabled",
            engine_status=ENGINE_STATUS_DEGRADED,
            fallback_method=FALLBACK_METHOD_LOCAL_CALCULATION,
            warning=f"{label} local calculation selected; using local fallback",
        )

    if calculation_adapter is None:
        if adapter_behavior == "local_ok":
            return EngineCallDisposition(
                use_calculation_adapter=False,
                mode="adapter_missing",
                engine_status=ENGINE_STATUS_OK,
            )
        return EngineCallDisposition(
            use_calculation_adapter=False,
            mode="adapter_missing",
            engine_status=ENGINE_STATUS_DEGRADED,
            fallback_method=FALLBACK_METHOD_LOCAL_CALCULATION,
            warning=f"{label} calculation unavailable; using local fallback",
        )

    return EngineCallDisposition(
        use_calculation_adapter=True,
        mode="use_calculation_adapter",
        engine_status=ENGINE_STATUS_OK,
    )


def calculation_unavailable_warning(*, engine_label: str, error: Any) -> str:
    label = str(engine_label or "Engine").strip() or "Engine"
    return f"{label} calculation unavailable: {error}"


def normalize_warnings(*values: str | Sequence[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = [str(item) for item in value]

        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)

    return normalized


def degraded_response_update(
    *,
    fallback_method: str | None,
    warning: str | None = None,
    warnings: Sequence[str] | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "engine_status": ENGINE_STATUS_DEGRADED,
        "fallback_method": fallback_method,
        "warnings": normalize_warnings(warnings, warning),
    }
    if engine is not None:
        payload["engine"] = engine
    return payload
