#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_SRC = REPO_ROOT / "services" / "orchestrator" / "src"
sys.path.insert(0, str(ORCHESTRATOR_SRC))

from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.price_updater import build_snapshot_from_holdings
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore
from buildwealth_orchestrator.services.user_settings import UserSettingsStore


DEMO_MARKER = "[demo-average-household]"
DEMO_SOURCE = "demo_average_household"
DEMO_PLAN_TITLE = "Average Household Retirement Simulation"
DEMO_IMPORT_FILE = "average-household-brokerage-import.csv"


def validate_demo_data_root(
    data_root: Path,
    *,
    workspace_type: str | None = None,
) -> Path:
    """Refuse to seed a household root that is not explicitly demo-scoped."""
    resolved = Path(data_root).resolve()
    repository_data_root = (REPO_ROOT / "data").resolve()
    forbidden_broad_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        REPO_ROOT.parent.resolve(),
    }
    workspace_name = resolved.name.lower()
    is_demo_workspace = (
        workspace_name == "ws_demo_household"
        or (workspace_name.startswith("ws_") and workspace_name.endswith("_demo"))
    )
    verified_demo_workspace = str(workspace_type or "").strip().lower() == "demo"
    if resolved in forbidden_broad_roots or resolved == repository_data_root or not (
        is_demo_workspace or verified_demo_workspace
    ):
        raise ValueError(
            "Demo data may only be seeded into a demo workspace root "
            "(ws_demo_household or ws_*_demo); refusing "
            f"{resolved}"
        )
    return resolved


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remove_demo_transactions(portfolio: PortfolioStore) -> int:
    removed = 0
    for transaction in portfolio.list_transactions(limit=50_000):
        note = str(transaction.get("note") or "")
        if DEMO_MARKER not in note:
            continue
        if portfolio.delete_transaction(str(transaction.get("id") or "")):
            removed += 1
    return removed


