from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.statement_profile_reconciliation import (
    CLARIFICATION_KIND,
    reconcile_statement_expenses,
    resolve_statement_payment_conflict,
)


def _profile() -> dict:
    return {
        "expense_items": [
            {
                "id": "expense-storage",
                "label": "Boat storage",
                "monthly_amount_usd": 200,
                "category": "storage",
                "linked_asset_id": "asset-boat",
            }
        ],
        "debt_items": [
            {
                "id": "debt-auto",
                "label": "Toyota auto loan",
                "debt_type": "auto",
                "balance_usd": 18_000,
                "minimum_payment_usd": 620,
                "linked_asset_id": "asset-car",
            },
            {
                "id": "debt-boat",
                "label": "Fishing boat loan",
                "debt_type": "vehicle",
                "balance_usd": 30_000,
                "minimum_payment_usd": 410,
                "linked_asset_id": "asset-boat",
            },
        ],
        "physical_assets": [
            {"id": "asset-car", "label": "Toyota Tacoma", "subtype": "truck"},
            {"id": "asset-boat", "label": "Fishing boat", "subtype": "boat"},
        ],
    }


def test_clear_statement_matches_are_not_added_twice() -> None:
    result = reconcile_statement_expenses(
        _profile(),
        [
            {
                "label": "Toyota Financial",
                "monthly_amount_usd": 620,
                "category": "transportation",
                "sample_descriptions": ["TOYOTA FINANCIAL ACH PAYMENT"],
            },
            {
                "label": "Boat storage",
                "monthly_amount_usd": 200,
                "category": "storage",
            },
            {
                "label": "Cardmember Payment Thank You",
                "monthly_amount_usd": 1_250,
                "category": "general",
            },
        ],
    )

    assert result["safe_expenses"] == []
    assert result["conflicts"] == []
    assert [row["match_kind"] for row in result["already_counted"]] == [
        "debt",
        "expense",
        "statement_transfer",
    ]


def test_uncertain_payment_is_held_for_a_question() -> None:
    result = reconcile_statement_expenses(
        _profile(),
        [
            {
                "label": "ACH Withdrawal",
                "monthly_amount_usd": 410,
                "category": "general",
                "sample_descriptions": ["ACH WITHDRAWAL 8841"],
            }
        ],
    )

    assert result["safe_expenses"] == []
    assert result["already_counted"] == []
    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert conflict["matches"][0]["id"] == "debt-boat"
    assert "same payment" in conflict["question"]
    assert "separate expense" in conflict["question"]


def test_near_semantic_match_is_held_but_unrelated_spending_is_safe() -> None:
    result = reconcile_statement_expenses(
        _profile(),
        [
            {
                "label": "Toyota Motor Credit",
                "monthly_amount_usd": 640,
                "category": "transportation",
            },
            {
                "label": "Neighborhood daycare",
                "monthly_amount_usd": 900,
                "category": "childcare",
            },
        ],
    )

    assert [row["label"] for row in result["safe_expenses"]] == ["Neighborhood daycare"]
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["matches"][0]["id"] == "debt-auto"
    assert result["conflicts"][0]["matches"][0]["amount_match"] == "near"


class _ContextService:
    def __init__(self) -> None:
        self.updated: dict | None = None
        self.restored: dict | None = None

    def update_context_candidate_lifecycle(
        self,
        candidate_id: str,
        *,
        lifecycle_state: str,
        prompt_influence: str,
        metadata_patch: dict,
    ) -> dict:
        self.updated = {
            "id": candidate_id,
            "lifecycle_state": lifecycle_state,
            "prompt_influence": prompt_influence,
            "metadata": metadata_patch,
        }
        return self.updated

    def restore_context_candidate_lifecycle(self, candidate: dict) -> None:
        self.restored = candidate


def _candidate() -> dict:
    return {
        "id": "candidate-1",
        "lifecycle_state": "pending_review",
        "metadata": {
            "clarification_kind": CLARIFICATION_KIND,
            "statement_suggestion": {
                "label": "ACH Withdrawal",
                "monthly_amount_usd": 410,
                "category": "general",
                "is_fixed": True,
            },
        },
    }


def test_copilot_resolution_adds_only_when_user_says_separate(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "profile.json")
    store.save({"expense_items": []})
    context = _ContextService()

    resolved = resolve_statement_payment_conflict(
        candidate=_candidate(),
        resolution="separate_expense",
        profile_store=store,
        context_service=context,
    )

    assert resolved["added_expenses"] == 1
    assert resolved["profile_changed"] is True
    assert store.get()["expense_items"][0]["label"] == "ACH Withdrawal"
    assert context.updated["lifecycle_state"] == "applied"


def test_copilot_resolution_same_payment_never_adds_an_expense(tmp_path: Path) -> None:
    store = FinancialProfileStore(tmp_path / "profile.json")
    store.save({"expense_items": []})
    context = _ContextService()

    resolved = resolve_statement_payment_conflict(
        candidate=_candidate(),
        resolution="same_as_existing",
        profile_store=store,
        context_service=context,
    )

    assert resolved["added_expenses"] == 0
    assert resolved["profile_changed"] is False
    assert store.get()["expense_items"] == []
    assert context.updated["metadata"]["resolution"] == "same_as_existing"
