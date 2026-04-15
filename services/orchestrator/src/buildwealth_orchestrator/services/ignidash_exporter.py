from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, TypedDict, cast

from buildwealth_orchestrator.schemas import PortfolioSnapshot


def _infer_account_type(name: str) -> str:
    text = name.lower()
    if "hsa" in text:
        return "hsa"
    if "roth 401" in text:
        return "roth401k"
    if "roth 403" in text:
        return "roth403b"
    if "roth" in text and "ira" in text:
        return "rothIra"
    if "401" in text:
        return "401k"
    if "403" in text:
        return "403b"
    if "ira" in text:
        return "ira"
    if "saving" in text or "cash" in text or "checking" in text:
        return "savings"
    return "taxableBrokerage"


class IgnidashAccount(TypedDict):
    id: str
    name: str
    balance: float
    type: str
    contributionBasis: int


class IgnidashContributionRuleAmount(TypedDict):
    type: str


class IgnidashContributionRule(TypedDict):
    id: str
    accountId: str
    rank: int
    amount: IgnidashContributionRuleAmount
    disabled: bool


class IgnidashPlanPayload(TypedDict):
    newPlanName: str
    isDefault: bool
    timeline: None
    incomes: list[object]
    expenses: list[object]
    debts: list[object]
    physicalAssets: list[object]
    accounts: list[IgnidashAccount]
    contributionRules: list[IgnidashContributionRule]
    baseContributionRule: dict[str, str]
    marketAssumptions: dict[str, float]
    taxSettings: dict[str, str]
    privacySettings: dict[str, bool]
    simulationSettings: dict[str, object]
    metadata: dict[str, object]


def build_ignidash_plan_payload(snapshot: PortfolioSnapshot) -> IgnidashPlanPayload:
    raw_accounts = snapshot.accounts or []

    accounts: list[IgnidashAccount] = []
    contribution_rules: list[IgnidashContributionRule] = []

    for index, account in enumerate(raw_accounts, start=1):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or f"account-{index}")
        account_name = str(account.get("name") or f"Account {index}")
        account_balance = float(account.get("balance") or 0.0)

        mapped: IgnidashAccount = {
            "id": f"gf-{account_id}",
            "name": account_name,
            "balance": account_balance,
            "type": _infer_account_type(account_name),
            "contributionBasis": 0,
        }
        accounts.append(mapped)
        contribution_rules.append(
            {
                "id": f"rule-{index}",
                "accountId": mapped["id"],
                "rank": index,
                "amount": {"type": "unlimited"},
                "disabled": False,
            }
        )

    if not accounts:
        accounts = [
            cast(
                IgnidashAccount,
                {
                    "id": "gf-default-taxable",
                    "name": "Taxable Brokerage",
                    "balance": snapshot.total_value_usd,
                    "type": "taxableBrokerage",
                    "contributionBasis": 0,
                },
            )
        ]
        contribution_rules = [
            cast(
                IgnidashContributionRule,
                {
                    "id": "rule-1",
                    "accountId": "gf-default-taxable",
                    "rank": 1,
                    "amount": {"type": "unlimited"},
                    "disabled": False,
                },
            )
        ]

    payload: IgnidashPlanPayload = {
        "newPlanName": "BuildWealth Imported Plan",
        "isDefault": False,
        "timeline": None,
        "incomes": [],
        "expenses": [],
        "debts": [],
        "physicalAssets": [],
        "accounts": accounts,
        "contributionRules": contribution_rules,
        "baseContributionRule": {"type": "save"},
        "marketAssumptions": {
            "stockReturn": 10.0,
            "stockYield": 3.5,
            "bondReturn": 5.0,
            "bondYield": 4.5,
            "cashReturn": 3.0,
            "inflationRate": 3.0,
        },
        "taxSettings": {"filingStatus": "single"},
        "privacySettings": {"isPrivate": True},
        "simulationSettings": {
            "simulationSeed": 9521,
            "simulationMode": "fixedReturns",
        },
        "metadata": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "ghostfolio",
            "snapshotValueUsd": snapshot.total_value_usd,
            "currency": snapshot.base_currency,
        },
    }
    return payload


class IgnidashExportStore:
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def write(self, payload: Mapping[str, object]) -> Path:
        generated = datetime.now(timezone.utc).strftime("ignidash-import-%Y%m%dT%H%M%SZ.json")
        path = self.export_dir / generated
        path.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
        return path
