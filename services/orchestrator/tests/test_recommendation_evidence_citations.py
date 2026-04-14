import asyncio
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_build_research_dossier_lookup_payload_filters_and_parses_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Dossier Lookup Plan")
    workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - NVDA vs MSFT",
        markdown="# Research Dossier: NVDA, MSFT\n\n## Scorecard\n",
        kind="research_dossier",
    )
    workspace.write_artifact(
        plan_id=plan["id"],
        title="Workflow Report",
        markdown="# Workflow Report\n",
        kind="daily_review",
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    payload = main.build_research_dossier_lookup_payload(plan_id=plan["id"], limit=5, include_content=False)

    assert payload["plan_id"] == plan["id"]
    assert payload["count"] == 1
    assert payload["items"][0]["symbols"] == ["NVDA", "MSFT"]


def test_tool_create_recommendation_auto_cites_latest_dossier_for_copilot_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Citation Plan")
    dossier_artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - NVDA vs MSFT",
        markdown="# Research Dossier: NVDA, MSFT\n\n## Headline\n",
        kind="research_dossier",
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = asyncio.run(
        main.tool_create_recommendation(
            {
                "title": "Reassess NVDA sizing",
                "detail": "Use research evidence before changing exposure.",
                "source": "copilot",
                "plan_id": plan["id"],
                "action_payload": {"research_symbols": ["NVDA"]},
            }
        )
    )

    recommendation = payload["recommendation"]
    evidence = recommendation["action_payload"]["evidence"]
    citation_quality = evidence["citation_quality"]
    citations = evidence["citations"]

    assert citation_quality["required"] is True
    assert citation_quality["status"] == "satisfied"
    assert citation_quality["missing_dossier_symbols"] == []
    assert any(item["symbol"] == "NVDA" for item in citations)
    assert any(item["artifact_id"] == dossier_artifact["id"] for item in citations)


def test_tool_create_recommendation_requires_dossier_citations_for_copilot_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Citation Enforcement Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    with pytest.raises(ValueError, match="require dossier-backed evidence citations"):
        asyncio.run(
            main.tool_create_recommendation(
                {
                    "title": "Review NVDA trade idea",
                    "detail": "Need citation enforcement.",
                    "source": "copilot",
                    "plan_id": plan["id"],
                    "action_payload": {"research_symbols": ["NVDA"]},
                }
            )
        )


def test_create_recommendation_route_manual_source_allows_missing_dossier_citations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Manual Source Plan")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    item = main.create_recommendation(
        main.RecommendationCreateRequest(
            title="Track NVDA for next review",
            detail="Manual note without dossier artifact.",
            source="manual-ui",
            plan_id=plan["id"],
            action_payload={"research_symbols": ["NVDA"]},
        )
    )

    citation_quality = item.action_payload.get("evidence", {}).get("citation_quality", {})
    assert citation_quality.get("required") is False
    assert citation_quality.get("status") == "missing"
