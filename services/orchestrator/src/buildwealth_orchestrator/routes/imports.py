"""Imports routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m
from buildwealth_orchestrator.services.profile_mutation import apply_reviewed_profile_patch
from buildwealth_orchestrator.services.statement_profile_reconciliation import (
    draft_statement_conflict_candidate,
    reconcile_statement_expenses,
    resolve_statement_payment_conflict,
)

router = APIRouter()

__all__ = [
    "upload_statement",
    "upload_statement_image",
    "apply_statement_suggestions",
    "resolve_statement_conflict",
    "list_import_files",
    "list_import_csv_templates",
    "import_csv_transactions",
    "import_uploaded_csv",
    "preview_import_workbench",
    "apply_import_workbench_session",
    "list_import_reports",
    "get_import_report",
]


@router.post("/api/import/statement")
async def upload_statement(
    file: m.UploadFile = m.File(...),
    delimiter: str = m.Form(","),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Upload a bank/credit card CSV statement and get expense/income suggestions."""
    m.require_permission(services.context, "imports.read")
    raw = (await file.read()).decode("utf-8", errors="replace")
    result = m.parse_statement_csv(raw, delimiter=delimiter)
    return {
        "file_name": file.filename,
        "transaction_count": len(result.transactions),
        "date_range_start": result.date_range_start.isoformat() if result.date_range_start else None,
        "date_range_end": result.date_range_end.isoformat() if result.date_range_end else None,
        "months_covered": result.months_covered,
        "total_monthly_expenses": result.total_expenses,
        "total_monthly_income": result.total_income,
        "expense_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "category": s.category,
                "is_fixed": s.is_fixed,
                "transaction_count": s.transaction_count,
                "sample_descriptions": s.sample_descriptions,
            }
            for s in result.expense_suggestions
        ],
        "income_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "source_type": s.source_type,
                "transaction_count": s.transaction_count,
            }
            for s in result.income_suggestions
        ],
        "parse_errors": result.parse_errors,
    }


