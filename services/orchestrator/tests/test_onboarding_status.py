from datetime import datetime, timezone

from buildwealth_orchestrator.main import build_onboarding_status_response
from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency="USD",
        total_value_usd=100000,
        total_investment_usd=90000,
        net_performance_usd=10000,
        net_performance_percent=0.111,
        holdings=[
            Holding(symbol="VTI", name="VTI", value_usd=70000, allocation_percent=70),
            Holding(symbol="VXUS", name="VXUS", value_usd=30000, allocation_percent=30),
        ],
    )


def test_onboarding_status_complete_path() -> None:
    status = build_onboarding_status_response(
        profile_payload={
            "income_items": [{"id": "income-1", "label": "Salary", "monthly_amount_usd": 10000}],
            "expense_items": [{"id": "expense-1", "label": "Rent", "monthly_amount_usd": 2000}],
            "debt_items": [],
            "goal_items": [{"id": "goal-1", "label": "FI", "target_amount_usd": 1200000}],
            "tax_profile": {"filing_status": "single", "marginal_tax_rate": 0.24},
            "investment_policy": {"max_single_symbol_exposure_pct": 10},
            "flags": {"no_debt": True, "no_goals": False},
            "notes": "",
        },
        latest_snapshot=_snapshot(),
        active_plan_detail={
            "settings": {
                "annual_contribution_usd": 22000,
                "years": 25,
                "hsa_extra_contribution_usd": 1000,
                "marginal_tax_rate": 0.24,
                "expected_return_baseline": 0.07,
            }
        },
        load_fallbacks=False,
    )

    assert status.completion_percent > 70
    assert any(step.id == "income" and step.status == "complete" for step in status.steps)
    assert any(step.id == "active_plan" and step.status == "complete" for step in status.steps)
    assert status.profile_readiness is not None
    assert status.profile_readiness.status == "ready"
    assert status.profile_readiness.next_gap_key is None
    assert status.profile_readiness.blocking_recommendation_sources == []
    assert status.decision_stage == "ready"
    assert status.decision_headline == "Ready for tailored advice"
    assert any(
        section.key == "investment_policy"
        and section.status == "complete"
        and "10%" in section.detail
        for section in status.profile_readiness.sections
    )


def test_onboarding_status_incomplete_path() -> None:
    status = build_onboarding_status_response(
        profile_payload={
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "tax_profile": {"filing_status": None, "marginal_tax_rate": None},
            "flags": {"no_debt": False, "no_goals": False},
            "notes": "",
        },
        latest_snapshot=None,
        active_plan_detail=None,
        load_fallbacks=False,
    )

    assert status.completion_percent < 40
    assert status.ready_for_daily_review is False
    assert any(step.id == "snapshot" and step.status == "incomplete" for step in status.steps)
    assert status.profile_readiness is not None
    assert status.profile_readiness.status == "incomplete"
    assert status.profile_readiness.next_gap_key == "income"
    assert status.decision_stage == "profile"
    assert status.decision_detail == "Next: Income profile."
    assert "profile_completeness" in status.profile_readiness.blocking_recommendation_sources
    assert any(section.key == "tax_profile" for section in status.profile_readiness.sections)
    assert any(
        section.key == "investment_policy"
        and section.status == "attention"
        and section.blocking_recommendations is False
        for section in status.profile_readiness.sections
    )
    readiness_by_key = {section.key: section for section in status.profile_readiness.sections}
    for step in status.steps:
        if step.id in readiness_by_key:
            section = readiness_by_key[step.id]
            assert (step.status, step.detail) == (section.status, section.detail)
