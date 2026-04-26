from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.schemas import (
    PortfolioFitAssessmentResponse,
    PortfolioSnapshot,
    ResearchEvidencePacket,
)
from buildwealth_orchestrator.services.portfolio_simulator import simulate_trade


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return default


def _threshold(holdings_payload: dict[str, Any], key: str, default: float) -> float:
    risk_policy = holdings_payload.get("risk_policy") if isinstance(holdings_payload, dict) else {}
    thresholds = risk_policy.get("thresholds") if isinstance(risk_policy, dict) else {}
    return _safe_float(thresholds.get(key), default) if isinstance(thresholds, dict) else default


def _evidence_summary(packet: ResearchEvidencePacket | None) -> dict[str, Any]:
    if packet is None:
        return {"available": False}
    freshness = packet.freshness if isinstance(packet.freshness, dict) else {}
    quality = packet.quality if isinstance(packet.quality, dict) else {}
    coverage = packet.coverage if isinstance(packet.coverage, dict) else {}
    blocking_gaps = quality.get("blocking_gaps")
    return {
        "available": True,
        "packet_id": packet.packet_id,
        "provider": packet.provider,
        "freshness_status": freshness.get("status"),
        "confidence": quality.get("confidence"),
        "coverage_score": quality.get("coverage_score"),
        "blocking_gaps": blocking_gaps if isinstance(blocking_gaps, list) else [],
        "quote_available": bool(coverage.get("quote_available")),
        "history_available": bool(coverage.get("history_available")),
    }


def _plan_impact(active_plan_detail: dict[str, Any] | None) -> tuple[dict[str, Any], list[str], list[str]]:
    if not isinstance(active_plan_detail, dict) or not active_plan_detail.get("id"):
        return {}, [], []

    settings = active_plan_detail.get("settings") if isinstance(active_plan_detail.get("settings"), dict) else {}
    years = _safe_float(settings.get("years"), 0.0)
    if years <= 0:
        return (
            {
                "plan_id": active_plan_detail.get("id"),
                "title": active_plan_detail.get("title"),
                "years": None,
                "time_horizon": "unknown",
            },
            [],
            ["plan:time_horizon"],
        )

    if years >= 15:
        horizon = "long"
    elif years >= 5:
        horizon = "medium"
    else:
        horizon = "short"

    return (
        {
            "plan_id": active_plan_detail.get("id"),
            "title": active_plan_detail.get("title"),
            "years": int(years) if years.is_integer() else years,
            "time_horizon": horizon,
            "expected_return_baseline": settings.get("expected_return_baseline"),
        },
        [f"Active plan horizon is {horizon} ({int(years) if years.is_integer() else years:g} years)."],
        [],
    )


