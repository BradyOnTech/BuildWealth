from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


IMPORT_WORKBENCH_SCHEMA_VERSION = 1
IMPORT_REPORT_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, *, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return token or fallback


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _count_rows_with_reason(rows: list[dict[str, Any]], reason: str) -> int:
    return sum(
        1
        for row in rows
        if reason in {str(item) for item in row.get("rejection_reasons", [])}
    )


def _count_rows_with_flag(rows: list[dict[str, Any]], flag: str) -> int:
    seen: set[str] = set()
    total = 0
    for index, row in enumerate(rows):
        if flag not in {str(item) for item in row.get("normalization_flags", [])}:
            continue
        key = str(row.get("row_number") or row.get("transaction_fingerprint") or index)
        if key in seen:
            continue
        seen.add(key)
        total += 1
    return total


def build_import_workbench_summary(import_response: Any) -> dict[str, Any]:
    response_payload = import_response if isinstance(import_response, dict) else {}
    report = getattr(import_response, "reconciliation_report", None)
    if report is None:
        report = response_payload.get("reconciliation_report")
    if hasattr(report, "model_dump"):
        report_payload = report.model_dump(mode="json")
    elif isinstance(report, dict):
        report_payload = report
    else:
        report_payload = {}

    rejected_rows = list(report_payload.get("rejected_rows") or [])
    accepted_rows = list(report_payload.get("accepted_rows") or [])
    normalized_rows = list(report_payload.get("normalized_rows") or [])

    duplicate_count = _count_rows_with_reason(rejected_rows, "duplicate_existing_transaction")
    account_review_count = _count_rows_with_flag(normalized_rows + accepted_rows, "account_missing_mapping")
    asset_review_count = sum(
        1
        for row in rejected_rows
        if _row_review_reason(row)
        and "account_missing_mapping" not in {str(item) for item in row.get("normalization_flags", [])}
    )
    unresolved_count = max(0, int(report_payload.get("rejected_count") or 0) - duplicate_count)

    warnings = getattr(import_response, "warnings", response_payload.get("warnings", [])) or []
    errors = getattr(import_response, "errors", response_payload.get("errors", [])) or []
    parsed_rows = getattr(import_response, "parsed_rows", response_payload.get("parsed_rows", 0)) or 0

    return {
        "parsed_rows": int(parsed_rows),
        "accepted_count": int(report_payload.get("accepted_count") or 0),
        "normalized_count": int(report_payload.get("normalized_count") or 0),
        "rejected_count": int(report_payload.get("rejected_count") or 0),
        "duplicate_count": duplicate_count,
        "unresolved_count": unresolved_count,
        "asset_review_count": asset_review_count,
        "account_review_count": account_review_count,
        "review_item_count": asset_review_count + account_review_count,
        "parser_confidence_flag": str(report_payload.get("parser_confidence_flag") or "low"),
        "parser_confidence_score": float(report_payload.get("parser_confidence_score") or 0.0),
        "warnings_count": len(warnings),
        "errors_count": len(errors),
    }


def _row_review_reason(row: dict[str, Any]) -> str:
    reasons = [str(item) for item in row.get("rejection_reasons", []) if item]
    flags = [str(item) for item in row.get("normalization_flags", []) if item]
    if "duplicate_existing_transaction" in reasons:
        return ""
    if "missing_symbol" in reasons:
        return "The row is missing an investment symbol, so BuildWealth cannot connect it to an asset."
    if any(reason.startswith("unsupported_or_missing_action") for reason in reasons):
        return "The row uses an activity type BuildWealth could not read."
    if any(reason.startswith("invalid_or_missing_date") for reason in reasons):
        return "The row is missing a usable date."
    if "unable_to_infer_quantity_or_unit_price" in reasons:
        return "The row is missing quantity or price information needed for portfolio history."
    if "account_missing_mapping" in flags:
        return "The account name was imported, but it is not matched to a saved portfolio account yet."
    return "The row needs review before BuildWealth treats it as portfolio history."


