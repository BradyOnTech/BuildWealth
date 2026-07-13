from __future__ import annotations

from buildwealth_orchestrator import main


def test_assumption_defaults_report_engine_fallbacks(monkeypatch, tmp_path) -> None:
    from buildwealth_orchestrator.routes.planning import planning_assumption_defaults
    from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore

    store = FinancialProfileStore(tmp_path / "financial_profile.json")

    class _Services:
        financial_profile_store = store

    monkeypatch.setattr(main, "route_workspace_services", lambda services, **kwargs: _Services())

    payload = planning_assumption_defaults(services=None)
    defaults = payload["defaults"]
    assert defaults["annual_contribution_usd"]["value"] == main.settings.planner_annual_contribution_usd
    assert defaults["inflation_rate"]["value"] == main.settings.planner_inflation
    assert defaults["withdrawal_strategy"] == {"value": "cashflow_only", "source": "buildwealth_default"}
    assert defaults["simulation_mode"]["value"] == "fixed"
    # Every entry carries value + source so the UI can render provenance.
    for entry in defaults.values():
        assert set(entry) == {"value", "source"}
        assert entry["source"] in {"profile", "buildwealth_default"}


def test_assumption_defaults_prefer_profile_tax_fields(monkeypatch, tmp_path) -> None:
    from buildwealth_orchestrator.routes.planning import planning_assumption_defaults
    from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore

    store = FinancialProfileStore(tmp_path / "financial_profile.json")
    store.save(
        {"tax_profile": {"filing_status": "married_filing_jointly", "marginal_tax_rate": 0.22}}
    )

    class _Services:
        financial_profile_store = store

    monkeypatch.setattr(main, "route_workspace_services", lambda services, **kwargs: _Services())

    payload = planning_assumption_defaults(services=None)
    defaults = payload["defaults"]
    assert defaults["marginal_tax_rate"] == {"value": 0.22, "source": "profile"}
    assert defaults["filing_status"] == {"value": "married_filing_jointly", "source": "profile"}
    mismatch = payload["profile_mismatch"]
    assert mismatch["profile_value"] == 0.22
    assert mismatch["engine_default"] == main.settings.planner_marginal_tax_rate
