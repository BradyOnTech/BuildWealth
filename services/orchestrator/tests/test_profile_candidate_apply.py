from __future__ import annotations

from copy import copy
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.profile_candidate_apply import apply_candidate_to_profile
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


def _install_temp_workspace_spine(monkeypatch, tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.auth_mode = "dev"
    test_settings.auth_dev_email = "owner@example.test"
    test_settings.auth_oidc_client_id = ""
    test_settings.auth_oidc_client_secret = ""
    test_settings.auth_oidc_issuer_url = ""
    test_settings.auth_oidc_logout_url = ""
    test_settings.auth_post_logout_redirect_uri = ""
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    control_plane.bootstrap_default_household(
        owner_email=test_settings.auth_dev_email,
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    factory = WorkspaceServiceFactory(settings=test_settings, control_plane=control_plane)

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "control_plane_store", control_plane)
    monkeypatch.setattr(main, "workspace_service_factory", factory)
    main.auth_rate_limiter.reset_all()


def _store(tmp_path: Path) -> FinancialProfileStore:
    return FinancialProfileStore(tmp_path / "profile" / "financial_profile.json")


def _income_candidate(items: list[dict]) -> dict:
    return {
        "id": "cand-income",
        "target_domain": "profile",
        "target_area": "income_items",
        "target_field": "income_items",
        "target_value": {"income_items": items},
        "metadata": {"profile_patch_kind": "income_items"},
    }


def test_income_items_append_with_dedupe(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save({
        "income_items": [
            {"label": "My income", "monthly_amount_usd": 7500.0, "source_type": "salary", "is_pre_tax": False},
        ]
    })

    result = apply_candidate_to_profile(
        _income_candidate([
            {"label": "My income", "monthly_amount_usd": 7500.0},  # duplicate
            {"label": "Spouse income", "monthly_amount_usd": 4000.0, "source_type": "salary"},
        ]),
        store,
    )

    assert result["applied"] is True
    assert result["sections"] == ["income_items"]
    assert result["added"] == 1
    assert result["skipped_duplicates"] == 1
    items = store.get()["income_items"]
    assert len(items) == 2
    labels = {item["label"] for item in items}
    assert labels == {"My income", "Spouse income"}
    spouse = next(item for item in items if item["label"] == "Spouse income")
    assert spouse["monthly_amount_usd"] == 4000.0
    assert spouse["source_type"] == "salary"
    assert spouse["is_pre_tax"] is False
    assert spouse["id"]  # store assigns an id


def test_income_items_all_duplicates_writes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save({"income_items": [{"label": "My income", "monthly_amount_usd": 7500.0}]})
    before = store.get()["income_items"]

    result = apply_candidate_to_profile(
        _income_candidate([{"label": "My income", "monthly_amount_usd": 7500.0}]),
        store,
    )

    assert result["applied"] is True
    assert result["sections"] == []
    assert result["added"] == 0
    assert store.get()["income_items"] == before


def test_expense_items_patch_kind_supported(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = apply_candidate_to_profile(
        {
            "target_domain": "profile",
            "target_field": "expense_items",
            "target_value": {"expense_items": [
                {"label": "Rent", "monthly_amount_usd": 2100.0, "category": "housing", "is_fixed": True},
            ]},
            "metadata": {"profile_patch_kind": "expense_items"},
        },
        store,
    )
    assert result["applied"] is True
    assert result["sections"] == ["expense_items"]
    items = store.get()["expense_items"]
    assert len(items) == 1
    assert items[0]["label"] == "Rent"
    assert items[0]["category"] == "housing"


def test_tax_scalar_percent_coercion(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = apply_candidate_to_profile(
        {
            "target_domain": "profile",
            "target_field": "tax_profile.marginal_tax_rate",
            "target_value": 32,
            "metadata": {},
        },
        store,
    )
    assert result["applied"] is True
    assert result["sections"] == ["tax_profile"]
    profile = store.get()
    assert profile["tax_profile"]["marginal_tax_rate"] == 0.32
    # save() marks the material field as user-confirmed from the apply bridge
    entry = profile["profile_metadata"]["tax_profile.marginal_tax_rate"]
    assert entry["source"] == "context_candidate_apply"
    assert entry["status"] == "user_confirmed"


def test_tax_scalar_fraction_kept_as_is(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = apply_candidate_to_profile(
        {
            "target_field": "tax_profile.effective_tax_rate",
            "target_value": {"value": "0.18"},
        },
        store,
    )
    assert result["applied"] is True
    assert store.get()["tax_profile"]["effective_tax_rate"] == 0.18


def test_investment_policy_scalar(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = apply_candidate_to_profile(
        {
            "target_field": "investment_policy.risk_tolerance",
            "target_value": "moderate",
        },
        store,
    )
    assert result["applied"] is True
    assert result["sections"] == ["investment_policy"]
    policy = store.get()["investment_policy"]
    assert policy["risk_tolerance"] == "moderate"

    # Exposure percentages are NOT rescaled — 10 means 10%.
    result = apply_candidate_to_profile(
        {
            "target_field": "investment_policy.max_single_symbol_exposure_pct",
            "target_value": "10",
        },
        store,
    )
    assert result["applied"] is True
    assert store.get()["investment_policy"]["max_single_symbol_exposure_pct"] == 10.0
    # And the earlier field is still there (section merged, not replaced).
    assert store.get()["investment_policy"]["risk_tolerance"] == "moderate"


def test_unsupported_target_does_not_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    before = store.get()

    result = apply_candidate_to_profile(
        {
            "target_domain": "plan",
            "target_field": "settings.annual_contribution_usd",
            "target_value": 12000,
        },
        store,
    )

    assert result["applied"] is False
    assert "reason" in result
    after = store.get()
    before.pop("updated_at", None)
    after.pop("updated_at", None)
    assert after == before


def test_apply_endpoint_flow(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        drafted = client.post(
            "/api/context/candidates",
            json={
                "source_domain": "conversation",
                "source_ref": "conversation/test#message.1",
                "extracted_claim": "My marginal tax rate is 32%.",
                "target_domain": "profile",
                "target_area": "tax_profile",
                "target_field": "tax_profile.marginal_tax_rate",
                "target_value": 0.32,
            },
        )
        assert drafted.status_code == 200
        candidate_id = drafted.json()["id"]

        applied = client.post(f"/api/context/candidates/{candidate_id}/apply")
        assert applied.status_code == 200
        payload = applied.json()
        assert payload["apply_result"]["applied"] is True
        assert payload["apply_result"]["sections"] == ["tax_profile"]
        assert payload["apply_result"]["detail"]
        assert payload["candidate"]["lifecycle_state"] == "applied"
        assert payload["candidate"]["prompt_influence"] == "authoritative"
        assert payload["candidate"]["metadata"]["review_action"] == "applied_to_profile"
        assert payload["candidate"]["metadata"]["resolution_state"] == "resolved_by_apply"
        assert payload["candidate"]["metadata"]["applied_sections"] == ["tax_profile"]

        profile = client.get("/api/financial-profile")
        assert profile.status_code == 200
        assert profile.json()["tax_profile"]["marginal_tax_rate"] == 0.32


def test_apply_endpoint_rejects_unsupported_target(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        drafted = client.post(
            "/api/context/candidates",
            json={
                "source_domain": "conversation",
                "source_ref": "conversation/test#message.2",
                "extracted_claim": "Retire at 55.",
                "target_domain": "plan",
                "target_area": "timeline",
                "target_field": "timeline.retirement.target_retirement_age",
                "target_value": 55,
            },
        )
        assert drafted.status_code == 200
        candidate_id = drafted.json()["id"]

        applied = client.post(f"/api/context/candidates/{candidate_id}/apply")
        assert applied.status_code == 400
        assert "detail" in applied.json()


def test_apply_endpoint_missing_candidate_404(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        response = client.post("/api/context/candidates/does-not-exist/apply")
        assert response.status_code == 404


def test_infer_profile_endpoint_creates_bracket_candidate(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        saved = client.put(
            "/api/financial-profile",
            json={
                "income_items": [
                    {
                        "id": "income-1",
                        "label": "My income",
                        "monthly_amount_usd": 7500.0,
                        "source_type": "salary",
                        "is_pre_tax": False,
                    },
                ],
            },
        )
        assert saved.status_code == 200

        response = client.post("/api/context/candidates/infer-profile")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["created"]) == 1

        # Re-sweeping upserts the same candidate (stable dedupe_key) rather
        # than duplicating it.
        again = client.post("/api/context/candidates/infer-profile")
        assert again.status_code == 200
        assert again.json()["created"] == payload["created"]

        listed = client.get("/api/context/candidates", params={"lifecycle_state": "pending_review"})
        items = [
            item for item in listed.json()["items"]
            if item["target_field"] == "tax_profile.marginal_tax_rate"
        ]
        assert len(items) == 1
        assert items[0]["dedupe_key"] == "profile_inference:tax_profile.marginal_tax_rate"
        assert items[0]["target_value"] == 0.22  # 90k single, 2026 brackets
        assert items[0]["metadata"]["inference_kind"] == "bracket_from_income"
        assert items[0]["metadata"]["requires_user_confirmation"] is True
