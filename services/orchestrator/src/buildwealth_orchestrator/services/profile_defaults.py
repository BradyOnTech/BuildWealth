"""Smart defaults — a labeled suggestion for every estimable profile field.

The setup UX never shows a blank the app can estimate: each suggestion carries
its value, a display string, a basis ("computed" from the household's own data
or "typical" population fallback), and a one-line explanation the UI shows
verbatim. Accepting a suggestion is an explicit user action; nothing here
writes to the profile.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.tax_engine import (
    TAX_CONFIG_BY_YEAR,
    TAX_YEAR_2026,
    estimate_federal_tax,
)

_STATE_RATES_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "state_tax_rates_seed.json"
)

TYPICAL_MARGINAL_RATE = 0.22
TYPICAL_EFFECTIVE_RATE = 0.12


def load_state_tax_rates() -> dict[str, float]:
    try:
        payload = json.loads(_STATE_RATES_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        return {}
    normalized: dict[str, float] = {}
    for state, rate in rates.items():
        try:
            normalized[str(state).strip().upper()] = float(rate)
        except (TypeError, ValueError):
            continue
    return normalized


def _suggestion(
    field_path: str,
    value: Any,
    *,
    display: str,
    basis: str,
    explanation: str,
) -> dict[str, Any]:
    return {
        "field_path": field_path,
        "value": value,
        "display": display,
        "basis": basis,  # "computed" | "typical"
        "explanation": explanation,
    }


def _annual_income_usd(profile: dict[str, Any]) -> float:
    total = 0.0
    for item in profile.get("income_items") or []:
        if isinstance(item, dict):
            total += float(item.get("monthly_amount_usd") or 0.0) * 12.0
    return total


def _monthly_expenses_usd(profile: dict[str, Any]) -> float:
    total = 0.0
    for item in profile.get("expense_items") or []:
        if isinstance(item, dict):
            total += float(item.get("monthly_amount_usd") or 0.0)
    return total


def _self_age(profile: dict[str, Any], *, current_year: int) -> int | None:
    members = profile.get("household_members")
    members = members if isinstance(members, list) else []
    self_member = next(
        (m for m in members if isinstance(m, dict) and str(m.get("relationship")) == "self"),
        None,
    ) or next((m for m in members if isinstance(m, dict) and m.get("birth_year")), None)
    if not self_member:
        return None
    try:
        birth_year = int(self_member.get("birth_year"))
    except (TypeError, ValueError):
        return None
    age = current_year - birth_year
    return age if 0 < age < 120 else None


def _household_counts(profile: dict[str, Any]) -> tuple[int, int]:
    members = profile.get("household_members")
    members = members if isinstance(members, list) else []
    adults = sum(
        1
        for m in members
        if isinstance(m, dict) and str(m.get("relationship")) in {"self", "partner", "other"}
    )
    dependents = sum(1 for m in members if isinstance(m, dict) and bool(m.get("dependent")))
    return adults, dependents


def _marginal_rate_for(income: float, filing_status: str, config) -> float:
    deduction = config.standard_deduction.get(filing_status, config.standard_deduction["single"])
    taxable = max(0.0, income - deduction)
    brackets = config.federal_income_brackets.get(
        filing_status, config.federal_income_brackets["single"]
    )
    rate = brackets[0].rate
    for bracket in brackets:
        if taxable >= bracket.min_income:
            rate = bracket.rate
    return rate


def _pct_display(rate: float) -> str:
    return f"{rate * 100:.1f}%".replace(".0%", "%")


def build_profile_default_suggestions(
    profile: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_now = now or datetime.now(timezone.utc)
    year = resolved_now.year
    config = TAX_CONFIG_BY_YEAR.get(year, TAX_YEAR_2026)

    tax_profile = profile.get("tax_profile") if isinstance(profile.get("tax_profile"), dict) else {}
    policy = (
        profile.get("investment_policy")
        if isinstance(profile.get("investment_policy"), dict)
        else {}
    )
    filing_status = str(tax_profile.get("filing_status") or "single")
    if filing_status not in config.standard_deduction:
        filing_status = "single"
    income = _annual_income_usd(profile)
    age = _self_age(profile, current_year=year)
    adults, dependents = _household_counts(profile)

    suggestions: dict[str, dict[str, Any]] = {}

    # ---- Tax rates ---------------------------------------------------------
    filing_label = filing_status.replace("_", " ")
    if not tax_profile.get("marginal_tax_rate"):
        if income > 0:
            rate = _marginal_rate_for(income, filing_status, config)
            suggestions["tax_profile.marginal_tax_rate"] = _suggestion(
                "tax_profile.marginal_tax_rate",
                rate,
                display=_pct_display(rate),
                basis="computed",
                explanation=(
                    f"Estimated from ${income:,.0f}/yr income, filing {filing_label}, "
                    f"{year} federal brackets."
                ),
            )
        else:
            suggestions["tax_profile.marginal_tax_rate"] = _suggestion(
                "tax_profile.marginal_tax_rate",
                TYPICAL_MARGINAL_RATE,
                display=_pct_display(TYPICAL_MARGINAL_RATE),
                basis="typical",
                explanation="Typical for a middle-income US household — add income to sharpen this.",
            )

    if not tax_profile.get("effective_tax_rate"):
        if income > 0:
            estimate = estimate_federal_tax(
                tax_year=year if year in TAX_CONFIG_BY_YEAR else 2026,
                filing_status=filing_status,
                ordinary_income_usd=income,
                include_irmaa=False,
            )
            effective = float(estimate.get("effective_tax_rate") or 0.0)
            suggestions["tax_profile.effective_tax_rate"] = _suggestion(
                "tax_profile.effective_tax_rate",
                round(effective, 4),
                display=_pct_display(effective),
                basis="computed",
                explanation=(
                    f"Federal average across ${income:,.0f}/yr after the standard deduction."
                ),
            )
        else:
            suggestions["tax_profile.effective_tax_rate"] = _suggestion(
                "tax_profile.effective_tax_rate",
                TYPICAL_EFFECTIVE_RATE,
                display=_pct_display(TYPICAL_EFFECTIVE_RATE),
                basis="typical",
                explanation="Typical federal average for a middle-income household.",
            )

    state = str(tax_profile.get("state") or "").strip().upper()
    if state and tax_profile.get("state_tax_rate") in (None, "", 0) :
        state_rates = load_state_tax_rates()
        if state in state_rates:
            rate = state_rates[state]
            suggestions["tax_profile.state_tax_rate"] = _suggestion(
                "tax_profile.state_tax_rate",
                rate,
                display=_pct_display(rate) if rate else "0% (no state income tax)",
                basis="computed",
                explanation=f"Representative {state} rate — flat approximation, not tax advice.",
            )

    # ---- Guardrails --------------------------------------------------------
    def _policy_missing(key: str) -> bool:
        value = policy.get(key)
        return value in (None, "", [])

    if _policy_missing("risk_tolerance"):
        if age is not None and age < 40:
            value, basis, why = (
                "aggressive",
                "computed",
                f"At {age}, a long horizon usually supports growth risk — pick what lets you sleep.",
            )
        elif age is not None and age >= 60:
            value, basis, why = (
                "conservative",
                "computed",
                f"At {age}, shorter horizons usually argue for protecting what you have.",
            )
        else:
            value, basis, why = (
                "moderate",
                "typical",
                "The balanced middle works for most households — adjust to your temperament.",
            )
        suggestions["investment_policy.risk_tolerance"] = _suggestion(
            "investment_policy.risk_tolerance", value, display=value, basis=basis, explanation=why
        )

    if _policy_missing("tax_sensitivity"):
        suggestions["investment_policy.tax_sensitivity"] = _suggestion(
            "investment_policy.tax_sensitivity",
            "medium",
            display="medium",
            basis="typical",
            explanation="Reasonable caution about taxable sales fits most households.",
        )

    if _policy_missing("simplicity_preference"):
        suggestions["investment_policy.simplicity_preference"] = _suggestion(
            "investment_policy.simplicity_preference",
            "medium",
            display="medium",
            basis="typical",
            explanation="Balance between few funds and fine-grained control.",
        )

    if _policy_missing("minimum_research_confidence"):
        suggestions["investment_policy.minimum_research_confidence"] = _suggestion(
            "investment_policy.minimum_research_confidence",
            "medium",
            display="medium",
            basis="typical",
            explanation="Require balanced evidence before recommendations.",
        )

    if _policy_missing("minimum_cash_runway_months"):
        months = 6.0 if (adults >= 2 or dependents > 0) else 3.0
        household_label = (
            f"{adults} adult(s), {dependents} dependent(s)"
            if adults or dependents
            else "a typical household"
        )
        suggestions["investment_policy.minimum_cash_runway_months"] = _suggestion(
            "investment_policy.minimum_cash_runway_months",
            months,
            display=f"{months:.0f} months",
            basis="computed" if (adults or dependents) else "typical",
            explanation=f"Common guidance for {household_label}.",
        )

    if _policy_missing("max_single_symbol_exposure_pct"):
        suggestions["investment_policy.max_single_symbol_exposure_pct"] = _suggestion(
            "investment_policy.max_single_symbol_exposure_pct",
            10.0,
            display="10%",
            basis="typical",
            explanation="A common concentration ceiling for a single stock or fund.",
        )

    if _policy_missing("max_sector_exposure_pct"):
        suggestions["investment_policy.max_sector_exposure_pct"] = _suggestion(
            "investment_policy.max_sector_exposure_pct",
            30.0,
            display="30%",
            basis="typical",
            explanation="Keeps any one sector from dominating the portfolio.",
        )

    # ---- Target mix --------------------------------------------------------
    targets = policy.get("target_asset_class_allocation_pct")
    has_targets = isinstance(targets, dict) and any(
        float(v or 0) > 0 for v in targets.values()
    )
    if not has_targets:
        if age is not None:
            equity = float(max(40, min(90, 110 - age)))
            basis = "computed"
            why = f"Age-based starting point ({age} → ~{equity:.0f}% stocks); presets below are one tap."
        else:
            equity = 80.0
            basis = "typical"
            why = "A classic three-fund starting point; presets below are one tap."
        bonds = round(max(5.0, 95.0 - equity), 0)
        cash = round(max(0.0, 100.0 - equity - bonds), 0)
        mix = {"equity": equity, "fixed_income": bonds, "real_estate": 0.0, "cash": cash}
        suggestions["investment_policy.target_asset_class_allocation_pct"] = {
            **_suggestion(
                "investment_policy.target_asset_class_allocation_pct",
                mix,
                display=f"{equity:.0f}% stocks / {bonds:.0f}% bonds / {cash:.0f}% cash",
                basis=basis,
                explanation=why,
            ),
            "presets": [
                {
                    "name": "Three-fund 80/20",
                    "mix": {"equity": 80, "fixed_income": 20, "real_estate": 0, "cash": 0},
                },
                {
                    "name": "Classic 60/40",
                    "mix": {"equity": 60, "fixed_income": 40, "real_estate": 0, "cash": 0},
                },
                {
                    "name": "Age-based",
                    "mix": mix,
                },
            ],
        }

    # ---- Cushion sanity note (informational) --------------------------------
    monthly_expenses = _monthly_expenses_usd(profile)
    if monthly_expenses > 0 and "investment_policy.minimum_cash_runway_months" in suggestions:
        months = suggestions["investment_policy.minimum_cash_runway_months"]["value"]
        dollars = monthly_expenses * float(months)
        suggestions["investment_policy.minimum_cash_runway_months"]["explanation"] += (
            f" That's about ${dollars:,.0f} at your current expenses."
        )

    return suggestions
