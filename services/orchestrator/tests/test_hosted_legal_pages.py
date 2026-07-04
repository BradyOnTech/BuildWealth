from __future__ import annotations

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main


def test_hosted_legal_pages_are_public() -> None:
    with TestClient(main.app) as client:
        privacy = client.get("/privacy")
        terms = client.get("/terms")
        ai_disclosure = client.get("/ai-disclosure")

    assert privacy.status_code == 200
    assert "BuildWealth Privacy Notice" in privacy.text
    assert "Closing BuildWealth access does not automatically delete" in privacy.text

    assert terms.status_code == 200
    assert "BuildWealth Terms" in terms.text
    assert "BuildWealth is not a registered investment adviser" in terms.text

    assert ai_disclosure.status_code == 200
    assert "BuildWealth AI Disclosure" in ai_disclosure.text
    assert "Copilot output is a draft or suggestion" in ai_disclosure.text
