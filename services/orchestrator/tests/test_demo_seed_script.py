from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed-demo-data.py"


def _run_seed(data_root: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SEED_SCRIPT), "--data-root", str(data_root)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_demo_seed_script_creates_realistic_idempotent_household(tmp_path: Path) -> None:
    data_root = tmp_path / "data"

    first = _run_seed(data_root)
    second = _run_seed(data_root)

    assert first["profile_income_items"] == 2
    assert first["profile_expense_items"] == 7
    assert first["profile_household_members"] == 3
    assert first["portfolio_total_value"] > 500_000
    assert second["portfolio_total_value"] == first["portfolio_total_value"]
    assert second["portfolio_transactions_removed_before_seed"] > 0
    assert second["plan_id"] == first["plan_id"]
    assert second["recommendations"] == 4
    assert second["has_llm_api_key"] is False
    assert Path(second["snapshot_file"]).exists()

    profile = json.loads((data_root / "profile" / "financial_profile.json").read_text())
    assert len(profile["household_members"]) == 3
    assert profile["tax_profile"]["filing_status"] == "married_filing_jointly"
    assert profile["investment_policy"]["risk_tolerance"] == "moderate"

    transactions = json.loads((data_root / "portfolio" / "transactions.json").read_text())
    marked_transactions = [
        row for row in transactions if "[demo-average-household]" in str(row.get("note", ""))
    ]
    assert len(marked_transactions) == len(transactions)
    assert len(transactions) == 19

    plans = json.loads((data_root / "plans" / "index.json").read_text())
    assert plans["active_plan_id"] == first["plan_id"]
    plan_dir = data_root / "plans" / first["plan_id"]
    settings = json.loads((plan_dir / "settings.json").read_text())
    assert settings["annual_contribution_usd"] == 25500.0
    assert settings["simulation_mode"] == "monte_carlo"
    assert (plan_dir / "contribution_rules.json").exists()
    assert (data_root / "imports" / "inbox" / "average-household-brokerage-import.csv").exists()
    assert list((data_root / "snapshots").glob("snapshot-*.json"))

    recommendations = json.loads((data_root / "recommendations" / "inbox.json").read_text())
    assert len(recommendations["recommendations"]) == 4
    assert {row["source"] for row in recommendations["recommendations"]} == {
        "demo_average_household"
    }
