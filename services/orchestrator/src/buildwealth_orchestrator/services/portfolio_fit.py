from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.schemas import (
    Holding,
    PortfolioFitAssessmentResponse,
    PortfolioSnapshot,
    ResearchEvidencePacket,
)
from buildwealth_orchestrator.services.contribution_rules import (
    normalize_account_type,
    tax_treatment_for_account_type,
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


def _single_symbol_policy(holdings_payload: dict[str, Any]) -> tuple[float, str]:
    investment_policy = holdings_payload.get("investment_policy") if isinstance(holdings_payload, dict) else {}
    if isinstance(investment_policy, dict):
        profile_cap = _safe_float(investment_policy.get("max_single_symbol_exposure_pct"), 0.0)
        if profile_cap > 0:
            return profile_cap, "profile.investment_policy"
    return _threshold(holdings_payload, "single_holding_max_pct", 35.0), "portfolio.risk_policy"


def _investment_policy(holdings_payload: dict[str, Any]) -> dict[str, Any]:
    policy = holdings_payload.get("investment_policy") if isinstance(holdings_payload, dict) else {}
    if not isinstance(policy, dict):
        return {}
    return {
        key: policy.get(key)
        for key in (
            "max_single_symbol_exposure_pct",
            "max_sector_exposure_pct",
            "minimum_research_confidence",
            "minimum_cash_runway_months",
            "max_asset_class_exposure_pct",
            "simplicity_preference",
            "tax_sensitivity",
            "risk_tolerance",
            "preferred_account_locations",
            "restricted_symbols",
            "restricted_sectors",
        )
        if policy.get(key) is not None
    }


def _policy_terms(policy: dict[str, Any], key: str) -> list[str]:
    values = policy.get(key)
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _normalized_policy_key(value: Any) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").lower()


def _normalize_tax_treatment(value: Any) -> str:
    text = _normalized_policy_key(value)
    if text in {"taxable", "tax_deferred", "tax_free"}:
        return text
    if not text:
        return ""
    return tax_treatment_for_account_type(text)


def _preferred_account_treatments(
    policy: dict[str, Any],
    *,
    symbol: str,
    asset_type: str,
    sector: str,
) -> tuple[str, list[str]]:
    preferences = policy.get("preferred_account_locations")
    if not isinstance(preferences, dict):
        return "", []

    lookup_keys = [
        symbol.upper(),
        _normalized_policy_key(asset_type),
        _normalized_policy_key(sector),
        "default",
    ]
    for key in lookup_keys:
        raw_values = preferences.get(key)
        if raw_values is None and key != symbol.upper():
            raw_values = preferences.get(key.replace("_", " "))
        if raw_values is None:
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        normalized = list(
            dict.fromkeys(
                treatment
                for treatment in (_normalize_tax_treatment(value) for value in values)
                if treatment
            )
        )
        if normalized:
            return key, normalized
    return "", []


_CONFIDENCE_RANKS = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _confidence_rank(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    return _CONFIDENCE_RANKS.get(text)


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
        "asset_type": packet.asset_type,
        "sector": packet.sector,
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


def _parse_utc_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" not in text and len(text) == 10:
        text = f"{text}T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lot_term(lot: dict[str, Any], *, as_of: datetime) -> str:
    raw_term = str(
        lot.get("term")
        or lot.get("tax_term")
        or lot.get("holding_period")
        or ""
    ).strip().lower()
    if raw_term in {"long", "long_term", "long-term", "lt"}:
        return "long_term"
    if raw_term in {"short", "short_term", "short-term", "st"}:
        return "short_term"

    acquired_at = _parse_utc_date(
        lot.get("acquired_date")
        or lot.get("acquired_at")
        or lot.get("purchase_date")
        or lot.get("date")
    )
    if acquired_at is None:
        return "unknown"
    return "long_term" if (as_of - acquired_at).days >= 365 else "short_term"


def _lot_term_mix(lots: list[dict[str, Any]], *, as_of: datetime) -> str:
    terms = {_lot_term(lot, as_of=as_of) for lot in lots if isinstance(lot, dict)}
    terms.discard("unknown")
    if not terms:
        return "unknown"
    if len(terms) > 1:
        return "mixed"
    return next(iter(terms))


def _account_lookup(holdings_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accounts = holdings_payload.get("accounts")
    lookup: dict[str, dict[str, Any]] = {}
    if not isinstance(accounts, list):
        return lookup
    for index, account in enumerate(accounts, start=1):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or account.get("account_id") or "").strip()
        if not account_id:
            account_id = f"account-{index}"
        lookup[account_id] = account
    return lookup


def _account_context_from_id(holdings_payload: dict[str, Any], account_id: str) -> dict[str, Any]:
    normalized_id = str(account_id or "").strip()
    if not normalized_id:
        return {}
    account = _account_lookup(holdings_payload).get(normalized_id)
    if not isinstance(account, dict):
        return {
            "account_id": normalized_id,
            "account_name": normalized_id,
            "status": "missing",
            "tax_treatment": "unknown",
        }
    account_type_raw = account.get("type") or account.get("account_type")
    account_type = normalize_account_type(account_type_raw or "unknown")
    return {
        "account_id": normalized_id,
        "account_name": str(account.get("name") or account.get("account_name") or normalized_id),
        "account_type": account_type,
        "tax_treatment": tax_treatment_for_account_type(account_type),
        "status": "known",
    }


def _holding_account_id(key: str, holding: dict[str, Any]) -> str:
    account = str(
        holding.get("account")
        or holding.get("account_id")
        or holding.get("accountId")
        or ""
    ).strip()
    if account:
        return account
    if ":" in key:
        return key.split(":", 1)[0]
    return ""


def _matching_holdings_by_symbol(holdings_payload: dict[str, Any], symbol: str) -> list[tuple[str, dict[str, Any]]]:
    raw_holdings = holdings_payload.get("holdings")
    if not isinstance(raw_holdings, dict):
        return []

    matches: list[tuple[str, dict[str, Any]]] = []
    for key, holding in raw_holdings.items():
        if not isinstance(holding, dict):
            continue
        holding_symbol = str(holding.get("symbol") or str(key).split(":")[-1]).strip().upper()
        if holding_symbol == symbol:
            matches.append((str(key), holding))
    return matches


def _holding_sector(holding: Holding | dict[str, Any] | None) -> str:
    if holding is None:
        return ""
    if isinstance(holding, Holding):
        return str(holding.sector or "").strip()
    if isinstance(holding, dict):
        return str(holding.get("sector") or "").strip()
    return ""


def _sector_value(snapshot: PortfolioSnapshot, sector: str) -> float:
    normalized_sector = sector.strip().lower()
    if not normalized_sector:
        return 0.0
    return sum(
        float(holding.value_usd or 0.0)
        for holding in snapshot.holdings
        if str(holding.sector or "").strip().lower() == normalized_sector
    )


def _asset_class_value(snapshot: PortfolioSnapshot, asset_class: str) -> float:
    normalized = _normalized_policy_key(asset_class)
    if not normalized:
        return 0.0
    return sum(
        float(holding.value_usd or 0.0)
        for holding in snapshot.holdings
        if _normalized_policy_key(holding.asset_class or holding.asset_type) == normalized
    )


def _policy_percent_map(policy: dict[str, Any], key: str) -> dict[str, float]:
    raw = policy.get(key)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for raw_key, raw_value in raw.items():
        normalized_key = _normalized_policy_key(raw_key)
        value = _safe_float(raw_value, 0.0)
        if normalized_key and value > 0:
            out[normalized_key] = value
    return out


def _coverage_from_bools(values: list[bool]) -> str:
    if not values:
        return "not_applicable"
    if all(values):
        return "known"
    if any(values):
        return "partial"
    return "missing"


def _account_location_context(
    *,
    symbol: str,
    holdings_payload: dict[str, Any],
    snapshot: PortfolioSnapshot | None,
    existing_position: bool,
) -> dict[str, Any]:
    matches = _matching_holdings_by_symbol(holdings_payload, symbol)
    if not existing_position and not matches:
        return {
            "status": "not_applicable",
            "tax_lot_coverage": "not_applicable",
            "accounts": [],
            "tax_treatments": [],
            "warnings": [],
            "confidence_gap": False,
        }

    accounts_by_id = _account_lookup(holdings_payload)
    as_of = snapshot.as_of if snapshot is not None else datetime.now(timezone.utc)
    account_rows: list[dict[str, Any]] = []
    account_known: list[bool] = []
    lot_known: list[bool] = []
    warnings: list[str] = []

    for key, holding in matches:
        account_id = _holding_account_id(key, holding)
        account = accounts_by_id.get(account_id, {})
        account_type_raw = account.get("type") or account.get("account_type") if isinstance(account, dict) else None
        account_type_known = bool(account_type_raw)
        account_known.append(account_type_known)
        account_type = normalize_account_type(account_type_raw or "unknown") if account_type_known else "unknown"
        tax_treatment = tax_treatment_for_account_type(account_type) if account_type_known else "unknown"

        current_value = _safe_float(
            holding.get("current_value", holding.get("current_value_usd", holding.get("value_usd"))),
            0.0,
        )
        cost_basis = _safe_float(holding.get("cost_basis", holding.get("cost_basis_usd")), 0.0)
        gain_loss = round(current_value - cost_basis, 2) if current_value or cost_basis else None
        gain_loss_pct = round((gain_loss / cost_basis) * 100.0, 2) if gain_loss is not None and cost_basis > 0 else None

        lots = holding.get("lots") if isinstance(holding.get("lots"), list) else []
        lot_known.append(bool(lots))
        account_rows.append(
            {
                "account_id": account_id or "unknown",
                "account_name": str(
                    account.get("name")
                    or account.get("account_name")
                    or account_id
                    or "Unknown account"
                ),
                "account_type": account_type,
                "tax_treatment": tax_treatment,
                "value_usd": round(current_value, 2),
                "portfolio_weight_pct": (
                    round((current_value / snapshot.total_value_usd) * 100.0, 2)
                    if snapshot is not None and snapshot.total_value_usd > 0 and current_value > 0
                    else None
                ),
                "cost_basis_usd": round(cost_basis, 2) if cost_basis else None,
                "unrealized_gain_loss_usd": gain_loss,
                "unrealized_gain_loss_pct": gain_loss_pct,
                "lot_count": len(lots),
                "lot_term_mix": _lot_term_mix(lots, as_of=as_of),
                "cost_basis_method": holding.get("cost_basis_method"),
            }
        )

    account_status = _coverage_from_bools(account_known)
    lot_coverage = _coverage_from_bools(lot_known)
    if account_status in {"missing", "partial"}:
        warnings.append("Account location is missing for at least one existing position.")
    if lot_coverage in {"missing", "partial"}:
        warnings.append("Tax-lot detail is missing or incomplete for at least one existing position.")

    treatments = sorted(
        {
            str(row.get("tax_treatment"))
            for row in account_rows
            if row.get("tax_treatment") and row.get("tax_treatment") != "unknown"
        }
    )
    confidence_gap = bool(warnings)
    return {
        "status": "known" if account_status == "known" and lot_coverage == "known" else "partial",
        "tax_lot_coverage": lot_coverage,
        "accounts": account_rows,
        "tax_treatments": treatments,
        "warnings": warnings,
        "confidence_gap": confidence_gap,
    }


def assess_portfolio_fit(
    *,
    symbol: str,
    amount_usd: float | None = None,
    proposed_account_id: str | None = None,
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
    investment_policy = _investment_policy(holdings_payload)
    candidate_asset_type = str(evidence.get("asset_type") or "").strip()
    candidate_asset_class = _normalized_policy_key(candidate_asset_type)
    candidate_sector = str(evidence.get("sector") or "").strip()

    fit_reasons: list[str] = []
    fit_risks: list[str] = []
    blocking_gaps: list[str] = []
    portfolio_impact: dict[str, Any] = {}
    if investment_policy:
        portfolio_impact["investment_policy"] = investment_policy
    if candidate_asset_type:
        portfolio_impact["candidate_asset_type"] = candidate_asset_type
        portfolio_impact["candidate_asset_class"] = candidate_asset_class
    if candidate_sector:
        portfolio_impact["candidate_sector"] = candidate_sector
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

    minimum_confidence = str(investment_policy.get("minimum_research_confidence") or "").strip().lower()
    evidence_confidence = str(evidence.get("confidence") or "").strip().lower()
    minimum_rank = _confidence_rank(minimum_confidence)
    evidence_rank = _confidence_rank(evidence_confidence)
    if minimum_rank is not None and evidence_rank is not None and evidence_rank < minimum_rank:
        blocking_gaps.append("research:confidence_policy")
        fit_risks.append(
            f"Research confidence is {evidence_confidence}, below personal policy minimum {minimum_confidence}."
        )

    restricted_symbols = {term.upper() for term in _policy_terms(investment_policy, "restricted_symbols")}
    if normalized_symbol in restricted_symbols:
        blocking_gaps.append("policy:restricted_symbol")
        fit_risks.append(f"The personal investment policy restricts {normalized_symbol}.")

    restricted_sectors = {term.lower() for term in _policy_terms(investment_policy, "restricted_sectors")}
    if candidate_sector and candidate_sector.lower() in restricted_sectors:
        blocking_gaps.append("policy:restricted_sector")
        fit_risks.append(f"The personal investment policy restricts {candidate_sector} exposure.")

    readiness_status = str(profile_readiness_payload.get("status") or "").strip().lower()
    if readiness_status and readiness_status != "ready":
        gap_key = str(profile_readiness_payload.get("next_gap_key") or "profile").strip()
        blocking_gaps.append(f"profile:{gap_key}")
        fit_risks.append("Profile readiness is incomplete, so investment fit confidence is limited.")

    minimum_cash_runway = _safe_float(investment_policy.get("minimum_cash_runway_months"), 0.0)
    if emergency_fund_months is None:
        blocking_gaps.append("cash_runway")
    elif minimum_cash_runway > 0 and emergency_fund_months < minimum_cash_runway:
        blocking_gaps.append("cash:policy_floor")
        fit_risks.append(
            f"Cash runway is {emergency_fund_months:.1f} months, below personal policy floor "
            f"{minimum_cash_runway:.1f} months."
        )
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
        if not candidate_sector:
            candidate_sector = _holding_sector(holding)
            if candidate_sector:
                portfolio_impact["candidate_sector"] = candidate_sector
        if not candidate_asset_class and holding is not None:
            candidate_asset_class = _normalized_policy_key(holding.asset_class or holding.asset_type)
            if candidate_asset_class:
                portfolio_impact["candidate_asset_class"] = candidate_asset_class

        max_single_pct, max_single_source = _single_symbol_policy(holdings_payload)
        portfolio_impact.update(
            {
                "existing_position": existing_position,
                "current_weight_pct": current_weight_pct,
                "single_holding_max_pct": max_single_pct,
                "single_holding_policy_source": max_single_source,
                "amount_usd": amount_usd,
            }
        )
        account_location = _account_location_context(
            symbol=normalized_symbol,
            holdings_payload=holdings_payload,
            snapshot=snapshot,
            existing_position=existing_position,
        )
        portfolio_impact["account_location"] = account_location
        proposed_account = _account_context_from_id(holdings_payload, proposed_account_id or "")
        preferred_key, preferred_treatments = _preferred_account_treatments(
            investment_policy,
            symbol=normalized_symbol,
            asset_type=candidate_asset_type,
            sector=candidate_sector,
        )
        if proposed_account:
            proposed_account["policy_preference_key"] = preferred_key or None
            proposed_account["policy_preferred_treatments"] = preferred_treatments
            portfolio_impact["proposed_account"] = proposed_account
            if proposed_account.get("status") == "missing":
                blocking_gaps.append("tax:proposed_account")
                fit_risks.append("The proposed account was not found, so account-location fit cannot be reviewed.")
            elif preferred_treatments and proposed_account.get("tax_treatment") not in preferred_treatments:
                blocking_gaps.append("tax:account_location_policy")
                preferred_label = ", ".join(preferred_treatments)
                asset_label = candidate_asset_type or preferred_key or "this asset"
                fit_risks.append(
                    f"Personal investment policy prefers {asset_label} in {preferred_label} accounts; "
                    f"proposed account is {proposed_account.get('tax_treatment')}."
                )
        max_sector_pct = _safe_float(investment_policy.get("max_sector_exposure_pct"), 0.0)
        if candidate_sector and max_sector_pct > 0 and snapshot.total_value_usd > 0:
            current_sector_value = _sector_value(snapshot, candidate_sector)
            sector_weight_before = round((current_sector_value / snapshot.total_value_usd) * 100.0, 2)
            amount_value = float(amount_usd or 0.0)
            sector_weight_after = round(
                ((current_sector_value + amount_value) / (snapshot.total_value_usd + amount_value)) * 100.0,
                2,
            )
            portfolio_impact.update(
                {
                    "sector_weight_before_trade_pct": sector_weight_before,
                    "sector_weight_after_trade_pct": sector_weight_after,
                    "sector_max_pct": max_sector_pct,
                    "sector_policy_source": "profile.investment_policy",
                }
            )
            if sector_weight_after >= max_sector_pct:
                blocking_gaps.append("sector:policy_cap")
                fit_risks.append(
                    f"{candidate_sector} exposure would be {sector_weight_after:.1f}%, "
                    f"above personal policy cap {max_sector_pct:.1f}%."
                )
        asset_class_caps = _policy_percent_map(investment_policy, "max_asset_class_exposure_pct")
        asset_class_cap = asset_class_caps.get(candidate_asset_class)
        if candidate_asset_class and asset_class_cap and snapshot.total_value_usd > 0:
            current_asset_class_value = _asset_class_value(snapshot, candidate_asset_class)
            asset_class_weight_before = round((current_asset_class_value / snapshot.total_value_usd) * 100.0, 2)
            amount_value = float(amount_usd or 0.0)
            asset_class_weight_after = round(
                ((current_asset_class_value + amount_value) / (snapshot.total_value_usd + amount_value)) * 100.0,
                2,
            )
            portfolio_impact.update(
                {
                    "asset_class_weight_before_trade_pct": asset_class_weight_before,
                    "asset_class_weight_after_trade_pct": asset_class_weight_after,
                    "asset_class_max_pct": asset_class_cap,
                    "asset_class_policy_source": "profile.investment_policy",
                }
            )
            if asset_class_weight_after >= asset_class_cap:
                blocking_gaps.append("asset_class:policy_cap")
                fit_risks.append(
                    f"{candidate_asset_class} exposure would be {asset_class_weight_after:.1f}%, "
                    f"above personal policy cap {asset_class_cap:.1f}%."
                )
        tax_sensitivity = str(investment_policy.get("tax_sensitivity") or "").strip().lower()
        if account_location.get("confidence_gap"):
            if account_location.get("status") in {"missing", "partial"}:
                blocking_gaps.append("tax:account_location")
            if account_location.get("tax_lot_coverage") in {"missing", "partial"}:
                blocking_gaps.append("tax:lots")
            fit_risks.append("Account location or tax-lot context is incomplete, so tax friction review is limited.")
            if tax_sensitivity == "high":
                blocking_gaps.append("tax:policy_context")
                fit_risks.append(
                    "Personal tax sensitivity is high, so missing account or tax-lot context limits fit confidence."
                )

        if existing_position:
            fit_risks.append(f"{normalized_symbol} already represents {current_weight_pct:.1f}% of the portfolio.")
            treatments = set(account_location.get("tax_treatments") or [])
            if "taxable" in treatments:
                fit_risks.append(
                    f"{normalized_symbol} has taxable-account exposure with unrealized gain/loss context to review."
                )
                if tax_sensitivity == "high":
                    blocking_gaps.append("tax:policy_review")
                    fit_risks.append(
                        f"Personal tax sensitivity is high; taxable exposure should be reviewed before changing {normalized_symbol}."
                    )
            if current_weight_pct >= max_single_pct:
                blocking_gaps.append("concentration")
        else:
            fit_reasons.append(f"{normalized_symbol} is not currently held, so it may add diversification.")
            simplicity_preference = str(investment_policy.get("simplicity_preference") or "").strip().lower()
            if simplicity_preference == "high":
                blocking_gaps.append("policy:simplicity_review")
                fit_risks.append(
                    f"Personal simplicity preference is high; a new {normalized_symbol} position should be "
                    "reviewed for portfolio complexity."
                )

        if amount_usd is not None:
            simulation = simulate_trade(
                snapshot=snapshot,
                symbol=normalized_symbol,
                action="buy",
                amount_usd=float(amount_usd),
            )
            simulated_symbol = next(
                (
                    row
                    for row in simulation.top_holdings
                    if str(row.symbol or "").strip().upper() == normalized_symbol
                ),
                None,
            )
            simulated_symbol_weight = simulated_symbol.new_allocation_pct if simulated_symbol else None
            portfolio_impact.update(
                {
                    "simulated_new_top_holding_symbol": simulation.new_top_holding_symbol,
                    "simulated_new_top_holding_pct": simulation.new_top_holding_pct,
                    "simulated_symbol_weight_pct": simulated_symbol_weight,
                    "simulated_concentration_change": simulation.concentration_change,
                    "simulated_new_concentration_risk": simulation.new_concentration_risk,
                    "simulation_highlights": simulation.highlights,
                }
            )
            if simulation.concentration_change == "worsened":
                fit_risks.append("Simulated trade worsens concentration risk.")
            if simulated_symbol_weight is not None and simulated_symbol_weight >= max_single_pct:
                blocking_gaps.append("concentration")
                if max_single_source == "profile.investment_policy":
                    fit_risks.append(
                        f"{normalized_symbol} would reach {simulated_symbol_weight:.1f}% of the portfolio; "
                        f"personal policy cap is {max_single_pct:.1f}%."
                    )

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
    elif "cash:policy_floor" in unique_blocking_gaps:
        fit_status = "needs_more_context"
        recommended_next_step = "review_cash_floor"
        fit_score = 35.0
    elif "asset_class:policy_cap" in unique_blocking_gaps:
        fit_status = "does_not_fit"
        recommended_next_step = "review_asset_class_exposure"
        fit_score = 30.0
    elif "policy:simplicity_review" in unique_blocking_gaps:
        fit_status = "mixed"
        recommended_next_step = "review_simplicity"
        fit_score = 58.0
    elif any(gap.startswith("policy:") for gap in unique_blocking_gaps):
        fit_status = "does_not_fit"
        recommended_next_step = "review_policy_restriction"
        fit_score = 20.0
    elif "sector:policy_cap" in unique_blocking_gaps:
        fit_status = "does_not_fit"
        recommended_next_step = "review_sector_exposure"
        fit_score = 30.0
    elif "concentration" in unique_blocking_gaps:
        fit_status = "does_not_fit"
        recommended_next_step = "review_concentration"
        fit_score = 25.0
    elif any(gap.startswith("research:") for gap in unique_blocking_gaps):
        fit_status = "needs_more_context"
        recommended_next_step = "research_more"
        fit_score = 45.0
    elif "tax:policy_context" in unique_blocking_gaps:
        fit_status = "needs_more_context"
        recommended_next_step = "update_profile"
        fit_score = 42.0
    elif "tax:policy_review" in unique_blocking_gaps:
        fit_status = "mixed"
        recommended_next_step = "discuss_in_copilot"
        fit_score = 55.0
    elif "tax:account_location_policy" in unique_blocking_gaps:
        fit_status = "mixed"
        recommended_next_step = "review_account_location"
        fit_score = 58.0
    elif "tax:proposed_account" in unique_blocking_gaps:
        fit_status = "needs_more_context"
        recommended_next_step = "review_account_location"
        fit_score = 42.0
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
