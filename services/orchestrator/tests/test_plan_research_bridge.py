import pytest

import buildwealth_orchestrator.main as main


def test_select_research_bridge_watchlist_items_respects_requested_symbols_and_limit() -> None:
    selected = main.select_research_bridge_watchlist_items(
        watchlist_items=[
            {"symbol": "nvda", "thesis": "AI demand"},
            {"symbol": "vti", "thesis": "Core market"},
            {"symbol": "cash", "thesis": "Reserve"},
            {"symbol": "vti", "thesis": "duplicate should collapse"},
        ],
        requested_symbols=["VTI", "NVDA", "TSLA"],
        max_symbols=2,
    )

    assert [item["symbol"] for item in selected] == ["VTI", "NVDA"]


def test_pin_watchlist_research_to_plan_branch_template_replaces_previous_bridge_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePlanWorkspace:
        def __init__(self) -> None:
            self.updated_payload = None

        def get_plan_branch_templates(self, plan_id: str) -> dict[str, object]:
            assert plan_id == "plan-bridge"
            return {
                "schema_version": 2,
                "default_template_id": "stress_case",
                "templates": [
                    {
                        "id": "stress_case",
                        "name": "Stress Case",
                        "description": "Existing preset",
                        "branch_name": "Stress Branch",
                        "assumption_set_id": "default",
                        "compare_settings": {"annual_contribution_usd": 18000},
                        "branch_events": [
                            {
                                "label": "Layoff",
                                "event_type": "job_change",
                                "impact_type": "income",
                                "amount_usd": -6000,
                                "recurring_frequency": "monthly",
                                "start_year_offset": 0,
                                "duration_months": 6,
                                "account_id": None,
                                "notes": "non-bridge-event",
                            },
                            {
                                "label": "Research Thesis: OLD",
                                "event_type": "milestone",
                                "impact_type": "portfolio",
                                "amount_usd": 0,
                                "recurring_frequency": "one_time",
                                "start_year_offset": 0,
                                "duration_months": None,
                                "account_id": None,
                                "notes": "[research-bridge] symbol=OLD | thesis: stale",
                            },
                        ],
                    }
                ],
            }

        def get_plan_assumption_sets(self, plan_id: str) -> dict[str, object]:
            assert plan_id == "plan-bridge"
            return {
                "schema_version": 2,
                "active_assumption_set_id": "default",
                "sets": [
                    {"id": "default", "name": "Default"},
                    {"id": "conservative", "name": "Conservative"},
                ],
            }

        def update_plan_branch_templates(
            self,
            *,
            plan_id: str,
            branch_templates_payload: dict[str, object],
            rationale: str | None = None,
            status: str = "accepted",
            log_decision: bool = True,
        ) -> dict[str, object]:
            assert plan_id == "plan-bridge"
            assert "research-to-planning bridge" in str(rationale or "")
            assert status == "accepted"
            assert log_decision is True
            self.updated_payload = branch_templates_payload
            return {
                "schema_version": 2,
                "default_template_id": branch_templates_payload.get("default_template_id"),
                "templates": branch_templates_payload.get("templates", []),
            }

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [
                {
                    "symbol": "NVDA",
                    "data_source": "OPENBB",
                    "thesis": "AI infra compounding demand",
                    "note": "Monitor valuation",
                    "target_price_usd": 1200,
                    "tags": ["ai", "semis"],
                },
                {
                    "symbol": "VTI",
                    "data_source": "OPENBB",
                    "thesis": "Core broad-market exposure",
                    "note": "Taxable core",
                    "target_price_usd": None,
                    "tags": ["core"],
                },
            ]

    fake_workspace = FakePlanWorkspace()
    monkeypatch.setattr(main, "plan_workspace", fake_workspace)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())

    response = main.pin_watchlist_research_to_plan_branch_template(
        "plan-bridge",
        main.PlanResearchBridgeRequest(
            branch_template_id="stress_case",
            assumption_set_id="conservative",
            symbols=["NVDA", "VTI"],
        ),
    )

    assert response.plan_id == "plan-bridge"
    assert response.template_id == "stress_case"
    assert response.pinned_symbols == ["NVDA", "VTI"]

    assert fake_workspace.updated_payload is not None
    templates = fake_workspace.updated_payload.get("templates")
    assert isinstance(templates, list)
    template = next(item for item in templates if item.get("id") == "stress_case")

    events = template.get("branch_events")
    assert isinstance(events, list)
    assert len(events) == 3
    assert any(event.get("label") == "Layoff" for event in events)
    assert not any("symbol=OLD" in str(event.get("notes") or "") for event in events)
    assert any(
        event.get("label") == "Research Thesis: NVDA"
        and "[research-bridge]" in str(event.get("notes") or "")
        and "thesis: AI infra compounding demand" in str(event.get("notes") or "")
        for event in events
    )


def test_pin_watchlist_research_to_plan_branch_template_returns_400_when_symbols_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePlanWorkspace:
        def get_plan_branch_templates(self, plan_id: str) -> dict[str, object]:
            assert plan_id == "plan-bridge"
            return {
                "schema_version": 2,
                "default_template_id": None,
                "templates": [],
            }

        def update_plan_branch_templates(self, **kwargs):  # pragma: no cover
            raise AssertionError("update_plan_branch_templates should not be called")

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "NVDA", "thesis": "AI infra"}]

    monkeypatch.setattr(main, "plan_workspace", FakePlanWorkspace())
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())

    with pytest.raises(main.HTTPException) as exc:
        main.pin_watchlist_research_to_plan_branch_template(
            "plan-bridge",
            main.PlanResearchBridgeRequest(symbols=["TSLA"]),
        )

    assert exc.value.status_code == 400
    assert "requested symbols" in str(exc.value.detail)
