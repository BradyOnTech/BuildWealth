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
    assert payload["physical_assets"] == []
