from buildwealth_orchestrator.services.engine_policy import (
    ENGINE_STATUS_DEGRADED,
    ENGINE_STATUS_OK,
    FALLBACK_METHOD_CONTRACT_VERSION_GUARD,
    FALLBACK_METHOD_LOCAL_CALCULATION,
    degraded_response_update,
    normalize_warnings,
    resolve_engine_call_disposition,
)


def test_resolve_engine_call_disposition_guarded() -> None:
    disposition = resolve_engine_call_disposition(
        engine_label="Portfolio benchmark",
        calculation_adapter_enabled=True,
        calculation_adapter=object(),
        contract_guard_reason="CalculationAdapter contract version mismatch (expected v1, got v2)",
        disabled_behavior="degraded_fallback",
    )

    assert disposition.use_calculation_adapter is False
    assert disposition.mode == "guarded"
    assert disposition.engine_status == ENGINE_STATUS_DEGRADED
    assert disposition.fallback_method == FALLBACK_METHOD_CONTRACT_VERSION_GUARD
    assert "calculation skipped" in str(disposition.warning).lower()


def test_resolve_engine_call_disposition_disabled_modes() -> None:
    degraded = resolve_engine_call_disposition(
        engine_label="Portfolio attribution",
        calculation_adapter_enabled=False,
        calculation_adapter=None,
        disabled_behavior="degraded_fallback",
    )
    assert degraded.use_calculation_adapter is False
    assert degraded.mode == "disabled"
    assert degraded.engine_status == ENGINE_STATUS_DEGRADED
    assert degraded.fallback_method == FALLBACK_METHOD_LOCAL_CALCULATION

    local_ok = resolve_engine_call_disposition(
        engine_label="Plan simulation",
        calculation_adapter_enabled=False,
        calculation_adapter=None,
        disabled_behavior="local_ok",
    )
    assert local_ok.use_calculation_adapter is False
    assert local_ok.mode == "disabled"
    assert local_ok.engine_status == ENGINE_STATUS_OK
    assert local_ok.fallback_method is None


def test_resolve_engine_call_disposition_adapter_missing_modes() -> None:
    degraded = resolve_engine_call_disposition(
        engine_label="Portfolio benchmark",
        calculation_adapter_enabled=True,
        calculation_adapter=None,
        disabled_behavior="degraded_fallback",
        adapter_missing_behavior="degraded_fallback",
    )
    assert degraded.use_calculation_adapter is False
    assert degraded.mode == "adapter_missing"
    assert degraded.engine_status == ENGINE_STATUS_DEGRADED
    assert degraded.fallback_method == FALLBACK_METHOD_LOCAL_CALCULATION

    local_ok = resolve_engine_call_disposition(
        engine_label="Plan simulation",
        calculation_adapter_enabled=True,
        calculation_adapter=None,
        disabled_behavior="local_ok",
        adapter_missing_behavior="local_ok",
    )
    assert local_ok.use_calculation_adapter is False
    assert local_ok.mode == "adapter_missing"
    assert local_ok.engine_status == ENGINE_STATUS_OK
    assert local_ok.fallback_method is None


def test_resolve_engine_call_disposition_use_calculation_adapter() -> None:
    disposition = resolve_engine_call_disposition(
        engine_label="Portfolio benchmark",
        calculation_adapter_enabled=True,
        calculation_adapter=object(),
        disabled_behavior="degraded_fallback",
    )

    assert disposition.use_calculation_adapter is True
    assert disposition.mode == "use_calculation_adapter"
    assert disposition.engine_status == ENGINE_STATUS_OK
    assert disposition.fallback_method is None
    assert disposition.warning is None


def test_warning_helpers_normalize_and_build_degraded_update() -> None:
    warnings = normalize_warnings(
        [" first ", "second", "second"],
        "third",
        None,
    )
    assert warnings == ["first", "second", "third"]

    update = degraded_response_update(
        fallback_method=FALLBACK_METHOD_LOCAL_CALCULATION,
        warning=" local calculation selected ",
        warnings=["existing", "existing"],
        engine="local",
    )
    assert update["engine_status"] == ENGINE_STATUS_DEGRADED
    assert update["fallback_method"] == FALLBACK_METHOD_LOCAL_CALCULATION
    assert update["warnings"] == ["existing", "local calculation selected"]
    assert update["engine"] == "local"