def seed_profile(data_root: Path) -> dict[str, Any]:
    store = FinancialProfileStore(data_root / "profile" / "financial_profile.json")
    now = utc_now_iso()
    payload = {
        "income_items": [
            {
                "id": "demo-income-alex-salary",
                "label": "Alex salary",
                "monthly_amount_usd": 8750,
                "source_type": "salary",
                "is_pre_tax": False,
                "annual_growth_rate": 0.035,
            },
            {
                "id": "demo-income-jordan-salary",
                "label": "Jordan salary",
                "monthly_amount_usd": 4580,
                "source_type": "salary",
                "is_pre_tax": False,
                "annual_growth_rate": 0.03,
            },
        ],
        "household_members": [
            {
                "id": "demo-member-alex",
                "display_name": "Alex",
                "relationship": "self",
                "birth_year": 1988,
                "retirement_age": 65,
                "dependent": False,
                "notes": "Primary earner in the demo household.",
            },
            {
                "id": "demo-member-jordan",
                "display_name": "Jordan",
                "relationship": "partner",
                "birth_year": 1990,
                "retirement_age": 65,
                "dependent": False,
                "notes": "Second earner in the demo household.",
            },
            {
                "id": "demo-member-riley",
                "display_name": "Riley",
                "relationship": "child",
                "birth_year": 2020,
                "retirement_age": None,
                "dependent": True,
                "notes": "Dependent used for childcare and college-savings planning examples.",
            },
        ],
        "expense_items": [
            {"id": "demo-expense-mortgage", "label": "Mortgage payment", "monthly_amount_usd": 2400, "category": "housing", "is_fixed": True, "inflation_rate": 0.02},
            {"id": "demo-expense-groceries", "label": "Groceries and household", "monthly_amount_usd": 950, "category": "food", "is_fixed": False, "inflation_rate": 0.035},
            {"id": "demo-expense-childcare", "label": "Childcare", "monthly_amount_usd": 900, "category": "family", "is_fixed": True, "inflation_rate": 0.04},
            {"id": "demo-expense-utilities", "label": "Utilities and internet", "monthly_amount_usd": 420, "category": "utilities", "is_fixed": True, "inflation_rate": 0.03},
            {"id": "demo-expense-transport", "label": "Transportation", "monthly_amount_usd": 650, "category": "transportation", "is_fixed": False, "inflation_rate": 0.03},
            {"id": "demo-expense-insurance", "label": "Insurance premiums", "monthly_amount_usd": 420, "category": "insurance", "is_fixed": True, "inflation_rate": 0.035},
            {"id": "demo-expense-discretionary", "label": "Restaurants, travel, shopping", "monthly_amount_usd": 1050, "category": "lifestyle", "is_fixed": False, "inflation_rate": 0.03},
        ],
        "debt_items": [
            {
                "id": "demo-debt-mortgage",
                "label": "Primary home mortgage",
                "balance_usd": 318000,
                "interest_rate": 0.062,
                "minimum_payment_usd": 2250,
                "payoff_strategy": "minimum",
            },
            {
                "id": "demo-debt-auto",
                "label": "Auto loan",
                "balance_usd": 18000,
                "interest_rate": 0.071,
                "minimum_payment_usd": 465,
                "payoff_strategy": "avalanche",
            },
            {
                "id": "demo-debt-student",
                "label": "Student loan",
                "balance_usd": 24000,
                "interest_rate": 0.054,
                "minimum_payment_usd": 280,
                "payoff_strategy": "minimum",
            },
        ],
        "goal_items": [
            {
                "id": "demo-goal-emergency-fund",
                "label": "Six-month emergency fund",
                "target_amount_usd": 41000,
                "target_date": "2027-12-31T00:00:00+00:00",
                "priority": "high",
                "notes": "Current cash covers about four months of core expenses.",
            },
            {
                "id": "demo-goal-home-maintenance",
                "label": "Home maintenance reserve",
                "target_amount_usd": 18000,
                "target_date": "2028-06-30T00:00:00+00:00",
                "priority": "medium",
                "notes": "Roof and HVAC replacement reserve.",
            },
            {
                "id": "demo-goal-college",
                "label": "College savings starter goal",
                "target_amount_usd": 55000,
                "target_date": "2038-08-01T00:00:00+00:00",
                "priority": "medium",
                "notes": "Early target for one child; not intended to cover full cost.",
            },
        ],
        "physical_assets": [
            {
                "id": "demo-asset-home",
                "label": "Primary residence",
                "current_value_usd": 420000,
                "asset_type": "real_estate",
                "annual_growth_rate": 0.025,
                "purchase_date": "2021-06-15T00:00:00+00:00",
            },
            {
                "id": "demo-asset-vehicle",
                "label": "Family vehicle",
                "current_value_usd": 24000,
                "asset_type": "vehicle",
                "annual_growth_rate": -0.08,
                "purchase_date": "2023-04-10T00:00:00+00:00",
            },
        ],
        "tax_profile": {
            "filing_status": "married_filing_jointly",
            "marginal_tax_rate": 0.24,
            "effective_tax_rate": 0.18,
            "state_tax_rate": 0.068,
            "state": "MN",
        },
        "investment_policy": {
            "max_single_symbol_exposure_pct": 12,
            "max_sector_exposure_pct": 35,
            "minimum_research_confidence": "medium",
            "minimum_cash_runway_months": 6,
            "max_asset_class_exposure_pct": {
                "equity": 85,
                "fixed_income": 35,
                "cash": 20,
                "real_estate": 45,
            },
            "simplicity_preference": "high",
            "tax_sensitivity": "medium",
            "risk_tolerance": "moderate",
            "preferred_account_locations": {
                "bonds": ["401k", "hsa"],
                "broad_equity_etfs": ["taxable", "roth_ira", "401k"],
                "single_stocks": ["taxable"],
            },
            "restricted_symbols": [],
            "restricted_sectors": [],
        },
        "flags": {"no_debt": False, "no_goals": False},
        "notes": (
            "Demo household for testing BuildWealth end-to-end: mid-career couple, one child, "
            "mortgage, retirement accounts, taxable brokerage, emergency savings, and realistic planning tradeoffs."
        ),
        "profile_metadata": {
            "tax_profile.filing_status": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 365},
            "tax_profile.marginal_tax_rate": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 180},
            "tax_profile.effective_tax_rate": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 180},
            "tax_profile.state_tax_rate": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 180},
            "investment_policy.risk_tolerance": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 365},
            "investment_policy.max_single_symbol_exposure_pct": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 365},
            "investment_policy.max_sector_exposure_pct": {"status": "user_confirmed", "source": DEMO_SOURCE, "confidence": "high", "updated_at": now, "last_confirmed_at": now, "confirmed_by_user": True, "stale_after_days": 365},
        },
    }
    return store.save(payload, metadata_source=DEMO_SOURCE, metadata_status="user_confirmed")