@router.post("/api/import/statement-vision")
async def upload_statement_image(
    file: m.UploadFile = m.File(...),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Read a statement screenshot/photo with the 'extract' vision model and
    return the same reviewable suggestions as a CSV upload — nothing is saved
    until the user applies them."""
    m.require_permission(services.context, "imports.read")
    image_bytes = await file.read()
    result = await m.extract_statement_from_image(
        image_bytes,
        str(file.content_type or "").strip().lower(),
        llm_client=m.llm_router.client_for("extract"),
    )
    if result.status != "ready":
        return {
            "status": result.status,
            "detail": result.detail,
            "file_name": file.filename,
            "warnings": result.warnings,
        }

    parsed = result.parse_result
    return {
        "status": "ready",
        "file_name": file.filename,
        "measurement_source": "ai_vision_extraction",
        "review_note": (
            "Read by AI from your image — check the numbers against the statement "
            "before applying. Nothing is saved until you apply."
        ),
        "account_name": result.account_name,
        "account_type": result.account_type,
        "institution": result.institution,
        "ending_balance_usd": result.ending_balance_usd,
        "statement_period_start": result.statement_period_start,
        "statement_period_end": result.statement_period_end,
        "transaction_count": len(parsed.transactions),
        "date_range_start": parsed.date_range_start.isoformat() if parsed.date_range_start else None,
        "date_range_end": parsed.date_range_end.isoformat() if parsed.date_range_end else None,
        "months_covered": parsed.months_covered,
        "total_monthly_expenses": parsed.total_expenses,
        "total_monthly_income": parsed.total_income,
        "expense_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "category": s.category,
                "is_fixed": s.is_fixed,
                "transaction_count": s.transaction_count,
                "sample_descriptions": s.sample_descriptions,
            }
            for s in parsed.expense_suggestions
        ],
        "income_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "source_type": s.source_type,
                "transaction_count": s.transaction_count,
            }
            for s in parsed.income_suggestions
        ],
        "warnings": [*result.warnings, *parsed.parse_errors],
    }


@router.post("/api/import/statement/apply")
def apply_statement_suggestions(
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Apply selected expense/income suggestions to the financial profile."""
    m.require_csrf(http_request)
    m.require_permission(services.context, "profile.write")
    reconciliation = reconcile_statement_expenses(
        services.financial_profile_store.get(),
        request.get("expenses", []),
    )
    clarifications: list[dict[str, m.Any]] = []
    previously_resolved: list[dict[str, m.Any]] = []
    for conflict in reconciliation["conflicts"]:
        candidate = draft_statement_conflict_candidate(
            services.context_intelligence_service,
            conflict,
        )
        candidate_id = str(candidate.get("id") or "")
        if str(candidate.get("lifecycle_state") or "") not in {"pending_review", "deferred"}:
            metadata = candidate.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            previously_resolved.append(
                {
                    "candidate_id": candidate_id,
                    "resolution": metadata.get("resolution"),
                    "suggestion": conflict["suggestion"],
                }
            )
            continue
        clarifications.append(
            {
                "candidate_id": candidate_id,
                "question": conflict["question"],
                "suggestion": conflict["suggestion"],
                "matches": conflict["matches"],
                "copilot_href": (
                    f"#copilot?intent=statement-payment-conflict&focus={candidate_id}"
                ),
            }
        )
    result = apply_reviewed_profile_patch(
        {
            "expense_items": reconciliation["safe_expenses"],
            "income_items": request.get("income", []),
        },
        services.financial_profile_store,
        metadata_source="statement_import",
    )
    counts = result.get("counts") or {}
    added_expenses = int(counts.get("expense_items") or 0)
    added_income = int(counts.get("income_items") or 0)
    profile = services.financial_profile_store.get()
    resolved_as_existing = sum(
        1
        for item in previously_resolved
        if item.get("resolution") == "same_as_existing"
    )

    return {
        "added_expenses": added_expenses,
        "added_income": added_income,
        "skipped_duplicates": (
            int(result.get("skipped_duplicates") or 0)
            + len(reconciliation["already_counted"])
            + resolved_as_existing
        ),
        "held_for_clarification": len(clarifications),
        "previously_resolved": previously_resolved,
        "already_counted": reconciliation["already_counted"],
        "clarifications": clarifications,
        "total_expense_items": len(profile.get("expense_items", [])),
        "total_income_items": len(profile.get("income_items", [])),
    }


@router.post("/api/import/statement/conflicts/{candidate_id}/resolve")
def resolve_statement_conflict(
    candidate_id: str,
    request: dict[str, m.Any],
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    """Apply the user's explicit answer to a held statement-payment question."""
    m.require_csrf(http_request)
    m.require_permission(services.context, "profile.write")
    try:
        candidate = services.context_intelligence_service.get_context_candidate(candidate_id)
    except KeyError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return resolve_statement_payment_conflict(
            candidate=candidate,
            resolution=str(request.get("resolution") or ""),
            profile_store=services.financial_profile_store,
            context_service=services.context_intelligence_service,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/import/files")
def list_import_files(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    m.require_permission(services.context, "imports.read")
    files = []
    inbox_dir = services.paths.import_inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(inbox_dir.glob("*.csv"), key=lambda item: item.name.lower()):
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": m.datetime.fromtimestamp(stat.st_mtime, tz=m.timezone.utc),
            }
        )
    return {
        "items": files,
        "files": [item["name"] for item in files],
    }


@router.get("/api/import/csv-templates")
def list_import_csv_templates() -> dict[str, list[m.CsvTemplateOption]]:
    templates = [m.CsvTemplateOption(**item) for item in m.list_csv_templates()]
    return {"templates": templates}


@router.post("/api/import/csv", response_model=m.CsvImportResponse)
async def import_csv_transactions(
    request: m.CsvImportRequest,
    http_request: m.Request,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CsvImportResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "imports.write")
    file_path = m.resolve_import_path(
        request.path,
        import_inbox_dir=services.paths.import_inbox_dir,
        workspace_root=services.paths.root,
    )
    return await m.execute_csv_import(file_path=file_path, request=request, services=services)


@router.post("/api/import/upload-csv", response_model=m.CsvImportResponse)
async def import_uploaded_csv(
    http_request: m.Request,
    file: m.UploadFile = m.File(...),
    dry_run: bool = m.Form(True),
    delimiter: str = m.Form(","),
    broker_template: str = m.Form("auto"),
    default_data_source: str | None = m.Form(None),
    default_currency: str | None = m.Form(None),
    archive_after_success: bool = m.Form(False),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.CsvImportResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "imports.write")
    if not file.filename:
        raise m.HTTPException(status_code=400, detail="No file name provided")

    inbox_name = m.normalize_upload_filename(file.filename)
    destination = m.unique_inbox_path(inbox_name, import_inbox_dir=services.paths.import_inbox_dir)

    try:
        content = await file.read()
        destination.write_bytes(content)
    finally:
        await file.close()

    request = m.CsvImportRequest(
        path=str(destination),
        dry_run=dry_run,
        delimiter=delimiter,
        broker_template=broker_template,
        default_data_source=default_data_source,
        default_currency=default_currency,
        archive_after_success=archive_after_success,
    )

    return await m.execute_csv_import(file_path=destination, request=request, services=services)


@router.post("/api/import/workbench/preview", response_model=m.ImportWorkbenchPreviewResponse)
async def preview_import_workbench(
    http_request: m.Request,
    file: m.UploadFile = m.File(...),
    delimiter: str = m.Form(","),
    broker_template: str = m.Form("auto"),
    default_data_source: str | None = m.Form(None),
    default_currency: str | None = m.Form(None),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ImportWorkbenchPreviewResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "imports.write")
    if not file.filename:
        raise m.HTTPException(status_code=400, detail="No file name provided")

    inbox_name = m.normalize_upload_filename(file.filename)
    destination = m.unique_inbox_path(inbox_name, import_inbox_dir=services.paths.import_inbox_dir)

    try:
        content = await file.read()
        destination.write_bytes(content)
    finally:
        await file.close()

    request = m.CsvImportRequest(
        path=str(destination),
        dry_run=True,
        delimiter=delimiter,
        broker_template=broker_template,
        default_data_source=default_data_source,
        default_currency=default_currency,
        archive_after_success=False,
    )
    preview = await m.execute_csv_import(file_path=destination, request=request, services=services)
    session = services.import_workbench_store.create_session(
        file_path=destination,
        original_file_name=file.filename,
        options=request.model_dump(mode="json"),
        preview_response=preview,
    )
    return m.ImportWorkbenchPreviewResponse.model_validate(session)


@router.post("/api/import/workbench/{session_id}/apply", response_model=m.ImportWorkbenchApplyResponse)
async def apply_import_workbench_session(
    session_id: str,
    http_request: m.Request,
    request: m.ImportWorkbenchApplyRequest | None = None,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ImportWorkbenchApplyResponse:
    m.require_csrf(http_request)
    m.require_permission(services.context, "imports.write")
    apply_request = request or m.ImportWorkbenchApplyRequest()
    try:
        session = services.import_workbench_store.load_session(session_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc

    if session.get("status") == "applied" and session.get("report_id"):
        raise m.HTTPException(
            status_code=409,
            detail=f"Import workbench session has already been applied: {session.get('report_id')}",
        )

    source_file = session.get("source_file") if isinstance(session.get("source_file"), dict) else {}
    file_path = m.resolve_import_path(
        str(source_file.get("path") or ""),
        import_inbox_dir=services.paths.import_inbox_dir,
        workspace_root=services.paths.root,
    )
    options = session.get("options") if isinstance(session.get("options"), dict) else {}
    import_request = m.CsvImportRequest(
        path=str(file_path),
        dry_run=False,
        delimiter=str(options.get("delimiter") or ","),
        broker_template=str(options.get("broker_template") or "auto"),
        default_data_source=options.get("default_data_source"),
        default_currency=options.get("default_currency"),
        archive_after_success=bool(apply_request.archive_after_success),
    )
    response = await m.execute_csv_import(file_path=file_path, request=import_request, services=services)
    report = services.import_workbench_store.create_report(
        session=session,
        apply_response=response,
        operator=apply_request.operator,
    )
    m._create_import_review_items(report, inbox=services.recommendation_inbox)
    updated_session = services.import_workbench_store.update_session_after_apply(
        session_id,
        apply_response=response,
        report=report,
    )
    m._queue_autogit_event("import_workbench_applied")
    return m.ImportWorkbenchApplyResponse(
        session=m.ImportWorkbenchPreviewResponse.model_validate(updated_session),
        report=m.ImportReportResponse.model_validate(report),
    )


@router.get("/api/import/reports", response_model=m.ImportReportListResponse)
def list_import_reports(
    limit: int = 50,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ImportReportListResponse:
    m.require_permission(services.context, "imports.read")
    reports = [
        m.ImportReportResponse.model_validate(report)
        for report in services.import_workbench_store.list_reports(limit=limit)
    ]
    return m.ImportReportListResponse(reports=reports)


@router.get("/api/import/reports/{report_id}", response_model=m.ImportReportResponse)
def get_import_report(
    report_id: str,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.ImportReportResponse:
    m.require_permission(services.context, "imports.read")
    try:
        report = services.import_workbench_store.load_report(report_id)
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc
    return m.ImportReportResponse.model_validate(report)