def assess_portfolio_fit(
    *,
    symbol: str,
    amount_usd: float | None = None,
    evidence_packet: ResearchEvidencePacket | None = None,
    snapshot: PortfolioSnapshot | None = None,
    holdings_payload: dict[str, Any] | None = None,
    profile_readiness_payload: dict[str, Any] | None = None,
    emergency_fund_months: float | None = None,
    active_plan_detail: dict[str, Any] | None = None,
) -> PortfolioFitAssessmentResponse:
    normalized_symbol = str(symbol or "").strip().upper()
    holdings_payload = holdings_payload if isinstance(holdings_payload, dict) else {}
    profile_readiness_payload = (
        profile_readiness_payload if isinstance(profile_readiness_payload, dict) else {}
    )
    evidence = _evidence_summary(evidence_packet)

    fit_reasons: list[str] = []
    fit_risks: list[str] = []
    blocking_gaps: list[str] = []
    portfolio_impact: dict[str, Any] = {}
    simulation_required = amount_usd is not None
    plan_impact, plan_reasons, plan_blocking_gaps = _plan_impact(active_plan_detail)
    fit_reasons.extend(plan_reasons)
    blocking_gaps.extend(plan_blocking_gaps)
    if "plan:time_horizon" in plan_blocking_gaps:
        fit_risks.append("Active plan is missing time-horizon assumptions needed for investment fit.")

    if snapshot is None:
        blocking_gaps.append("portfolio_snapshot")
    if not evidence.get("available"):
        blocking_gaps.append("research:evidence_packet")
    elif evidence.get("freshness_status") != "fresh":
        blocking_gaps.append(f"research:{evidence.get('freshness_status') or 'unknown'}")
    for gap in evidence.get("blocking_gaps", []):
        blocking_gaps.append(f"research:{gap}")

    readiness_status = str(profile_readiness_payload.get("status") or "").strip().lower()
    if readiness_status and readiness_status != "ready":
        gap_key = str(profile_readiness_payload.get("next_gap_key") or "profile").strip()
        blocking_gaps.append(f"profile:{gap_key}")
        fit_risks.append("Profile readiness is incomplete, so investment fit confidence is limited.")

    if emergency_fund_months is None:
        blocking_gaps.append("cash_runway")
    elif emergency_fund_months < 3:
        blocking_gaps.append("cash_runway")
        fit_risks.append("Emergency fund runway is below 3 months; preserve liquidity before adding investment risk.")
    elif emergency_fund_months >= 6:
        fit_reasons.append("Cash runway is at or above the 6-month target.")

    current_weight_pct = 0.0
    existing_position = False
    if snapshot is not None:
        holding = next((item for item in snapshot.holdings if item.symbol.upper() == normalized_symbol), None)
        existing_position = holding is not None
        if holding is not None and snapshot.total_value_usd > 0:
            current_weight_pct = round((holding.value_usd / snapshot.total_value_usd) * 100.0, 2)

        max_single_pct = _threshold(holdings_payload, "single_holding_max_pct", 35.0)
        portfolio_impact.update(
            {
                "existing_position": existing_position,
                "current_weight_pct": current_weight_pct,
                "single_holding_max_pct": max_single_pct,
                "amount_usd": amount_usd,
            }
        )
        if existing_position:
            fit_risks.append(f"{normalized_symbol} already represents {current_weight_pct:.1f}% of the portfolio.")
            if current_weight_pct >= max_single_pct:
                blocking_gaps.append("concentration")
        else:
            fit_reasons.append(f"{normalized_symbol} is not currently held, so it may add diversification.")

        if amount_usd is not None:
            simulation = simulate_trade(
                snapshot=snapshot,
                symbol=normalized_symbol,
                action="buy",
                amount_usd=float(amount_usd),
            )
            portfolio_impact.update(
                {
                    "simulated_new_top_holding_symbol": simulation.new_top_holding_symbol,
                    "simulated_new_top_holding_pct": simulation.new_top_holding_pct,
                    "simulated_concentration_change": simulation.concentration_change,
                    "simulated_new_concentration_risk": simulation.new_concentration_risk,
                    "simulation_highlights": simulation.highlights,
                }
            )
            if simulation.concentration_change == "worsened":
                fit_risks.append("Simulated trade worsens concentration risk.")

    if not fit_reasons and evidence.get("freshness_status") == "fresh":
        fit_reasons.append("Research evidence is fresh enough for a preliminary fit review.")

    unique_blocking_gaps = list(dict.fromkeys(blocking_gaps))
    if (
        any(gap.startswith("profile:") for gap in unique_blocking_gaps)
        or "cash_runway" in unique_blocking_gaps
        or "plan:time_horizon" in unique_blocking_gaps
    ):
        fit_status = "needs_more_context"
        recommended_next_step = "update_profile"
        fit_score = 35.0
    elif "concentration" in unique_blocking_gaps:
        fit_status = "does_not_fit"
        recommended_next_step = "review_concentration"
        fit_score = 25.0
    elif any(gap.startswith("research:") for gap in unique_blocking_gaps):
        fit_status = "needs_more_context"
        recommended_next_step = "research_more"
        fit_score = 45.0
    else:
        fit_status = "mixed"
        recommended_next_step = "simulate_trade" if simulation_required else "discuss_in_copilot"
        fit_score = 68.0 if simulation_required else 72.0

    return PortfolioFitAssessmentResponse(
        symbol=normalized_symbol,
        fit_status=fit_status,
        fit_score=fit_score,
        fit_reasons=fit_reasons[:8],
        fit_risks=fit_risks[:8],
        blocking_gaps=unique_blocking_gaps,
        portfolio_impact=portfolio_impact,
        plan_impact=plan_impact,
        evidence=evidence,
        simulation_required=simulation_required,
        recommended_next_step=recommended_next_step,
    )
