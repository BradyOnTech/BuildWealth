from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


RISK_POSTURES = ("conservative", "moderate", "aggressive")
RISK_POLICY_VERSION = "cash-liquidity-v1"
RISK_COMPARISON_SCHEMA_VERSION = 1
RESERVE_MONTHS = {
    "conservative": 9.0,
    "moderate": 6.0,
    "aggressive": 4.0,
}
DEPLOYMENT_POLICY = {
    "conservative": {
        "leading_candidate": "Protect liquidity first, then favor high-quality fixed income and near-term goals before adding growth exposure.",
        "upside": "More resilience to income shocks and market drawdowns.",
        "downside": "More capital stays in lower-return assets, which can slow long-horizon growth.",
    },
    "moderate": {
        "leading_candidate": "After the reserve, deploy across confirmed allocation underweights without changing concentration or tax guardrails.",
        "upside": "Balances resilience with diversified long-term growth.",
        "downside": "Accepts more volatility than Conservative while keeping less growth exposure than Aggressive.",
    },
    "aggressive": {
        "leading_candidate": "After the reserve, prioritize diversified growth-asset underweights while preserving concentration, restriction, and tax guardrails.",
        "upside": "Puts more eligible capital to work for long-horizon growth.",
        "downside": "Leaves less liquidity and increases drawdown and sequence-of-returns exposure.",
    },
}


def normalize_risk_posture(value: Any, *, fallback: str = "moderate") -> str:
    clean = str(value or "").strip().lower()
    if clean == "balanced":
        clean = "moderate"
    return clean if clean in RISK_POSTURES else fallback


def profile_risk_posture(profile: dict[str, Any] | None) -> str | None:
    policy = profile.get("investment_policy") if isinstance(profile, dict) else None
    raw = policy.get("risk_tolerance") if isinstance(policy, dict) else None
    clean = str(raw or "").strip().lower()
    if not clean:
        return None
    return normalize_risk_posture(clean)