def _row_symbol(row: dict[str, Any]) -> str:
    normalized = row.get("normalized_row") if isinstance(row.get("normalized_row"), dict) else {}
    raw = row.get("raw_row") if isinstance(row.get("raw_row"), dict) else {}
    return str(
        normalized.get("symbol")
        or raw.get("symbol")
        or raw.get("ticker")
        or raw.get("Symbol")
        or ""
    ).strip().upper()


def _row_account_name(row: dict[str, Any]) -> str:
    normalized = row.get("normalized_row") if isinstance(row.get("normalized_row"), dict) else {}
    raw = row.get("raw_row") if isinstance(row.get("raw_row"), dict) else {}
    return str(
        normalized.get("account_name")
        or raw.get("account_name")
        or raw.get("account")
        or raw.get("Account")
        or ""
    ).strip()


def build_import_review_item_drafts(report: dict[str, Any]) -> list[dict[str, Any]]:
    reconciliation = report.get("reconciliation_report") if isinstance(report.get("reconciliation_report"), dict) else {}
    rows: list[dict[str, Any]] = []
    for row in reconciliation.get("rejected_rows") or []:
        if isinstance(row, dict):
            rows.append(row)
    for row in (reconciliation.get("normalized_rows") or []) + (reconciliation.get("accepted_rows") or []):
        if not isinstance(row, dict):
            continue
        flags = {str(item) for item in row.get("normalization_flags", [])}
        if "account_missing_mapping" in flags:
            rows.append(row)

    drafts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        reason = _row_review_reason(row)
        if not reason:
            continue
        row_number = row.get("row_number")
        reason_keys = [str(item) for item in (row.get("rejection_reasons", []) or row.get("normalization_flags", []) or [])]
        dedupe_key = f"{report.get('report_id')}:{row_number}:{','.join(reason_keys)}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        symbol = _row_symbol(row)
        is_account_review = "account_missing_mapping" in set(reason_keys)
        account_name = _row_account_name(row)
        if is_account_review:
            row_label = f"row {row_number or '?'}"
            title = f"Account needs review: {account_name or row_label}"
            recommendation_type = "portfolio_account_review_item"
            kind = "portfolio_account_review_item"
            review_label = "Portfolio Accounts"
            review_target = "accounts"
        else:
            title_subject = symbol if symbol else f"row {row_number or '?'}"
            title = f"Asset needs review: {title_subject}"
            recommendation_type = "asset_review_item"
            kind = "asset_review_item"
            review_label = "Portfolio Assets"
            review_target = "assets"
        drafts.append(
            {
                "title": title,
                "detail": reason,
                "priority": "medium",
                "recommendation_type": recommendation_type,
                "source": "import_workbench",
                "action_payload": {
                    "kind": kind,
                    "report_id": report.get("report_id"),
                    "session_id": report.get("session_id"),
                    "row_number": row_number,
                    "symbol": symbol or None,
                    "account_name": account_name or None,
                    "reasons": reason_keys,
                    "raw_row": row.get("raw_row") if isinstance(row.get("raw_row"), dict) else {},
                    "normalized_row": row.get("normalized_row") if isinstance(row.get("normalized_row"), dict) else {},
                    "review_route": {
                        "route": "portfolio",
                        "label": review_label,
                        "target": review_target,
                        "reason": "Resolve the asset or account mapping before relying on this import row.",
                    },
                },
            }
        )
    return drafts


def _report_like_payload_for_session(payload: dict[str, Any]) -> dict[str, Any]:
    preview = payload.get("preview_response") if isinstance(payload.get("preview_response"), dict) else {}
    return {
        "report_id": payload.get("report_id"),
        "session_id": payload.get("session_id"),
        "reconciliation_report": preview.get("reconciliation_report") if isinstance(preview, dict) else {},
    }


