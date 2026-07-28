#!/usr/bin/env python3
"""Repair the legacy local household after demo data was seeded into its root."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_SRC = REPO_ROOT / "services" / "orchestrator" / "src"
sys.path.insert(0, str(ORCHESTRATOR_SRC))

from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


DEFAULT_HOUSEHOLD_WORKSPACE_ID = "ws_default_household"
DEFAULT_DEMO_WORKSPACE_ID = "ws_demo_household"
DEMO_MARKER = "[demo-average-household]"
DEMO_SOURCE = "demo_average_household"
DEMO_PLAN_TITLE = "Average Household Retirement Simulation"
DEMO_IMPORT_FILE = "average-household-brokerage-import.csv"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def is_demo_record(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    identifier = str(item.get("id") or "").lower()
    account = str(item.get("account") or "").lower()
    source = str(item.get("source") or "").lower()
    note = str(item.get("note") or "")
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    action_payload = item.get("action_payload")
    return (
        identifier.startswith(("demo-", "demo_"))
        or account.startswith(("demo-", "demo_"))
        or source == DEMO_SOURCE
        or DEMO_MARKER in note
        or any(str(tag).lower() == "demo" for tag in tags)
        or (
            isinstance(action_payload, dict)
            and bool(action_payload.get("demo_seed"))
        )
    )


def clean_profile(household_root: Path, *, apply: bool) -> dict[str, int]:
    path = household_root / "profile" / "financial_profile.json"
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return {"profile_items": 0}
    removed = 0
    for key in (
        "household_members",
        "income_items",
        "expense_items",
        "debt_items",
        "goal_items",
        "physical_assets",
    ):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        kept = [item for item in items if not is_demo_record(item)]
        removed += len(items) - len(kept)
        payload[key] = kept
    if removed and apply:
        payload["updated_at"] = utc_now_iso()
        write_json(path, payload)
    return {"profile_items": removed}


def clean_portfolio(household_root: Path, *, apply: bool) -> dict[str, int]:
    portfolio_dir = household_root / "portfolio"
    transactions_path = portfolio_dir / "transactions.json"
    accounts_path = portfolio_dir / "accounts.json"
    manual_prices_path = portfolio_dir / "manual_prices.json"
    metadata_path = portfolio_dir / "asset_metadata.json"
    watchlist_path = portfolio_dir / "watchlist.json"

    transactions = read_json(transactions_path, [])
    transactions = transactions if isinstance(transactions, list) else []
    kept_transactions = [
        item
        for item in transactions
        if not is_demo_record(item)
        and str(item.get("symbol") or "").upper() != "DEMO_HOME"
    ]

    accounts = read_json(accounts_path, {})
    account_items = accounts.get("accounts") if isinstance(accounts, dict) else []
    account_items = account_items if isinstance(account_items, list) else []
    kept_accounts = [item for item in account_items if not is_demo_record(item)]

    manual_prices = read_json(manual_prices_path, {})
    manual_by_symbol = (
        manual_prices.get("by_symbol") if isinstance(manual_prices, dict) else {}
    )
    manual_by_symbol = manual_by_symbol if isinstance(manual_by_symbol, dict) else {}
    kept_manual_prices = {
        symbol: item
        for symbol, item in manual_by_symbol.items()
        if str(symbol).upper() != "DEMO_HOME" and not is_demo_record(item)
    }

    metadata = read_json(metadata_path, {})
    metadata_symbols = metadata.get("symbols") if isinstance(metadata, dict) else {}
    metadata_symbols = metadata_symbols if isinstance(metadata_symbols, dict) else {}
    kept_metadata = {
        symbol: item
        for symbol, item in metadata_symbols.items()
        if str(symbol).upper() != "DEMO_HOME" and not is_demo_record(item)
    }

    watchlist = read_json(watchlist_path, {})
    watchlist_items = watchlist.get("items") if isinstance(watchlist, dict) else []
    watchlist_items = watchlist_items if isinstance(watchlist_items, list) else []
    kept_watchlist = [item for item in watchlist_items if not is_demo_record(item)]

    counts = {
        "portfolio_transactions": len(transactions) - len(kept_transactions),
        "portfolio_accounts": len(account_items) - len(kept_accounts),
        "portfolio_manual_prices": len(manual_by_symbol) - len(kept_manual_prices),
        "portfolio_asset_metadata": len(metadata_symbols) - len(kept_metadata),
        "portfolio_watchlist_items": len(watchlist_items) - len(kept_watchlist),
    }
    if not apply or not any(counts.values()):
        return counts

    write_json(transactions_path, kept_transactions)
    if isinstance(accounts, dict):
        accounts["accounts"] = kept_accounts
        valid_account_ids = {
            str(item.get("id") or "") for item in kept_accounts if isinstance(item, dict)
        }
        if str(accounts.get("default_account_id") or "") not in valid_account_ids:
            accounts["default_account_id"] = next(iter(valid_account_ids), "default")
        accounts["updated_at"] = utc_now_iso()
        write_json(accounts_path, accounts)
    if isinstance(manual_prices, dict):
        manual_prices["by_symbol"] = kept_manual_prices
        manual_prices["updated_at"] = utc_now_iso()
        write_json(manual_prices_path, manual_prices)
    if isinstance(metadata, dict):
        metadata["symbols"] = kept_metadata
        metadata["updated_at"] = utc_now_iso()
        write_json(metadata_path, metadata)
    if isinstance(watchlist, dict):
        watchlist["items"] = kept_watchlist
        watchlist["updated_at"] = utc_now_iso()
        write_json(watchlist_path, watchlist)

    # Holdings are derived canonical output. Rebuild after the source records
    # are clean so no demo account or valuation survives in My Household.
    PortfolioStore(portfolio_dir)._rebuild_holdings()
    # A running price/snapshot worker may have begun a rebuild just before the
    # source cleanup and recreated empty account shells from its stale read.
    # Scrub account IDs once more after the canonical rebuild closes that race.
    refreshed_accounts = read_json(accounts_path, {})
    refreshed_items = (
        refreshed_accounts.get("accounts")
        if isinstance(refreshed_accounts, dict)
        else []
    )
    refreshed_items = refreshed_items if isinstance(refreshed_items, list) else []
    final_accounts = [item for item in refreshed_items if not is_demo_record(item)]
    if len(final_accounts) != len(refreshed_items) and isinstance(refreshed_accounts, dict):
        refreshed_accounts["accounts"] = final_accounts
        final_account_ids = {
            str(item.get("id") or "")
            for item in final_accounts
            if isinstance(item, dict)
        }
        if str(refreshed_accounts.get("default_account_id") or "") not in final_account_ids:
            refreshed_accounts["default_account_id"] = next(iter(final_account_ids), "default")
        refreshed_accounts["updated_at"] = utc_now_iso()
        write_json(accounts_path, refreshed_accounts)
    return counts


def clean_plans(household_root: Path, *, apply: bool) -> dict[str, int]:
    plans_dir = household_root / "plans"
    index_path = plans_dir / "index.json"
    payload = read_json(index_path, {})
    plans = payload.get("plans") if isinstance(payload, dict) else []
    plans = plans if isinstance(plans, list) else []
    demo_plan_ids = {
        str(item.get("id") or "")
        for item in plans
        if str(item.get("title") or "") == DEMO_PLAN_TITLE
        or "demo plan" in str(item.get("description") or "").lower()
    }
    kept = [item for item in plans if str(item.get("id") or "") not in demo_plan_ids]
    if demo_plan_ids and apply and isinstance(payload, dict):
        for plan_id in demo_plan_ids:
            plan_dir = (plans_dir / plan_id).resolve()
            if plan_dir.parent == plans_dir.resolve() and plan_dir.exists():
                shutil.rmtree(plan_dir)
        payload["plans"] = kept
        if str(payload.get("active_plan_id") or "") in demo_plan_ids:
            payload["active_plan_id"] = str(kept[0].get("id") or "") if kept else None
        write_json(index_path, payload)
    return {"plans": len(demo_plan_ids)}


def clean_recommendations(
    household_root: Path,
    *,
    apply: bool,
    remaining_transactions: int,
    removed_demo_transactions: int,
) -> dict[str, int]:
    path = household_root / "recommendations" / "inbox.json"
    payload = read_json(path, {})
    items = payload.get("recommendations") if isinstance(payload, dict) else []
    items = items if isinstance(items, list) else []

    def should_remove(item: Any) -> bool:
        if is_demo_record(item):
            return True
        return (
            removed_demo_transactions > 0
            and remaining_transactions == 0
            and isinstance(item, dict)
            and str(item.get("source") or "").startswith("generator:")
        )

    kept = [item for item in items if not should_remove(item)]
    removed = len(items) - len(kept)
    if removed and apply and isinstance(payload, dict):
        payload["recommendations"] = kept
        write_json(path, payload)
    return {"recommendations": removed}


def clean_derived_and_imported_data(
    household_root: Path,
    *,
    apply: bool,
) -> dict[str, int]:
    removed_snapshots = 0
    for path in (household_root / "snapshots").glob("snapshot-*.json"):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if DEMO_MARKER not in raw and '"DEMO_HOME"' not in raw and '"demo_' not in raw:
            continue
        removed_snapshots += 1
        if apply:
            path.unlink()

    import_path = household_root / "imports" / "inbox" / DEMO_IMPORT_FILE
    removed_imports = int(import_path.exists())
    if removed_imports and apply:
        import_path.unlink()

    context_path = household_root / "storage" / "context_index.db"
    removed_context_indexes = int(context_path.exists())
    if removed_context_indexes and apply:
        context_path.unlink()

    return {
        "snapshots": removed_snapshots,
        "imports": removed_imports,
        "context_indexes": removed_context_indexes,
    }


def clean_household_root(household_root: Path, *, apply: bool) -> dict[str, Any]:
    household_root = household_root.resolve()
    profile_counts = clean_profile(household_root, apply=apply)
    portfolio_counts = clean_portfolio(household_root, apply=apply)
    transactions = read_json(household_root / "portfolio" / "transactions.json", [])
    if not apply:
        transactions = [
            item
            for item in transactions
            if not is_demo_record(item)
            and str(item.get("symbol") or "").upper() != "DEMO_HOME"
        ]
    plan_counts = clean_plans(household_root, apply=apply)
    recommendation_counts = clean_recommendations(
        household_root,
        apply=apply,
        remaining_transactions=len(transactions) if isinstance(transactions, list) else 0,
        removed_demo_transactions=portfolio_counts["portfolio_transactions"],
    )
    derived_counts = clean_derived_and_imported_data(household_root, apply=apply)
    return {
        **profile_counts,
        **portfolio_counts,
        **plan_counts,
        **recommendation_counts,
        **derived_counts,
    }


def load_demo_seed_module() -> Any:
    script_path = REPO_ROOT / "scripts" / "seed-demo-data.py"
    spec = importlib.util.spec_from_file_location("buildwealth_demo_seed", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load demo seed script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workspace_record(connection: sqlite3.Connection, workspace_id: str) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT id, name, workspace_type, storage_path FROM workspaces WHERE id = ?",
        (workspace_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Workspace not found: {workspace_id}")
    return row


def storage_path_value(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def repair_default_workspaces(
    *,
    control_db: Path,
    household_root: Path,
    demo_root: Path,
    apply: bool,
) -> dict[str, Any]:
    control_db = control_db.resolve()
    household_root = household_root.resolve()
    demo_root = demo_root.resolve()
    seed_module = load_demo_seed_module()
    seed_module.validate_demo_data_root(demo_root)
    if household_root == demo_root or demo_root.parent != (household_root / "workspaces").resolve():
        raise ValueError("Demo workspace must be a direct child of the household workspaces directory")
    if not control_db.exists():
        raise ValueError(f"Control database does not exist: {control_db}")

    with sqlite3.connect(control_db) as connection:
        household = workspace_record(connection, DEFAULT_HOUSEHOLD_WORKSPACE_ID)
        demo = workspace_record(connection, DEFAULT_DEMO_WORKSPACE_ID)
        if household["workspace_type"] != "household":
            raise ValueError("Default household workspace is not typed as household")
        if demo["workspace_type"] != "demo":
            raise ValueError("Default demo workspace is not typed as demo")

    cleanup = clean_household_root(household_root, apply=apply)
    demo_summary: dict[str, Any] | None = None
    if apply:
        if demo_root.exists():
            shutil.rmtree(demo_root)
        demo_root.mkdir(parents=True, exist_ok=True)
        demo_summary = seed_module.seed_demo_dataset(demo_root, include_settings=False)
        with sqlite3.connect(control_db) as connection:
            now = utc_now_iso()
            connection.execute(
                "UPDATE workspaces SET storage_path = ?, updated_at = ? WHERE id = ?",
                (
                    storage_path_value(household_root),
                    now,
                    DEFAULT_HOUSEHOLD_WORKSPACE_ID,
                ),
            )
            connection.execute(
                "UPDATE workspaces SET storage_path = ?, updated_at = ? WHERE id = ?",
                (storage_path_value(demo_root), now, DEFAULT_DEMO_WORKSPACE_ID),
            )

    return {
        "mode": "apply" if apply else "dry-run",
        "household_root": str(household_root),
        "demo_root": str(demo_root),
        "household_cleanup": cleanup,
        "demo_seed": demo_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move synthetic demo state into Demo Household and clean My Household."
    )
    parser.add_argument(
        "--control-db",
        type=Path,
        default=REPO_ROOT / "data" / "control" / "control.db",
    )
    parser.add_argument(
        "--household-root",
        type=Path,
        default=REPO_ROOT / "data",
    )
    parser.add_argument(
        "--demo-root",
        type=Path,
        default=REPO_ROOT / "data" / "workspaces" / DEFAULT_DEMO_WORKSPACE_ID,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Without this flag the script only reports changes.",
    )
    args = parser.parse_args()
    summary = repair_default_workspaces(
        control_db=args.control_db,
        household_root=args.household_root,
        demo_root=args.demo_root,
        apply=args.apply,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
