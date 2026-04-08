from pathlib import Path

from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore


def test_financial_profile_store_defaults(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    payload = store.get()

    assert payload["income_items"] == []
    assert payload["expense_items"] == []
    assert payload["debt_items"] == []
    assert payload["goal_items"] == []
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
        }
    )

    assert saved["income_items"][0]["id"].startswith("income-")
    assert saved["expense_items"][0]["id"].startswith("expense-")
    assert saved["debt_items"][0]["id"].startswith("debt-")
    assert saved["goal_items"][0]["id"].startswith("goal-")
