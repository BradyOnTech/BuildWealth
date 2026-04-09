"""Local portfolio store — holdings, transactions, account tracking, and asset metadata."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from buildwealth_orchestrator.services.portfolio_performance import calculate_portfolio_performance

PORTFOLIO_STORE_SCHEMA_VERSION = 3
ACCOUNTS_SCHEMA_VERSION = 2
ASSET_METADATA_SCHEMA_VERSION = 1
DEFAULT_ACCOUNT_ID = "default"
DEFAULT_ACCOUNT_NAME = "Default Brokerage"
DEFAULT_CURRENCY = "USD"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


@dataclass
class Transaction:
    id: str
    date: str  # ISO date
    symbol: str
    action: Literal["BUY", "SELL", "DIVIDEND", "INTEREST", "FEE"]
    quantity: float
    unit_price: float
    fee: float = 0.0
    currency: str = DEFAULT_CURRENCY
    account: str = DEFAULT_ACCOUNT_ID
    note: str = ""
    lot_method: str = "FIFO"
    created_at: str = ""

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "symbol": self.symbol,
            "action": self.action,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "fee": self.fee,
            "currency": self.currency,
            "account": self.account,
            "note": self.note,
            "lot_method": self.lot_method,
            "created_at": self.created_at,
        }


class PortfolioStore:
    """Manages holdings and transactions via local JSON files."""

    def __init__(self, portfolio_dir: Path):
        self.portfolio_dir = portfolio_dir
        self.portfolio_dir.mkdir(parents=True, exist_ok=True)
        self._transactions_path = portfolio_dir / "transactions.json"
        self._holdings_path = portfolio_dir / "holdings.json"
        self._accounts_path = portfolio_dir / "accounts.json"
        self._asset_metadata_path = portfolio_dir / "asset_metadata.json"
        self._initialize()

    @staticmethod
    def _default_holdings_payload() -> dict[str, Any]:
        return {
            "schema_version": PORTFOLIO_STORE_SCHEMA_VERSION,
            "holdings": {},
            "holdings_by_symbol": {},
            "account_totals": {},
            "performance": {
                "start_date": None,
                "as_of": None,
                "period_days": 0,
                "net_contributions": 0.0,
                "ending_value": 0.0,
                "twr_return_pct": None,
                "twr_annualized_return_pct": None,
                "xirr_annualized_return_pct": None,
                "calculation_basis": "transaction_price_estimate",
            },
            "updated_at": _utc_now(),
        }

    @staticmethod
    def _default_accounts_payload() -> dict[str, Any]:
        return {
            "schema_version": ACCOUNTS_SCHEMA_VERSION,
            "default_account_id": DEFAULT_ACCOUNT_ID,
            "accounts": [
                {
                    "id": DEFAULT_ACCOUNT_ID,
                    "name": DEFAULT_ACCOUNT_NAME,
                    "type": "taxable",
                    "currency": DEFAULT_CURRENCY,
                    "created_at": _utc_now(),
                }
            ],
            "updated_at": _utc_now(),
        }

    @staticmethod
    def _default_asset_metadata_payload() -> dict[str, Any]:
        return {
            "schema_version": ASSET_METADATA_SCHEMA_VERSION,
            "symbols": {},
            "updated_at": _utc_now(),
        }

    def _initialize(self) -> None:
        if not self._accounts_path.exists():
            self._write_json(self._accounts_path, self._default_accounts_payload())
        else:
            self._read_accounts_payload()

        if not self._transactions_path.exists():
            self._write_json(self._transactions_path, [])
        self._migrate_transactions_payload()

        if not self._asset_metadata_path.exists():
            self._write_json(self._asset_metadata_path, self._default_asset_metadata_payload())
        else:
            self._read_asset_metadata_payload()

        if not self._holdings_path.exists():
            self._write_json(self._holdings_path, self._default_holdings_payload())
        else:
            self._read_holdings_payload()

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return slug or "account"

    def _generate_account_id(self, name: str, existing_ids: set[str]) -> str:
        base = self._slugify(name)
        candidate = base
        index = 1
        while candidate in existing_ids:
            index += 1
            candidate = f"{base}_{index}"
        return candidate

    def _migrate_accounts_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_accounts_payload()

        if isinstance(payload, list):
            payload = {"accounts": payload}

        if not isinstance(payload, dict):
            return default_payload

        raw_accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
        accounts: list[dict[str, Any]] = []
        existing_ids: set[str] = set()

        for raw_account in raw_accounts:
            if isinstance(raw_account, str):
                raw_account = {"name": raw_account}
            if not isinstance(raw_account, dict):
                continue

            name = str(raw_account.get("name") or "").strip() or "Account"
            requested_id = str(raw_account.get("id") or "").strip().lower() or None
            account_id = requested_id if requested_id and requested_id not in existing_ids else None
            if account_id is None:
                account_id = self._generate_account_id(name, existing_ids)
            existing_ids.add(account_id)

            accounts.append(
                {
                    "id": account_id,
                    "name": name,
                    "type": str(raw_account.get("type") or "taxable").strip().lower() or "taxable",
                    "currency": str(raw_account.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY,
                    "created_at": str(raw_account.get("created_at") or _utc_now()),
                }
            )

        if not accounts:
            accounts = default_payload["accounts"]
            existing_ids = {DEFAULT_ACCOUNT_ID}

        default_account_id = str(payload.get("default_account_id") or "").strip().lower() or accounts[0]["id"]
        if default_account_id not in existing_ids:
            default_account_id = accounts[0]["id"]

        return {
            "schema_version": ACCOUNTS_SCHEMA_VERSION,
            "default_account_id": default_account_id,
            "accounts": accounts,
            "updated_at": str(payload.get("updated_at") or _utc_now()),
        }

    def _read_accounts_payload(self) -> dict[str, Any]:
        original = self._read_json(self._accounts_path)
        payload = self._migrate_accounts_payload(original)
        if payload != original:
            self._write_json(self._accounts_path, payload)
        return payload

    @staticmethod
    def _find_account_in_payload(accounts_payload: dict[str, Any], account_ref: str | None) -> dict[str, Any] | None:
        accounts = accounts_payload.get("accounts", [])
        if not account_ref:
            target = accounts_payload.get("default_account_id")
            for account in accounts:
                if account.get("id") == target:
                    return account
            return accounts[0] if accounts else None

        raw = str(account_ref).strip()
        if not raw:
            return None

        lowered = raw.lower()

        for account in accounts:
            if str(account.get("id", "")).lower() == lowered:
                return account
        for account in accounts:
            if str(account.get("name", "")).strip().lower() == lowered:
                return account

        return None

    def _ensure_account(
        self,
        account_ref: str | None,
        *,
        account_type: str = "taxable",
        currency: str = DEFAULT_CURRENCY,
        create_if_missing: bool = True,
    ) -> dict[str, Any]:
        accounts_payload = self._read_accounts_payload()
        account = self._find_account_in_payload(accounts_payload, account_ref)
        if account is not None:
            return account

        if not create_if_missing:
            return self._find_account_in_payload(accounts_payload, None) or {
                "id": DEFAULT_ACCOUNT_ID,
                "name": DEFAULT_ACCOUNT_NAME,
                "type": "taxable",
                "currency": DEFAULT_CURRENCY,
            }

        raw = str(account_ref or "").strip()
        if not raw:
            raw = "Imported Account"

        account_id_hint = raw.lower() if re.fullmatch(r"[a-zA-Z0-9_-]+", raw) else None
        return self.add_account(
            name=raw,
            account_type=account_type,
            currency=currency,
            account_id=account_id_hint,
        )

    @staticmethod
    def _normalize_metadata_record(symbol: str, raw: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        symbol_normalized = PortfolioStore._normalize_symbol(symbol)
        merged = {**(existing or {}), **raw}

        def _clean(value: Any) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            return text if text else None

        return {
            "symbol": symbol_normalized,
            "name": _clean(merged.get("name") or merged.get("asset_name") or merged.get("long_name") or merged.get("short_name")),
            "asset_type": _clean(merged.get("asset_type") or merged.get("quote_type") or merged.get("type")),
            "asset_class": _clean(merged.get("asset_class")),
            "sector": _clean(merged.get("sector")),
            "region": _clean(merged.get("region") or merged.get("country") or merged.get("geography")),
            "updated_at": _utc_now(),
        }

    def _migrate_asset_metadata_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_asset_metadata_payload()

        if not isinstance(payload, dict):
            return default_payload

        raw_symbols: dict[str, Any]
        if "symbols" in payload and isinstance(payload.get("symbols"), dict):
            raw_symbols = payload.get("symbols", {})
        else:
            raw_symbols = payload

        symbols: dict[str, dict[str, Any]] = {}
        for symbol, raw in raw_symbols.items():
            if not isinstance(raw, dict):
                continue
            normalized_symbol = self._normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            symbols[normalized_symbol] = self._normalize_metadata_record(normalized_symbol, raw)

        return {
            "schema_version": ASSET_METADATA_SCHEMA_VERSION,
            "symbols": symbols,
            "updated_at": str(payload.get("updated_at") or _utc_now()),
        }

    def _read_asset_metadata_payload(self) -> dict[str, Any]:
        original = self._read_json(self._asset_metadata_path)
        payload = self._migrate_asset_metadata_payload(original)
        if payload != original:
            self._write_json(self._asset_metadata_path, payload)
        return payload

    def get_asset_metadata_map(self) -> dict[str, dict[str, Any]]:
        payload = self._read_asset_metadata_payload()
        symbols = payload.get("symbols", {})
        return symbols if isinstance(symbols, dict) else {}

    def upsert_asset_metadata(self, symbol: str, metadata: dict[str, Any]) -> dict[str, Any]:
        symbol_normalized = self._normalize_symbol(symbol)
        if not symbol_normalized:
            return {}

        payload = self._read_asset_metadata_payload()
        symbols = payload.setdefault("symbols", {})
        existing = symbols.get(symbol_normalized)
        updated = self._normalize_metadata_record(symbol_normalized, metadata, existing=existing)
        symbols[symbol_normalized] = updated
        payload["updated_at"] = _utc_now()
        self._write_json(self._asset_metadata_path, payload)
        return updated

    def upsert_asset_metadata_bulk(self, metadata_by_symbol: dict[str, dict[str, Any]]) -> int:
        if not metadata_by_symbol:
            return 0

        payload = self._read_asset_metadata_payload()
        symbols = payload.setdefault("symbols", {})
        changed = 0

        for symbol, metadata in metadata_by_symbol.items():
            symbol_normalized = self._normalize_symbol(symbol)
            if not symbol_normalized or not isinstance(metadata, dict):
                continue
            existing = symbols.get(symbol_normalized)
            updated = self._normalize_metadata_record(symbol_normalized, metadata, existing=existing)
            if updated != existing:
                symbols[symbol_normalized] = updated
                changed += 1

        if changed:
            payload["updated_at"] = _utc_now()
            self._write_json(self._asset_metadata_path, payload)

        return changed

    def _migrate_transactions_payload(self) -> list[dict[str, Any]]:
        raw_payload = self._read_json(self._transactions_path)
        if not isinstance(raw_payload, list):
            self._write_json(self._transactions_path, [])
            return []

        migrated: list[dict[str, Any]] = []

        for raw in raw_payload:
            if not isinstance(raw, dict):
                continue

            symbol = self._normalize_symbol(raw.get("symbol"))
            if not symbol:
                continue

            action = str(raw.get("action") or "BUY").strip().upper() or "BUY"
            account = self._ensure_account(str(raw.get("account") or DEFAULT_ACCOUNT_ID), create_if_missing=True)

            migrated.append(
                {
                    "id": str(raw.get("id") or str(uuid.uuid4())[:8]),
                    "date": str(raw.get("date") or ""),
                    "symbol": symbol,
                    "action": action,
                    "quantity": _safe_float(raw.get("quantity"), 0.0),
                    "unit_price": _safe_float(raw.get("unit_price"), 0.0),
                    "fee": _safe_float(raw.get("fee"), 0.0),
                    "currency": str(raw.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY,
                    "account": str(account.get("id") or DEFAULT_ACCOUNT_ID),
                    "note": str(raw.get("note") or ""),
                    "lot_method": str(raw.get("lot_method") or "FIFO").strip().upper() or "FIFO",
                    "created_at": str(raw.get("created_at") or _utc_now()),
                }
            )

        if migrated != raw_payload:
            self._write_json(self._transactions_path, migrated)

        return migrated

    def _migrate_holdings_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_holdings_payload()
        if not isinstance(payload, dict):
            return default_payload

        holdings_input = payload.get("holdings") if isinstance(payload.get("holdings"), dict) else {}
        migrated_holdings: dict[str, dict[str, Any]] = {}
        total_value = 0.0
        total_cost = 0.0

        for holding_key, raw_holding in holdings_input.items():
            if not isinstance(raw_holding, dict):
                continue

            symbol = self._normalize_symbol(raw_holding.get("symbol") or str(holding_key).split(":")[-1])
            if not symbol:
                continue

            account_ref = str(
                raw_holding.get("account")
                or raw_holding.get("account_id")
                or (str(holding_key).split(":")[0] if ":" in str(holding_key) else DEFAULT_ACCOUNT_ID)
            )
            account = self._ensure_account(account_ref, create_if_missing=True)
            account_id = str(account.get("id") or DEFAULT_ACCOUNT_ID)
            scoped_key = f"{account_id}:{symbol}"

            quantity = _safe_float(raw_holding.get("quantity"), 0.0)
            cost_basis = _safe_float(raw_holding.get("cost_basis"), 0.0)
            avg_cost = raw_holding.get("avg_cost_per_share")
            avg_cost_per_share = _safe_float(avg_cost, round(cost_basis / quantity, 8) if quantity > 0 else 0.0)

            current_price = raw_holding.get("current_price")
            current_price_value = _safe_float(current_price, None) if current_price is not None else None
            current_value = raw_holding.get("current_value")
            current_value_value = _safe_float(current_value, None) if current_value is not None else None
            if current_value_value is None and current_price_value is not None:
                current_value_value = round(quantity * current_price_value, 2)

            lots: list[dict[str, Any]] = []
            raw_lots = raw_holding.get("lots") if isinstance(raw_holding.get("lots"), list) else []
            if raw_lots:
                for index, lot in enumerate(raw_lots, start=1):
                    if not isinstance(lot, dict):
                        continue
                    lot_qty = _safe_float(lot.get("quantity"), 0.0)
                    lot_remaining = _safe_float(lot.get("remaining_quantity"), lot_qty)
                    unit_cost = _safe_float(lot.get("unit_cost"), avg_cost_per_share)
                    if lot_remaining <= 0:
                        continue
                    lots.append(
                        {
                            "lot_id": str(lot.get("lot_id") or f"{scoped_key}-lot-{index}"),
                            "acquired_date": str(lot.get("acquired_date") or raw_holding.get("updated_at") or ""),
                            "quantity": round(max(lot_qty, lot_remaining), 8),
                            "remaining_quantity": round(lot_remaining, 8),
                            "unit_cost": round(unit_cost, 8),
                        }
                    )

            if not lots and quantity > 0:
                lots = [
                    {
                        "lot_id": f"{scoped_key}-legacy-1",
                        "acquired_date": str(raw_holding.get("acquired_date") or payload.get("updated_at") or ""),
                        "quantity": round(quantity, 8),
                        "remaining_quantity": round(quantity, 8),
                        "unit_cost": round(avg_cost_per_share, 8),
                    }
                ]

            holding_record = {
                "symbol": symbol,
                "account": account_id,
                "quantity": round(quantity, 8),
                "cost_basis": round(cost_basis, 2),
                "avg_cost_per_share": round(avg_cost_per_share, 8),
                "cost_basis_method": str(raw_holding.get("cost_basis_method") or "FIFO").strip().upper() or "FIFO",
                "dividends_received": round(_safe_float(raw_holding.get("dividends_received"), 0.0), 2),
                "realized_gains": round(_safe_float(raw_holding.get("realized_gains"), 0.0), 2),
                "fees_paid": round(_safe_float(raw_holding.get("fees_paid"), 0.0), 2),
                "lots": lots,
                "lot_count": len(lots),
                "current_price": round(current_price_value, 4) if current_price_value is not None else None,
                "current_value": round(current_value_value, 2) if current_value_value is not None else None,
                "name": raw_holding.get("name"),
                "asset_type": raw_holding.get("asset_type"),
                "asset_class": raw_holding.get("asset_class"),
                "sector": raw_holding.get("sector"),
                "region": raw_holding.get("region"),
            }

            migrated_holdings[scoped_key] = holding_record

            if current_value_value is not None:
                total_value += float(current_value_value)
            total_cost += float(cost_basis)

        performance_input = payload.get("performance") if isinstance(payload.get("performance"), dict) else {}
        performance = {
            **default_payload["performance"],
            **performance_input,
        }
        if performance.get("ending_value") in (None, 0, 0.0) and total_value > 0:
            performance["ending_value"] = round(total_value, 2)
        if performance.get("as_of") is None:
            performance["as_of"] = payload.get("prices_updated_at")

        total_value = float(payload.get("total_value", total_value) or total_value)
        total_cost = float(payload.get("total_cost_basis", total_cost) or total_cost)

        migrated = {
            **default_payload,
            **payload,
            "schema_version": PORTFOLIO_STORE_SCHEMA_VERSION,
            "holdings": migrated_holdings,
            "holdings_by_symbol": self._summarize_holdings_by_symbol(migrated_holdings),
            "account_totals": self._summarize_account_totals(migrated_holdings),
            "performance": performance,
            "total_value": round(total_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "net_performance": round(
                _safe_float(payload.get("net_performance"), total_value - total_cost),
                2,
            ),
            "net_performance_pct": (
                round(
                    _safe_float(
                        payload.get("net_performance_pct"),
                        ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0.0,
                    ),
                    2,
                )
                if total_cost > 0
                else 0.0
            ),
            "updated_at": payload.get("updated_at") or default_payload["updated_at"],
        }
        return migrated

    def _read_holdings_payload(self) -> dict[str, Any]:
        original = self._read_json(self._holdings_path)
        payload = self._migrate_holdings_payload(original)
        if payload != original:
            self._write_json(self._holdings_path, payload)
        return payload

    def _summarize_holdings_by_symbol(self, holdings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = {}

        for holding in holdings.values():
            symbol = self._normalize_symbol(holding.get("symbol"))
            if not symbol:
                continue

            quantity = _safe_float(holding.get("quantity"), 0.0)
            cost_basis = _safe_float(holding.get("cost_basis"), 0.0)
            current_value = _safe_float(holding.get("current_value"), 0.0)
            current_price = holding.get("current_price")

            bucket = summary.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "quantity": 0.0,
                    "cost_basis": 0.0,
                    "current_value": 0.0,
                    "dividends_received": 0.0,
                    "realized_gains": 0.0,
                    "fees_paid": 0.0,
                    "accounts": [],
                    "current_price": None,
                    "name": holding.get("name"),
                    "asset_type": holding.get("asset_type"),
                    "asset_class": holding.get("asset_class"),
                    "sector": holding.get("sector"),
                    "region": holding.get("region"),
                },
            )

            bucket["quantity"] += quantity
            bucket["cost_basis"] += cost_basis
            bucket["current_value"] += current_value
            bucket["dividends_received"] += _safe_float(holding.get("dividends_received"), 0.0)
            bucket["realized_gains"] += _safe_float(holding.get("realized_gains"), 0.0)
            bucket["fees_paid"] += _safe_float(holding.get("fees_paid"), 0.0)
            account_id = str(holding.get("account") or "")
            if account_id and account_id not in bucket["accounts"]:
                bucket["accounts"].append(account_id)

            if current_price is not None and quantity > 0:
                existing_price = bucket.get("current_price")
                if existing_price is None:
                    bucket["current_price"] = float(current_price)
                else:
                    prev_qty = max(bucket["quantity"] - quantity, 0.0)
                    weighted = ((prev_qty * float(existing_price)) + (quantity * float(current_price))) / max(bucket["quantity"], 1e-9)
                    bucket["current_price"] = round(weighted, 4)

            for field in ("name", "asset_type", "asset_class", "sector", "region"):
                if not bucket.get(field) and holding.get(field):
                    bucket[field] = holding.get(field)

        for symbol, bucket in summary.items():
            qty = _safe_float(bucket.get("quantity"), 0.0)
            cost_basis = _safe_float(bucket.get("cost_basis"), 0.0)
            bucket["quantity"] = round(qty, 8)
            bucket["cost_basis"] = round(cost_basis, 2)
            bucket["current_value"] = round(_safe_float(bucket.get("current_value"), 0.0), 2)
            bucket["avg_cost_per_share"] = round(cost_basis / qty, 8) if qty > 0 else 0.0
            bucket["dividends_received"] = round(_safe_float(bucket.get("dividends_received"), 0.0), 2)
            bucket["realized_gains"] = round(_safe_float(bucket.get("realized_gains"), 0.0), 2)
            bucket["fees_paid"] = round(_safe_float(bucket.get("fees_paid"), 0.0), 2)
            bucket["position_count"] = len(bucket.get("accounts", []))
            if bucket.get("current_price") is not None:
                bucket["current_price"] = round(float(bucket["current_price"]), 4)

        return summary

    def _summarize_account_totals(self, holdings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        accounts_payload = self._read_accounts_payload()
        accounts_by_id = {
            str(account.get("id")): account
            for account in accounts_payload.get("accounts", [])
            if isinstance(account, dict) and account.get("id")
        }

        totals: dict[str, dict[str, Any]] = {}

        for holding in holdings.values():
            account_id = str(holding.get("account") or DEFAULT_ACCOUNT_ID)
            account = accounts_by_id.get(account_id, {})
            bucket = totals.setdefault(
                account_id,
                {
                    "account_id": account_id,
                    "name": account.get("name") or account_id,
                    "type": account.get("type") or "taxable",
                    "currency": account.get("currency") or DEFAULT_CURRENCY,
                    "market_value": 0.0,
                    "cost_basis": 0.0,
                    "holdings_count": 0,
                },
            )

            bucket["market_value"] += _safe_float(holding.get("current_value"), 0.0)
            bucket["cost_basis"] += _safe_float(holding.get("cost_basis"), 0.0)
            bucket["holdings_count"] += 1

        for account_id, bucket in totals.items():
            bucket["market_value"] = round(_safe_float(bucket.get("market_value"), 0.0), 2)
            bucket["cost_basis"] = round(_safe_float(bucket.get("cost_basis"), 0.0), 2)
            bucket["net_performance"] = round(bucket["market_value"] - bucket["cost_basis"], 2)
            if bucket["cost_basis"] > 0:
                bucket["net_performance_pct"] = round((bucket["net_performance"] / bucket["cost_basis"]) * 100, 2)
            else:
                bucket["net_performance_pct"] = 0.0

        return totals

    def _apply_metadata(self, symbol: str, base: dict[str, Any], metadata_map: dict[str, dict[str, Any]]) -> None:
        metadata = metadata_map.get(symbol) if isinstance(metadata_map, dict) else None
        if not isinstance(metadata, dict):
            return
        for field in ("name", "asset_type", "asset_class", "sector", "region"):
            if metadata.get(field) is not None:
                base[field] = metadata.get(field)

    def _finalize_holdings_payload(
        self,
        *,
        holdings: dict[str, dict[str, Any]],
        transactions: list[dict[str, Any]],
        prices_updated_at: str | None = None,
    ) -> dict[str, Any]:
        total_value = 0.0
        total_cost = 0.0

        for holding in holdings.values():
            current_price = holding.get("current_price")
            if current_price is not None:
                holding["current_value"] = round(_safe_float(holding.get("quantity"), 0.0) * float(current_price), 2)
            if holding.get("current_value") is not None:
                total_value += float(holding["current_value"])
            total_cost += float(holding.get("cost_basis", 0) or 0)

        payload = self._default_holdings_payload()
        payload["holdings"] = holdings
        payload["holdings_by_symbol"] = self._summarize_holdings_by_symbol(holdings)
        payload["account_totals"] = self._summarize_account_totals(holdings)
        payload["total_value"] = round(total_value, 2)
        payload["total_cost_basis"] = round(total_cost, 2)
        payload["net_performance"] = round(total_value - total_cost, 2)
        payload["net_performance_pct"] = round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0
        payload["performance"] = calculate_portfolio_performance(
            transactions=transactions,
            holdings=holdings,
            as_of=prices_updated_at or _utc_now(),
        )
        payload["prices_updated_at"] = prices_updated_at
        payload["asset_metadata_updated_at"] = self._read_asset_metadata_payload().get("updated_at")
        payload["updated_at"] = _utc_now()
        return payload

    def _read_transactions(self) -> list[dict[str, Any]]:
        payload = self._read_json(self._transactions_path)
        return payload if isinstance(payload, list) else []

    # ---- Transactions ----

    def list_transactions(self, limit: int = 200) -> list[dict[str, Any]]:
        txns = self._read_transactions()
        txns.sort(key=lambda t: (t.get("date", ""), t.get("created_at", ""), t.get("id", "")), reverse=True)
        return txns[:limit]

    def add_transaction(
        self,
        *,
        date: str,
        symbol: str,
        action: str,
        quantity: float,
        unit_price: float,
        fee: float = 0.0,
        account: str = DEFAULT_ACCOUNT_ID,
        currency: str = DEFAULT_CURRENCY,
        note: str = "",
        lot_method: str = "FIFO",
        name: str | None = None,
        asset_type: str | None = None,
        asset_class: str | None = None,
        sector: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        account_record = self._ensure_account(account, create_if_missing=True)
        normalized_symbol = self._normalize_symbol(symbol)

        txn = Transaction(
            id=str(uuid.uuid4())[:8],
            date=str(date),
            symbol=normalized_symbol,
            action=str(action).upper().strip(),
            quantity=float(quantity),
            unit_price=float(unit_price),
            fee=float(fee),
            currency=str(currency).strip().upper() or DEFAULT_CURRENCY,
            account=str(account_record.get("id") or DEFAULT_ACCOUNT_ID),
            note=note,
            lot_method=str(lot_method).upper().strip() or "FIFO",
            created_at=_utc_now(),
        )

        txns = self._read_transactions()
        txns.append(txn.to_dict())
        self._write_json(self._transactions_path, txns)

        metadata_payload = {
            "name": name,
            "asset_type": asset_type,
            "asset_class": asset_class,
            "sector": sector,
            "region": region,
        }
        if any(value for value in metadata_payload.values()):
            self.upsert_asset_metadata(normalized_symbol, metadata_payload)

        self._rebuild_holdings()
        return txn.to_dict()

    def add_transactions_bulk(self, items: list[dict[str, Any]]) -> int:
        txns = self._read_transactions()
        count = 0
        metadata_updates: dict[str, dict[str, Any]] = {}

        for item in items:
            account_ref = (
                item.get("account")
                or item.get("account_id")
                or item.get("account_name")
                or DEFAULT_ACCOUNT_ID
            )
            account_record = self._ensure_account(str(account_ref), create_if_missing=True)
            symbol = self._normalize_symbol(item.get("symbol"))
            if not symbol:
                continue

            txn = Transaction(
                id=str(uuid.uuid4())[:8],
                date=str(item.get("date", "")),
                symbol=symbol,
                action=str(item.get("action", "BUY")).upper().strip() or "BUY",
                quantity=float(item.get("quantity", 0)),
                unit_price=float(item.get("unit_price", 0)),
                fee=float(item.get("fee", 0)),
                currency=str(item.get("currency", DEFAULT_CURRENCY)).strip().upper() or DEFAULT_CURRENCY,
                account=str(account_record.get("id") or DEFAULT_ACCOUNT_ID),
                note=str(item.get("note", "")),
                lot_method=str(item.get("lot_method", "FIFO")).upper().strip() or "FIFO",
                created_at=_utc_now(),
            )
            txns.append(txn.to_dict())
            count += 1

            metadata_payload = {
                "name": item.get("name") or item.get("asset_name"),
                "asset_type": item.get("asset_type"),
                "asset_class": item.get("asset_class"),
                "sector": item.get("sector"),
                "region": item.get("region"),
            }
            if any(value for value in metadata_payload.values()):
                metadata_updates[symbol] = {**metadata_updates.get(symbol, {}), **metadata_payload}

        self._write_json(self._transactions_path, txns)
        if metadata_updates:
            self.upsert_asset_metadata_bulk(metadata_updates)
        self._rebuild_holdings()
        return count

    def delete_transaction(self, transaction_id: str) -> bool:
        txns = self._read_transactions()
        before = len(txns)
        txns = [t for t in txns if t.get("id") != transaction_id]
        if len(txns) == before:
            return False
        self._write_json(self._transactions_path, txns)
        self._rebuild_holdings()
        return True

    # ---- Holdings ----

    def get_holdings(self) -> dict[str, Any]:
        payload = self._read_holdings_payload()
        payload["accounts"] = self.get_accounts()
        return payload

    @staticmethod
    def _lot_sort_key(lot: dict[str, Any]) -> tuple[str, str]:
        return str(lot.get("acquired_date") or ""), str(lot.get("lot_id") or "")

    def _consume_lots_fifo(self, lots: list[dict[str, Any]], quantity_to_sell: float) -> float:
        remaining = quantity_to_sell
        consumed_cost = 0.0

        lots.sort(key=self._lot_sort_key)

        for lot in lots:
            lot_remaining = _safe_float(lot.get("remaining_quantity"), 0.0)
            if lot_remaining <= 0:
                continue
            take = min(lot_remaining, remaining)
            if take <= 0:
                continue

            unit_cost = _safe_float(lot.get("unit_cost"), 0.0)
            consumed_cost += take * unit_cost
            lot["remaining_quantity"] = round(lot_remaining - take, 8)
            remaining -= take

            if remaining <= 1e-9:
                break

        return consumed_cost

    def _rebuild_holdings(self) -> dict[str, Any]:
        """Recompute account-scoped holdings from transaction history using lot-aware accounting."""
        txns = self._read_transactions()

        try:
            existing_holdings = self._read_holdings_payload().get("holdings", {})
        except Exception:
            existing_holdings = {}

        metadata_map = self.get_asset_metadata_map()

        positions: dict[str, dict[str, Any]] = {}
        sorted_txns = sorted(
            txns,
            key=lambda t: (str(t.get("date", "")), str(t.get("created_at", "")), str(t.get("id", ""))),
        )

        for txn in sorted_txns:
            symbol = self._normalize_symbol(txn.get("symbol"))
            if not symbol:
                continue

            account_record = self._ensure_account(str(txn.get("account") or DEFAULT_ACCOUNT_ID), create_if_missing=True)
            account_id = str(account_record.get("id") or DEFAULT_ACCOUNT_ID)
            key = f"{account_id}:{symbol}"

            action = str(txn.get("action") or "").upper().strip()
            quantity = abs(_safe_float(txn.get("quantity"), 0.0))
            price = abs(_safe_float(txn.get("unit_price"), 0.0))
            fee = abs(_safe_float(txn.get("fee"), 0.0))
            lot_method = str(txn.get("lot_method") or "FIFO").strip().upper() or "FIFO"

            if key not in positions:
                preserved = existing_holdings.get(key, {}) if isinstance(existing_holdings, dict) else {}
                positions[key] = {
                    "symbol": symbol,
                    "account": account_id,
                    "quantity": 0.0,
                    "dividends": 0.0,
                    "realized_gains": 0.0,
                    "fees": 0.0,
                    "lots": [],
                    "cost_basis_method": str(preserved.get("cost_basis_method") or lot_method or "FIFO").upper(),
                    "current_price": preserved.get("current_price"),
                }

            position = positions[key]

            if action == "BUY":
                if quantity <= 0:
                    continue
                unit_cost = price + (fee / quantity if quantity > 0 else 0.0)
                position["quantity"] += quantity
                position["lots"].append(
                    {
                        "lot_id": str(txn.get("id") or f"{key}-{len(position['lots']) + 1}"),
                        "acquired_date": str(txn.get("date") or ""),
                        "quantity": round(quantity, 8),
                        "remaining_quantity": round(quantity, 8),
                        "unit_cost": round(unit_cost, 8),
                    }
                )
            elif action == "SELL":
                available_qty = sum(_safe_float(lot.get("remaining_quantity"), 0.0) for lot in position["lots"])
                sell_qty = min(quantity, available_qty)
                if sell_qty <= 0:
                    continue

                consumed_cost = self._consume_lots_fifo(position["lots"], sell_qty)
                proceeds = (sell_qty * price) - fee
                realized_gain = proceeds - consumed_cost

                position["quantity"] = max(position["quantity"] - sell_qty, 0.0)
                position["realized_gains"] += realized_gain
                position["fees"] += fee
            elif action in {"DIVIDEND", "INTEREST"}:
                income = (quantity * price) - fee
                position["dividends"] += income
            elif action == "FEE":
                charge = fee if fee > 0 else quantity * price
                position["fees"] += abs(charge)
                position["realized_gains"] -= abs(charge)

        holdings: dict[str, dict[str, Any]] = {}
        for key, position in positions.items():
            quantity = _safe_float(position.get("quantity"), 0.0)
            if quantity <= 1e-6:
                continue

            remaining_lots = [
                {
                    "lot_id": str(lot.get("lot_id") or ""),
                    "acquired_date": str(lot.get("acquired_date") or ""),
                    "quantity": round(_safe_float(lot.get("quantity"), 0.0), 8),
                    "remaining_quantity": round(_safe_float(lot.get("remaining_quantity"), 0.0), 8),
                    "unit_cost": round(_safe_float(lot.get("unit_cost"), 0.0), 8),
                }
                for lot in position.get("lots", [])
                if _safe_float(lot.get("remaining_quantity"), 0.0) > 1e-9
            ]

            cost_basis = sum(_safe_float(lot.get("remaining_quantity"), 0.0) * _safe_float(lot.get("unit_cost"), 0.0) for lot in remaining_lots)
            avg_cost_per_share = (cost_basis / quantity) if quantity > 0 else 0.0

            current_price = position.get("current_price")
            current_value = round(quantity * _safe_float(current_price), 2) if current_price is not None else None

            holding = {
                "symbol": position["symbol"],
                "account": position["account"],
                "quantity": round(quantity, 8),
                "cost_basis": round(cost_basis, 2),
                "avg_cost_per_share": round(avg_cost_per_share, 8),
                "cost_basis_method": str(position.get("cost_basis_method") or "FIFO"),
                "dividends_received": round(_safe_float(position.get("dividends"), 0.0), 2),
                "realized_gains": round(_safe_float(position.get("realized_gains"), 0.0), 2),
                "fees_paid": round(_safe_float(position.get("fees"), 0.0), 2),
                "lots": remaining_lots,
                "lot_count": len(remaining_lots),
                "current_price": round(_safe_float(current_price), 4) if current_price is not None else None,
                "current_value": current_value,
                "name": None,
                "asset_type": None,
                "asset_class": None,
                "sector": None,
                "region": None,
            }

            self._apply_metadata(position["symbol"], holding, metadata_map)
            holdings[key] = holding

        try:
            prices_updated_at = self._read_holdings_payload().get("prices_updated_at")
        except Exception:
            prices_updated_at = None

        data = self._finalize_holdings_payload(
            holdings=holdings,
            transactions=txns,
            prices_updated_at=prices_updated_at,
        )
        self._write_json(self._holdings_path, data)
        return data

    def update_prices(self, prices: dict[str, float]) -> dict[str, Any]:
        """Update current prices for holdings and compute values."""
        data = self._read_holdings_payload()
        holdings = data.get("holdings", {})

        for holding in holdings.values():
            symbol = self._normalize_symbol(holding.get("symbol"))
            if not symbol:
                continue
            price = prices.get(symbol)
            if price is not None:
                holding["current_price"] = round(float(price), 4)

        data = self._finalize_holdings_payload(
            holdings=holdings,
            transactions=self._read_transactions(),
            prices_updated_at=_utc_now(),
        )
        self._write_json(self._holdings_path, data)
        return data

    # ---- Accounts ----

    def get_accounts(self) -> list[dict[str, Any]]:
        data = self._read_accounts_payload()
        accounts = data.get("accounts", [])
        return accounts if isinstance(accounts, list) else []

    def account_ids_by_name(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for account in self.get_accounts():
            if not isinstance(account, dict):
                continue
            account_id = str(account.get("id") or "").strip()
            name = str(account.get("name") or "").strip()
            if account_id:
                mapping[account_id.lower()] = account_id
            if name and account_id:
                mapping[name.lower()] = account_id
        return mapping

    def ensure_account(self, account_ref: str, account_type: str = "taxable", currency: str = DEFAULT_CURRENCY) -> dict[str, Any]:
        return self._ensure_account(account_ref, account_type=account_type, currency=currency, create_if_missing=True)

    def add_account(
        self,
        name: str,
        account_type: str = "taxable",
        currency: str = DEFAULT_CURRENCY,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._read_accounts_payload()
        accounts = payload.setdefault("accounts", [])

        normalized_name = str(name).strip() or "Account"

        for account in accounts:
            if str(account.get("name", "")).strip().lower() == normalized_name.lower():
                return account
            if account_id and str(account.get("id", "")).strip().lower() == account_id.strip().lower():
                return account

        existing_ids = {
            str(account.get("id", "")).strip().lower()
            for account in accounts
            if isinstance(account, dict)
        }

        requested_id = str(account_id or "").strip().lower() or None
        final_id = requested_id if requested_id and requested_id not in existing_ids else self._generate_account_id(normalized_name, existing_ids)

        account = {
            "id": final_id,
            "name": normalized_name,
            "type": str(account_type).strip().lower() or "taxable",
            "currency": str(currency).strip().upper() or DEFAULT_CURRENCY,
            "created_at": _utc_now(),
        }
        accounts.append(account)
        payload["updated_at"] = _utc_now()
        self._write_json(self._accounts_path, payload)
        return account
