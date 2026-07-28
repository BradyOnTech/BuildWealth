from datetime import datetime, timezone
from pathlib import Path

from buildwealth_orchestrator.services.financial_profile import (
    FinancialProfileStore,
    profile_metadata_quality_warnings,
    profile_metadata_review_field_paths,
)


def test_financial_profile_store_defaults(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    payload = store.get()

    assert payload["schema_version"] == 3
    assert payload["income_items"] == []
    assert payload["expense_items"] == []
    assert payload["debt_items"] == []
    assert payload["goal_items"] == []
    assert payload["physical_assets"] == []
    assert payload["insurance_policies"] == []
    assert payload["benefit_items"] == []
    assert payload["estate_readiness"]["will_status"] == "unknown"
    assert payload["tax_profile"]["filing_status"] is None
    assert payload["tax_profile"]["state_tax_rate"] is None
    assert payload["investment_policy"]["max_single_symbol_exposure_pct"] is None
    assert payload["investment_policy"]["max_sector_exposure_pct"] is None
    assert payload["investment_policy"]["minimum_research_confidence"] is None
    assert payload["investment_policy"]["minimum_cash_runway_months"] is None
    assert payload["investment_policy"]["max_asset_class_exposure_pct"] == {}
    assert payload["investment_policy"]["simplicity_preference"] is None
    assert payload["investment_policy"]["preferred_account_locations"] == {}
    assert payload["investment_policy"]["restricted_symbols"] == []
    assert payload["investment_policy"]["restricted_sectors"] == []
    assert payload["flags"]["no_debt"] is False
    assert payload["profile_metadata"] == {}
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
                "minimum_cash_runway_months": 9.0,
                "max_asset_class_exposure_pct": {"equity": 85.0},
                "simplicity_preference": "high",
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
    assert saved["investment_policy"]["minimum_cash_runway_months"] == 9.0
    assert saved["investment_policy"]["max_asset_class_exposure_pct"] == {"equity": 85.0}
    assert saved["investment_policy"]["simplicity_preference"] == "high"
    assert saved["investment_policy"]["tax_sensitivity"] == "high"
    assert saved["investment_policy"]["preferred_account_locations"] == {"equity": ["tax_free"]}
    assert saved["investment_policy"]["restricted_symbols"] == ["NVDA"]
    assert saved["investment_policy"]["restricted_sectors"] == ["Crypto"]
    metadata = saved["profile_metadata"]
    single_symbol_metadata = metadata["investment_policy.max_single_symbol_exposure_pct"]
    assert single_symbol_metadata["status"] == "user_confirmed"
    assert single_symbol_metadata["source"] == "profile_editor"
    assert single_symbol_metadata["confirmed_by_user"] is True
    assert single_symbol_metadata["last_confirmed_at"]


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

    assert payload["schema_version"] == 3
    assert payload["income_items"][0]["annual_growth_rate"] is None
    assert payload["expense_items"][0]["inflation_rate"] is None
    assert payload["debt_items"][0]["payoff_strategy"] == "minimum"
    assert payload["debt_items"][0]["custom_monthly_payment_usd"] is None
    assert payload["physical_assets"] == []
    assert payload["insurance_policies"] == []
    assert payload["benefit_items"] == []
    assert payload["estate_readiness"]["will_status"] == "unknown"
    assert payload["investment_policy"]["max_single_symbol_exposure_pct"] is None
    assert payload["profile_metadata"] == {}


def test_financial_profile_store_marks_changed_tax_fields_with_metadata(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "financial_profile.json")

    saved = store.save(
        {
            "tax_profile": {
                "filing_status": "single",
                "marginal_tax_rate": 0.28,
            },
        },
        metadata_source="profile_editor",
    )

    metadata = saved["profile_metadata"]
    assert metadata["tax_profile.filing_status"]["status"] == "user_confirmed"
    assert metadata["tax_profile.marginal_tax_rate"]["status"] == "user_confirmed"
    assert metadata["tax_profile.marginal_tax_rate"]["stale_after_days"] == 180
    assert "tax_profile.effective_tax_rate" not in metadata


def test_profile_metadata_review_helpers_flag_stale_material_fields() -> None:
    payload = {
        "tax_profile": {"filing_status": "single", "marginal_tax_rate": 0.28},
        "investment_policy": {"max_single_symbol_exposure_pct": 10.0},
        "profile_metadata": {
            "tax_profile.marginal_tax_rate": {
                "status": "user_confirmed",
                "source": "profile_editor",
                "confidence": "high",
                "last_confirmed_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "stale_after_days": 180,
                "confirmed_by_user": True,
            },
            "investment_policy.max_single_symbol_exposure_pct": {
                "status": "user_confirmed",
                "source": "profile_editor",
                "confidence": "high",
                "last_confirmed_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "stale_after_days": 365,
                "confirmed_by_user": True,
            },
        },
    }

    now = datetime(2026, 5, 7, tzinfo=timezone.utc)

    assert profile_metadata_review_field_paths(payload, now=now) == [
        "tax_profile.marginal_tax_rate"
    ]
    assert profile_metadata_quality_warnings(payload, now=now) == [
        "financial_profile.tax_profile.marginal_tax_rate.stale"
    ]
