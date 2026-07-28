from __future__ import annotations

import asyncio

from buildwealth_orchestrator import main


def test_assumption_defaults_report_engine_fallbacks(monkeypatch, tmp_path) -> None:
    from buildwealth_orchestrator.routes.planning import planning_assumption_defaults
    from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore

    store = FinancialProfileStore(tmp_path / "financial_profile.json")

    class _Services:
        financial_profile_store = store

    monkeypatch.setattr(main, "route_workspace_services", lambda services, **kwargs: _Services())

    payload = planning_assumption_defaults(services=None)
    defaults = payload["defaults"]
    assert defaults["annual_contribution_usd"]["value"] == main.settings.planner_annual_contribution_usd
    assert defaults["inflation_rate"]["value"] == main.settings.planner_inflation
    assert defaults["withdrawal_strategy"] == {"value": "cashflow_only", "source": "buildwealth_default"}
    assert defaults["simulation_mode"]["value"] == "fixed"
    # Every entry carries value + source so the UI can render provenance.
    for entry in defaults.values():
        assert set(entry) == {"value", "source"}
        assert entry["source"] in {
            "profile",
            "profile_cash_flow",
            "profile_retirement_horizon",
            "buildwealth_default",
        }


def test_assumption_defaults_prefer_profile_tax_fields(monkeypatch, tmp_path) -> None:
    from buildwealth_orchestrator.routes.planning import planning_assumption_defaults
    from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore

    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    store.save(
        {"tax_profile": {"filing_status": "married_filing_jointly", "marginal_tax_rate": 0.22}}
    )

    class _Services:
        financial_profile_store = store

    monkeypatch.setattr(main, "route_workspace_services", lambda services, **kwargs: _Services())

    payload = planning_assumption_defaults(services=None)
    defaults = payload["defaults"]
    assert defaults["marginal_tax_rate"] == {"value": 0.22, "source": "profile"}
    assert defaults["filing_status"] == {"value": "married_filing_jointly", "source": "profile"}
    mismatch = payload["profile_mismatch"]
    assert mismatch["profile_value"] == 0.22
    assert mismatch["engine_default"] == main.settings.planner_marginal_tax_rate


def test_assumption_defaults_cover_retirement_and_use_profile_cash_flow(monkeypatch, tmp_path) -> None:
    from buildwealth_orchestrator.routes.planning import planning_assumption_defaults
    from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore

    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    store.save(
        {
            "household_members": [
                {
                    "id": "self",
                    "display_name": "Avery",
                    "relationship": "self",
                    "birth_year": main.utc_now().year - 22,
                    "retirement_age": 67,
                }
            ],
            "income_items": [
                {
                    "id": "salary",
                    "label": "Salary",
                    "monthly_amount_usd": 8000,
                    "is_pre_tax": True,
                }
            ],
            "expense_items": [
                {"id": "living", "label": "Living", "monthly_amount_usd": 3000}
            ],
            "tax_profile": {"effective_tax_rate": 0.12, "state_tax_rate": 0.05},
        }
    )

    class _Services:
        financial_profile_store = store

    monkeypatch.setattr(main, "route_workspace_services", lambda services, **kwargs: _Services())

    defaults = planning_assumption_defaults(services=None)["defaults"]

    assert defaults["years"] == {"value": 75, "source": "profile_retirement_horizon"}
    assert defaults["annual_contribution_usd"] == {
        "value": 43680.0,
        "source": "profile_cash_flow",
    }


def test_plan_run_uses_explicit_household_profile_and_accounts() -> None:
    profile = {
        "household_members": [
            {"display_name": "Alex", "relationship": "self", "birth_year": 1988}
        ],
        "income_items": [
            {"label": "Salary", "monthly_amount_usd": 8_000, "source_type": "salary"}
        ],
        "expense_items": [
            {"label": "Household spending", "monthly_amount_usd": 4_500, "category": "living"}
        ],
        "debt_items": [],
        "tax_profile": {
            "filing_status": "single",
            "marginal_tax_rate": 0.24,
            "state_tax_rate": 0.068,
        },
    }
    settings = {"annual_contribution_usd": 18_000, "years": 1}
    income = main.build_income_projection_for_plan_settings(settings, profile_payload=profile)
    expenses = main.build_expense_projection_for_plan_settings(settings, profile_payload=profile)

    result = asyncio.run(
        main.run_scenarios_for_plan_settings(
            current_portfolio_value_usd=15_000,
            plan_settings=settings,
            income_projection=income,
            expense_projection=expenses,
            profile_payload=profile,
            planning_accounts_override=[
                {
                    "account_id": "default",
                    "account_name": "Default Brokerage",
                    "account_type": "taxable",
                    "balance_usd": 15_000,
                }
            ],
        )
    )

    point = result.scenarios[0].timeline_points[0]
    assumptions = result.scenarios[0].assumptions
    assert point.income_usd == 96_000
    assert point.expenses_usd == 54_000
    assert point.age == main.utc_now().year - 1988
    assert assumptions["filing_status"] == "single"
    assert assumptions["state_tax_rate"] == 0.068
    assert assumptions["account_count"] == 1


def test_plan_value_falls_back_to_current_holdings_without_snapshot(tmp_path) -> None:
    portfolio = main.PortfolioStore(tmp_path / "portfolio")
    portfolio.add_transaction(
        date="2026-07-14",
        symbol="CASH",
        action="CASH_DEPOSIT",
        quantity=1,
        unit_price=1_234,
    )
    snapshots = main.SnapshotStore(tmp_path / "snapshots")

    assert main.resolve_portfolio_value(None, store=snapshots, portfolio=portfolio) == 1_234


def test_scale_expense_projection_payload_scales_money_fields_immutably() -> None:
    payload = {
        "first_year_expenses_usd": 100_000.0,
        "final_year_expenses_usd": 120_000.0,
        "yearly_points": [
            {"year": 2026, "total_expenses_usd": 100_000.0, "fixed_expenses_usd": 60_000.0},
            {"year": 2027, "total_expenses_usd": 103_000.0, "fixed_expenses_usd": 61_800.0},
        ],
    }
    scaled = main.scale_expense_projection_payload(payload, scale=0.9)
    assert scaled is not payload
    assert scaled["first_year_expenses_usd"] == 90_000.0
    assert scaled["final_year_expenses_usd"] == 108_000.0
    assert scaled["yearly_points"][0]["total_expenses_usd"] == 90_000.0
    assert scaled["yearly_points"][0]["fixed_expenses_usd"] == 54_000.0
    assert scaled["expense_scale"] == 0.9
    # Original untouched
    assert payload["first_year_expenses_usd"] == 100_000.0
    assert payload["yearly_points"][0]["total_expenses_usd"] == 100_000.0
    # Identity scale returns original reference
    assert main.scale_expense_projection_payload(payload, scale=1.0) is payload
