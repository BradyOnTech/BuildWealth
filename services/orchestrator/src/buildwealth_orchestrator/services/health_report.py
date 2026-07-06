"""Health that means something.

A health endpoint that always says "ok" is a lie with an HTTP status; the
Docker healthcheck and any uptime monitor inherit whatever this reports, so
it verifies the three things that actually take the app down: the control
database answers, the data directory accepts writes, and the disk has
headroom. Reason strings stay generic on purpose — this endpoint is
unauthenticated and must not leak paths or internals.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

# Below WARN the report stays ok but names the pressure; below FAIL the
# instance is degraded — SQLite and JSON writes both die ugly on a full disk.
DISK_WARN_FREE_PERCENT = 10.0
DISK_FAIL_FREE_PERCENT = 3.0


def check_database(connect: Callable[[], Any]) -> tuple[bool, str]:
    try:
        connection = connect()
        try:
            row = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
            applied = int(row[0] if not hasattr(row, "keys") else row["COUNT(*)"])
        finally:
            connection.close()
        if applied < 1:
            return False, "no schema migrations applied"
        return True, "ok"
    except Exception:
        return False, "database check failed"


def check_storage_writable(data_dir: Path) -> tuple[bool, str]:
    try:
        probe = data_dir / f".health-probe-{uuid.uuid4().hex[:8]}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, "ok"
    except Exception:
        return False, "data directory is not writable"


def check_disk(data_dir: Path) -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(data_dir)
        free_percent = usage.free / usage.total * 100 if usage.total else 0.0
    except Exception:
        return False, "disk check failed"
    if free_percent < DISK_FAIL_FREE_PERCENT:
        return False, f"disk critically full ({free_percent:.0f}% free)"
    if free_percent < DISK_WARN_FREE_PERCENT:
        return True, f"low disk ({free_percent:.0f}% free)"
    return True, f"ok ({free_percent:.0f}% free)"


def build_health_report(*, connect: Callable[[], Any], data_dir: Path) -> dict[str, Any]:
    """{status: ok|degraded, checks: {...}} — degraded maps to HTTP 503."""
    database_ok, database_detail = check_database(connect)
    storage_ok, storage_detail = check_storage_writable(data_dir)
    disk_ok, disk_detail = check_disk(data_dir)
    healthy = database_ok and storage_ok and disk_ok
    return {
        "status": "ok" if healthy else "degraded",
        "checks": {
            "database": database_detail,
            "storage": storage_detail,
            "disk": disk_detail,
        },
    }
