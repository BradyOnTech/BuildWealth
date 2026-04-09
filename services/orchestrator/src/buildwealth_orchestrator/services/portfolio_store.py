"""Local portfolio store — holdings, transactions, and account tracking.

Replaces Ghostfolio as the holdings/transaction ledger with a simple
JSON-based store suitable for single-user local operation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Transaction:
    id: str
    date: str  # ISO date
    symbol: str
    action: Literal["BUY", "SELL", "DIVIDEND"]
    quantity: float
    unit_price: float
    fee: float = 0.0
    currency: str = "USD"
    account: str = "default"
    note: str = ""
    created_at: str = ""

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "date": self.date, "symbol": self.symbol,
            "action": self.action, "quantity": self.quantity,
            "unit_price": self.unit_price, "fee": self.fee,
            "currency": self.currency, "account": self.account,
            "note": self.note, "created_at": self.created_at,
        }


class PortfolioStore:
    """Manages holdings and transactions via local JSON files."""

    def __init__(self, portfolio_dir: Path):
        self.portfolio_dir = portfolio_dir
        self.portfolio_dir.mkdir(parents=True, exist_ok=True)
        self._transactions_path = portfolio_dir / "transactions.json"
        self._holdings_path = portfolio_dir / "holdings.json"
        self._accounts_path = portfolio_dir / "accounts.json"
        self._initialize()

    def _initialize(self) -> None:
        if not self._transactions_path.exists():
            self._write_json(self._transactions_path, [])
        if not self._holdings_path.exists():
            self._write_json(self._holdings_path, {"holdings": {}, "updated_at": _utc_now()})
        if not self._accounts_path.exists():
            self._write_json(self._accounts_path, {"accounts": [{"name": "default", "type": "taxable"}]})

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- Transactions ----

    def list_transactions(self, limit: int = 200) -> list[dict[str, Any]]:
        txns = self._read_json(self._transactions_path)
        txns.sort(key=lambda t: t.get("date", ""), reverse=True)
        return txns[:limit]

    def add_transaction(
        self, *, date: str, symbol: str, action: str, quantity: float,
        unit_price: float, fee: float = 0.0, account: str = "default",
        currency: str = "USD", note: str = "",
    ) -> dict[str, Any]:
        txn = Transaction(
            id=str(uuid.uuid4())[:8],
            date=date, symbol=symbol.upper().strip(),
            action=action.upper().strip(),
            quantity=quantity, unit_price=unit_price, fee=fee,
            currency=currency, account=account, note=note,
            created_at=_utc_now(),
        )
        txns = self._read_json(self._transactions_path)
        txns.append(txn.to_dict())
        self._write_json(self._transactions_path, txns)
        self._rebuild_holdings()
        return txn.to_dict()

    def add_transactions_bulk(self, items: list[dict[str, Any]]) -> int:
        txns = self._read_json(self._transactions_path)
        count = 0
        for item in items:
            txn = Transaction(
                id=str(uuid.uuid4())[:8],
                date=item.get("date", ""),
                symbol=str(item.get("symbol", "")).upper().strip(),
                action=str(item.get("action", "BUY")).upper().strip(),
                quantity=float(item.get("quantity", 0)),
                unit_price=float(item.get("unit_price", 0)),
                fee=float(item.get("fee", 0)),
                currency=item.get("currency", "USD"),
                account=item.get("account", "default"),
                note=item.get("note", ""),
                created_at=_utc_now(),
            )
            txns.append(txn.to_dict())
            count += 1
        self._write_json(self._transactions_path, txns)
        self._rebuild_holdings()
        return count

    def delete_transaction(self, transaction_id: str) -> bool:
        txns = self._read_json(self._transactions_path)
        before = len(txns)
        txns = [t for t in txns if t["id"] != transaction_id]
        if len(txns) == before:
            return False
        self._write_json(self._transactions_path, txns)
        self._rebuild_holdings()
        return True

    # ---- Holdings ----

    def get_holdings(self) -> dict[str, Any]:
        return self._read_json(self._holdings_path)

    def _rebuild_holdings(self) -> dict[str, Any]:
        """Recompute holdings from transaction history."""
        txns = self._read_json(self._transactions_path)
        positions: dict[str, dict[str, float]] = {}

        for txn in sorted(txns, key=lambda t: t.get("date", "")):
            sym = txn["symbol"]
            action = txn["action"]
            qty = float(txn.get("quantity", 0))
            price = float(txn.get("unit_price", 0))

            if sym not in positions:
                positions[sym] = {"quantity": 0.0, "cost_basis": 0.0, "dividends": 0.0}

            if action == "BUY":
                positions[sym]["cost_basis"] += qty * price
                positions[sym]["quantity"] += qty
            elif action == "SELL":
                if positions[sym]["quantity"] > 0:
                    avg_cost = positions[sym]["cost_basis"] / positions[sym]["quantity"]
                    sell_qty = min(qty, positions[sym]["quantity"])
                    positions[sym]["cost_basis"] -= sell_qty * avg_cost
                    positions[sym]["quantity"] -= sell_qty
            elif action == "DIVIDEND":
                positions[sym]["dividends"] += qty * price

        # Remove zero-quantity positions
        holdings = {}
        for sym, pos in positions.items():
            if pos["quantity"] > 0.001:
                holdings[sym] = {
                    "symbol": sym,
                    "quantity": round(pos["quantity"], 6),
                    "cost_basis": round(pos["cost_basis"], 2),
                    "avg_cost_per_share": round(pos["cost_basis"] / pos["quantity"], 4) if pos["quantity"] > 0 else 0,
                    "dividends_received": round(pos["dividends"], 2),
                    "current_price": None,
                    "current_value": None,
                }

        data = {"holdings": holdings, "updated_at": _utc_now()}
        self._write_json(self._holdings_path, data)
        return data

    def update_prices(self, prices: dict[str, float]) -> dict[str, Any]:
        """Update current prices for holdings and compute values."""
        data = self._read_json(self._holdings_path)
        holdings = data.get("holdings", {})

        total_value = 0.0
        total_cost = 0.0

        for sym, holding in holdings.items():
            price = prices.get(sym)
            if price is not None:
                holding["current_price"] = round(price, 4)
                holding["current_value"] = round(holding["quantity"] * price, 2)
            else:
                holding["current_value"] = None
            if holding.get("current_value") is not None:
                total_value += holding["current_value"]
            total_cost += holding.get("cost_basis", 0)

        data["holdings"] = holdings
        data["total_value"] = round(total_value, 2)
        data["total_cost_basis"] = round(total_cost, 2)
        data["net_performance"] = round(total_value - total_cost, 2)
        data["net_performance_pct"] = round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0
        data["prices_updated_at"] = _utc_now()
        data["updated_at"] = _utc_now()
        self._write_json(self._holdings_path, data)
        return data

    # ---- Accounts ----

    def get_accounts(self) -> list[dict[str, Any]]:
        data = self._read_json(self._accounts_path)
        return data.get("accounts", [])

    def add_account(self, name: str, account_type: str = "taxable") -> dict[str, Any]:
        data = self._read_json(self._accounts_path)
        account = {"name": name, "type": account_type}
        data.setdefault("accounts", []).append(account)
        self._write_json(self._accounts_path, data)
        return account
