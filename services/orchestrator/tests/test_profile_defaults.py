from __future__ import annotations

from datetime import datetime, timezone

from buildwealth_orchestrator.services.profile_defaults import (
    build_profile_default_suggestions,
    load_state_tax_rates,
)

NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _profile(**overrides):
    base = {
        "household_members": [],
        "income_items": [],
        "expense_items": [],
        "tax_profile": {},
        "investment_policy": {},
    }
    base.update(overrides)
    return base


def test_marginal_rate_computed_from_income_and_filing_status() -> None:
    profile = _profile(
        income_items=[{"monthly_amount_usd": 7500}],  # 90k/yr
        tax_profile={"filing_status": "single"},
    )
    suggestions = build_profile_default_suggestions(profile, now=NOW)
    marginal = suggestions["tax_profile.marginal_tax_rate"]
    # 90k - 16.1k deduction = 73.9k taxable -> 22% bracket (single, 2026)
    assert marginal["value"] == 0.22
    assert marginal["basis"] == "computed"
    assert "$90,000/yr" in marginal["explanation"]

    effective = suggestions["tax_profile.effective_tax_rate"]
    assert effective["basis"] == "computed"
    assert 0.05 < effective["value"] < 0.22


def test_typical_fallbacks_without_income() -> None:
    suggestions = build_profile_default_suggestions(_profile(), now=NOW)
    assert suggestions["tax_profile.marginal_tax_rate"]["basis"] == "typical"
    assert suggestions["tax_profile.marginal_tax_rate"]["value"] == 0.22
    assert suggestions["tax_profile.effective_tax_rate"]["basis"] == "typical"


def test_state_rate_from_seed_and_no_tax_states() -> None:
    rates = load_state_tax_rates()
    assert rates["TX"] == 0.0
    assert rates["MN"] > 0.05

    mn = build_profile_default_suggestions(
        _profile(tax_profile={"state": "MN"}), now=NOW
    )["tax_profile.state_tax_rate"]
    assert mn["value"] == rates["MN"]

    tx = build_profile_default_suggestions(
        _profile(tax_profile={"state": "tx"}), now=NOW
    )["tax_profile.state_tax_rate"]
    assert tx["value"] == 0.0
    assert "no state income tax" in tx["display"]


def test_no_suggestions_for_fields_already_set() -> None:
    profile = _profile(
        tax_profile={"filing_status": "single", "marginal_tax_rate": 0.24, "state": "MN", "state_tax_rate": 0.07},
        investment_policy={"risk_tolerance": "moderate"},
    )
    suggestions = build_profile_default_suggestions(profile, now=NOW)
    assert "tax_profile.marginal_tax_rate" not in suggestions
    assert "tax_profile.state_tax_rate" not in suggestions
    assert "investment_policy.risk_tolerance" not in suggestions


def test_risk_and_mix_use_self_age() -> None:
    young = _profile(
        household_members=[{"relationship": "self", "birth_year": 1996}],  # 30
    )
    suggestions = build_profile_default_suggestions(young, now=NOW)
    assert suggestions["investment_policy.risk_tolerance"]["value"] == "aggressive"
    mix = suggestions["investment_policy.target_asset_class_allocation_pct"]
    assert mix["value"]["equity"] == 80.0  # 110 - 30
    assert mix["basis"] == "computed"
    assert any(p["name"] == "Classic 60/40" for p in mix["presets"])

    older = _profile(household_members=[{"relationship": "self", "birth_year": 1961}])  # 65
    older_mix = build_profile_default_suggestions(older, now=NOW)[
        "investment_policy.target_asset_class_allocation_pct"
    ]
    assert older_mix["value"]["equity"] == 45.0
    assert (
        build_profile_default_suggestions(older, now=NOW)["investment_policy.risk_tolerance"]["value"]
        == "conservative"
    )


def test_cash_runway_scales_with_household_and_notes_dollars() -> None:
    family = _profile(
        household_members=[
            {"relationship": "self", "birth_year": 1988},
            {"relationship": "partner"},
            {"relationship": "child", "dependent": True},
        ],
        expense_items=[{"monthly_amount_usd": 4000}],
    )
    runway = build_profile_default_suggestions(family, now=NOW)[
        "investment_policy.minimum_cash_runway_months"
    ]
    assert runway["value"] == 6.0
    assert "$24,000" in runway["explanation"]

    solo = build_profile_default_suggestions(
        _profile(household_members=[{"relationship": "self", "birth_year": 1990}]), now=NOW
    )["investment_policy.minimum_cash_runway_months"]
    assert solo["value"] == 3.0
