"""Statement vision: screenshots become reviewable budgets, never silent writes."""

from __future__ import annotations

import asyncio
import json

from buildwealth_orchestrator.services.statement_vision import (
    build_extraction_messages,
    extract_statement_from_image,
    parse_extraction_payload,
)

_PAYLOAD = {
    "account_name": "Chase Total Checking",
    "account_type": "checking",
    "institution": "Chase",
    "ending_balance_usd": 12432.55,
    "statement_period": {"start": "2026-05-01", "end": "2026-06-30"},
    "transactions": [
        {"date": "2026-05-03", "description": "TRADER JOE'S #512", "amount_usd": 84.12, "direction": "charge"},
        {"date": "2026-06-03", "description": "TRADER JOE'S #512", "amount_usd": 91.40, "direction": "charge"},
        {"date": "2026-05-15", "description": "ACME PAYROLL DIRECT DEP", "amount_usd": 3200.00, "direction": "credit"},
        {"date": "2026-06-15", "description": "ACME PAYROLL DIRECT DEP", "amount_usd": 3200.00, "direction": "credit"},
        {"date": "2026-05-20", "description": "NETFLIX.COM", "amount_usd": 15.49, "direction": "charge"},
        {"date": "2026-06-20", "description": "NETFLIX.COM", "amount_usd": 15.49, "direction": "charge"},
    ],
    "warnings": ["Bottom two rows are cut off."],
}


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


def test_extraction_flows_into_the_shared_suggestion_pipeline() -> None:
    client = _FakeVisionClient(json.dumps(_PAYLOAD))
    result = asyncio.run(extract_statement_from_image(b"fake-png-bytes", "image/png", llm_client=client))

    assert result.status == "ready"
    assert result.account_type == "checking"
    assert result.ending_balance_usd == 12432.55
    assert "Bottom two rows are cut off." in result.warnings

    parsed = result.parse_result
    labels = {s.label.lower() for s in parsed.expense_suggestions}
    assert any("trader joe" in label for label in labels)
    assert any("netflix" in label for label in labels)
    # Recurring charges over two months read as fixed monthly expenses.
    netflix = next(s for s in parsed.expense_suggestions if "netflix" in s.label.lower())
    assert netflix.category == "subscriptions"
    assert netflix.is_fixed is True
    # Payroll credits become income suggestions, not expenses.
    assert parsed.income_suggestions
    assert parsed.income_suggestions[0].source_type == "salary"

    # The prompt and the image both actually went to the model.
    content = client.last_messages[0]["content"]
    assert content[0]["type"] == "text" and "ONLY a JSON object" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_fenced_json_and_prose_are_tolerated() -> None:
    wrapped = "Here is the extraction:\n```json\n" + json.dumps(_PAYLOAD) + "\n```\nLet me know!"
    client = _FakeVisionClient(wrapped)
    result = asyncio.run(extract_statement_from_image(b"x", "image/jpeg", llm_client=client))
    assert result.status == "ready"


def test_non_json_response_is_an_error_not_a_guess() -> None:
    client = _FakeVisionClient("I cannot read this image, sorry!")
    result = asyncio.run(extract_statement_from_image(b"x", "image/png", llm_client=client))
    assert result.status == "error"
    assert "not valid JSON" in result.detail


def test_unreadable_rows_are_dropped_and_counted_never_invented() -> None:
    payload = dict(_PAYLOAD)
    payload["transactions"] = [
        {"date": "2026-05-03", "description": "OK ROW", "amount_usd": 50.0, "direction": "charge"},
        {"date": "2026-05-04", "description": "BAD AMOUNT", "amount_usd": "??", "direction": "charge"},
        "not-a-dict",
    ]
    result = parse_extraction_payload(payload)
    assert result.status == "ready"
    assert len(result.parse_result.transactions) == 1
    assert any("2 extracted row(s) were unreadable" in w for w in result.warnings)


def test_empty_extraction_reports_unreadable() -> None:
    result = parse_extraction_payload({"transactions": [], "warnings": []})
    assert result.status == "unreadable"
    assert "sharper" in result.detail


def test_guardrails_bad_media_type_size_and_disabled_client() -> None:
    ok_client = _FakeVisionClient(json.dumps(_PAYLOAD))

    pdf = asyncio.run(extract_statement_from_image(b"x", "application/pdf", llm_client=ok_client))
    assert pdf.status == "error" and "screenshot the pages" in pdf.detail

    huge = asyncio.run(extract_statement_from_image(b"x" * (8 * 1024 * 1024 + 1), "image/png", llm_client=ok_client))
    assert huge.status == "error" and "8 MB" in huge.detail

    class _Disabled:
        enabled = False

    off = asyncio.run(extract_statement_from_image(b"x", "image/png", llm_client=_Disabled()))
    assert off.status == "error" and "Settings" in off.detail
