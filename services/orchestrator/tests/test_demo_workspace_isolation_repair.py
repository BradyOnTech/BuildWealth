from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    DEFAULT_HOUSEHOLD_WORKSPACE_ID,
    DEMO_HOUSEHOLD_WORKSPACE_ID,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed-demo-data.py"
REPAIR_SCRIPT = REPO_ROOT / "scripts" / "repair-demo-workspace-isolation.py"


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_moves_demo_state_to_demo_workspace_and_preserves_real_records(
    tmp_path: Path,
) -> None:
    seed = _load_script(SEED_SCRIPT, "test_demo_seed")
    repair = _load_script(REPAIR_SCRIPT, "test_demo_repair")
    staged_demo_root = tmp_path / "ws_staged_demo"
    household_root = tmp_path / "household"
    demo_root = household_root / "workspaces" / DEMO_HOUSEHOLD_WORKSPACE_ID
    control_db = tmp_path / "control" / "control.db"

    seed.seed_demo_dataset(staged_demo_root, include_settings=False)
    shutil.copytree(staged_demo_root, household_root)

    profile_path = household_root / "profile" / "financial_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["household_members"].append(
        {
            "id": "real-member",
            "display_name": "Real Person",
            "relationship": "self",
            "birth_year": 1990,
            "retirement_age": 65,
            "dependent": False,
            "notes": "",
        }
    )
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    portfolio = PortfolioStore(household_root / "portfolio")
    portfolio.add_transaction(
        date="2026-07-01",
        symbol="",
        action="CASH_DEPOSIT",
        quantity=1000,
        unit_price=1,
        account="default",
        note="real emergency cash",
    )

    control_plane = ControlPlaneStore(control_db)
    control_plane.bootstrap_default_household(
        owner_email="owner@example.test",
        default_storage_root=household_root,
        demo_storage_root=demo_root,
    )

    summary = repair.repair_default_workspaces(
        control_db=control_db,
        household_root=household_root,
        demo_root=demo_root,
        apply=True,
    )

    assert summary["household_cleanup"]["portfolio_transactions"] == 19
    assert summary["demo_seed"]["portfolio_total_value"] > 500_000

    repaired_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert [item["id"] for item in repaired_profile["household_members"]] == [
        "real-member"
    ]
    repaired_portfolio = PortfolioStore(household_root / "portfolio")
    assert len(repaired_portfolio.list_transactions(limit=100)) == 1
    assert repaired_portfolio.get_holdings()["total_portfolio_value"] == 1000
    assert not list((household_root / "snapshots").glob("snapshot-*.json"))
    assert not (household_root / "imports" / "inbox" / seed.DEMO_IMPORT_FILE).exists()
    assert json.loads(
        (household_root / "recommendations" / "inbox.json").read_text(encoding="utf-8")
    )["recommendations"] == []
    assert json.loads(
        (household_root / "plans" / "index.json").read_text(encoding="utf-8")
    )["plans"] == []

    demo_profile = json.loads(
        (demo_root / "profile" / "financial_profile.json").read_text(encoding="utf-8")
    )
    assert {item["display_name"] for item in demo_profile["household_members"]} == {
        "Alex",
        "Jordan",
        "Riley",
    }
    assert PortfolioStore(demo_root / "portfolio").get_holdings()[
        "total_portfolio_value"
    ] > 500_000

    with control_plane._connect() as connection:
        rows = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, workspace_type, storage_path FROM workspaces"
            ).fetchall()
        }
    assert rows[DEFAULT_HOUSEHOLD_WORKSPACE_ID]["workspace_type"] == "household"
    assert rows[DEMO_HOUSEHOLD_WORKSPACE_ID]["workspace_type"] == "demo"
    assert Path(rows[DEFAULT_HOUSEHOLD_WORKSPACE_ID]["storage_path"]).resolve() == (
        household_root.resolve()
    )
    assert Path(rows[DEMO_HOUSEHOLD_WORKSPACE_ID]["storage_path"]).resolve() == (
        demo_root.resolve()
    )
