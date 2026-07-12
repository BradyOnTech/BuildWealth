"""Pages routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "ui_root",
    "ui_root_v2",
    "privacy_notice_page",
    "terms_page",
    "ai_disclosure_page",
    "health",
]


@router.get("/", include_in_schema=False)
def ui_root() -> m.Response:
    """Send root visitors to the canonical v2 product surface."""
    v2_index = m.web_v2_dir / "index.html"
    if v2_index.exists():
        return m.RedirectResponse(url="/v2", status_code=307)
    return m.HTMLResponse(
        "<h1>BuildWealth v2 UI not found</h1><p>Expected index.html in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


@router.get("/v2", include_in_schema=False)
@router.get("/v2/", include_in_schema=False)
def ui_root_v2() -> m.Response:
    index_file = m.web_v2_dir / "index.html"
    if index_file.exists():
        return m.FileResponse(index_file)

    return m.HTMLResponse(
        "<h1>BuildWealth v2 UI not found</h1><p>Expected index.html in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


@router.get("/privacy", include_in_schema=False)
@router.get("/privacy/", include_in_schema=False)
def privacy_notice_page() -> m.Response:
    return m._hosted_static_page("privacy.html", "BuildWealth privacy notice")


@router.get("/terms", include_in_schema=False)
@router.get("/terms/", include_in_schema=False)
def terms_page() -> m.Response:
    return m._hosted_static_page("terms.html", "BuildWealth terms")


@router.get("/ai-disclosure", include_in_schema=False)
@router.get("/ai-disclosure/", include_in_schema=False)
def ai_disclosure_page() -> m.Response:
    return m._hosted_static_page("ai-disclosure.html", "BuildWealth AI disclosure")


@router.get("/health")
def health(response: m.Response) -> dict[str, m.Any]:
    """Liveness that means something: database answers, data dir writable,
    disk has headroom. Degraded → 503, which flips the Docker healthcheck
    and any uptime monitor watching this URL."""
    report = m.build_health_report(
        connect=m.control_plane_store.database.connect,
        data_dir=m.settings.control_db_path.parent.parent,
    )
    if report["status"] != "ok":
        response.status_code = 503
    return report
