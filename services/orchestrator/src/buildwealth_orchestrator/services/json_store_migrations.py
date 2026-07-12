"""Ordered, append-only migrations for the JSON document stores.

The control-plane SQLite database has a disciplined migration runner
(control_db_migrations.py); this module gives the JSON stores the same
discipline. Stores call `migrate_payload(<store name>, payload)` when they
load their document; pending migrations run in order and the payload is
stamped with the new `schema_version`.

Rules, mirroring the control-DB runner:
- Migrations are append-only and numbered consecutively starting at 2
  (version 1 is the historical, possibly unstamped baseline).
- Never edit an applied migration — append a new one.
- Each migration takes the payload dict and returns the migrated dict; the
  runner stamps `schema_version`.
"""

from __future__ import annotations

from typing import Any, Callable

Migration = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATIONS: dict[str, list[tuple[int, Migration]]] = {}


def register_migration(store: str, target_version: int, fn: Migration) -> None:
    steps = _MIGRATIONS.setdefault(store, [])
    expected = (steps[-1][0] + 1) if steps else 2
    if target_version != expected:
        raise ValueError(
            f"{store}: migrations must be consecutive; expected {expected}, got {target_version}"
        )
    steps.append((target_version, fn))


def latest_version(store: str) -> int:
    steps = _MIGRATIONS.get(store)
    return steps[-1][0] if steps else 1


def migrate_payload(store: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Apply pending migrations to a store payload.

    Returns (payload, changed). `changed` is True when at least one migration
    ran — callers should persist the payload so migrations run once, not on
    every load.
    """
    try:
        version = int(payload.get("schema_version") or 1)
    except (TypeError, ValueError):
        version = 1
    changed = False
    for target, fn in _MIGRATIONS.get(store, []):
        if version >= target:
            continue
        payload = fn(dict(payload))
        payload["schema_version"] = target
        version = target
        changed = True
    return payload, changed


# ---------------------------------------------------------------------------
# Registered migrations (append below; never reorder or edit applied entries)
# ---------------------------------------------------------------------------

# No schema changes are pending today. Example of the shape a real migration
# takes, for the next person who needs one:
#
# def _holdings_v2_add_lot_ids(payload: dict[str, Any]) -> dict[str, Any]:
#     for holding in payload.get("holdings", []):
#         for lot in holding.get("lots", []):
#             lot.setdefault("lot_id", uuid.uuid4().hex)
#     return payload
#
# register_migration("portfolio_holdings", 2, _holdings_v2_add_lot_ids)
