"""Profile document vision: a paystub/W-2 photo becomes a reviewable profile patch.

The user photographs a paystub, W-2, mortgage statement, or insurance
declaration page; the router's 'extract' vision model reads it into a strict
JSON contract; build_profile_suggestions turns those fields into a
financial-profile PATCH the user reviews section by section. Nothing is ever
saved without the human confirming — extraction can misread, and this is
financial data.

Amounts in the profile are MONTHLY: paystub gross is per pay period and is
converted using pay_frequency; annual figures (W-2 wages, annual premiums)
are divided down to monthly here, never at apply time.

Image plumbing (data-URI message parts, media-type and size guardrails, JSON
block parsing) is shared with statement_vision — only the prompt differs.
The reviewed patch is written by profile_document_apply (re-exported here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from buildwealth_orchestrator.services.profile_candidate_apply import _numeric_or_none
from buildwealth_orchestrator.services.profile_document_apply import (
    apply_document_suggestions,
)
from buildwealth_orchestrator.services.statement_vision import (
    ALLOWED_MEDIA_TYPES,
    MAX_IMAGE_BYTES,
    _json_block,
    build_extraction_messages,
)

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "MAX_IMAGE_BYTES",
    "ProfileDocumentResult",
    "apply_document_suggestions",
    "build_document_messages",
    "build_profile_suggestions",
    "extract_profile_document",
]

DOCUMENT_TYPES = {"paystub", "w2", "mortgage_statement", "insurance_declaration", "other"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}

# Per-pay-period gross → monthly. Profile amounts are always monthly.
PAY_FREQUENCY_TO_MONTHLY = {
    "weekly": 52.0 / 12.0,
    "biweekly": 26.0 / 12.0,
    "semimonthly": 2.0,
    "monthly": 1.0,
}

PREMIUM_PERIOD_TO_MONTHLY = {"monthly": 1.0, "semiannual": 1.0 / 6.0, "annual": 1.0 / 12.0}

EXTRACTION_PROMPT = """You are reading a photograph or screenshot of a personal financial document: a paystub, a W-2, a mortgage statement, or an insurance declaration page.

Extract only what is actually visible. Never invent values; use null for anything you cannot read.

Respond with ONLY a JSON object, no prose, in exactly this shape:
{
  "document_type": "paystub"|"w2"|"mortgage_statement"|"insurance_declaration"|"other",
  "confidence": "high"|"medium"|"low",
  "fields": { ...see below, depends on document_type... },
  "warnings": [string]              // anything cut off, blurry, or ambiguous
}

"fields" by document_type:
- paystub: {
    "employer": string|null,
    "pay_frequency": "weekly"|"biweekly"|"semimonthly"|"monthly"|"unknown",
    "gross_pay_usd": number|null,           // gross for THIS pay period
    "net_pay_usd": number|null,
    "pre_tax_deductions_usd": number|null,  // 401k + HSA + insurance, per period
    "federal_withholding_usd": number|null,
    "ytd_gross_usd": number|null,
    "pay_period_end": "YYYY-MM-DD"|null
  }
- w2: {
    "employer": string|null,
    "box1_wages_usd": number|null,
    "box2_federal_withholding_usd": number|null,
    "box17_state_tax_usd": number|null,
    "state": string|null,                   // two-letter code from box 15
    "tax_year": number|null
  }
- mortgage_statement: {
    "lender": string|null,
    "outstanding_balance_usd": number|null,
    "interest_rate_pct": number|null,       // e.g. 6.5 for 6.5%
    "monthly_payment_usd": number|null,
    "escrow_monthly_usd": number|null
  }
- insurance_declaration: {
    "insurer": string|null,
    "policy_type": string|null,             // e.g. "auto", "home", "term life"
    "premium_usd": number|null,
    "premium_period": "monthly"|"semiannual"|"annual"|null
  }
