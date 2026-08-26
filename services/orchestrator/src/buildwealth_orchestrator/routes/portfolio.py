"""Portfolio routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.portfolio_add_flow import execute_add_flow

router = APIRouter()


def _current_holdings(services: m.WorkspaceServices) -> dict[str, m.Any]:
    return (
        services.current_portfolio()
        if isinstance(services, m.WorkspaceServices)
        else services.portfolio_store.get_holdings()
    )

__all__ = [
    "get_portfolio_holdings",
    "get_portfolio_transactions",
    "add_portfolio_entry",
    "add_portfolio_transaction",
    "delete_portfolio_transaction",
    "refresh_portfolio_prices",
    "get_portfolio_benchmark",
    "get_portfolio_attribution",
    "get_portfolio_analytics",
    "get_portfolio_accounts",
    "get_portfolio_audit",
    "get_portfolio_export_bundle",
    "search_portfolio_assets",
    "get_portfolio_asset",
    "update_portfolio_asset_metadata",
    "add_portfolio_account",
    "get_portfolio_watchlist",
    "upsert_portfolio_watchlist_item",
    "save_portfolio_watchlist_thesis_revision",
    "delete_portfolio_watchlist_item",
    "get_portfolio_risk_policy",
    "set_portfolio_risk_policy",
    "create_portfolio_review_packet_route",
    "list_portfolio_review_packets",
    "get_portfolio_review_packet",
    "get_portfolio_cost_basis_methods",
    "set_portfolio_cost_basis_method",
    "get_portfolio_manual_prices",
    "set_portfolio_manual_price",
    "clear_portfolio_manual_price",
    "get_portfolio_fx_rates",
    "get_portfolio_fx_rate_history",
    "set_portfolio_fx_rate",
    "set_portfolio_fx_rate_history",
    "clear_portfolio_fx_rate",
    "get_portfolio_custom_assets",
    "create_portfolio_custom_asset",
    "simulate_portfolio_trade",
    "portfolio_fit_assessment",
]


@router.get("/api/portfolio/holdings")
def get_portfolio_holdings(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    payload = _current_holdings(services)
    profile = services.financial_profile_store.get()
    investment_policy = (
        profile.get("investment_policy")
        if isinstance(profile.get("investment_policy"), dict)
        else {}
    )
    if not investment_policy:
        return payload

    from buildwealth_orchestrator.services.portfolio_risk_alerts import (
        apply_investment_policy_thresholds,
        calculate_profile_aware_portfolio_risk_alerts,
    )

    stored_policy = payload.get("risk_policy") if isinstance(payload.get("risk_policy"), dict) else {}
    thresholds = apply_investment_policy_thresholds(
        stored_policy.get("thresholds"),
        investment_policy,
    )
    result = dict(payload)
    result["investment_policy"] = investment_policy
    result["risk_policy"] = {
        **stored_policy,
        "thresholds": thresholds,
        "source": "profile_investment_policy",
    }
    result["risk_alerts"] = calculate_profile_aware_portfolio_risk_alerts(result, investment_policy)
    return result


@router.get("/api/portfolio/transactions")
def get_portfolio_transactions(
    limit: int = 200,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[dict[str, m.Any]]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.list_transactions(limit=limit)


@router.post("/api/portfolio/add")
def add_portfolio_entry(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Plain-language front door: investment, cash, or property in one call."""
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    try:
        return execute_add_flow(services.portfolio_store, request)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/portfolio/transactions")
