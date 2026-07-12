"""Recommendations routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "list_recommendations",
    "get_recommendation_closure_analytics",
    "generate_portfolio_risk_recommendation_candidates",
    "generate_plan_tracking_recommendation_candidates",
    "generate_cash_liquidity_recommendation_candidates",
    "generate_profile_completeness_recommendation_candidates",
    "generate_stale_assumption_recommendation_candidates",
    "generate_allocation_drift_recommendation_candidates",
    "generate_fund_overlap_recommendation_candidates",
    "generate_due_outcome_review_recommendation_candidates",
    "generate_watchlist_research_recommendation_candidates",
    "generate_research_thesis_expiration_recommendation_candidates",
    "run_all_recommendation_factories",
    "create_recommendation",
    "get_recommendation",
    "update_recommendation",
    "preview_recommendation_route",
    "apply_recommendation_route",
    "reject_recommendation_route",
    "update_recommendation_outcome_route",
    "get_recommendation_outcome_prefill",
    "archive_recommendation_route",
]


@router.get("/api/recommendations", response_model=list[m.RecommendationItem])
def list_recommendations(
    limit: int = 100,
    status: str | None = None,
    plan_id: str | None = None,
    include_archived: bool = False,
    sort: str = "ranked",
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> list[m.RecommendationItem]:
    m.require_permission(services.context, "recommendations.read")
    rows = m._recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
        sort=sort,
        inbox=services.recommendation_inbox,
    )
    return [m.RecommendationItem(**row) for row in rows]


@router.get("/api/recommendations/closure-analytics", response_model=m.RecommendationClosureAnalyticsResponse)
def get_recommendation_closure_analytics(
    limit: int = 200,
    statuses: str = "applied,rejected",
    include_pending_realized: bool = True,
    plan_id: str | None = None,
) -> m.RecommendationClosureAnalyticsResponse:
    payload = m.build_recommendation_closure_analytics_payload(
        limit=limit,
        statuses=statuses,
        include_pending_realized=include_pending_realized,
        plan_id=plan_id,
    )
    return m.RecommendationClosureAnalyticsResponse(**payload)


@router.post("/api/recommendations/generate/portfolio-risk", response_model=m.RecommendationFactoryResponse)
def generate_portfolio_risk_recommendation_candidates(
    request: m.PortfolioRiskRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_portfolio_risk_recommendations(
        holdings_payload=holdings_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
        accounts=services.portfolio_store.get_accounts(),
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("portfolio_risk_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/plan-tracking", response_model=m.RecommendationFactoryResponse)
def generate_plan_tracking_recommendation_candidates(
    request: m.PlanTrackingRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        plan_id = m.resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
        detail = services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = m.PlanSettings(**detail.get("settings", {}))
    snapshots = services.snapshot_store.recent(limit=90)
    transactions = services.portfolio_store.list_transactions(limit=10_000)
    planner_defaults = {
        "annual_contribution_usd": m.settings.planner_annual_contribution_usd,
        "expected_return_baseline": m.settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": m.settings.planner_hsa_delta_default,
    }
    tracking_payload = m.compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    ).model_dump(mode="json")
    tracking_payload["plan_settings"] = plan_settings.model_dump(mode="json", exclude_none=True)
    tracking_payload["planner_defaults"] = planner_defaults
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_plan_tracking_recommendations(
        plan_tracking_payload=tracking_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("plan_tracking_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/cash-liquidity", response_model=m.RecommendationFactoryResponse)
def generate_cash_liquidity_recommendation_candidates(
    request: m.CashLiquidityRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    financial_profile_payload = m.get_financial_profile_payload(services.financial_profile_store)
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_cash_liquidity_recommendations(
        holdings_payload=holdings_payload,
        financial_profile_payload=financial_profile_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("cash_liquidity_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/profile-completeness", response_model=m.RecommendationFactoryResponse)
def generate_profile_completeness_recommendation_candidates(
    request: m.ProfileCompletenessRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    profile_payload = m.get_financial_profile_payload(services.financial_profile_store)
    profile_readiness = m.build_onboarding_status_response(
        profile_payload=profile_payload,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_profile_completeness_recommendations(
        profile_readiness_payload=profile_readiness.model_dump(mode="json") if profile_readiness else {},
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("profile_completeness_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/stale-assumptions", response_model=m.RecommendationFactoryResponse)
def generate_stale_assumption_recommendation_candidates(
    request: m.StaleAssumptionRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        plan_id = m.resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
        detail = services.plan_workspace.get_plan(plan_id)
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = m.PlanSettings(**detail.get("settings", {}))
    snapshots = services.snapshot_store.recent(limit=90)
    transactions = services.portfolio_store.list_transactions(limit=10_000)
    planner_defaults = {
        "annual_contribution_usd": m.settings.planner_annual_contribution_usd,
        "expected_return_baseline": m.settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": m.settings.planner_hsa_delta_default,
    }
    tracking_payload = m.compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    ).model_dump(mode="json")
    tracking_payload["plan_settings"] = plan_settings.model_dump(mode="json", exclude_none=True)
    tracking_payload["planner_defaults"] = planner_defaults

    profile_payload = m.get_financial_profile_payload(services.financial_profile_store)
    profile_readiness = m.build_onboarding_status_response(
        profile_payload=profile_payload,
        latest_snapshot=None,
        active_plan_detail=detail,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_stale_assumption_recommendations(
        plan_detail_payload=detail,
        plan_tracking_payload=tracking_payload,
        profile_readiness_payload=profile_readiness.model_dump(mode="json") if profile_readiness else {},
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("stale_assumption_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/allocation-drift", response_model=m.RecommendationFactoryResponse)
def generate_allocation_drift_recommendation_candidates(
    request: m.AllocationDriftRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    profile_payload = m.get_financial_profile_payload(services.financial_profile_store)
    investment_policy = (
        profile_payload.get("investment_policy")
        if isinstance(profile_payload.get("investment_policy"), dict)
        else {}
    )
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_allocation_drift_recommendations(
        holdings_payload=holdings_payload,
        investment_policy=investment_policy,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("allocation_drift_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/fund-overlap", response_model=m.RecommendationFactoryResponse)
def generate_fund_overlap_recommendation_candidates(
    request: m.FundOverlapRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_fund_overlap_recommendations(
        holdings_payload=services.portfolio_store.get_holdings(),
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("fund_overlap_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/due-outcome-review", response_model=m.RecommendationFactoryResponse)
def generate_due_outcome_review_recommendation_candidates(
    request: m.DueOutcomeReviewRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_due_outcome_review_recommendations(
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("due_outcome_review_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/watchlist-research", response_model=m.RecommendationFactoryResponse)
def generate_watchlist_research_recommendation_candidates(
    request: m.WatchlistResearchRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        watchlist_payload = m.build_portfolio_watchlist_payload(
            period=request.period,
            interval=request.interval,
            limit=request.limit,
            sort="ranked",
            store=services.portfolio_store,
        )
    except AttributeError:
        watchlist_payload = {
            "period": request.period,
            "interval": request.interval,
            "count": 0,
            "items": [],
            "warnings": ["Portfolio store does not expose watchlist items."],
        }

    fit_assessments_by_symbol: dict[str, dict[str, m.Any]] = {}
    items = watchlist_payload.get("items") if isinstance(watchlist_payload.get("items"), list) else []
    for item in items[: request.limit]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            fit_assessments_by_symbol[symbol.upper()] = m.build_portfolio_fit_assessment_payload(
                m.PortfolioFitAssessmentRequest(symbol=symbol, period=request.period, interval=request.interval),
                services=services,
            ).model_dump(mode="json")
        except Exception as exc:
            fit_assessments_by_symbol[symbol.upper()] = {
                "symbol": symbol.upper(),
                "fit_status": "needs_more_context",
                "fit_score": 0.0,
                "fit_reasons": [],
                "fit_risks": [f"Portfolio-fit assessment unavailable: {exc}"],
                "blocking_gaps": ["portfolio_fit"],
                "recommended_next_step": "research_more",
            }

    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_watchlist_research_recommendations(
        watchlist_rank_payload=watchlist_payload,
        fit_assessments_by_symbol=fit_assessments_by_symbol,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("watchlist_research_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/research-thesis-expiration", response_model=m.RecommendationFactoryResponse)
def generate_research_thesis_expiration_recommendation_candidates(
    request: m.ResearchThesisExpirationRecommendationGenerateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        plan_id = m.resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    lookup = m.build_research_dossier_lookup_payload(
        plan_id=plan_id,
        limit=request.limit,
        include_content=True,
        workspace=services.plan_workspace,
    )
    dossier_items = lookup.get("items") if isinstance(lookup.get("items"), list) else []
    fit_assessments_by_symbol: dict[str, dict[str, m.Any]] = {}
    dossier_symbols: list[str] = []
    for item in dossier_items:
        if not isinstance(item, dict):
            continue
        symbols = item.get("symbols") if isinstance(item.get("symbols"), list) else []
        for raw_symbol in symbols:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol and symbol not in dossier_symbols and len(dossier_symbols) < request.limit:
                dossier_symbols.append(symbol)
    for symbol in dossier_symbols:
        try:
            try:
                fit_assessments_by_symbol[symbol] = m.build_portfolio_fit_assessment_payload(
                    m.PortfolioFitAssessmentRequest(symbol=symbol),
                    services=services,
                ).model_dump(mode="json")
            except TypeError:
                fit_assessments_by_symbol[symbol] = m.build_portfolio_fit_assessment_payload(
                    m.PortfolioFitAssessmentRequest(symbol=symbol)
                ).model_dump(mode="json")
        except Exception as exc:
            fit_assessments_by_symbol[symbol] = {
                "symbol": symbol,
                "fit_status": "needs_more_context",
                "fit_score": 0.0,
                "fit_reasons": [],
                "fit_risks": [f"Portfolio-fit assessment unavailable: {exc}"],
                "blocking_gaps": ["portfolio_fit"],
                "recommended_next_step": "research_more",
            }
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = m.generate_research_thesis_expiration_recommendations(
        dossier_artifacts=dossier_items,
        existing_recommendations=existing_recommendations,
        fit_assessments_by_symbol=fit_assessments_by_symbol,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=plan_id,
        limit=request.limit,
        stale_after_days=request.stale_after_days,
    )
    if not request.dry_run and result.created:
        m._queue_autogit_event("research_thesis_expiration_recommendations_generated")
    return m.RecommendationFactoryResponse(**result.to_dict())


@router.post("/api/recommendations/generate/run-all", response_model=m.RecommendationFactoryRunAllResponse)
def run_all_recommendation_factories(
    request: m.RecommendationFactoryRunAllRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationFactoryRunAllResponse:
    services = m.workspace_services_or_legacy(services)
    if http_request is not None:
        m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    factories: dict[str, m.RecommendationFactoryResponse] = {}
    errors: list[dict[str, m.Any]] = []

    try:
        factories["portfolio_risk"] = m.generate_portfolio_risk_recommendation_candidates(
            m.PortfolioRiskRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "portfolio_risk", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "portfolio_risk", "reason": str(exc)})

    try:
        factories["plan_tracking"] = m.generate_plan_tracking_recommendation_candidates(
            m.PlanTrackingRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "plan_tracking", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "plan_tracking", "reason": str(exc)})

    try:
        factories["cash_liquidity"] = m.generate_cash_liquidity_recommendation_candidates(
            m.CashLiquidityRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "cash_liquidity", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "cash_liquidity", "reason": str(exc)})

    try:
        factories["profile_completeness"] = m.generate_profile_completeness_recommendation_candidates(
            m.ProfileCompletenessRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "profile_completeness", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "profile_completeness", "reason": str(exc)})

    try:
        factories["stale_assumptions"] = m.generate_stale_assumption_recommendation_candidates(
            m.StaleAssumptionRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc)})

    try:
        factories["allocation_drift"] = m.generate_allocation_drift_recommendation_candidates(
            m.AllocationDriftRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "allocation_drift", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "allocation_drift", "reason": str(exc)})

    try:
        factories["fund_overlap"] = m.generate_fund_overlap_recommendation_candidates(
            m.FundOverlapRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "fund_overlap", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "fund_overlap", "reason": str(exc)})

    try:
        factories["due_outcome_review"] = m.generate_due_outcome_review_recommendation_candidates(
            m.DueOutcomeReviewRecommendationGenerateRequest(
                dry_run=request.dry_run,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "due_outcome_review", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "due_outcome_review", "reason": str(exc)})

    try:
        factories["watchlist_research"] = m.generate_watchlist_research_recommendation_candidates(
            m.WatchlistResearchRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc)})

    try:
        factories["research_thesis_expiration"] = m.generate_research_thesis_expiration_recommendation_candidates(
            m.ResearchThesisExpirationRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except m.HTTPException as exc:
        errors.append({"factory": "research_thesis_expiration", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "research_thesis_expiration", "reason": str(exc)})

    generated_count = sum(factory.generated_count for factory in factories.values())
    skipped_count = sum(factory.skipped_count for factory in factories.values())
    refreshed_count = sum(factory.refreshed_count for factory in factories.values())
    if not request.dry_run and (generated_count or refreshed_count):
        m._queue_autogit_event("recommendation_factories_generated")

    return m.RecommendationFactoryRunAllResponse(
        generated_count=generated_count,
        skipped_count=skipped_count,
        refreshed_count=refreshed_count,
        factory_count=len(factories),
        factories=factories,
        errors=errors,
        dry_run=request.dry_run,
    )


@router.post("/api/recommendations", response_model=m.RecommendationItem)
def create_recommendation(
    request: m.RecommendationCreateRequest,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationItem:
    resolved_services = m.route_workspace_services(
        services,
        permission="recommendations.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        prepared_payload = m._prepare_recommendation_action_payload(
            source=request.source,
            action_payload=request.action_payload,
            plan_id=request.plan_id,
        )
        recommendation = resolved_services.recommendation_inbox.create(
            title=request.title,
            detail=request.detail,
            priority=request.priority,
            recommendation_type=request.recommendation_type,
            source=request.source,
            plan_id=request.plan_id,
            action_payload=prepared_payload,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("recommendation_created")
    return m._recommendation_item_from_row(recommendation)


@router.get("/api/recommendations/{recommendation_id}", response_model=m.RecommendationItem)
def get_recommendation(
    recommendation_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationItem:
    m.require_permission(services.context, "recommendations.read")
    try:
        recommendation = services.recommendation_inbox.get(recommendation_id)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m._recommendation_item_from_row(recommendation)


@router.put("/api/recommendations/{recommendation_id}", response_model=m.RecommendationItem)
def update_recommendation(
    recommendation_id: str,
    request: m.RecommendationUpdateRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationItem:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise m.HTTPException(status_code=400, detail="Provide at least one field to update")

    try:
        recommendation = services.recommendation_inbox.update(recommendation_id, updates=updates)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc

    m._queue_autogit_event("recommendation_updated")
    return m._recommendation_item_from_row(recommendation)


@router.post("/api/recommendations/{recommendation_id}/preview", response_model=m.RecommendationPreviewResponse)
async def preview_recommendation_route(
    recommendation_id: str,
    request: m.RecommendationPreviewRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationPreviewResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.read")
    try:
        return await m.preview_recommendation(recommendation_id, request, services=services)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/recommendations/{recommendation_id}/apply", response_model=m.RecommendationActionResponse)
async def apply_recommendation_route(
    recommendation_id: str,
    request: m.RecommendationApplyRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationActionResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        response = await m.apply_recommendation_with_decision_packet(recommendation_id, request, services=services)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("recommendation_applied")
    return response


@router.post("/api/recommendations/{recommendation_id}/reject", response_model=m.RecommendationActionResponse)
async def reject_recommendation_route(
    recommendation_id: str,
    request: m.RecommendationRejectRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationActionResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        response = await m.reject_recommendation(
            recommendation_id,
            plan_id=request.plan_id,
            reason=request.reason,
            capture_scenario_diff=request.capture_scenario_diff,
            create_decision_packet=request.create_decision_packet,
            decision_packet_research_symbols=request.decision_packet_research_symbols,
            services=services,
        )
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("recommendation_rejected")
    return response


@router.post("/api/recommendations/{recommendation_id}/outcome", response_model=m.RecommendationActionResponse)
def update_recommendation_outcome_route(
    recommendation_id: str,
    request: m.RecommendationOutcomeUpdateRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationActionResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        response = m.update_recommendation_outcome(recommendation_id, request, services=services)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except m.PlanNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("recommendation_outcome_updated")
    return response


@router.get(
    "/api/recommendations/{recommendation_id}/outcome/prefill",
    response_model=m.RecommendationOutcomePrefillResponse,
)
def get_recommendation_outcome_prefill(
    recommendation_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationOutcomePrefillResponse:
    m.require_permission(services.context, "recommendations.read")
    try:
        return m.build_recommendation_outcome_prefill_payload(recommendation_id, services=services)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/recommendations/{recommendation_id}/archive", response_model=m.RecommendationActionResponse)
def archive_recommendation_route(
    recommendation_id: str,
    request: m.RecommendationRejectRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.RecommendationActionResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "recommendations.write")
    try:
        response = m.archive_recommendation(recommendation_id, note=request.reason, services=services)
    except m.RecommendationNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc
    m._queue_autogit_event("recommendation_archived")
    return response