@dataclass
class ImportWorkbenchStore:
    workbench_dir: Path
    reports_dir: Path

    def __post_init__(self) -> None:
        self.workbench_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        *,
        file_path: Path,
        original_file_name: str,
        options: dict[str, Any],
        preview_response: Any,
    ) -> dict[str, Any]:
        session_id = f"imp_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
        now = utc_now_iso()
        payload = {
            "schema_version": IMPORT_WORKBENCH_SCHEMA_VERSION,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "status": "previewed",
            "source_file": {
                "path": str(file_path),
                "name": original_file_name,
                "stored_name": file_path.name,
                "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            },
            "options": options,
            "summary": build_import_workbench_summary(preview_response),
            "preview_response": (
                preview_response.model_dump(mode="json")
                if hasattr(preview_response, "model_dump")
                else preview_response
            ),
            "report_id": None,
        }
        payload["review_items"] = build_import_review_item_drafts(_report_like_payload_for_session(payload))
        _write_json(self._session_path(session_id), payload)
        return payload

    def load_session(self, session_id: str) -> dict[str, Any]:
        clean_id = _safe_token(session_id, fallback="session")
        payload = _read_json(self._session_path(clean_id))
        if not payload:
            raise FileNotFoundError(f"Import workbench session not found: {session_id}")
        return payload

    def update_session_after_apply(self, session_id: str, *, apply_response: Any, report: dict[str, Any]) -> dict[str, Any]:
        payload = self.load_session(session_id)
        payload["updated_at"] = utc_now_iso()
        payload["status"] = "applied"
        payload["summary"] = build_import_workbench_summary(apply_response)
        payload["apply_response"] = (
            apply_response.model_dump(mode="json")
            if hasattr(apply_response, "model_dump")
            else apply_response
        )
        payload["report_id"] = report.get("report_id")
        payload["review_items"] = report.get("review_items") if isinstance(report.get("review_items"), list) else []
        _write_json(self._session_path(session_id), payload)
        return payload

    def create_report(
        self,
        *,
        session: dict[str, Any],
        apply_response: Any,
        operator: str = "user",
    ) -> dict[str, Any]:
        report_id = f"ir_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
        response_payload = (
            apply_response.model_dump(mode="json")
            if hasattr(apply_response, "model_dump")
            else apply_response
        )
        source_file = session.get("source_file") if isinstance(session.get("source_file"), dict) else {}
        payload = {
            "schema_version": IMPORT_REPORT_SCHEMA_VERSION,
            "report_id": report_id,
            "session_id": session.get("session_id"),
            "created_at": utc_now_iso(),
            "operator": operator,
            "source_file": source_file,
            "options": session.get("options") if isinstance(session.get("options"), dict) else {},
            "summary": build_import_workbench_summary(apply_response),
            "imported_activities": int(getattr(apply_response, "imported_activities", 0) or 0),
            "selected_template": getattr(apply_response, "selected_template", None),
            "detected_template": getattr(apply_response, "detected_template", None),
            "warnings": list(getattr(apply_response, "warnings", []) or []),
            "errors": list(getattr(apply_response, "errors", []) or []),
            "reconciliation_report": response_payload.get("reconciliation_report", {}),
            "affected_links": {
                "portfolio_transactions": "#portfolio?section=transactions",
                "portfolio_history": f"#portfolio?section=transactions&import_report={report_id}",
                "portfolio_accounts": "#portfolio?section=accounts",
                "portfolio_assets": "#portfolio?section=assets",
                "import_reports": "#import-sync",
                "import_report": f"#import-sync?report={report_id}",
            },
        }
        payload["review_items"] = build_import_review_item_drafts(payload)
        _write_json(self._report_path(report_id), payload)
        return payload

    def list_reports(self, *, limit: int = 50) -> list[dict[str, Any]]:
        reports = [_read_json(path) for path in self.reports_dir.glob("*.json")]
        reports = [report for report in reports if report]
        reports.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return reports[: max(1, min(limit, 200))]

    def load_report(self, report_id: str) -> dict[str, Any]:
        clean_id = _safe_token(report_id, fallback="report")
        payload = _read_json(self._report_path(clean_id))
        if not payload:
            raise FileNotFoundError(f"Import report not found: {report_id}")
        return payload

    def _session_path(self, session_id: str) -> Path:
        return self.workbench_dir / f"{_safe_token(session_id, fallback='session')}.json"

    def _report_path(self, report_id: str) -> Path:
        return self.reports_dir / f"{_safe_token(report_id, fallback='report')}.json"
