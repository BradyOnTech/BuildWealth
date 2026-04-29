from pathlib import Path

from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore


def test_financial_profile_store_defaults(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    payload = store.get()

    assert payload["schema_version"] == 2
    assert payload["income_items"] == []
    assert payload["expense_items"] == []
    assert payload["debt_items"] == []
    assert payload["goal_items"] == []
    assert payload["physical_assets"] == []
    assert payload["tax_profile"]["filing_status"] is None
    assert payload["tax_profile"]["state_tax_rate"] is None
    assert payload["investment_policy"]["max_single_symbol_exposure_pct"] is None
    assert payload["investment_policy"]["max_sector_exposure_pct"] is None
    assert payload["investment_policy"]["minimum_research_confidence"] is None
    assert payload["investment_policy"]["preferred_account_locations"] == {}
    assert payload["investment_policy"]["restricted_symbols"] == []
    assert payload["investment_policy"]["restricted_sectors"] == []
    assert payload["flags"]["no_debt"] is False
    assert payload["updated_at"]


def test_financial_profile_store_save_generates_ids(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    saved = store.save(
        {
            "income_items": [{"id": "", "label": "Salary", "monthly_amount_usd": 10000}],
            "expense_items": [{"id": "", "label": "Rent", "monthly_amount_usd": 2500}],
            "debt_items": [{"id": "", "label": "Loan", "balance_usd": 12000}],
            "goal_items": [{"id": "", "label": "FI", "target_amount_usd": 1000000}],
            "physical_assets": [{"id": "", "label": "House", "current_value_usd": 450000}],
        }
    )

    assert saved["income_items"][0]["id"].startswith("income-")
    assert saved["expense_items"][0]["id"].startswith("expense-")
    assert saved["debt_items"][0]["id"].startswith("debt-")
    assert saved["goal_items"][0]["id"].startswith("goal-")
    assert saved["physical_assets"][0]["id"].startswith("asset-")


def test_financial_profile_store_saves_investment_policy(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    saved = store.save(
        {
            "investment_policy": {
                "max_single_symbol_exposure_pct": 10.0,
                "max_sector_exposure_pct": 30.0,
                "minimum_research_confidence": "medium",
                "tax_sensitivity": "high",
                "preferred_account_locations": {"equity": ["tax_free"]},
                "restricted_symbols": ["NVDA"],
                "restricted_sectors": ["Crypto"],
            },
        }
    )

    assert saved["investment_policy"]["max_single_symbol_exposure_pct"] == 10.0
    assert saved["investment_policy"]["max_sector_exposure_pct"] == 30.0
    assert saved["investment_policy"]["minimum_research_confidence"] == "medium"
    assert saved["investment_policy"]["tax_sensitivity"] == "high"
    assert saved["investment_policy"]["preferred_account_locations"] == {"equity": ["tax_free"]}
    assert saved["investment_policy"]["restricted_symbols"] == ["NVDA"]
    assert saved["investment_policy"]["restricted_sectors"] == ["Crypto"]


def test_financial_profile_store_migrates_legacy_payload(tmp_path: Path) -> None:
    path = tmp_path / "financial_profile.json"
    path.write_text(
        """
{
  "income_items": [{"id": "income-1", "label": "Salary", "monthly_amount_usd": 10000}],
  "expense_items": [{"id": "expense-1", "label": "Rent", "monthly_amount_usd": 2500}],
  "debt_items": [{"id": "debt-1", "label": "Loan", "balance_usd": 12000}],
  "goal_items": [{"id": "goal-1", "label": "FI", "target_amount_usd": 1000000}]
}
        """.strip(),
        encoding="utf-8",
    )

    store = FinancialProfileStore(path)
    payload = store.get()

    assert payload["schema_version"] == 2
    assert payload["income_items"][0]["annual_growth_rate"] is None
    assert payload["expense_items"][0]["inflation_rate"] is None
    assert payload["debt_items"][0]["payoff_strategy"] == "minimum"
    assert payload["debt_items"][0]["custom_monthly_payment_usd"] is None
    assert payload["physical_assets"] == []
    assert payload["investment_policy"]["max_single_symbol_exposure_pct"] is None