def add_portfolio_transaction(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    return services.portfolio_store.add_transaction(
        date=request.get("date", ""),
        symbol=request.get("symbol", ""),
        action=request.get("action", "BUY"),
        quantity=float(request.get("quantity", 0)),
        unit_price=float(request.get("unit_price", 0)),
        fee=float(request.get("fee", 0)),
        account=request.get("account", "default"),
        currency=request.get("currency", "USD"),
        note=request.get("note", ""),
        lot_method=request.get("lot_method", "FIFO"),
        name=request.get("name"),
        asset_type=request.get("asset_type"),
        asset_class=request.get("asset_class"),
        sector=request.get("sector"),
        region=request.get("region"),
    )


@router.delete("/api/portfolio/transactions/{transaction_id}")
def delete_portfolio_transaction(
    transaction_id: str,
    request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.delete_transaction(transaction_id)
    if not deleted:
        raise m.HTTPException(status_code=404, detail="Transaction not found.")
    return {"deleted": True, "id": transaction_id}


@router.post("/api/portfolio/refresh-prices")
async def refresh_portfolio_prices(
    request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(services.context, "portfolio.write")
    holdings_data = await m.refresh_portfolio(services.portfolio_store, m.research_service)
    snapshot = m.build_snapshot_from_holdings(holdings_data)
    services.snapshot_store.write(snapshot)
    return {
        "total_value": holdings_data.get("total_value", 0),
        "holdings_count": len(holdings_data.get("holdings", {})),
        "prices_updated_at": holdings_data.get("prices_updated_at"),
    }


@router.get("/api/portfolio/benchmark", response_model=m.PortfolioBenchmarkResponse)
async def get_portfolio_benchmark(
    symbols: str | None = None,
    limit: int = 180,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioBenchmarkResponse:
    m.require_permission(services.context, "portfolio.read")
    resolved_symbols = m.parse_benchmark_symbols(
        symbols,
        default_symbols=m.settings.portfolio_benchmark_default_symbols,
    )
    if not resolved_symbols:
        raise m.HTTPException(status_code=400, detail="At least one benchmark symbol is required.")

    bounded_limit = max(2, min(int(limit), 3650))
    try:
        return await m.benchmark_service_for_workspace(services).compare(
            benchmark_symbols=resolved_symbols,
            limit=bounded_limit,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/portfolio/attribution", response_model=m.PortfolioAttributionResponse)
async def get_portfolio_attribution(
    top_n: int = 5,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioAttributionResponse:
    m.require_permission(services.context, "portfolio.read")
    bounded_top_n = max(1, min(int(top_n), 50))
    try:
        return await m.attribution_service_for_workspace(services).analyze(
            top_n=bounded_top_n,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/portfolio/analytics", response_model=m.PortfolioAnalyticsResponse)
async def get_portfolio_analytics(
    symbols: str | None = None,
    limit: int = 180,
    top_n: int = 5,
    period: str = "1y",
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioAnalyticsResponse:
    m.require_permission(services.context, "portfolio.read")
    holdings_payload = _current_holdings(services)
    profile_payload = services.financial_profile_store.get()
    investment_policy = (
        profile_payload.get("investment_policy")
        if isinstance(profile_payload, dict)
        and isinstance(profile_payload.get("investment_policy"), dict)
        else {}
    )
    # Keep the analytics panel on the same fund look-through and Profile
    # guardrails as the Holdings/Watch response. Otherwise two adjacent risk
    # summaries can disagree about both the largest holding and its threshold.
    holdings_payload = dict(holdings_payload)
    holdings_payload["risk_alerts"] = m.calculate_profile_aware_portfolio_risk_alerts(
        holdings_payload,
        investment_policy,
    )
    benchmark_response: m.PortfolioBenchmarkResponse | None = None
    benchmark_error = ""
    attribution_response: m.PortfolioAttributionResponse | None = None
    attribution_error = ""

    resolved_symbols = m.parse_benchmark_symbols(
        symbols,
        default_symbols=m.settings.portfolio_benchmark_default_symbols,
    )
    period_limits = {
        "today": 2,
        "wtd": 7,
        "mtd": 31,
        "ytd": 370,
        "1y": 370,
        "5y": 1826,
        "max": 3650,
    }
    normalized_period = str(period or "1y").strip().lower()
    benchmark_limit = period_limits.get(normalized_period, max(2, min(int(limit), 3650)))
    if resolved_symbols:
        try:
            benchmark_response = await m.benchmark_service_for_workspace(services).compare(
                benchmark_symbols=resolved_symbols,
                limit=max(2, min(benchmark_limit, 3650)),
            )
        except ValueError as exc:
            benchmark_error = str(exc)

    try:
        attribution_response = await m.attribution_service_for_workspace(services).analyze(
            top_n=max(1, min(int(top_n), 50)),
        )
    except ValueError as exc:
        attribution_error = str(exc)

    registry_payload = services.asset_registry.search(limit=500)
    return m.PortfolioAnalyticsResponse(
        **m.build_portfolio_analytics_payload(
            holdings_payload=holdings_payload,
            benchmark_response=benchmark_response,
            benchmark_error=benchmark_error,
            attribution_response=attribution_response,
            attribution_error=attribution_error,
            period=normalized_period,
            snapshot_limit=benchmark_limit,
            registry_rows=registry_payload.get("items") if isinstance(registry_payload, dict) else None,
            debt_items=profile_payload.get("debt_items") if isinstance(profile_payload, dict) else None,
            physical_assets=profile_payload.get("physical_assets") if isinstance(profile_payload, dict) else None,
        )
    )


@router.get("/api/portfolio/accounts")
def get_portfolio_accounts(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[dict[str, m.Any]]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_accounts()


@router.get("/api/portfolio/audit", response_model=m.PortfolioAuditResponse)
def get_portfolio_audit(
    limit: int = 25,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioAuditResponse:
    m.require_permission(services.context, "portfolio.read")
    bounded_limit = max(1, min(int(limit), 100))
    payload = m.build_portfolio_audit_payload(
        import_reports=services.import_workbench_store.list_reports(limit=bounded_limit),
        asset_registry_payload=services.asset_registry.search(limit=500),
        accounts=services.portfolio_store.get_accounts(),
        transactions=services.portfolio_store.list_transactions(limit=500),
        manual_prices_payload=services.portfolio_store.get_manual_prices(),
        cost_basis_payload=services.portfolio_store.get_cost_basis_methods(),
        recommendations=services.recommendation_inbox.list(
            limit=500,
            include_archived=False,
            sort="created_at_desc",
        ),
    )
    return m.PortfolioAuditResponse(**payload)


@router.get("/api/portfolio/export-bundle")
def get_portfolio_export_bundle(
    limit: int = 10_000,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "export.create")
    bounded_limit = max(1, min(int(limit), 50_000))
    transactions = services.portfolio_store.list_transactions(limit=bounded_limit)
    holdings_payload = _current_holdings(services)
    import_reports = services.import_workbench_store.list_reports(limit=200)
    audit_report = m.build_portfolio_audit_payload(
        import_reports=import_reports,
        asset_registry_payload=services.asset_registry.search(limit=500),
        accounts=services.portfolio_store.get_accounts(),
        transactions=transactions,
        manual_prices_payload=services.portfolio_store.get_manual_prices(),
        cost_basis_payload=services.portfolio_store.get_cost_basis_methods(),
        recommendations=services.recommendation_inbox.list(
            limit=500,
            include_archived=False,
            sort="created_at_desc",
        ),
    )
    holdings_by_symbol = holdings_payload.get("holdings_by_symbol") if isinstance(holdings_payload.get("holdings_by_symbol"), dict) else {}
    lots = [
        {
            "symbol": symbol,
            **lot,
        }
        for symbol, holding in holdings_by_symbol.items()
        if isinstance(holding, dict)
        for lot in (holding.get("lots") if isinstance(holding.get("lots"), list) else [])
        if isinstance(lot, dict)
    ]
    connection_store = getattr(services, "financial_connection_store", None)
    financial_connections = None
    if connection_store is not None:
        connection_rows = connection_store.list_connections()
        financial_connections = {
            "connections": [
                {key: value for key, value in row.items() if key != "provider_item_id"}
                for row in connection_rows
            ],
            "account_mappings": [
                mapping
                for row in connection_rows
                for mapping in connection_store.list_account_mappings(row["connection_id"])
            ],
            "reports": connection_store.list_connection_reports(),
            "observations": {
                row["connection_id"]: connection_store.get_observation_state(row["connection_id"])
                for row in connection_rows
            },
        }
    return {
        "schema_version": 1,
        "generated_at": m.utc_now().isoformat(),
        "summary": {
            "transactions": len(transactions),
            "holdings": len(holdings_by_symbol),
            "lots": len(lots),
            "import_reports": len(import_reports),
            "audit_events": len(audit_report.get("audit_events", [])),
        },
        "transactions": transactions,
        "holdings": holdings_payload,
        "lots": lots,
        "asset_metadata": services.portfolio_store.get_asset_metadata_map(),
        "manual_prices": services.portfolio_store.get_manual_prices(),
        "fx_rates": services.portfolio_store.get_fx_rates(),
        "fx_rate_history": services.portfolio_store.get_fx_rates_history(),
        "cost_basis_methods": services.portfolio_store.get_cost_basis_methods(),
        "import_reports": import_reports,
        "audit_report": audit_report,
        "financial_connections": financial_connections,
        "recovery_posture": {
            "manual_changes": "Manual metadata, price, FX, and cost-basis changes are local records that can be edited or cleared in Portfolio maintenance.",
            "imports": "Applied import rows are preserved with an Import Report ID so Portfolio History can be traced back to the source file.",
            "destructive_changes": "Before cleanup or removal work, export this bundle and create a Data & Recovery checkpoint.",
        },
    }


@router.get("/api/portfolio/assets/search", response_model=m.AssetRegistrySearchResponse)
def search_portfolio_assets(
    q: str = "",
    limit: int = 100,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.AssetRegistrySearchResponse:
    m.require_permission(services.context, "portfolio.read")
    payload = services.asset_registry.search(query=q, limit=limit)
    return m.AssetRegistrySearchResponse(**payload)


@router.get("/api/portfolio/assets/{symbol}", response_model=m.AssetRegistryItem)
def get_portfolio_asset(
    symbol: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.AssetRegistryItem:
    m.require_permission(services.context, "portfolio.read")
    item = services.asset_registry.detail(symbol)
    if item is None:
        raise m.HTTPException(status_code=404, detail="Asset not found.")
    return m.AssetRegistryItem(**item)


@router.put("/api/portfolio/assets/{symbol}/metadata", response_model=m.AssetRegistryItem)
def update_portfolio_asset_metadata(
    symbol: str,
    request: m.AssetMetadataUpdateRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.AssetRegistryItem:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    updates = request.model_dump(exclude_unset=True)
    try:
        item = services.asset_registry.update_metadata(symbol, updates)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return m.AssetRegistryItem(**item)


@router.post("/api/portfolio/accounts")
def add_portfolio_account(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    name = str(request.get("name") or "").strip()
    if not name:
        raise m.HTTPException(status_code=400, detail="Account name is required.")
    return services.portfolio_store.add_account(
        name=name,
        account_type=str(request.get("type") or "taxable"),
        currency=str(request.get("currency") or "USD"),
    )


@router.patch("/api/portfolio/accounts/{account_id}")
def update_portfolio_account(
    account_id: str,
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    try:
        return services.portfolio_store.update_account(
            account_id,
            name=request.get("name") if "name" in request else None,
            account_type=request.get("type") if "type" in request else None,
            currency=request.get("currency") if "currency" in request else None,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/portfolio/watchlist", response_model=m.WatchlistRankResponse)
def get_portfolio_watchlist(
    period: str = "2y",
    interval: str = "1d",
    sort: str = "ranked",
    limit: int = 200,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.WatchlistRankResponse:
    m.require_permission(services.context, "portfolio.read")
    payload = m.build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort=sort,
        limit=limit,
        store=services.portfolio_store,
    )
    return m.WatchlistRankResponse(**payload)


@router.post("/api/portfolio/watchlist")
def upsert_portfolio_watchlist_item(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    symbol = str(request.get("symbol") or "").strip().upper()
    if not symbol:
        raise m.HTTPException(status_code=400, detail="symbol is required")

    target_price_raw = request.get("target_price_usd")
    target_price_value: float | None = None
    if target_price_raw not in (None, "", "null"):
        try:
            target_price_value = float(target_price_raw)
        except (TypeError, ValueError) as exc:
            raise m.HTTPException(status_code=400, detail="target_price_usd must be a number") from exc
    thesis_reference_raw = request.get("thesis_reference_price_usd")
    thesis_reference_value: float | None = None
    if thesis_reference_raw not in (None, "", "null"):
        try:
            thesis_reference_value = float(thesis_reference_raw)
        except (TypeError, ValueError) as exc:
            raise m.HTTPException(status_code=400, detail="thesis_reference_price_usd must be a number") from exc

    try:
        item = services.portfolio_store.upsert_watchlist_item(
            symbol=symbol,
            data_source=str(request.get("data_source") or "OPENBB"),
            note=request.get("note"),
            thesis=request.get("thesis"),
            thesis_reference_price_usd=thesis_reference_value,
            target_price_usd=target_price_value,
            tags=request.get("tags"),
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.put("/api/portfolio/watchlist/{symbol}/thesis")
def save_portfolio_watchlist_thesis_revision(
    symbol: str,
    request: dict[str, m.Any],
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    scoped_services = hasattr(services, "context")
    if http_request is not None:
        m.require_csrf(http_request)
    if scoped_services:
        m.require_permission(services.context, "portfolio.write")
    resolved_portfolio_store = services.portfolio_store if scoped_services else m.portfolio_store
    resolved_recommendation_inbox = services.recommendation_inbox if scoped_services else m.recommendation_inbox
    normalized_symbol = str(symbol or request.get("symbol") or "").strip().upper()
    if not normalized_symbol:
        raise m.HTTPException(status_code=400, detail="symbol is required")
    thesis = str(request.get("thesis") or request.get("proposed_thesis") or "").strip()
    if not thesis:
        raise m.HTTPException(status_code=400, detail="thesis is required")
    note = request.get("note")
    data_source = str(request.get("data_source") or "OPENBB").strip().upper() or "OPENBB"
    reference_raw = (
        request.get("thesis_reference_price_usd")
        if request.get("thesis_reference_price_usd") is not None
        else request.get("reference_price_usd")
    )
    reference_value: float | None = None
    if reference_raw not in (None, "", "null"):
        try:
            reference_value = float(reference_raw)
        except (TypeError, ValueError) as exc:
            raise m.HTTPException(status_code=400, detail="thesis_reference_price_usd must be a number") from exc
        if reference_value <= 0:
            raise m.HTTPException(status_code=400, detail="thesis_reference_price_usd must be greater than 0")

    try:
        review_window_days = max(1, min(int(request.get("review_window_days") or m.TODAY_THESIS_REVIEW_DAYS), 3650))
    except (TypeError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail="review_window_days must be an integer") from exc

    reviewed_at_dt = m.utc_now()
    reviewed_at = reviewed_at_dt.isoformat()
    expires_at = str(request.get("thesis_expires_at") or request.get("expires_at") or "").strip()
    if not expires_at:
        expires_at = (reviewed_at_dt + m.timedelta(days=review_window_days)).isoformat()

    try:
        current = m._watchlist_item_for_symbol(
            normalized_symbol,
            data_source,
            store=resolved_portfolio_store,
        ) or {}
        revision_event = m._compact_thesis_revision_event(
            target_type="watchlist",
            symbol=normalized_symbol,
            data_source=data_source,
            previous_thesis=current.get("thesis"),
            revised_thesis=thesis,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
            review_window_days=review_window_days,
            request=request,
        )
        resolved_portfolio_store.upsert_watchlist_item(
            symbol=normalized_symbol,
            data_source=data_source,
            thesis=thesis,
            note=str(note) if note is not None else None,
            thesis_reference_price_usd=reference_value,
            tags=request.get("tags") if isinstance(request.get("tags"), list) else None,
        )
        item = resolved_portfolio_store.refresh_watchlist_thesis_review(
            symbol=normalized_symbol,
            data_source=data_source,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
        )
        item = resolved_portfolio_store.append_watchlist_thesis_revision_event(
            symbol=normalized_symbol,
            data_source=data_source,
            event=revision_event,
            limit=m.THESIS_REVISION_HISTORY_LIMIT,
        )
        m._link_thesis_revision_to_recommendation(
            request.get("recommendation_id"),
            revision_event,
            inbox=resolved_recommendation_inbox,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    review = m.research_thesis_review_metadata(
        {
            "reviewed_at": item.get("thesis_reviewed_at"),
            "expires_at": item.get("thesis_expires_at"),
            "reference_price_usd": item.get("thesis_reference_price_usd"),
        }
    )
    return {
        "item": item,
        "thesis_review": {
            "status": review.get("status") or "current",
            "target": "watchlist",
            "symbol": normalized_symbol,
            "data_source": data_source,
            "reviewed_at": item.get("thesis_reviewed_at"),
            "expires_at": item.get("thesis_expires_at"),
            "reference_price_usd": item.get("thesis_reference_price_usd"),
            "age_days": review.get("age_days"),
        },
    }


@router.delete("/api/portfolio/watchlist/{symbol}")
def delete_portfolio_watchlist_item(
    symbol: str,
    request: m.Request,
    data_source: str | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.delete_watchlist_item(symbol, data_source=data_source)
    if not deleted:
        raise m.HTTPException(status_code=404, detail="Watchlist item not found.")
    return {
        "deleted": True,
        "symbol": str(symbol or "").strip().upper(),
        "data_source": str(data_source or "").strip().upper() or None,
    }


@router.get("/api/portfolio/risk-policy")
def get_portfolio_risk_policy(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_risk_policy()


@router.put("/api/portfolio/risk-policy")
def set_portfolio_risk_policy(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    allowed_fields = {
        "single_holding_max_pct",
        "top3_holdings_max_pct",
        "account_max_pct",
        "asset_class_max_pct",
        "sector_max_pct",
        "region_max_pct",
        "hhi_max",
        "effective_positions_min",
    }
    updates: dict[str, float] = {}
    for key in allowed_fields:
        if key not in request:
            continue
        try:
            updates[key] = float(request.get(key))
        except (TypeError, ValueError) as exc:
            raise m.HTTPException(status_code=400, detail=f"{key} must be a number") from exc
    if not updates:
        raise m.HTTPException(status_code=400, detail="At least one risk threshold field is required.")
    return services.portfolio_store.set_risk_policy_thresholds(updates=updates)


@router.post("/api/portfolio/review-packets", response_model=m.PortfolioReviewPacketResponse)
def create_portfolio_review_packet_route(
    request: m.PortfolioReviewPacketRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioReviewPacketResponse:
    m.require_csrf(http_request)
    return m.create_portfolio_review_packet(request, services=services)


@router.get("/api/portfolio/review-packets", response_model=m.PortfolioReviewPacketListResponse)
def list_portfolio_review_packets(
    limit: int = 20,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioReviewPacketListResponse:
    m.require_permission(services.context, "portfolio.read")
    items = services.portfolio_review_packet_store.list(limit=max(1, min(int(limit), 200)))
    return m.PortfolioReviewPacketListResponse(items=items)


@router.get("/api/portfolio/review-packets/{packet_id}", response_model=m.PortfolioReviewPacketResponse)
def get_portfolio_review_packet(
    packet_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioReviewPacketResponse:
    m.require_permission(services.context, "portfolio.read")
    try:
        payload = services.portfolio_review_packet_store.read(packet_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    return m.PortfolioReviewPacketResponse(
        summary=payload["summary"],
        packet=payload["packet"],
        markdown=payload["markdown"],
    )


@router.get("/api/portfolio/cost-basis-methods")
def get_portfolio_cost_basis_methods(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_cost_basis_methods()


@router.put("/api/portfolio/cost-basis-methods")
def set_portfolio_cost_basis_method(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    method = str(request.get("method") or "").strip().upper()
    if not method:
        raise m.HTTPException(status_code=400, detail="method is required")
    try:
        return services.portfolio_store.set_cost_basis_method(
            method=method,
            account=request.get("account"),
            symbol=request.get("symbol"),
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/portfolio/manual-prices")
def get_portfolio_manual_prices(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_manual_prices()


@router.put("/api/portfolio/manual-prices")
def set_portfolio_manual_price(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    symbol = str(request.get("symbol") or "").strip().upper()
    if not symbol:
        raise m.HTTPException(status_code=400, detail="symbol is required")
    try:
        price = float(request.get("price"))
    except (TypeError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail="price must be a number") from exc
    note = str(request.get("note") or "")
    try:
        return services.portfolio_store.set_manual_price(symbol=symbol, price=price, note=note)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/portfolio/manual-prices/{symbol}")
def clear_portfolio_manual_price(
    symbol: str,
    request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.clear_manual_price(symbol)
    if not deleted:
        raise m.HTTPException(status_code=404, detail="Manual price override not found.")
    return {"deleted": True, "symbol": str(symbol).upper()}


@router.get("/api/portfolio/fx-rates")
def get_portfolio_fx_rates(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_fx_rates()


@router.get("/api/portfolio/fx-rates/history")
def get_portfolio_fx_rate_history(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_fx_rates_history()


@router.put("/api/portfolio/fx-rates")
def set_portfolio_fx_rate(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise m.HTTPException(status_code=400, detail="currency is required")
    try:
        rate = float(request.get("rate"))
    except (TypeError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail="rate must be a number") from exc
    base_currency = request.get("base_currency")
    try:
        return services.portfolio_store.set_fx_rate(
            currency=currency,
            rate=rate,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/portfolio/fx-rates/history")
def set_portfolio_fx_rate_history(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise m.HTTPException(status_code=400, detail="currency is required")
    rates_by_date = request.get("rates_by_date")
    if not isinstance(rates_by_date, dict):
        raise m.HTTPException(status_code=400, detail="rates_by_date must be an object of date->rate")
    base_currency = request.get("base_currency")
    try:
        return services.portfolio_store.set_fx_rate_history(
            currency=currency,
            rates_by_date=rates_by_date,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/portfolio/fx-rates/{currency}")
def clear_portfolio_fx_rate(
    currency: str,
    request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(request)
    m.require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.clear_fx_rate(currency)
    if not deleted:
        raise m.HTTPException(status_code=404, detail="FX rate not found or cannot clear base currency.")
    return {"deleted": True, "currency": str(currency).upper()}


@router.get("/api/portfolio/custom-assets")
def get_portfolio_custom_assets(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[dict[str, m.Any]]:
    m.require_permission(services.context, "portfolio.read")
    return services.portfolio_store.list_custom_assets()


@router.post("/api/portfolio/custom-assets")
def create_portfolio_custom_asset(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_csrf(http_request)
    m.require_permission(services.context, "portfolio.write")
    name = str(request.get("name") or "").strip()
    if not name:
        raise m.HTTPException(status_code=400, detail="name is required")
    try:
        value = float(request.get("value"))
    except (TypeError, ValueError) as exc:
        raise m.HTTPException(status_code=400, detail="value must be a number") from exc

    try:
        return services.portfolio_store.create_custom_asset(
            name=name,
            value=value,
            account=str(request.get("account") or "default"),
            asset_type=str(request.get("asset_type") or "custom_asset"),
            asset_class=request.get("asset_class"),
            sector=request.get("sector"),
            region=request.get("region"),
            symbol=request.get("symbol"),
            date=request.get("date"),
            note=str(request.get("note") or ""),
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/portfolio/simulate-trade", response_model=m.SimulateTradeResponse)
def simulate_portfolio_trade(
    request: m.SimulateTradeRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.SimulateTradeResponse:
    resolved_services = m.route_workspace_services(services, permission="portfolio.read")
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        raise m.HTTPException(status_code=400, detail="No portfolio snapshot available. Run sync first.")
    return m.simulate_trade(
        snapshot=snap,
        symbol=request.symbol,
        action=request.action,
        amount_usd=request.amount_usd,
        name=request.name,
    )


@router.post("/api/portfolio/fit-assessment", response_model=m.PortfolioFitAssessmentResponse)
def portfolio_fit_assessment(
    request: m.PortfolioFitAssessmentRequest,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioFitAssessmentResponse:
    m.require_permission(services.context, "portfolio.read")
    try:
        return m.build_portfolio_fit_assessment_payload(request, services=services)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
