"""Infer-and-confirm sweep: draft profile context candidates from what the
workspace already knows (income items, statement import suggestions).

Every draft carries requires_user_confirmation metadata and a stable
dedupe_key ("profile_inference:<target>") so repeated sweeps upsert the same
candidate instead of duplicating it. Nothing is written to the profile here —
drafts land in the context-capture lane and only reach the profile through
the apply bridge after the user confirms.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from buildwealth_orchestrator.services.tax_engine import (
    TAX_CONFIG_BY_YEAR,
    TAX_YEAR_2026,
)

INFERENCE_SOURCE_DOMAIN = "profile"
INFERENCE_DETECTOR = "profile_inference_v1"

_FILING_STATUSES = {
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
}


def build_profile_inference_candidates(
    *,
    profile_payload: Mapping[str, Any],
    statement_reports: Iterable[Mapping[str, Any]] | None = None,
    portfolio_transactions: Iterable[Mapping[str, Any]] | None = None,
    tax_year: int = 2026,
) -> list[dict[str, Any]]:
    """Return candidate DRAFT dicts accepted by
    ContextIntelligenceService.draft_context_candidate(**draft)."""
    del portfolio_transactions  # Reserved input; no current rule keys off it.
    profile = profile_payload if isinstance(profile_payload, Mapping) else {}
    reports = [report for report in (statement_reports or []) if isinstance(report, Mapping)]

    drafts: list[dict[str, Any]] = []

    bracket_draft = _marginal_rate_from_income_draft(profile, tax_year=tax_year)
    if bracket_draft is not None:
        drafts.append(bracket_draft)

    # Filing status is deliberately NOT inferred — household composition is
    # not a reliable signal for it, so no draft is created.

    for section, suggestions_key in (
        ("income_items", "income_suggestions"),
        ("expense_items", "expense_suggestions"),
    ):
        suggestion_draft = _statement_suggestions_draft(
            profile,
            reports,
            section=section,
            suggestions_key=suggestions_key,
        )
        if suggestion_draft is not None:
            drafts.append(suggestion_draft)

    return drafts


def _marginal_rate_from_income_draft(
    profile: Mapping[str, Any],
    *,
    tax_year: int,
) -> dict[str, Any] | None:
    tax_profile = profile.get("tax_profile")
    tax_profile = tax_profile if isinstance(tax_profile, Mapping) else {}
    if _has_value(tax_profile.get("marginal_tax_rate")):
        return None

    income_items = profile.get("income_items")
    income_items = income_items if isinstance(income_items, list) else []
    annual_income = sum(
        _safe_float(item.get("monthly_amount_usd")) for item in income_items if isinstance(item, Mapping)
    ) * 12.0
    if annual_income <= 0:
        return None

    filing_status = str(tax_profile.get("filing_status") or "").strip().lower()
    if filing_status not in _FILING_STATUSES:
        filing_status = "single"

    config = TAX_CONFIG_BY_YEAR.get(int(tax_year), TAX_YEAR_2026)
    standard_deduction = config.standard_deduction.get(
        filing_status, config.standard_deduction["single"]
    )
    taxable_income = max(0.0, annual_income - standard_deduction)
    rate = _marginal_rate_for_taxable_income(
        taxable_income,
        config.federal_income_brackets.get(filing_status, config.federal_income_brackets["single"]),
    )
    if rate is None:
        return None

    filing_label = filing_status.replace("_", " ")
    claim = (
        f"Estimated marginal federal tax rate of {rate * 100:.0f}% from "
        f"${annual_income:,.0f}/yr income, {filing_label} filer, {tax_year} brackets "
        f"(≈${taxable_income:,.0f} taxable after the ${standard_deduction:,.0f} standard deduction)."
    )
    return {
        "source_domain": INFERENCE_SOURCE_DOMAIN,
        "source_ref": "profile_inference/tax_profile.marginal_tax_rate",
        "extracted_claim": claim,
        "target_domain": "profile",
        "target_area": "tax_profile",
        "target_field": "tax_profile.marginal_tax_rate",
        "target_value": rate,
        "confidence": "medium",
        "metadata": {
            "detector": INFERENCE_DETECTOR,
            "inference_kind": "bracket_from_income",
            "requires_user_confirmation": True,
        },
        "lifecycle_state": "pending_review",
        "dedupe_key": "profile_inference:tax_profile.marginal_tax_rate",
    }


def _statement_suggestions_draft(
    profile: Mapping[str, Any],
    reports: list[Mapping[str, Any]],
    *,
    section: str,
    suggestions_key: str,
) -> dict[str, Any] | None:
    existing = profile.get(section)
    if isinstance(existing, list) and existing:
        return None

    report, suggestions = _newest_report_suggestions(reports, suggestions_key=suggestions_key)
    if not suggestions:
        return None

    items = []
    for raw in suggestions:
        item = _normalize_suggestion(raw, section=section)
        if item is not None:
            items.append(item)
    if not items:
        return None

    report_id = str(report.get("report_id") or "statement") if report else "statement"
    label = section.replace("_", " ")
    summary = "; ".join(
        f"{item['label']}: ${item['monthly_amount_usd']:,.2f}/month" for item in items
    )
    claim = (
        f"Statement import {report_id} suggested {len(items)} {label} "
        f"while the profile has none: {summary}"
    )
    return {
        "source_domain": "import",
        "source_ref": f"profile_inference/{section}",
        "extracted_claim": claim,
        "target_domain": "profile",
        "target_area": section,
        "target_field": section,
        "target_value": {
            section: items,
            "summary": summary,
            "requires_user_confirmation": True,
        },
        "confidence": "medium",
        "metadata": {
            "detector": INFERENCE_DETECTOR,
            "inference_kind": f"statement_{suggestions_key}",
            "profile_patch_kind": section,
            "requires_user_confirmation": True,
            "import_report_id": report_id,
        },
        "lifecycle_state": "pending_review",
        "dedupe_key": f"profile_inference:{section}",
    }


def _newest_report_suggestions(
    reports: list[Mapping[str, Any]],
    *,
    suggestions_key: str,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    ordered = sorted(
        reports,
        key=lambda report: str(report.get("created_at") or ""),
        reverse=True,
    )
    for report in ordered:
        raw = report.get(suggestions_key)
        if isinstance(raw, list):
            suggestions = [item for item in raw if isinstance(item, Mapping)]
            if suggestions:
                return report, suggestions
    return None, []


def _normalize_suggestion(raw: Mapping[str, Any], *, section: str) -> dict[str, Any] | None:
    label = str(raw.get("label") or "").strip()
    amount = _safe_float(raw.get("monthly_amount_usd"))
    if not label or amount <= 0:
        return None
    if section == "income_items":
        return {
            "label": label,
            "monthly_amount_usd": round(amount, 2),
            "source_type": str(raw.get("source_type") or "other").strip() or "other",
            "is_pre_tax": bool(raw.get("is_pre_tax", False)),
        }
    return {
        "label": label,
        "monthly_amount_usd": round(amount, 2),
        "category": str(raw.get("category") or "general").strip() or "general",
        "is_fixed": bool(raw.get("is_fixed", True)),
    }


def _marginal_rate_for_taxable_income(taxable_income: float, brackets: tuple) -> float | None:
    rate = None
    for bracket in brackets:
        if taxable_income >= bracket.min_income:
            rate = bracket.rate
        else:
            break
    return rate


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _safe_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