def seed_portfolio(data_root: Path) -> dict[str, Any]:
    portfolio = PortfolioStore(data_root / "portfolio")
    removed = remove_demo_transactions(portfolio)
    accounts = {
        "checking": portfolio.add_account("Household Checking", "depository", "USD", account_id="demo_checking"),
        "emergency": portfolio.add_account("Emergency Savings", "depository", "USD", account_id="demo_emergency_savings"),
        "401k": portfolio.add_account("Alex 401k", "401k", "USD", account_id="demo_401k"),
        "roth": portfolio.add_account("Jordan Roth IRA", "roth_ira", "USD", account_id="demo_roth_ira"),
        "taxable": portfolio.add_account("Taxable Brokerage", "taxable", "USD", account_id="demo_taxable"),
        "hsa": portfolio.add_account("Family HSA", "hsa", "USD", account_id="demo_hsa"),
        "home": portfolio.add_account("Home Equity", "real_estate", "USD", account_id="demo_home_equity"),
    }
    transactions = [
        {"date": "2024-01-05", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 2500, "unit_price": 1, "account": accounts["checking"]["id"], "note": f"{DEMO_MARKER} checking buffer for cash-flow testing"},
        {"date": "2024-01-15", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 36500, "unit_price": 1, "account": accounts["emergency"]["id"], "note": f"{DEMO_MARKER} emergency fund starting cash"},
        {"date": "2024-02-28", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 37789.75, "unit_price": 1, "account": accounts["401k"]["id"], "note": f"{DEMO_MARKER} 401k payroll contributions and match funding"},
        {"date": "2024-03-01", "symbol": "VTI", "action": "BUY", "quantity": 120, "unit_price": 215.40, "fee": 0, "account": accounts["401k"]["id"], "note": f"{DEMO_MARKER} broad US equity in 401k", "name": "Vanguard Total Stock Market ETF", "asset_type": "ETF", "asset_class": "equity", "sector": "Diversified", "region": "United States"},
        {"date": "2024-03-01", "symbol": "VXUS", "action": "BUY", "quantity": 80, "unit_price": 55.10, "fee": 0, "account": accounts["401k"]["id"], "note": f"{DEMO_MARKER} international stock allocation", "name": "Vanguard Total International Stock ETF", "asset_type": "ETF", "asset_class": "equity", "sector": "Diversified", "region": "Global ex-US"},
        {"date": "2024-03-01", "symbol": "BND", "action": "BUY", "quantity": 105, "unit_price": 71.75, "fee": 0, "account": accounts["401k"]["id"], "note": f"{DEMO_MARKER} bond ballast", "name": "Vanguard Total Bond Market ETF", "asset_type": "ETF", "asset_class": "fixed_income", "sector": "Bonds", "region": "United States"},
        {"date": "2024-06-09", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 10914, "unit_price": 1, "account": accounts["roth"]["id"], "note": f"{DEMO_MARKER} Roth IRA annual contribution funding"},
        {"date": "2024-06-10", "symbol": "VTI", "action": "BUY", "quantity": 32, "unit_price": 232.50, "fee": 0, "account": accounts["roth"]["id"], "note": f"{DEMO_MARKER} Roth IRA contribution"},
        {"date": "2024-06-10", "symbol": "SCHD", "action": "BUY", "quantity": 45, "unit_price": 77.20, "fee": 0, "account": accounts["roth"]["id"], "note": f"{DEMO_MARKER} dividend ETF in Roth IRA", "name": "Schwab US Dividend Equity ETF", "asset_type": "ETF", "asset_class": "equity", "sector": "Diversified", "region": "United States"},
        {"date": "2024-09-04", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 14088, "unit_price": 1, "account": accounts["taxable"]["id"], "note": f"{DEMO_MARKER} taxable brokerage transfer funding"},
        {"date": "2024-09-05", "symbol": "VOO", "action": "BUY", "quantity": 22, "unit_price": 458.00, "fee": 0, "account": accounts["taxable"]["id"], "note": f"{DEMO_MARKER} taxable broad-market ETF", "name": "Vanguard S&P 500 ETF", "asset_type": "ETF", "asset_class": "equity", "sector": "Diversified", "region": "United States"},
        {"date": "2024-09-05", "symbol": "AAPL", "action": "BUY", "quantity": 8, "unit_price": 190.10, "fee": 0, "account": accounts["taxable"]["id"], "note": f"{DEMO_MARKER} legacy employer stock position", "asset_type": "Equity", "asset_class": "equity", "sector": "Technology", "region": "United States"},
        {"date": "2024-09-05", "symbol": "MSFT", "action": "BUY", "quantity": 6, "unit_price": 415.20, "fee": 0, "account": accounts["taxable"]["id"], "note": f"{DEMO_MARKER} taxable individual stock position", "asset_type": "Equity", "asset_class": "equity", "sector": "Technology", "region": "United States"},
        {"date": "2025-01-09", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 4980.60, "unit_price": 1, "account": accounts["hsa"]["id"], "note": f"{DEMO_MARKER} HSA payroll contribution funding"},
        {"date": "2025-01-10", "symbol": "VTI", "action": "BUY", "quantity": 12, "unit_price": 247.80, "fee": 0, "account": accounts["hsa"]["id"], "note": f"{DEMO_MARKER} HSA long-term investment"},
        {"date": "2025-01-10", "symbol": "SGOV", "action": "BUY", "quantity": 20, "unit_price": 100.35, "fee": 0, "account": accounts["hsa"]["id"], "note": f"{DEMO_MARKER} HSA short-term medical reserve", "name": "iShares 0-3 Month Treasury Bond ETF", "asset_type": "ETF", "asset_class": "cash", "sector": "Treasury Bills", "region": "United States"},
        {"date": "2025-04-30", "symbol": "VTI", "action": "DIVIDEND", "quantity": 0, "unit_price": 245.00, "fee": 0, "account": accounts["401k"]["id"], "note": f"{DEMO_MARKER} dividend activity for audit trail"},
        {"date": "2025-12-31", "symbol": "", "action": "CASH_DEPOSIT", "quantity": 420000, "unit_price": 1, "account": accounts["home"]["id"], "note": f"{DEMO_MARKER} home equity funding offset for net-worth testing"},
    ]
    portfolio.add_transactions_bulk(transactions)
    portfolio.create_custom_asset(
        name="Primary residence estimate",
        value=420000,
        account=accounts["home"]["id"],
        asset_type="real_estate",
        asset_class="real_estate",
        sector="Residential Real Estate",
        region="United States",
        symbol="DEMO_HOME",
        date="2026-01-01",
        note=f"{DEMO_MARKER} local home-value estimate for net-worth testing",
    )
    portfolio.update_prices(
        {
            "VTI": 271.40,
            "VXUS": 64.80,
            "BND": 73.30,
            "SCHD": 81.60,
            "VOO": 525.20,
            "AAPL": 205.10,
            "MSFT": 452.70,
            "SGOV": 100.55,
            "DEMO_HOME": 420000,
        }
    )
    portfolio.set_risk_policy_thresholds(
        {
            "single_symbol_watch_pct": 8,
            "single_symbol_breach_pct": 12,
            "sector_watch_pct": 25,
            "sector_breach_pct": 35,
            "cash_min_pct": 3,
            "cash_max_pct": 20,
        }
    )
    portfolio.upsert_watchlist_item(
        symbol="VTI",
        note="Core index holding to compare against taxable and retirement account placement.",
        thesis="Use as the simple core equity building block unless allocation or tax-location rules say otherwise.",
        thesis_reference_price_usd=271.40,
        target_price_usd=300,
        tags=["core", "etf", "demo"],
    )
    portfolio.upsert_watchlist_item(
        symbol="AAPL",
        note="Small legacy single-stock position that should stay below household concentration limits.",
        thesis="Keep only if single-stock exposure stays under policy and tax impact is reasonable.",
        thesis_reference_price_usd=205.10,
        target_price_usd=220,
        tags=["single-stock", "concentration", "demo"],
    )
    return {
        "removed_demo_transactions": removed,
        "accounts": portfolio.get_accounts(),
        "holdings": portfolio.get_holdings(),
    }