def resolve_risk_lens(
    requested: dict[str, Any] | None,
    *,
    stored: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved = profile_risk_posture(profile)
    source = requested if isinstance(requested, dict) else stored if isinstance(stored, dict) else {}
    mode = str(source.get("mode") or "profile").strip().lower()
    posture = normalize_risk_posture(source.get("posture")) if mode == "override" else None
    effective = posture or saved or "moderate"
    return {
        "mode": "override" if mode == "override" else "profile",
        "posture": posture,
        "profile_posture": saved,
        "effective_posture": effective,
        "is_override": bool(mode == "override" and posture != saved),
        "label": effective.title(),
        "schema_version": 1,
    }


def question_requests_risk_comparison(question: str) -> bool:
    clean = str(question or "").lower()
    patterns = (
        r"risk\s+(?:tolerance|posture|approach|level|lens)",
        r"compare.+(?:conservative|moderate|balanced|aggressive)",
        r"(?:conservative|moderate|balanced|aggressive).+compare",
        r"under.+(?:conservative|moderate|balanced|aggressive)",
    )
    return any(re.search(pattern, clean) for pattern in patterns)


def question_supports_risk_comparison(question: str) -> bool:
    clean = str(question or "").lower()
    return question_requests_risk_comparison(clean) or any(
        term in clean
        for term in (
            "invest", "portfolio", "allocation", "cash", "reserve", "retire",
            "contribution", "financial plan", "on track", "what should i do",
        )
    )


def _safe_number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _monthly_outflow(profile: dict[str, Any]) -> float:
    expenses = profile.get("expense_items") if isinstance(profile.get("expense_items"), list) else []
    debts = profile.get("debt_items") if isinstance(profile.get("debt_items"), list) else []
    expense_total = sum(
        _safe_number(item.get("monthly_amount_usd"))
        for item in expenses
        if isinstance(item, dict)
    )
    debt_total = sum(
        _safe_number(
            item.get("custom_monthly_payment_usd")
            if item.get("custom_monthly_payment_usd") is not None
            else item.get("minimum_payment_usd")
        )
        for item in debts
        if isinstance(item, dict)
    )
    return round(expense_total + debt_total, 2)


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _variant(posture: str, *, total_cash: float, monthly_outflow: float) -> dict[str, Any]:
    reserve_months = RESERVE_MONTHS[posture]
    deployment = DEPLOYMENT_POLICY[posture]
    target = round(monthly_outflow * reserve_months, 2) if monthly_outflow > 0 else None
    if target is None:
        action = (
            f"Explore a {reserve_months:g}-month cash reserve, then direct additional "
            "cash toward the highest-priority goal or diversified investments."
        )
        return {
            "posture": posture,
            "label": posture.title(),
            "exploration_status": "partial",
            "recommendation_status": "reasonable",
            "capacity_fit": "unknown",
            "reserve_months": reserve_months,
            "reserve_target_usd": None,
            "cash_available_to_deploy_usd": None,
            "cash_shortfall_usd": None,
            "action": action,
            **deployment,
            "tradeoff": "Monthly outflows are missing, so the amount cannot be calculated yet.",
            "warning": "Add monthly expenses and debt minimums to test capacity; exploration remains available.",
        }

    deployable = round(max(total_cash - target, 0.0), 2)
    shortfall = round(max(target - total_cash, 0.0), 2)
    cash_months = total_cash / monthly_outflow if monthly_outflow else 0.0
    if total_cash >= target:
        capacity_fit = "within"
        recommendation_status = "recommended"
        action = f"Keep {_money(target)} in reserve and explore deploying {_money(deployable)}."
        warning = ""
    elif cash_months >= 3:
        capacity_fit = "stretches"
        recommendation_status = "caution"
        action = f"Explore this posture now, with a {_money(shortfall)} gap to its reserve target."
        warning = "This posture stretches the current cash cushion; compare the downside before acting."
    else:
        capacity_fit = "exceeds"
        recommendation_status = "not_recommended"
        action = f"Explore this posture with a {_money(shortfall)} reserve gap; no option is hidden or blocked."
        warning = "This is not recommended from current cash capacity, but BuildWealth will still show and model it."
    return {
        "posture": posture,
        "label": posture.title(),
        "exploration_status": "complete",
        "recommendation_status": recommendation_status,
        "capacity_fit": capacity_fit,
        "reserve_months": reserve_months,
        "reserve_target_usd": target,
        "cash_available_to_deploy_usd": deployable,
        "cash_shortfall_usd": shortfall,
        "action": action,
        **deployment,
        "tradeoff": (
            f"A {reserve_months:g}-month reserve favors "
            f"{'stability' if posture == 'conservative' else 'balance' if posture == 'moderate' else 'more market exposure'} "
            "in exchange for less immediately deployable cash."
        ),
        "warning": warning,
    }


def build_risk_comparison(
    *,
    question: str,
    profile: dict[str, Any] | None,
    holdings: dict[str, Any] | None,
    lens: dict[str, Any],
    plan_id: str | None = None,
    source_turn_id: str | None = None,
) -> dict[str, Any]:
    profile_payload = profile if isinstance(profile, dict) else {}
    holdings_payload = holdings if isinstance(holdings, dict) else {}
    total_cash = round(_safe_number(holdings_payload.get("total_cash")), 2)
    monthly_outflow = _monthly_outflow(profile_payload)
    frozen = {
        "question": str(question or "").strip(),
        "profile_updated_at": profile_payload.get("updated_at"),
        "holdings_updated_at": holdings_payload.get("updated_at") or holdings_payload.get("prices_updated_at"),
        "plan_id": plan_id,
        "total_cash_usd": total_cash,
        "monthly_outflow_usd": monthly_outflow if monthly_outflow > 0 else None,
    }
    fingerprint = hashlib.sha256(
        json.dumps(frozen, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "id": f"risk-{uuid.uuid4().hex[:12]}",
        "schema_version": RISK_COMPARISON_SCHEMA_VERSION,
        "policy_version": RISK_POLICY_VERSION,
        "adapter_versions": {"cash_liquidity": "v1"},
        "source_turn_id": source_turn_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_fingerprint": fingerprint,
        "frozen_conditions": frozen,
        "selected_posture": lens.get("effective_posture") or "moderate",
        "profile_posture": lens.get("profile_posture"),
        "variants": [
            _variant(posture, total_cash=total_cash, monthly_outflow=monthly_outflow)
            for posture in RISK_POSTURES
        ],
        "policy": {
            "exploration_is_never_blocked": True,
            "warnings_are_advisory": True,
            "saved_profile_changed": False,
        },
    }


def risk_comparison_prompt_block(comparison: dict[str, Any]) -> str:
    return (
        "\n\nRisk Lens comparison (deterministic, same frozen inputs for every posture):\n"
        + json.dumps(comparison, sort_keys=True, default=str)
        + "\nExplain the tradeoffs. Never hide a posture or imply that a warning blocks exploration. "
        "Do not claim the saved risk tolerance changed."
    )


def risk_comparison_fallback_answer(comparison: dict[str, Any]) -> str:
    variants = comparison.get("variants") if isinstance(comparison.get("variants"), list) else []
    lines = [
        "I compared all three risk postures using the same saved conditions. "
        "Every posture remains available to explore; warnings are advisory and your saved profile was not changed."
    ]
    for item in variants:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "Risk posture")
        lines.append(f"**{label}:** {item.get('action')} {item.get('tradeoff')}")
    return "\n\n".join(lines)
