from __future__ import annotations

from buildwealth_orchestrator.services.profile_inference import (
    build_profile_inference_candidates,
)


def _profile(**overrides) -> dict:
    base = {
        "income_items": [],
        "expense_items": [],
        "tax_profile": {
            "filing_status": None,
            "marginal_tax_rate": None,
            "effective_tax_rate": None,
            "state_tax_rate": None,
            "state": None,
        },
        "investment_policy": {},
    }
    base.update(overrides)
    return base


def _income(monthly: float) -> dict:
    return {"id": "income-1", "label": "My income", "monthly_amount_usd": monthly}


def test_bracket_inference_single_90k_is_22_percent() -> None:
    drafts = build_profile_inference_candidates(
        profile_payload=_profile(income_items=[_income(7500.0)]),
        statement_reports=[],
        portfolio_transactions=[],
        tax_year=2026,
    )
    bracket = [d for d in drafts if d["target_field"] == "tax_profile.marginal_tax_rate"]
    assert len(bracket) == 1
    draft = bracket[0]
    # 90,000 - 16,100 standard deduction = 73,900 taxable -> 22% bracket
    assert draft["target_value"] == 0.22
    assert draft["target_domain"] == "profile"
    assert draft["target_area"] == "tax_profile"
    assert draft["confidence"] == "medium"
    assert draft["lifecycle_state"] == "pending_review"
    assert draft["metadata"]["inference_kind"] == "bracket_from_income"
    assert draft["metadata"]["requires_user_confirmation"] is True
    claim = draft["extracted_claim"]
    assert "90,000" in claim
    assert "single" in claim
    assert "2026" in claim


def test_bracket_inference_respects_filing_status() -> None:
    profile = _profile(income_items=[_income(7500.0)])
    profile["tax_profile"]["filing_status"] = "married_filing_jointly"
    drafts = build_profile_inference_candidates(
        profile_payload=profile,
        statement_reports=[],
        portfolio_transactions=[],
    )
    draft = next(d for d in drafts if d["target_field"] == "tax_profile.marginal_tax_rate")
    # 90,000 - 32,200 = 57,800 taxable -> 12% MFJ bracket
    assert draft["target_value"] == 0.12


def test_no_bracket_candidate_when_marginal_rate_already_set() -> None:
    profile = _profile(income_items=[_income(7500.0)])
    profile["tax_profile"]["marginal_tax_rate"] = 0.24
    drafts = build_profile_inference_candidates(
        profile_payload=profile,
        statement_reports=[],
        portfolio_transactions=[],
    )
    assert not [d for d in drafts if d["target_field"] == "tax_profile.marginal_tax_rate"]


def test_no_bracket_candidate_without_income() -> None:
    drafts = build_profile_inference_candidates(
        profile_payload=_profile(),
        statement_reports=[],
        portfolio_transactions=[],
    )
    assert not [d for d in drafts if d["target_field"] == "tax_profile.marginal_tax_rate"]


def test_no_filing_status_guess() -> None:
    profile = _profile(
        income_items=[_income(7500.0)],
        household_members=[
            {"id": "m1", "relationship": "self"},
            {"id": "m2", "relationship": "partner"},
        ],
    )
    drafts = build_profile_inference_candidates(
        profile_payload=profile,
        statement_reports=[],
        portfolio_transactions=[],
    )
    assert not [d for d in drafts if d["target_field"] == "tax_profile.filing_status"]


def _report(**overrides) -> dict:
    base = {
        "report_id": "ir_20260701T000000_abc",
        "created_at": "2026-07-01T00:00:00+00:00",
        "income_suggestions": [
            {"label": "Employer payroll", "monthly_amount_usd": 6250.0, "source_type": "salary"},
        ],
        "expense_suggestions": [
            {"label": "Rent", "monthly_amount_usd": 2100.0, "category": "housing", "is_fixed": True},
        ],
    }
    base.update(overrides)
    return base


def test_statement_suggestions_only_when_profile_sections_empty() -> None:
    drafts = build_profile_inference_candidates(
        profile_payload=_profile(),
        statement_reports=[_report()],
        portfolio_transactions=[],
    )
    income = next(d for d in drafts if d["target_field"] == "income_items")
    expense = next(d for d in drafts if d["target_field"] == "expense_items")

    assert income["metadata"]["profile_patch_kind"] == "income_items"
    assert income["metadata"]["requires_user_confirmation"] is True
    items = income["target_value"]["income_items"]
    assert items == [
        {
            "label": "Employer payroll",
            "monthly_amount_usd": 6250.0,
            "source_type": "salary",
            "is_pre_tax": False,
        }
    ]

    assert expense["metadata"]["profile_patch_kind"] == "expense_items"
    assert expense["target_value"]["expense_items"][0]["category"] == "housing"

    # Populated profile sections suppress the statement candidates.
    populated = build_profile_inference_candidates(
        profile_payload=_profile(
            income_items=[_income(7500.0)],
            expense_items=[{"id": "e1", "label": "Rent", "monthly_amount_usd": 2100.0}],
        ),
        statement_reports=[_report()],
        portfolio_transactions=[],
    )
    assert not [d for d in populated if d["target_field"] in {"income_items", "expense_items"}]


def test_statement_suggestions_use_newest_report_with_data() -> None:
    stale = _report(
        report_id="ir_old",
        created_at="2026-01-01T00:00:00+00:00",
        income_suggestions=[{"label": "Old employer", "monthly_amount_usd": 5000.0, "source_type": "salary"}],
    )
    newest_empty = _report(
        report_id="ir_new_empty",
        created_at="2026-07-05T00:00:00+00:00",
        income_suggestions=[],
        expense_suggestions=[],
    )
    drafts = build_profile_inference_candidates(
        profile_payload=_profile(),
        statement_reports=[stale, newest_empty],
        portfolio_transactions=[],
    )
    income = next(d for d in drafts if d["target_field"] == "income_items")
    assert income["target_value"]["income_items"][0]["label"] == "Old employer"
    assert income["metadata"]["import_report_id"] == "ir_old"


def test_stable_dedupe_keys_across_sweeps() -> None:
    kwargs = dict(
        profile_payload=_profile(income_items=[_income(7500.0)]),
        statement_reports=[_report()],
        portfolio_transactions=[],
    )
    first = {d["target_field"]: d["dedupe_key"] for d in build_profile_inference_candidates(**kwargs)}
    second = {d["target_field"]: d["dedupe_key"] for d in build_profile_inference_candidates(**kwargs)}

    assert first == second
    assert first["tax_profile.marginal_tax_rate"] == "profile_inference:tax_profile.marginal_tax_rate"
    assert first["expense_items"] == "profile_inference:expense_items"
    # Every draft has its own stable key.
    assert len(set(first.values())) == len(first)