- other: {}"""


@dataclass
class ProfileDocumentResult:
    status: str  # ready | error | unconfigured
    detail: str = ""
    document_type: str = "other"
    confidence: str = "low"
    suggestions: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_fields: dict[str, Any] = field(default_factory=dict)


def build_document_messages(image_bytes: bytes, media_type: str) -> list[dict[str, Any]]:
    """statement_vision's data-URI message shape with this module's prompt."""
    messages = build_extraction_messages(image_bytes, media_type)
    messages[0]["content"][0]["text"] = EXTRACTION_PROMPT
    return messages


async def extract_profile_document(
    image_bytes: bytes,
    media_type: str,
    *,
    llm_client: Any,
) -> ProfileDocumentResult:
    if media_type not in ALLOWED_MEDIA_TYPES:
        return ProfileDocumentResult(
            status="error",
            detail=(
                f"Unsupported image type {media_type or 'unknown'}. Use PNG, JPEG, WebP, "
                "or GIF; for a PDF, screenshot the page."
            ),
        )
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return ProfileDocumentResult(status="error", detail="Image is larger than 8 MB — crop or downscale it.")
    if not getattr(llm_client, "enabled", False):
        return ProfileDocumentResult(
            status="unconfigured",
            detail="No AI provider is configured. Add one in Settings → Connections & AI to read document photos.",
        )

    try:
        completion = await llm_client.complete(build_document_messages(image_bytes, media_type), [])
    except Exception as exc:
        return ProfileDocumentResult(status="error", detail=f"The AI provider could not read the image: {exc}")

    message = completion.get("message") if isinstance(completion, dict) else {}
    payload = _json_block(str(message.get("content") or ""))
    if payload is None:
        return ProfileDocumentResult(
            status="error",
            detail=(
                "The model's response was not valid JSON. Try again, or route the "
                "'extract' task to a vision-capable model in Settings."
            ),
        )

    document_type = str(payload.get("document_type") or "other").strip().lower()
    if document_type not in DOCUMENT_TYPES:
        document_type = "other"
    confidence = str(payload.get("confidence") or "low").strip().lower()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    warnings = [str(w) for w in payload.get("warnings") or [] if str(w or "").strip()]

    suggestions = build_profile_suggestions(document_type, fields)
    warnings.extend(suggestions.pop("warnings", []))

    return ProfileDocumentResult(
        status="ready",
        document_type=document_type,
        confidence=confidence,
        suggestions=suggestions,
        warnings=warnings,
        raw_fields=dict(fields),
    )


def build_profile_suggestions(document_type: str, fields: Mapping[str, Any] | None) -> dict[str, Any]:
    """Turn extracted fields into a financial-profile PATCH for review.

    Only sections the document actually supports appear. The returned dict may
    also carry "warnings" (merged into the result by the caller) and
    "notes_hint" (shown to the user, never applied).
    """
    fields = fields if isinstance(fields, Mapping) else {}
    builder = {
        "paystub": _paystub_suggestions,
        "w2": _w2_suggestions,
        "mortgage_statement": _mortgage_suggestions,
        "insurance_declaration": _insurance_suggestions,
    }.get(str(document_type or "").strip().lower())
    if builder is None:
        return {"warnings": ["This document type is not supported for profile suggestions yet — nothing to apply."]}
    return builder(fields)


def _paystub_suggestions(fields: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    warnings: list[str] = []
    employer = _text(fields.get("employer"))
    gross = _numeric_or_none(fields.get("gross_pay_usd"))
    frequency = str(fields.get("pay_frequency") or "unknown").strip().lower()
    factor = PAY_FREQUENCY_TO_MONTHLY.get(frequency)

    if gross is None:
        warnings.append("Gross pay was unreadable on the paystub — no income suggestion was made.")
    elif factor is None:
        warnings.append(
            "The pay frequency was unreadable, so the per-period gross pay could not be "
            "converted to a monthly amount. Add the income manually."
        )
    else:
        out["income_items"] = [
            {
                "label": f"Salary — {employer}" if employer else "Salary (from paystub)",
                "monthly_amount_usd": round(gross * factor, 2),
                "source_type": "salary",
                "is_pre_tax": False,
            }
        ]

    pre_tax = _numeric_or_none(fields.get("pre_tax_deductions_usd"))
    if pre_tax:
        out["notes_hint"] = (
            f"The paystub shows ${pre_tax:,.2f} per pay period in pre-tax deductions "
            "(401k/HSA/insurance). Record those as contributions or expenses separately — "
            "a single paystub is not enough to infer tax rates."
        )
    if warnings:
        out["warnings"] = warnings
    return out


def _w2_suggestions(fields: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    warnings: list[str] = []
    employer = _text(fields.get("employer"))
    box1 = _numeric_or_none(fields.get("box1_wages_usd"))
    box2 = _numeric_or_none(fields.get("box2_federal_withholding_usd"))
    state = _text(fields.get("state"))
    tax_year = _numeric_or_none(fields.get("tax_year"))

    tax_profile: dict[str, Any] = {}
    if state:
        tax_profile["state"] = state
    if box1 and box1 > 0 and box2 is not None:
        estimate = round(box2 / box1, 4)
        tax_profile["effective_tax_rate"] = estimate
        warnings.append(
            f"Effective tax rate {estimate:.2%} is an ESTIMATE (W-2 box 2 federal withholding ÷ "
            "box 1 wages) — withholding is not tax owed; confirm against your return."
        )
    if tax_profile:
        out["tax_profile"] = tax_profile

    if box1 and box1 > 0:
        year_label = f" (from W-2 {int(tax_year)})" if tax_year else " (from W-2)"
        out["income_items"] = [
            {
                "label": (f"Salary — {employer}" if employer else "Salary") + year_label,
                "monthly_amount_usd": round(box1 / 12.0, 2),
                "source_type": "salary",
                "is_pre_tax": False,
            }
        ]
    else:
        warnings.append("Box 1 wages were unreadable on the W-2 — no income suggestion was made.")

    if warnings:
        out["warnings"] = warnings
    return out


def _mortgage_suggestions(fields: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    warnings: list[str] = []
    lender = _text(fields.get("lender"))
    balance = _numeric_or_none(fields.get("outstanding_balance_usd"))
    rate_pct = _numeric_or_none(fields.get("interest_rate_pct"))
    payment = _numeric_or_none(fields.get("monthly_payment_usd"))
    escrow = _numeric_or_none(fields.get("escrow_monthly_usd"))

    if balance is None:
        warnings.append("The outstanding balance was unreadable — no debt suggestion was made.")
    else:
        debt: dict[str, Any] = {
            "label": f"Mortgage — {lender}" if lender else "Mortgage",
            "balance_usd": round(balance, 2),
        }
        if rate_pct is not None:
            debt["interest_rate"] = round(rate_pct / 100.0, 6)
        if payment is not None:
            debt["minimum_payment_usd"] = round(payment, 2)
        out["debt_items"] = [debt]

    if escrow:
        out["expense_items"] = [
            {
                "label": f"Mortgage escrow — {lender}" if lender else "Mortgage escrow",
                "monthly_amount_usd": round(escrow, 2),
                "category": "housing",
                "is_fixed": True,
            }
        ]
    if warnings:
        out["warnings"] = warnings
    return out


def _insurance_suggestions(fields: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    warnings: list[str] = []
    insurer = _text(fields.get("insurer"))
    policy_type = _text(fields.get("policy_type"))
    premium = _numeric_or_none(fields.get("premium_usd"))
    period = str(fields.get("premium_period") or "").strip().lower()
    factor = PREMIUM_PERIOD_TO_MONTHLY.get(period)

    if premium is None:
        warnings.append("The premium was unreadable — no expense suggestion was made.")
    elif factor is None:
        warnings.append(
            "The premium period (monthly/semiannual/annual) was unreadable, so the premium "
            "could not be converted to a monthly amount."
        )
    else:
        base = f"{policy_type.capitalize()} insurance" if policy_type else "Insurance"
        out["expense_items"] = [
            {
                "label": f"{base} — {insurer}" if insurer else base,
                "monthly_amount_usd": round(premium * factor, 2),
                "category": "insurance",
                "is_fixed": True,
            }
        ]
    if warnings:
        out["warnings"] = warnings
    return out


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
