from __future__ import annotations

import asyncio

from buildwealth_orchestrator import main


def _readiness(**overrides):
    base = dict(
        household_members=[],
        income_items=[],
        expense_items=[],
        debt_items=[],
        goal_items=[],
        physical_assets=[],
        flags={},
        tax_profile={},
        investment_policy={},
        profile_metadata={},
    )
    base.update(overrides)
    return main._build_profile_readiness_summary(**base)


def _section(summary, key):
    return next(section for section in summary.sections if section.key == key)


def test_household_section_incomplete_when_empty() -> None:
    summary = _readiness()
    section = _section(summary, "household")
    assert section.status == "incomplete"
    assert "Add who is in the household" in section.detail


def test_household_section_complete_with_members() -> None:
    summary = _readiness(
        household_members=[
            {"id": "m1", "display_name": "Me", "relationship": "self", "birth_year": 1988},
            {"id": "m2", "display_name": "Kid", "relationship": "child", "dependent": True},
        ]
    )
    section = _section(summary, "household")
    assert section.status == "complete"
    assert "2 member(s)" in section.detail
    assert "1 dependent(s)" in section.detail


def test_mfj_without_partner_flags_attention() -> None:
    summary = _readiness(
        household_members=[{"id": "m1", "display_name": "Me", "relationship": "self"}],
        tax_profile={"filing_status": "married_filing_jointly", "marginal_tax_rate": 0.24},
    )
    section = _section(summary, "household")
    assert section.status == "attention"
    assert "no partner is on record" in section.detail


def test_partner_with_single_filing_flags_attention() -> None:
    summary = _readiness(
        household_members=[
            {"id": "m1", "display_name": "Me", "relationship": "self"},
            {"id": "m2", "display_name": "Sam", "relationship": "partner"},
        ],
        tax_profile={"filing_status": "single"},
    )
    section = _section(summary, "household")
    assert section.status == "attention"
    assert "filing status is single" in section.detail


def test_copilot_draft_accepts_household_members() -> None:
    draft = asyncio.run(
        main.tool_draft_financial_profile_update(
            {
                "household_members": [
                    {"display_name": "Me", "relationship": "self", "birth_year": 1988},
                    {"display_name": "Kid", "relationship": "child", "dependent": True},
                ]
            }
        )
    )
    assert draft["draft_kind"] == "financial_profile_update"
    members = draft["patch_payload"]["household_members"]
    assert len(members) == 2
    assert all(str(member.get("id", "")).startswith("member-") for member in members)
    assert draft["section_counts"]["household_members"] == 2
    assert draft["requires_confirmation"] is True
