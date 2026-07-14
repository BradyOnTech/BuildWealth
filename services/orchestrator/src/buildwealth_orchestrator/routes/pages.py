"""Pages routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "ui_root",
    "ui_root_v2",
    "privacy_notice_page",
    "terms_page",
    "ai_disclosure_page",
    "robots_txt",
    "sitemap_xml",
    "health",
]


def _site_origin(request: Request) -> str:
    """Absolute origin (scheme://host[:port]) the page is being served from.

    Used to fill absolute canonical/Open Graph/JSON-LD URLs so crawlers and
    social scrapers resolve them correctly. Behind a TLS-terminating proxy,
    run uvicorn with --proxy-headers so the scheme reflects https.
    """
    return str(request.base_url).rstrip("/")


@router.get("/", include_in_schema=False)
def ui_root(request: Request) -> m.Response:
    """Public marketing front door. The v2 product surface lives at /v2."""
    landing = m.web_v2_dir / "landing.html"
    if landing.exists():
        html = landing.read_text(encoding="utf-8").replace("%%BASE%%", _site_origin(request))
        return m.HTMLResponse(html)
    # Fall back to the product surface if the landing page is missing.
    v2_index = m.web_v2_dir / "index.html"
    if v2_index.exists():
        return m.RedirectResponse(url="/v2", status_code=307)
    return m.HTMLResponse(
        "<h1>BuildWealth v2 UI not found</h1><p>Expected index.html in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


@router.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request) -> m.Response:
    """Allow indexing of the marketing surface; keep the app + API out of the index."""
    origin = _site_origin(request)
    body = (
        "User-agent: *\n"
        "Disallow: /v2\n"
        "Disallow: /api/\n"
        f"Sitemap: {origin}/sitemap.xml\n"
    )
    return m.Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request) -> m.Response:
    """Minimal sitemap for the public marketing surface (legal pages are noindex)."""
    origin = _site_origin(request)
    paths = ["/"]
    urls = "".join(f"  <url><loc>{origin}{p}</loc></url>\n" for p in paths)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )
    return m.Response(content=body, media_type="application/xml")


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
