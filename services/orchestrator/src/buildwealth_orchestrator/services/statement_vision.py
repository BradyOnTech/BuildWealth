"""Statement vision: a screenshot becomes a reviewable budget, not homework.

The user photographs or screenshots a bank/credit-card statement; a
vision-capable model (the router's 'extract' task) reads it into a strict
JSON contract; the transactions flow through the SAME aggregation as CSV
imports (statement_importer.build_statement_result) and land in the same
suggest-then-apply review flow. Nothing is ever saved without the human
confirming — extraction can misread, and this is financial data.

Image content uses the OpenAI-compatible parts format, which the openai/
gemini/custom clients pass through verbatim. The Anthropic client's message
transform doesn't carry image parts yet — route 'extract' to an
OpenAI-compatible provider until it does.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from buildwealth_orchestrator.services.statement_importer import (
    ParsedTransaction,
    StatementParseResult,
    _infer_category,
    build_statement_result,
)

ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024

EXTRACTION_PROMPT = """You are reading a photograph or screenshot of a bank or credit-card statement.

Extract what is actually visible. Never invent values; use null for anything you cannot read.

Respond with ONLY a JSON object, no prose, in exactly this shape:
{
  "account_name": string|null,        // e.g. "Chase Total Checking"
  "account_type": "checking"|"savings"|"credit_card"|"unknown",
  "institution": string|null,
  "ending_balance_usd": number|null,  // statement ending balance; for credit cards, the balance owed
  "statement_period": {"start": "YYYY-MM-DD"|null, "end": "YYYY-MM-DD"|null},
  "transactions": [
    {
      "date": "YYYY-MM-DD"|null,
      "description": string,
      "amount_usd": number,           // always positive
      "direction": "charge"|"credit"  // charge = money out / purchase; credit = money in / payment / refund
    }
  ],
  "warnings": [string]                // anything cut off, blurry, or ambiguous
}"""


@dataclass
class StatementVisionResult:
    status: str  # ready | unreadable | error
    detail: str = ""
    account_name: str | None = None
    account_type: str = "unknown"
    institution: str | None = None
    ending_balance_usd: float | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    warnings: list[str] = field(default_factory=list)
    parse_result: StatementParseResult | None = None


def build_extraction_messages(image_bytes: bytes, media_type: str) -> list[dict[str, Any]]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                },
            ],
        }
    ]


def _json_block(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model response, fences and all."""
    cleaned = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    candidate = fenced.group(1) if fenced else cleaned
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_extraction_payload(payload: dict[str, Any]) -> StatementVisionResult:
    """Validate and convert the model's JSON into the shared pipeline shapes."""
    raw_transactions = payload.get("transactions")
    transactions: list[ParsedTransaction] = []
    dropped = 0
    for row in raw_transactions if isinstance(raw_transactions, list) else []:
        if not isinstance(row, dict):
            dropped += 1
            continue
        try:
            amount = abs(float(row.get("amount_usd")))
        except (TypeError, ValueError):
            dropped += 1
            continue
        if amount <= 0:
            dropped += 1
            continue
        description = str(row.get("description") or "").strip()
        direction = str(row.get("direction") or "charge").strip().lower()
        # The shared aggregation's convention: charges negative, credits positive.
        signed = -amount if direction != "credit" else amount
        transactions.append(
            ParsedTransaction(
                date=_parse_date(row.get("date")),
                description=description,
                amount=signed,
                category=_infer_category(description) if description else "general",
            )
        )

    warnings = [str(w) for w in payload.get("warnings") or [] if str(w or "").strip()]
    if dropped:
        warnings.append(f"{dropped} extracted row(s) were unreadable and skipped.")

    if not transactions:
        return StatementVisionResult(
            status="unreadable",
            detail="No readable transactions were found in the image. Try a sharper, fuller screenshot.",
            warnings=warnings,
        )

    balance = payload.get("ending_balance_usd")
    try:
        balance_value = round(float(balance), 2) if balance is not None else None
    except (TypeError, ValueError):
        balance_value = None

    period = payload.get("statement_period") if isinstance(payload.get("statement_period"), dict) else {}
    account_type = str(payload.get("account_type") or "unknown").strip().lower()
    if account_type not in {"checking", "savings", "credit_card"}:
        account_type = "unknown"

    return StatementVisionResult(
        status="ready",
        account_name=(str(payload.get("account_name")).strip() or None) if payload.get("account_name") else None,
        account_type=account_type,
        institution=(str(payload.get("institution")).strip() or None) if payload.get("institution") else None,
        ending_balance_usd=balance_value,
        statement_period_start=str(period.get("start")) if period.get("start") else None,
        statement_period_end=str(period.get("end")) if period.get("end") else None,
        warnings=warnings,
        parse_result=build_statement_result(transactions),
    )


async def extract_statement_from_image(
    image_bytes: bytes,
    media_type: str,
    *,
    llm_client: Any,
) -> StatementVisionResult:
    if media_type not in ALLOWED_MEDIA_TYPES:
        return StatementVisionResult(
            status="error",
            detail=f"Unsupported image type {media_type}. Use PNG, JPEG, WebP, or GIF; for a PDF statement, screenshot the pages.",
        )
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return StatementVisionResult(status="error", detail="Image is larger than 8 MB — crop or downscale it.")
    if not getattr(llm_client, "enabled", False):
        return StatementVisionResult(
            status="error",
            detail="No AI provider is configured. Add one in Settings → Connections & AI to read statement images.",
        )

    try:
        completion = await llm_client.complete(build_extraction_messages(image_bytes, media_type), [])
    except Exception as exc:
        return StatementVisionResult(status="error", detail=f"The AI provider could not read the image: {exc}")

    message = completion.get("message") if isinstance(completion, dict) else {}
    payload = _json_block(str(message.get("content") or ""))
    if payload is None:
        return StatementVisionResult(
            status="error",
            detail="The model's response was not valid JSON. Try again, or route the 'extract' task to a vision-capable model in Settings.",
        )
    return parse_extraction_payload(payload)
