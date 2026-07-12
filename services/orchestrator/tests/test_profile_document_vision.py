"""Profile document vision: paystub/W-2 photos become reviewable profile patches."""

from __future__ import annotations

import asyncio
import json
from copy import copy
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.profile_document_vision import (
    apply_document_suggestions,
    build_profile_suggestions,
    extract_profile_document,
)
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


class _FakeVisionClient:
    provider = "openai"
    model = "gpt-5.5"
    enabled = True

    def __init__(self, content: str):
        self._content = content
        self.last_messages = None

    async def complete(self, messages, tools):
        self.last_messages = messages
        return {"message": {"content": self._content}, "usage": {}, "model": self.model, "provider": self.provider}


class _FakeRouter:
    def __init__(self, client):
        self._client = client
        self.requested_tasks: list[str] = []

    def client_for(self, task: str):
        self.requested_tasks.append(task)
        return self._client


def _install_temp_workspace_spine(monkeypatch, tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.auth_mode = "dev"
    test_settings.auth_dev_email = "owner@example.test"
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


def _workspace_services():
    return main.workspace_service_factory.for_context(
        main.control_plane_store.dev_request_context(auth_mode="dev")
    )


# ─────────────  Suggestion building  ─────────────


def test_paystub_biweekly_gross_converts_to_monthly_income() -> None:
    suggestions = build_profile_suggestions(
        "paystub",
        {
            "employer": "Acme Corp",
            "pay_frequency": "biweekly",
            "gross_pay_usd": 4000,
            "pre_tax_deductions_usd": 350,
        },
    )
    items = suggestions["income_items"]
    assert len(items) == 1
    item = items[0]
    assert item["label"] == "Salary — Acme Corp"
    # 4000 per biweekly period × 26 / 12 = 8666.67 monthly.
    assert item["monthly_amount_usd"] == 8666.67
    assert item["source_type"] == "salary"
    assert item["is_pre_tax"] is False
    # Pre-tax deductions become a hint, never invented tax rates.
    assert "pre-tax deductions" in suggestions["notes_hint"]
    assert "tax_profile" not in suggestions


def test_paystub_amounts_coerce_dollar_strings() -> None:
    suggestions = build_profile_suggestions(
        "paystub",
        {"employer": "Acme", "pay_frequency": "monthly", "gross_pay_usd": "$4,000.00"},
    )
    assert suggestions["income_items"][0]["monthly_amount_usd"] == 4000.0


def test_paystub_unknown_frequency_warns_instead_of_guessing() -> None:
    suggestions = build_profile_suggestions(
        "paystub",
        {"employer": "Acme", "pay_frequency": "unknown", "gross_pay_usd": 4000},
    )
    assert "income_items" not in suggestions
    assert any("pay frequency" in w.lower() for w in suggestions["warnings"])


def test_w2_estimates_effective_rate_and_monthly_income() -> None:
    suggestions = build_profile_suggestions(
        "w2",
        {
            "employer": "Acme Corp",
            "box1_wages_usd": 120000,
            "box2_federal_withholding_usd": 21600,
            "box17_state_tax_usd": 5400,
            "state": "CO",
            "tax_year": 2025,
        },
    )
    tax = suggestions["tax_profile"]
    assert tax["state"] == "CO"
    assert tax["effective_tax_rate"] == round(21600 / 120000, 4)  # 0.18
    # The rate is only an estimate — say so out loud.
    assert any("estimate" in w.lower() for w in suggestions["warnings"])
    item = suggestions["income_items"][0]
    assert item["label"] == "Salary — Acme Corp (from W-2 2025)"
    assert item["monthly_amount_usd"] == 10000.0


def test_mortgage_statement_becomes_debt_item_with_fractional_rate() -> None:
    suggestions = build_profile_suggestions(
        "mortgage_statement",
        {
            "lender": "First National",
            "outstanding_balance_usd": "412,300.55",
            "interest_rate_pct": 6.5,
            "monthly_payment_usd": 2612.4,
            "escrow_monthly_usd": 480,
        },
    )
    debt = suggestions["debt_items"][0]
    assert debt["label"] == "Mortgage — First National"
    assert debt["balance_usd"] == 412300.55
    assert debt["interest_rate"] == 0.065
    assert debt["minimum_payment_usd"] == 2612.4
    escrow = suggestions["expense_items"][0]
    assert escrow["monthly_amount_usd"] == 480.0
    assert escrow["category"] == "housing"
    assert escrow["is_fixed"] is True


def test_insurance_annual_premium_normalizes_to_monthly() -> None:
    suggestions = build_profile_suggestions(
        "insurance_declaration",
        {"insurer": "Allied", "policy_type": "auto", "premium_usd": 1200, "premium_period": "annual"},
    )
    item = suggestions["expense_items"][0]
    assert item["label"] == "Auto insurance — Allied"
    assert item["monthly_amount_usd"] == 100.0
    assert item["category"] == "insurance"
    assert item["is_fixed"] is True


def test_unknown_document_type_yields_empty_suggestions_and_warning() -> None:
    suggestions = build_profile_suggestions("other", {"anything": 1})
    assert set(suggestions.keys()) == {"warnings"}
    assert suggestions["warnings"]


# ─────────────  Extraction  ─────────────


def test_extraction_sends_document_prompt_and_returns_suggestions() -> None:
    payload = {
        "document_type": "paystub",
        "confidence": "high",
        "fields": {"employer": "Acme", "pay_frequency": "biweekly", "gross_pay_usd": 4000},
        "warnings": ["YTD column is blurry."],
    }
    client = _FakeVisionClient(json.dumps(payload))
    result = asyncio.run(extract_profile_document(b"fake-png", "image/png", llm_client=client))

    assert result.status == "ready"
    assert result.document_type == "paystub"
    assert result.confidence == "high"
    assert result.suggestions["income_items"][0]["monthly_amount_usd"] == 8666.67
    assert "YTD column is blurry." in result.warnings
    assert result.raw_fields["employer"] == "Acme"

    content = client.last_messages[0]["content"]
    assert content[0]["type"] == "text"
    assert "paystub" in content[0]["text"] and "w2" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_extraction_guardrails_media_size_and_unconfigured() -> None:
    ok_client = _FakeVisionClient("{}")

    pdf = asyncio.run(extract_profile_document(b"x", "application/pdf", llm_client=ok_client))
    assert pdf.status == "error" and "Unsupported image type" in pdf.detail

    huge = asyncio.run(
        extract_profile_document(b"x" * (8 * 1024 * 1024 + 1), "image/png", llm_client=ok_client)
    )
    assert huge.status == "error" and "8 MB" in huge.detail

    class _Disabled:
        enabled = False

    off = asyncio.run(extract_profile_document(b"x", "image/png", llm_client=_Disabled()))
    assert off.status == "unconfigured" and "Settings" in off.detail


def test_extraction_non_json_is_an_error_not_a_guess() -> None:
    client = _FakeVisionClient("Sorry, I cannot read this.")
    result = asyncio.run(extract_profile_document(b"x", "image/png", llm_client=client))
    assert result.status == "error"
    assert "not valid JSON" in result.detail


# ─────────────  Apply merge  ─────────────


class _MemoryProfileStore:
    def __init__(self, payload=None):
        self.payload = payload or {}
        self.saved_patches: list[dict] = []
        self.saved_kwargs: list[dict] = []

    def get(self):
        return json.loads(json.dumps(self.payload))

    def save(self, patch, **kwargs):
        self.payload.update(patch)
        self.saved_patches.append(patch)
        self.saved_kwargs.append(kwargs)
        return self.payload


def test_apply_appends_with_dedupe_and_only_known_sections() -> None:
    store = _MemoryProfileStore(
        {
            "income_items": [{"label": "Salary — Acme Corp", "monthly_amount_usd": 8666.67}],
            "tax_profile": {"filing_status": "single", "marginal_tax_rate": 0.24},
        }
    )
    result = apply_document_suggestions(
        {
            "income_items": [
                {"label": "Salary — Acme Corp", "monthly_amount_usd": 8666.67},  # duplicate
                {"label": "Salary — Beta LLC", "monthly_amount_usd": "$2,000.00"},
            ],
            "debt_items": [{"label": "Mortgage — First National", "balance_usd": 412300.55, "interest_rate": 6.5}],
            "tax_profile": {"state": "CO", "effective_tax_rate": 0.18, "not_a_field": "ignored"},
            "notes_hint": "never applied",
            "warnings": ["never applied"],
            "holdings": [{"symbol": "VTI"}],  # unknown section, dropped
        },
        store,
    )

    assert sorted(result["applied_sections"]) == ["debt_items", "income_items", "tax_profile"]
    assert result["counts"] == {"income_items": 1, "debt_items": 1, "tax_profile": 2}
    assert result["skipped_duplicates"] == 1

    assert len(store.saved_patches) == 1
    patch = store.saved_patches[0]
    assert {item["label"] for item in patch["income_items"]} == {"Salary — Acme Corp", "Salary — Beta LLC"}
    assert patch["debt_items"][0]["interest_rate"] == 0.065  # percent coerced to fraction
    # tax_profile merges over the existing dict rather than replacing it.
    assert patch["tax_profile"]["filing_status"] == "single"
    assert patch["tax_profile"]["state"] == "CO"
    assert patch["tax_profile"]["effective_tax_rate"] == 0.18
    assert "not_a_field" not in patch["tax_profile"]
    assert "notes_hint" not in patch and "holdings" not in patch

    assert store.saved_kwargs[0] == {
        "metadata_source": "profile_document_vision",
        "metadata_status": "user_confirmed",
    }


def test_apply_with_nothing_new_saves_nothing() -> None:
    store = _MemoryProfileStore({"income_items": [{"label": "Salary", "monthly_amount_usd": 5000}]})
    result = apply_document_suggestions(
        {"income_items": [{"label": "Salary", "monthly_amount_usd": 5000}]},
        store,
    )
    assert result["applied_sections"] == []
    assert result["skipped_duplicates"] == 1
    assert store.saved_patches == []


# ─────────────  Endpoints  ─────────────

_PAYSTUB_MODEL_PAYLOAD = json.dumps(
    {
        "document_type": "paystub",
        "confidence": "high",
        "fields": {"employer": "Acme Corp", "pay_frequency": "biweekly", "gross_pay_usd": 4000},
        "warnings": [],
    }
)


def test_document_vision_endpoint_extracts_and_apply_endpoint_saves(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    fake_router = _FakeRouter(_FakeVisionClient(_PAYSTUB_MODEL_PAYLOAD))

    with TestClient(main.app) as client:
        # App startup reloads the router from workspace settings; install the
        # fake after startup so the route resolves it at call time via m.*.
        monkeypatch.setattr(main, "llm_router", fake_router)
        response = client.post(
            "/api/profile/document-vision",
            files={"file": ("paystub.png", b"fake-png-bytes", "image/png")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["document_type"] == "paystub"
        assert payload["confidence"] == "high"
        assert payload["file_name"] == "paystub.png"
        assert payload["suggestions"]["income_items"][0]["monthly_amount_usd"] == 8666.67
        assert fake_router.requested_tasks == ["extract"]

        apply_response = client.post("/api/profile/document-vision/apply", json=payload["suggestions"])
        assert apply_response.status_code == 200
        applied = apply_response.json()
        assert applied["applied_sections"] == ["income_items"]
        assert applied["counts"] == {"income_items": 1}

        # Applying the same suggestions again dedupes instead of double-adding.
        again = client.post("/api/profile/document-vision/apply", json=payload["suggestions"]).json()
        assert again["applied_sections"] == []
        assert again["skipped_duplicates"] == 1

        # tax_profile fields (a W-2 apply) are metadata-material; the store
        # must record document vision as their source.
        tax_apply = client.post(
            "/api/profile/document-vision/apply",
            json={"tax_profile": {"state": "CO", "effective_tax_rate": 0.18}},
        )
        assert tax_apply.status_code == 200
        assert tax_apply.json()["applied_sections"] == ["tax_profile"]

    services = _workspace_services()
    profile = services.financial_profile_store.get()
    items = [item for item in profile["income_items"] if item["label"] == "Salary — Acme Corp"]
    assert len(items) == 1
    assert items[0]["monthly_amount_usd"] == 8666.67
    assert profile["tax_profile"]["state"] == "CO"
    metadata = profile.get("profile_metadata") or {}
    assert metadata.get("tax_profile.state", {}).get("source") == "profile_document_vision"


def test_document_vision_endpoint_rejects_bad_media_and_oversized(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "llm_router", _FakeRouter(_FakeVisionClient(_PAYSTUB_MODEL_PAYLOAD)))

    with TestClient(main.app) as client:
        pdf = client.post(
            "/api/profile/document-vision",
            files={"file": ("doc.pdf", b"%PDF-1.7", "application/pdf")},
        )
        assert pdf.status_code == 400
        assert "Unsupported image type" in pdf.json()["detail"]

        huge = client.post(
            "/api/profile/document-vision",
            files={"file": ("big.png", b"x" * (8 * 1024 * 1024 + 1), "image/png")},
        )
        assert huge.status_code == 400
        assert "8 MB" in huge.json()["detail"]


def test_document_vision_endpoint_reports_unconfigured_llm(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    class _Disabled:
        enabled = False

    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "llm_router", _FakeRouter(_Disabled()))
        response = client.post(
            "/api/profile/document-vision",
            files={"file": ("paystub.png", b"fake", "image/png")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "unconfigured"
        assert "Settings" in payload["detail"]