def _find_demo_plan(workspace: PlanWorkspace) -> str | None:
    for plan in workspace.list_plans(limit=500):
        if str(plan.get("title") or "") == DEMO_PLAN_TITLE:
            return str(plan.get("id") or "")
    return None


def _remove_demo_plan_rows(path: Path) -> None:
    if not path.exists():
        return
    kept: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = f"{row.get('summary', '')} {row.get('rationale', '')}"
        if "Seeded " in text or "average-household demo" in text:
            continue
        kept.append(row)
    path.write_text("".join(f"{json.dumps(row)}\n" for row in kept), encoding="utf-8")


def _replace_demo_saved_simulation(workspace: PlanWorkspace, plan_id: str) -> None:
    path = workspace._saved_simulations_path(plan_id)  # Intentional for demo idempotence.
    payload = {"schema_version": 2, "items": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            payload.update(loaded)
    payload["items"] = [
        item
        for item in payload.get("items", [])
        if isinstance(item, dict) and str(item.get("title") or "") != "Demo: save more comparison"
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    workspace.save_simulation(
        plan_id,
        {
            "title": "Demo: save more comparison",
            "source": "scenario_diff",
            "summary": "Increasing annual savings by $4,500 improves the projected ending balance.",
            "input_payload": {"annual_contribution_usd": 30000, "current_portfolio_value_usd": 519484.50},
            "result_payload": {
                "scenario_deltas": [
                    {"label": "baseline", "base_future_value_usd": 1510000, "candidate_future_value_usd": 1695000, "delta_future_value_usd": 185000, "base_real_value_usd": 735000, "candidate_real_value_usd": 826000, "delta_real_value_usd": 91000}
                ],
                "changed_settings": {"annual_contribution_usd": {"base": 25500, "candidate": 30000}},
            },
        },
    )


def seed_plan(data_root: Path) -> dict[str, Any]:
    workspace = PlanWorkspace(data_root / "plans")
    plan_id = _find_demo_plan(workspace)
    if plan_id:
        detail = workspace.get_plan(plan_id)
    else:
        detail = workspace.create_plan(
            title=DEMO_PLAN_TITLE,
            description=(
                "Demo plan for testing simulation, contribution ordering, withdrawal strategy, "
                "life-event branches, saved simulations, and Copilot context."
            ),
        )
        plan_id = str(detail["id"])

    _remove_demo_plan_rows(data_root / "plans" / plan_id / "decisions.jsonl")
    workspace.update_plan_files(
        plan_id=plan_id,
        plan_markdown="\n".join(
            [
                f"# {DEMO_PLAN_TITLE}",
                "",
                "Alex and Jordan want to retire around age 65 while keeping enough cash for normal household surprises.",
                "",
                "## What The User Wants To Test",
                "",
                "- Whether current savings are enough.",
                "- Whether to increase 401k, Roth IRA, HSA, or taxable contributions first.",
                "- What happens if childcare costs last longer or income drops for a year.",
                "- Which withdrawal order is easiest to understand and safest to explain.",
                "",
            ]
        ),
        tasks_markdown="\n".join(
            [
                "# Tasks",
                "",
                "- [ ] Run the baseline retirement simulation.",
                "- [ ] Compare maxing HSA before taxable brokerage.",
                "- [ ] Compare a one-year income drop scenario.",
                "- [ ] Ask Copilot to explain the difference in plain English.",
                "",
            ]
        ),
    )
    workspace.update_plan_settings(
        plan_id=plan_id,
        updates={
            "annual_contribution_usd": 25500,
            "years": 27,
            "hsa_extra_contribution_usd": 1800,
            "marginal_tax_rate": 0.24,
            "state_tax_rate": 0.068,
            "simulation_mode": "monte_carlo",
            "simulation_monte_carlo_variant": "p50",
            "simulation_seed": 424242,
            "household_mode": "couple",
            "household_partner_income_usd": 54960,
            "household_partner_income_growth_rate": 0.03,
            "household_partner_retirement_age": 65,
            "household_partner_social_security_annual_usd": 22000,
            "household_partner_social_security_claiming_age": 67,
            "household_shared_goal_target_usd": 55000,
            "household_shared_goal_target_year": 2038,
            "filing_status": "married_filing_jointly",
            "drawdown_order": "taxable_traditional_roth",
            "roth_conversion_annual_amount_usd": 6000,
            "roth_conversion_start_age": 60,
            "roth_conversion_end_age": 64,
            "inflation_rate": 0.028,
            "expected_return_baseline": 0.064,
            "expected_return_optimistic": 0.082,
            "expected_return_conservative": 0.041,
        },
        rationale="Seeded average-household assumptions for realistic end-to-end testing.",
        status="accepted",
        log_decision=False,
    )
    workspace.update_plan_timeline(
        plan_id=plan_id,
        timeline_payload={
            "events": [
                {"id": "demo-childcare-ends", "date": "2029-09-01", "label": "Childcare drops after school starts", "event_type": "milestone", "impact_type": "expense", "amount_usd": -7200, "recurring_frequency": "yearly", "notes": "Frees cash flow for savings."},
                {"id": "demo-roof-replacement", "date": "2028-06-01", "label": "Roof replacement", "event_type": "purchase", "impact_type": "expense", "amount_usd": 18000, "recurring_frequency": "one_time", "notes": "Fund from home maintenance reserve."},
                {"id": "demo-college-start", "date": "2038-08-01", "label": "College costs begin", "event_type": "milestone", "impact_type": "expense", "amount_usd": 18000, "recurring_frequency": "yearly", "end_date": "2041-08-01", "notes": "Partial annual family contribution."},
                {"id": "demo-retirement", "date": "2053-05-01", "label": "Target retirement", "event_type": "retirement", "impact_type": "contribution", "amount_usd": -25500, "recurring_frequency": "yearly", "notes": "Stop accumulation contributions."},
            ],
            "retirement": {
                "target_retirement_age": 65,
                "withdrawal_strategy": "dynamic_guardrails",
                "drawdown_order": "taxable_traditional_roth",
                "social_security_birth_year": 1988,
                "social_security_claiming_age": 67,
                "social_security_life_expectancy_age": 92,
                "social_security_fra_monthly_benefit_usd": 2600,
                "social_security_estimated_annual_earnings_usd": 105000,
                "rmd_birth_year": 1988,
                "rmd_start_age": 75,
            },
        },
        rationale="Seeded realistic household milestones.",
        status="accepted",
        log_decision=False,
    )
    workspace.update_plan_contribution_rules(
        plan_id=plan_id,
        contribution_rules_payload={
            "base_rule": {"type": "save"},
            "profile_id": "demo-average-household",
            "employer_match_target_usd": 6300,
            "age": 38,
            "rules": [
                {"id": "match", "label": "Capture employer 401k match", "account_type": "401k", "annual_limit_usd": 6300, "priority": 1, "reason": "Free employer match comes first."},
                {"id": "hsa", "label": "Fund HSA for medical reserve", "account_type": "hsa", "annual_limit_usd": 4150, "priority": 2, "reason": "Triple tax advantage and useful emergency healthcare reserve."},
                {"id": "roth", "label": "Fund Roth IRA if eligible", "account_type": "roth_ira", "annual_limit_usd": 14000, "priority": 3, "reason": "Adds tax diversification before taxable investing."},
                {"id": "taxable", "label": "Taxable brokerage overflow", "account_type": "taxable", "annual_limit_usd": 999999, "priority": 4, "reason": "Flexible investing after higher-priority buckets."},
            ],
        },
        rationale="Seeded contribution ordering for a user-facing workflow.",
        status="accepted",
        log_decision=False,
    )
    workspace.update_plan_assumption_sets(
        plan_id=plan_id,
        assumption_sets_payload={
            "active_assumption_set_id": "base",
            "sets": [
                {"id": "base", "name": "Base case", "expected_return_baseline": 0.064, "expected_return_optimistic": 0.082, "expected_return_conservative": 0.041, "inflation_rate": 0.028, "marginal_tax_rate": 0.24, "state_tax_rate": 0.068, "simulation_mode": "monte_carlo", "simulation_monte_carlo_variant": "p50", "simulation_seed": 424242, "roth_conversion_annual_amount_usd": 6000, "roth_conversion_start_age": 60, "roth_conversion_end_age": 64},
                {"id": "stress", "name": "Stress case", "expected_return_baseline": 0.048, "expected_return_optimistic": 0.065, "expected_return_conservative": 0.025, "inflation_rate": 0.034, "marginal_tax_rate": 0.24, "state_tax_rate": 0.068, "simulation_mode": "monte_carlo", "simulation_monte_carlo_variant": "p10", "simulation_seed": 424242, "roth_conversion_annual_amount_usd": 0},
                {"id": "save-more", "name": "Save more", "expected_return_baseline": 0.064, "expected_return_optimistic": 0.082, "expected_return_conservative": 0.041, "inflation_rate": 0.028, "marginal_tax_rate": 0.24, "state_tax_rate": 0.068, "simulation_mode": "monte_carlo", "simulation_monte_carlo_variant": "p50", "simulation_seed": 424242, "roth_conversion_annual_amount_usd": 9000, "roth_conversion_start_age": 60, "roth_conversion_end_age": 64},
            ],
        },
        rationale="Seeded scenario templates for comparison testing.",
        status="accepted",
        log_decision=False,
    )
    workspace.update_plan_branch_templates(
        plan_id=plan_id,
        branch_templates_payload={
            "default_template_id": "one-income-gap",
            "templates": [
                {
                    "id": "one-income-gap",
                    "name": "One-year income gap",
                    "description": "Tests whether cash and contributions can absorb a temporary job loss.",
                    "branch_name": "Temporary income drop",
                    "assumption_set_id": "stress",
                    "compare_settings": {"annual_contribution_usd": 12000},
                    "branch_events": [{"label": "Temporary income drop", "event_type": "job_change", "impact_type": "income", "amount_usd": -45000, "recurring_frequency": "yearly", "start_year_offset": 1, "duration_months": 12, "notes": "Partner income continues."}],
                },
                {
                    "id": "childcare-lasts-longer",
                    "name": "Childcare lasts longer",
                    "description": "Tests a common family cash-flow surprise.",
                    "branch_name": "Childcare extension",
                    "assumption_set_id": "base",
                    "compare_settings": {"annual_contribution_usd": 21000},
                    "branch_events": [{"label": "Childcare extension", "event_type": "purchase", "impact_type": "expense", "amount_usd": 7200, "recurring_frequency": "yearly", "start_year_offset": 3, "duration_months": 24, "notes": "Two extra years of higher childcare costs."}],
                },
            ],
        },
        rationale="Seeded what-if templates for real-user simulation testing.",
        status="accepted",
        log_decision=False,
    )
    workspace.append_decision(
        plan_id=plan_id,
        summary="Seeded average-household demo plan.",
        rationale=(
            "Refreshed assumptions, timeline, contribution order, branch templates, "
            "and saved simulation for real-user testing."
        ),
        status="accepted",
        action_payload={"source": DEMO_SOURCE},
    )
    _replace_demo_saved_simulation(workspace, plan_id)
    detail = workspace.get_plan(plan_id)
    return {"plan_id": plan_id, "title": detail.get("title"), "saved_simulations": len(workspace.list_saved_simulations(plan_id).get("items", []))}


def seed_recommendations(data_root: Path, plan_id: str | None) -> list[dict[str, Any]]:
    store = RecommendationInbox(data_root / "recommendations" / "inbox.json")
    payload = store._load()  # Intentional for idempotent demo cleanup.
    payload["recommendations"] = [
        row
        for row in payload.get("recommendations", [])
        if str(row.get("source") or "") != DEMO_SOURCE
    ]
    store._save(payload)
    items = [
        {
            "title": "Finish the emergency fund",
            "detail": "Core expenses imply a six-month target near $41,000; current demo cash is closer to four months.",
            "priority": "high",
            "recommendation_type": "workflow_action",
            "action_payload": {"kind": "cash_liquidity_review", "demo_seed": True, "target_months": 6},
        },
        {
            "title": "Check contribution order before adding taxable deposits",
            "detail": "The household has HSA and Roth room, so taxable brokerage should be overflow rather than the first extra dollar.",
            "priority": "medium",
            "recommendation_type": "plan_settings_update",
            "action_payload": {"kind": "contribution_order_review", "demo_seed": True, "plan_id": plan_id},
        },
        {
            "title": "Watch single-stock exposure",
            "detail": "AAPL and MSFT are intentionally small in the demo, but this tests concentration and research-thesis workflows.",
            "priority": "medium",
            "recommendation_type": "general",
            "action_payload": {"kind": "portfolio_concentration_review", "demo_seed": True, "symbols": ["AAPL", "MSFT"]},
        },
        {
            "title": "Preview the demo brokerage import",
            "detail": "Use the sample import file to test preview, reconciliation, account mapping, and audit report flows.",
            "priority": "low",
            "recommendation_type": "workflow_action",
            "action_payload": {"kind": "import_workbench_review", "demo_seed": True, "file_name": DEMO_IMPORT_FILE},
        },
    ]
    return [
        store.create(
            title=item["title"],
            detail=item["detail"],
            priority=item["priority"],
            recommendation_type=item["recommendation_type"],
            source=DEMO_SOURCE,
            plan_id=plan_id,
            action_payload=item["action_payload"],
        )
        for item in items
    ]


def seed_import_file(data_root: Path) -> Path:
    inbox = data_root / "imports" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / DEMO_IMPORT_FILE
    rows = [
        {"Date": "2026-01-15", "Action": "Buy", "Symbol": "VTI", "Quantity": "4.25", "Price": "271.40", "Fees & Comm": "0", "Amount": "-1153.45", "Account": "Taxable Brokerage", "Security Name": "Vanguard Total Stock Market ETF", "Asset Class": "Equity", "Asset Type": "ETF", "Sector": "Diversified", "Region": "United States", "Notes": "Monthly taxable investment"},
        {"Date": "2026-01-15", "Action": "Buy", "Symbol": "VXUS", "Quantity": "3.5", "Price": "64.80", "Fees & Comm": "0", "Amount": "-226.80", "Account": "Alex 401k", "Security Name": "Vanguard Total International Stock ETF", "Asset Class": "Equity", "Asset Type": "ETF", "Sector": "Diversified", "Region": "Global ex-US", "Notes": "401k allocation"},
        {"Date": "2026-02-03", "Action": "Dividend", "Symbol": "SCHD", "Quantity": "0", "Price": "0", "Fees & Comm": "0", "Amount": "39.42", "Account": "Jordan Roth IRA", "Security Name": "Schwab US Dividend Equity ETF", "Asset Class": "Equity", "Asset Type": "ETF", "Sector": "Diversified", "Region": "United States", "Notes": "Dividend received"},
        {"Date": "2026-02-10", "Action": "Deposit", "Symbol": "", "Quantity": "", "Price": "", "Fees & Comm": "0", "Amount": "500", "Account": "Emergency Savings", "Security Name": "Cash deposit", "Asset Class": "Cash", "Asset Type": "Cash", "Sector": "Cash", "Region": "United States", "Notes": "Emergency fund transfer"},
        {"Date": "2026-03-01", "Action": "Buy", "Symbol": "UNKNOWN123", "Quantity": "2", "Price": "50", "Fees & Comm": "0", "Amount": "-100", "Account": "New 529 Account", "Security Name": "Unmapped 529 fund", "Asset Class": "", "Asset Type": "Mutual Fund", "Sector": "", "Region": "", "Notes": "Intentional review row"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def seed_snapshot(data_root: Path) -> Path:
    portfolio = PortfolioStore(data_root / "portfolio")
    snapshot_store = SnapshotStore(data_root / "snapshots")
    return snapshot_store.write(build_snapshot_from_holdings(portfolio.get_holdings()))


def seed_settings(data_root: Path) -> dict[str, Any]:
    store = UserSettingsStore(data_root / "settings" / "user_settings.json")
    updates: dict[str, Any] = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "llm_model": os.environ.get("LLM_MODEL", "gpt-5.5"),
        "llm_base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        "llm_timeout_seconds": 60,
        "llm_max_tokens": 2048,
        "llm_parallel_tool_calls": True,
    }
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        updates["llm_api_key"] = api_key
        updates["openai_api_key"] = api_key if updates["llm_provider"] == "openai" else ""
    saved = store.save(updates)
    return {
        "llm_provider": saved.get("llm_provider"),
        "llm_model": saved.get("llm_model"),
        "has_llm_api_key": bool(saved.get("llm_api_key")),
    }


def seed_demo_dataset(
    data_root: Path,
    *,
    include_settings: bool = True,
    workspace_type: str | None = None,
) -> dict[str, Any]:
    data_root = validate_demo_data_root(data_root, workspace_type=workspace_type)
    data_root.mkdir(parents=True, exist_ok=True)

    profile = seed_profile(data_root)
    portfolio = seed_portfolio(data_root)
    plan = seed_plan(data_root)
    recommendations = seed_recommendations(data_root, str(plan.get("plan_id") or ""))
    import_file = seed_import_file(data_root)
    snapshot_path = seed_snapshot(data_root)
    settings = seed_settings(data_root) if include_settings else {
        "llm_provider": None,
        "llm_model": None,
        "has_llm_api_key": False,
    }

    return {
        "data_root": str(data_root),
        "profile_income_items": len(profile.get("income_items", [])),
        "profile_expense_items": len(profile.get("expense_items", [])),
        "profile_household_members": len(profile.get("household_members", [])),
        "portfolio_total_value": portfolio.get("holdings", {}).get("total_portfolio_value"),
        "portfolio_transactions_removed_before_seed": portfolio.get("removed_demo_transactions"),
        "plan_id": plan.get("plan_id"),
        "recommendations": len(recommendations),
        "import_file": str(import_file),
        "snapshot_file": str(snapshot_path),
        "llm_provider": settings.get("llm_provider"),
        "llm_model": settings.get("llm_model"),
        "has_llm_api_key": settings.get("has_llm_api_key"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed BuildWealth with a realistic average-household demo dataset.")
    parser.add_argument(
        "--data-root",
        required=True,
        help="Demo workspace data root (ws_demo_household or ws_*_demo).",
    )
    args = parser.parse_args()

    summary = seed_demo_dataset(Path(args.data_root), include_settings=True)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
