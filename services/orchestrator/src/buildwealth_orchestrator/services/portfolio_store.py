"""Local portfolio store — holdings, transactions, account tracking, and asset metadata."""

from __future__ import annotations

# Exchange-rate payload and rate-normalization flow adapted from Ghostfolio (MIT):
# apps/api/src/services/exchange-rate-data/exchange-rate-data.service.ts

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from buildwealth_orchestrator.services.portfolio_performance import calculate_portfolio_performance

PORTFOLIO_STORE_SCHEMA_VERSION = 6
ACCOUNTS_SCHEMA_VERSION = 2
ASSET_METADATA_SCHEMA_VERSION = 1
COST_BASIS_METHODS_SCHEMA_VERSION = 1
MANUAL_PRICES_SCHEMA_VERSION = 1
FX_RATES_SCHEMA_VERSION = 1
DEFAULT_ACCOUNT_ID = "default"
DEFAULT_ACCOUNT_NAME = "Default Brokerage"
DEFAULT_CURRENCY = "USD"
VALID_COST_BASIS_METHODS = {"FIFO", "LIFO", "AVERAGE"}
SUPPORTED_TRANSACTION_ACTIONS = {
    "BUY",
    "SELL",
    "DIVIDEND",
    "INTEREST",
    "FEE",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "CASH_DEPOSIT",
    "CASH_WITHDRAW",
    "STOCK_SPLIT",
    "MERGER",
}
SYMBOL_OPTIONAL_ACTIONS = {"TRANSFER_IN", "TRANSFER_OUT", "CASH_DEPOSIT", "CASH_WITHDRAW"}


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
    action: Literal[
        "BUY",
        "SELL",
        "DIVIDEND",
        "INTEREST",
        "FEE",
        "TRANSFER_IN",
        "TRANSFER_OUT",
        "CASH_DEPOSIT",
        "CASH_WITHDRAW",
        "STOCK_SPLIT",
        "MERGER",
    ]
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
        self._cost_basis_methods_path = portfolio_dir / "cost_basis_methods.json"
        self._manual_prices_path = portfolio_dir / "manual_prices.json"
        self._fx_rates_path = portfolio_dir / "fx_rates.json"
        self._initialize()

    @staticmethod
    def _default_holdings_payload() -> dict[str, Any]:
        return {
            "schema_version": PORTFOLIO_STORE_SCHEMA_VERSION,
            "holdings": {},
            "holdings_by_symbol": {},
            "account_cash": {},
            "account_totals": {},
            "allocation_breakdowns": {
                "asset_class": [],
                "sector": [],
                "region": [],
            },
            "cost_basis_methods": {
                "global": "FIFO",
                "by_account": {},
                "by_symbol": {},
                "by_position": {},
            },
            "manual_prices": {},
            "base_currency": DEFAULT_CURRENCY,
            "fx_rates": {
                DEFAULT_CURRENCY: 1.0,
            },
            "performance": {
                "start_date": None,
                "as_of": None,
                "period_days": 0,
                "gross_contributions": 0.0,
                "net_contributions": 0.0,
                "ending_value": 0.0,
                "twr_return_pct": None,
                "twr_annualized_return_pct": None,
                "xirr_annualized_return_pct": None,
                "realized_gains_usd": 0.0,
                "unrealized_gains_usd": 0.0,
                "income_received_usd": 0.0,
                "fees_paid_usd": 0.0,
                "price_return_usd": 0.0,
                "income_return_usd": 0.0,
                "total_return_usd": 0.0,
                "price_return_pct": None,
                "income_return_pct": None,
                "total_return_pct": None,
                "return_denominator_usd": 0.0,
                "calculation_basis": "transaction_price_estimate",
            },
            "total_cash": 0.0,
            "total_portfolio_value": 0.0,
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

    @staticmethod
    def _default_cost_basis_methods_payload() -> dict[str, Any]:
        return {
            "schema_version": COST_BASIS_METHODS_SCHEMA_VERSION,
            "global": "FIFO",
            "by_account": {},
            "by_symbol": {},
            "by_position": {},
            "updated_at": _utc_now(),
        }

    @staticmethod
    def _default_manual_prices_payload() -> dict[str, Any]:
        return {
            "schema_version": MANUAL_PRICES_SCHEMA_VERSION,
            "by_symbol": {},
            "updated_at": _utc_now(),
        }

    @staticmethod
    def _default_fx_rates_payload() -> dict[str, Any]:
        return {
            "schema_version": FX_RATES_SCHEMA_VERSION,
            "base_currency": DEFAULT_CURRENCY,
            "rates": {
                DEFAULT_CURRENCY: 1.0,
            },
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

        if not self._cost_basis_methods_path.exists():
            self._write_json(self._cost_basis_methods_path, self._default_cost_basis_methods_payload())
        else:
            self._read_cost_basis_methods_payload()

        if not self._manual_prices_path.exists():
            self._write_json(self._manual_prices_path, self._default_manual_prices_payload())
        else:
            self._read_manual_prices_payload()

        if not self._fx_rates_path.exists():
            self._write_json(self._fx_rates_path, self._default_fx_rates_payload())
        else:
            self._read_fx_rates_payload()

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
    def _normalize_action(value: Any, fallback: str = "BUY") -> str:
        action = str(value or "").strip().upper() or fallback
        return action if action in SUPPORTED_TRANSACTION_ACTIONS else fallback

    @staticmethod
    def _normalize_cost_basis_method(value: Any, fallback: str = "FIFO") -> str:
        candidate = str(value or "").strip().upper() or fallback
        return candidate if candidate in VALID_COST_BASIS_METHODS else fallback

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

        raw_custom = merged.get("is_custom_asset")
        if isinstance(raw_custom, bool):
            is_custom_asset = raw_custom
        elif raw_custom is None:
            is_custom_asset = bool(existing.get("is_custom_asset")) if isinstance(existing, dict) else False
        else:
            is_custom_asset = str(raw_custom).strip().lower() in {"1", "true", "yes", "y"}

        data_source = _clean(merged.get("data_source") or merged.get("dataSource") or merged.get("source"))
        valuation_method = _clean(merged.get("valuation_method") or merged.get("valuationMethod"))

        return {
            "symbol": symbol_normalized,
            "name": _clean(merged.get("name") or merged.get("asset_name") or merged.get("long_name") or merged.get("short_name")),
            "asset_type": _clean(merged.get("asset_type") or merged.get("quote_type") or merged.get("type")),
            "asset_class": _clean(merged.get("asset_class")),
            "sector": _clean(merged.get("sector")),
            "region": _clean(merged.get("region") or merged.get("country") or merged.get("geography")),
            "data_source": data_source.upper() if data_source else None,
            "is_custom_asset": is_custom_asset,
            "valuation_method": valuation_method,
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

    def _migrate_cost_basis_methods_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_cost_basis_methods_payload()
        if not isinstance(payload, dict):
            return default_payload

        by_account_raw = payload.get("by_account") if isinstance(payload.get("by_account"), dict) else {}
        by_symbol_raw = payload.get("by_symbol") if isinstance(payload.get("by_symbol"), dict) else {}
        by_position_raw = payload.get("by_position") if isinstance(payload.get("by_position"), dict) else {}

        by_account: dict[str, str] = {}
        by_symbol: dict[str, str] = {}
        by_position: dict[str, str] = {}

        for account_ref, method in by_account_raw.items():
            account = self._ensure_account(str(account_ref), create_if_missing=True)
            account_id = str(account.get("id") or DEFAULT_ACCOUNT_ID)
            by_account[account_id] = self._normalize_cost_basis_method(method)

        for symbol, method in by_symbol_raw.items():
            normalized_symbol = self._normalize_symbol(symbol)
            if not normalized_symbol:
                continue
            by_symbol[normalized_symbol] = self._normalize_cost_basis_method(method)

        for position_key, method in by_position_raw.items():
            key = str(position_key or "").strip()
            if ":" not in key:
                continue
            account_ref, symbol_ref = key.split(":", 1)
            account = self._ensure_account(account_ref, create_if_missing=True)
            account_id = str(account.get("id") or DEFAULT_ACCOUNT_ID)
            symbol = self._normalize_symbol(symbol_ref)
            if not symbol:
                continue
            by_position[f"{account_id}:{symbol}"] = self._normalize_cost_basis_method(method)

        return {
            "schema_version": COST_BASIS_METHODS_SCHEMA_VERSION,
            "global": self._normalize_cost_basis_method(payload.get("global"), "FIFO"),
            "by_account": by_account,
            "by_symbol": by_symbol,
            "by_position": by_position,
            "updated_at": str(payload.get("updated_at") or _utc_now()),
        }

    def _read_cost_basis_methods_payload(self) -> dict[str, Any]:
        original = self._read_json(self._cost_basis_methods_path)
        payload = self._migrate_cost_basis_methods_payload(original)
        if payload != original:
            self._write_json(self._cost_basis_methods_path, payload)
        return payload

    def _migrate_manual_prices_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_manual_prices_payload()
        if payload is None:
            return default_payload

        if isinstance(payload, dict) and "by_symbol" not in payload:
            payload = {"by_symbol": payload}

        if not isinstance(payload, dict):
            return default_payload

        by_symbol_raw = payload.get("by_symbol") if isinstance(payload.get("by_symbol"), dict) else {}
        by_symbol: dict[str, dict[str, Any]] = {}
        for symbol_ref, raw_entry in by_symbol_raw.items():
            symbol = self._normalize_symbol(symbol_ref)
            if not symbol:
                continue

            if isinstance(raw_entry, dict):
                price = _safe_float(raw_entry.get("price"), None)
                note = str(raw_entry.get("note") or "")
                updated_at = str(raw_entry.get("updated_at") or _utc_now())
            else:
                price = _safe_float(raw_entry, None)
                note = ""
                updated_at = _utc_now()

            if price is None or price <= 0:
                continue

            by_symbol[symbol] = {
                "symbol": symbol,
                "price": round(price, 4),
                "note": note,
                "updated_at": updated_at,
            }

        return {
            "schema_version": MANUAL_PRICES_SCHEMA_VERSION,
            "by_symbol": by_symbol,
            "updated_at": str(payload.get("updated_at") or _utc_now()),
        }

    def _read_manual_prices_payload(self) -> dict[str, Any]:
        original = self._read_json(self._manual_prices_path)
        payload = self._migrate_manual_prices_payload(original)
        if payload != original:
            self._write_json(self._manual_prices_path, payload)
        return payload

    def _migrate_fx_rates_payload(self, payload: Any) -> dict[str, Any]:
        default_payload = self._default_fx_rates_payload()

        if isinstance(payload, dict) and "rates" not in payload:
            payload = {
                "base_currency": payload.get("base_currency") if isinstance(payload, dict) else DEFAULT_CURRENCY,
                "rates": payload,
            }
        if not isinstance(payload, dict):
            return default_payload

        base_currency = str(payload.get("base_currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        rates_raw = payload.get("rates") if isinstance(payload.get("rates"), dict) else {}

        rates: dict[str, float] = {base_currency: 1.0}
        for currency_ref, raw_rate in rates_raw.items():
            currency = str(currency_ref or "").strip().upper()
            if not currency:
                continue
            rate = _safe_float(raw_rate, None)
            if rate is None or rate <= 0:
                continue
            rates[currency] = round(rate, 8)

        return {
            "schema_version": FX_RATES_SCHEMA_VERSION,
            "base_currency": base_currency,
            "rates": rates,
            "updated_at": str(payload.get("updated_at") or _utc_now()),
        }

    def _read_fx_rates_payload(self) -> dict[str, Any]:
        original = self._read_json(self._fx_rates_path)
        payload = self._migrate_fx_rates_payload(original)
        if payload != original:
            self._write_json(self._fx_rates_path, payload)
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

            action = self._normalize_action(raw.get("action"), "BUY")
            symbol = self._normalize_symbol(raw.get("symbol"))
            if not symbol and action in SYMBOL_OPTIONAL_ACTIONS:
                symbol = "CASH"
            if not symbol:
                continue

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
                    "lot_method": self._normalize_cost_basis_method(raw.get("lot_method"), "FIFO"),
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
        manual_prices = self._manual_prices_by_symbol()
        base_currency, fx_rates = self._fx_rates_data()
        migrated_holdings: dict[str, dict[str, Any]] = {}
        total_market_value = 0.0
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
            currency = str(raw_holding.get("currency") or account.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
            fx_rate_to_base = self._fx_rate_to_base(currency, base_currency=base_currency, rates=fx_rates)

            quantity = _safe_float(raw_holding.get("quantity"), 0.0)
            cost_basis_native_raw = raw_holding.get("cost_basis_native")
            if cost_basis_native_raw is None:
                cost_basis_native = _safe_float(raw_holding.get("cost_basis"), 0.0) / fx_rate_to_base
            else:
                cost_basis_native = _safe_float(cost_basis_native_raw, 0.0)

            avg_cost_native_raw = raw_holding.get("avg_cost_per_share_native")
            if avg_cost_native_raw is None:
                avg_cost_base = raw_holding.get("avg_cost_per_share")
                if avg_cost_base is None:
                    avg_cost_per_share_native = round(cost_basis_native / quantity, 8) if quantity > 0 else 0.0
                else:
                    avg_cost_per_share_native = _safe_float(avg_cost_base, 0.0) / fx_rate_to_base
            else:
                avg_cost_per_share_native = _safe_float(avg_cost_native_raw, 0.0)

            current_price_native_raw = raw_holding.get("current_price_native")
            if current_price_native_raw is None:
                current_price = raw_holding.get("current_price")
                current_price_native = (
                    _safe_float(current_price, None) / fx_rate_to_base if current_price is not None else None
                )
            else:
                current_price_native = _safe_float(current_price_native_raw, None)
            manual_price_entry = manual_prices.get(symbol)
            if isinstance(manual_price_entry, dict):
                current_price_native = _safe_float(manual_price_entry.get("price"), current_price_native)
            current_value_native_raw = raw_holding.get("current_value_native")
            if current_value_native_raw is None:
                current_value = raw_holding.get("current_value")
                current_value_native = (
                    _safe_float(current_value, None) / fx_rate_to_base if current_value is not None else None
                )
            else:
                current_value_native = _safe_float(current_value_native_raw, None)
            if current_value_native is None and current_price_native is not None:
                current_value_native = round(quantity * current_price_native, 2)
            elif current_price_native is not None:
                current_value_native = round(quantity * current_price_native, 2)

            cost_basis = round(cost_basis_native * fx_rate_to_base, 2)
            avg_cost_per_share = round(avg_cost_per_share_native * fx_rate_to_base, 8)
            current_price_value = round(current_price_native * fx_rate_to_base, 4) if current_price_native is not None else None
            current_value_value = round(current_value_native * fx_rate_to_base, 2) if current_value_native is not None else None
            dividends_native_raw = raw_holding.get("dividends_received_native")
            if dividends_native_raw is None:
                dividends_native = round(_safe_float(raw_holding.get("dividends_received"), 0.0) / fx_rate_to_base, 2)
            else:
                dividends_native = round(_safe_float(dividends_native_raw, 0.0), 2)
            realized_gains_native_raw = raw_holding.get("realized_gains_native")
            if realized_gains_native_raw is None:
                realized_gains_native = round(_safe_float(raw_holding.get("realized_gains"), 0.0) / fx_rate_to_base, 2)
            else:
                realized_gains_native = round(_safe_float(realized_gains_native_raw, 0.0), 2)
            fees_paid_native_raw = raw_holding.get("fees_paid_native")
            if fees_paid_native_raw is None:
                fees_paid_native = round(_safe_float(raw_holding.get("fees_paid"), 0.0) / fx_rate_to_base, 2)
            else:
                fees_paid_native = round(_safe_float(fees_paid_native_raw, 0.0), 2)

            lots: list[dict[str, Any]] = []
            raw_lots = raw_holding.get("lots") if isinstance(raw_holding.get("lots"), list) else []
            if raw_lots:
                for index, lot in enumerate(raw_lots, start=1):
                    if not isinstance(lot, dict):
                        continue
                    lot_qty = _safe_float(lot.get("quantity"), 0.0)
                    lot_remaining = _safe_float(lot.get("remaining_quantity"), lot_qty)
                    unit_cost_native_raw = lot.get("unit_cost_native")
                    if unit_cost_native_raw is None:
                        unit_cost_native = _safe_float(lot.get("unit_cost"), avg_cost_per_share_native) / fx_rate_to_base
                    else:
                        unit_cost_native = _safe_float(unit_cost_native_raw, avg_cost_per_share_native)
                    if lot_remaining <= 0:
                        continue
                    lots.append(
                        {
                            "lot_id": str(lot.get("lot_id") or f"{scoped_key}-lot-{index}"),
                            "acquired_date": str(lot.get("acquired_date") or raw_holding.get("updated_at") or ""),
                            "quantity": round(max(lot_qty, lot_remaining), 8),
                            "remaining_quantity": round(lot_remaining, 8),
                            "unit_cost_native": round(unit_cost_native, 8),
                            "unit_cost": round(unit_cost_native * fx_rate_to_base, 8),
                        }
                    )

            if not lots and quantity > 0:
                lots = [
                    {
                        "lot_id": f"{scoped_key}-legacy-1",
                        "acquired_date": str(raw_holding.get("acquired_date") or payload.get("updated_at") or ""),
                        "quantity": round(quantity, 8),
                        "remaining_quantity": round(quantity, 8),
                        "unit_cost_native": round(avg_cost_per_share_native, 8),
                        "unit_cost": round(avg_cost_per_share_native * fx_rate_to_base, 8),
                    }
                ]

            holding_record = {
                "symbol": symbol,
                "account": account_id,
                "currency": currency,
                "base_currency": base_currency,
                "fx_rate_to_base": round(fx_rate_to_base, 8),
                "quantity": round(quantity, 8),
                "cost_basis_native": round(cost_basis_native, 2),
                "cost_basis": round(cost_basis, 2),
                "avg_cost_per_share_native": round(avg_cost_per_share_native, 8),
                "avg_cost_per_share": round(avg_cost_per_share, 8),
                "cost_basis_method": self._normalize_cost_basis_method(raw_holding.get("cost_basis_method"), "FIFO"),
                "dividends_received_native": dividends_native,
                "dividends_received": round(dividends_native * fx_rate_to_base, 2),
                "realized_gains_native": realized_gains_native,
                "realized_gains": round(realized_gains_native * fx_rate_to_base, 2),
                "fees_paid_native": fees_paid_native,
                "fees_paid": round(fees_paid_native * fx_rate_to_base, 2),
                "lots": lots,
                "lot_count": len(lots),
                "current_price_native": round(current_price_native, 4) if current_price_native is not None else None,
                "current_price": round(current_price_value, 4) if current_price_value is not None else None,
                "current_value_native": round(current_value_native, 2) if current_value_native is not None else None,
                "current_value": round(current_value_value, 2) if current_value_value is not None else None,
                "price_source": "MANUAL" if isinstance(manual_price_entry, dict) else ("LIVE" if current_price_value is not None else None),
                "name": raw_holding.get("name"),
                "asset_type": raw_holding.get("asset_type"),
                "asset_class": raw_holding.get("asset_class"),
                "sector": raw_holding.get("sector"),
                "region": raw_holding.get("region"),
                "data_source": raw_holding.get("data_source"),
                "is_custom_asset": bool(raw_holding.get("is_custom_asset", False)),
                "valuation_method": raw_holding.get("valuation_method"),
            }

            migrated_holdings[scoped_key] = holding_record

            if current_value_value is not None:
                total_market_value += float(current_value_value)
            total_cost += float(cost_basis)

        performance_input = payload.get("performance") if isinstance(payload.get("performance"), dict) else {}
        performance = {
            **default_payload["performance"],
            **performance_input,
        }
        if performance.get("ending_value") in (None, 0, 0.0) and total_market_value > 0:
            performance["ending_value"] = round(total_market_value, 2)
        if performance.get("as_of") is None:
            performance["as_of"] = payload.get("prices_updated_at")

        total_market_value = round(total_market_value, 2)
        total_cost = round(total_cost, 2)
        account_cash = self._normalize_account_cash_payload(payload.get("account_cash"))
        total_cash = round(sum(account_cash.values()), 2)
        total_portfolio_value = round(total_market_value + total_cash, 2)

        migrated = {
            **default_payload,
            **payload,
            "schema_version": PORTFOLIO_STORE_SCHEMA_VERSION,
            "holdings": migrated_holdings,
            "holdings_by_symbol": self._summarize_holdings_by_symbol(migrated_holdings),
            "account_cash": account_cash,
            "account_totals": self._summarize_account_totals(migrated_holdings, account_cash=account_cash),
            "allocation_breakdowns": self._summarize_allocation_breakdowns(
                migrated_holdings,
                total_market_value=total_market_value,
                total_cash=total_cash,
            ),
            "cost_basis_methods": self._read_cost_basis_methods_payload(),
            "manual_prices": manual_prices,
            "base_currency": base_currency,
            "fx_rates": fx_rates,
            "performance": performance,
            "total_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "total_cash": total_cash,
            "total_portfolio_value": total_portfolio_value,
            "net_performance": round(
                _safe_float(payload.get("net_performance"), total_market_value - total_cost),
                2,
            ),
            "net_performance_pct": (
                round(
                    _safe_float(
                        payload.get("net_performance_pct"),
                        ((total_market_value - total_cost) / total_cost * 100) if total_cost > 0 else 0.0,
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

    def _normalize_account_cash_payload(self, account_cash: Any) -> dict[str, float]:
        if not isinstance(account_cash, dict):
            return {}

        normalized: dict[str, float] = {}
        for account_ref, raw_balance in account_cash.items():
            account = self._ensure_account(str(account_ref), create_if_missing=True)
            account_id = str(account.get("id") or DEFAULT_ACCOUNT_ID)
            normalized[account_id] = round(_safe_float(raw_balance, 0.0), 2)
        return normalized

    def _manual_prices_by_symbol(self) -> dict[str, dict[str, Any]]:
        payload = self._read_manual_prices_payload()
        by_symbol = payload.get("by_symbol", {})
        return by_symbol if isinstance(by_symbol, dict) else {}

    def _fx_rates_data(self) -> tuple[str, dict[str, float]]:
        payload = self._read_fx_rates_payload()
        base_currency = str(payload.get("base_currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        rates_raw = payload.get("rates", {})
        rates: dict[str, float] = {}
        if isinstance(rates_raw, dict):
            for currency_ref, raw_rate in rates_raw.items():
                currency = str(currency_ref or "").strip().upper()
                if not currency:
                    continue
                rate = _safe_float(raw_rate, None)
                if rate is None or rate <= 0:
                    continue
                rates[currency] = float(rate)
        rates[base_currency] = 1.0
        return base_currency, rates

    @staticmethod
    def _fx_rate_to_base(currency: str, *, base_currency: str, rates: dict[str, float]) -> float:
        normalized = str(currency or "").strip().upper() or base_currency
        if normalized == base_currency:
            return 1.0
        rate = rates.get(normalized)
        if rate is None or rate <= 0:
            return 1.0
        return float(rate)

    def _convert_amount_between_currencies(
        self,
        amount: float,
        *,
        from_currency: str,
        to_currency: str,
        base_currency: str,
        rates: dict[str, float],
    ) -> float:
        source_rate = self._fx_rate_to_base(from_currency, base_currency=base_currency, rates=rates)
        target_rate = self._fx_rate_to_base(to_currency, base_currency=base_currency, rates=rates)
        if target_rate <= 0:
            return amount * source_rate
        return amount * (source_rate / target_rate)

    @staticmethod
    def _transaction_gross_amount(quantity: float, unit_price: float, fee: float = 0.0) -> float:
        gross = abs(quantity) * abs(unit_price)
        if gross <= 0 and fee > 0:
            return abs(fee)
        return gross

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
                    "price_source": holding.get("price_source"),
                    "name": holding.get("name"),
                    "asset_type": holding.get("asset_type"),
                    "asset_class": holding.get("asset_class"),
                    "sector": holding.get("sector"),
                    "region": holding.get("region"),
                    "data_source": holding.get("data_source"),
                    "is_custom_asset": bool(holding.get("is_custom_asset", False)),
                    "valuation_method": holding.get("valuation_method"),
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
            if holding.get("price_source") == "MANUAL":
                bucket["price_source"] = "MANUAL"

            for field in ("name", "asset_type", "asset_class", "sector", "region", "data_source", "valuation_method"):
                if not bucket.get(field) and holding.get(field):
                    bucket[field] = holding.get(field)
            bucket["is_custom_asset"] = bool(bucket.get("is_custom_asset")) or bool(holding.get("is_custom_asset"))

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

    def _summarize_account_totals(
        self,
        holdings: dict[str, dict[str, Any]],
        *,
        account_cash: dict[str, float] | None = None,
    ) -> dict[str, dict[str, Any]]:
        accounts_payload = self._read_accounts_payload()
        accounts_by_id = {
            str(account.get("id")): account
            for account in accounts_payload.get("accounts", [])
            if isinstance(account, dict) and account.get("id")
        }

        totals: dict[str, dict[str, Any]] = {}
        normalized_cash = account_cash or {}

        def ensure_bucket(account_id: str) -> dict[str, Any]:
            account = accounts_by_id.get(account_id, {})
            return totals.setdefault(
                account_id,
                {
                    "account_id": account_id,
                    "name": account.get("name") or account_id,
                    "type": account.get("type") or "taxable",
                    "currency": account.get("currency") or DEFAULT_CURRENCY,
                    "market_value": 0.0,
                    "cash_balance": 0.0,
                    "cost_basis": 0.0,
                    "holdings_count": 0,
                },
            )

        for holding in holdings.values():
            account_id = str(holding.get("account") or DEFAULT_ACCOUNT_ID)
            bucket = ensure_bucket(account_id)
            bucket["market_value"] += _safe_float(holding.get("current_value"), 0.0)
            bucket["cost_basis"] += _safe_float(holding.get("cost_basis"), 0.0)
            bucket["holdings_count"] += 1

        for account_id, balance in normalized_cash.items():
            ensure_bucket(account_id)["cash_balance"] += _safe_float(balance, 0.0)

        for account_id, bucket in totals.items():
            bucket["market_value"] = round(_safe_float(bucket.get("market_value"), 0.0), 2)
            bucket["cash_balance"] = round(_safe_float(bucket.get("cash_balance"), 0.0), 2)
            bucket["cost_basis"] = round(_safe_float(bucket.get("cost_basis"), 0.0), 2)
            bucket["total_value"] = round(bucket["market_value"] + bucket["cash_balance"], 2)
            bucket["net_performance"] = round(bucket["market_value"] - bucket["cost_basis"], 2)
            if bucket["cost_basis"] > 0:
                bucket["net_performance_pct"] = round((bucket["net_performance"] / bucket["cost_basis"]) * 100, 2)
            else:
                bucket["net_performance_pct"] = 0.0

        return totals

    def _resolve_cost_basis_method(
        self,
        *,
        methods_payload: dict[str, Any],
        account_id: str,
        symbol: str,
        transaction_method: str | None = None,
        preserved_method: str | None = None,
    ) -> str:
        position_key = f"{account_id}:{symbol}"
        by_position = methods_payload.get("by_position", {})
        by_account = methods_payload.get("by_account", {})
        by_symbol = methods_payload.get("by_symbol", {})

        for candidate in (
            by_position.get(position_key) if isinstance(by_position, dict) else None,
            by_account.get(account_id) if isinstance(by_account, dict) else None,
            by_symbol.get(symbol) if isinstance(by_symbol, dict) else None,
            preserved_method,
            transaction_method,
            methods_payload.get("global"),
            "FIFO",
        ):
            normalized = self._normalize_cost_basis_method(candidate, "")
            if normalized:
                return normalized
        return "FIFO"

    def _summarize_allocation_breakdowns(
        self,
        holdings: dict[str, dict[str, Any]],
        *,
        total_market_value: float,
        total_cash: float = 0.0,
    ) -> dict[str, list[dict[str, Any]]]:
        breakdown_map: dict[str, dict[str, float]] = {
            "asset_class": {},
            "sector": {},
            "region": {},
        }
        fallback_labels = {
            "asset_class": "Unclassified",
            "sector": "Unknown",
            "region": "Unknown",
        }

        for holding in holdings.values():
            value = _safe_float(holding.get("current_value"), 0.0)
            if value <= 0:
                continue
            for dimension in ("asset_class", "sector", "region"):
                raw_key = str(holding.get(dimension) or "").strip()
                key = raw_key or fallback_labels[dimension]
                breakdown_map[dimension][key] = breakdown_map[dimension].get(key, 0.0) + value

        if total_cash > 0:
            breakdown_map["asset_class"]["Cash"] = breakdown_map["asset_class"].get("Cash", 0.0) + total_cash

        breakdowns: dict[str, list[dict[str, Any]]] = {}
        for dimension, buckets in breakdown_map.items():
            if dimension == "asset_class":
                denominator = (total_market_value + total_cash) if (total_market_value + total_cash) > 0 else 1.0
            else:
                denominator = total_market_value if total_market_value > 0 else 1.0
            rows = [
                {
                    "key": key,
                    "value": round(value, 2),
                    "allocation_pct": round((value / denominator) * 100, 2),
                }
                for key, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
            ]
            breakdowns[dimension] = rows
        return breakdowns

    def _apply_metadata(self, symbol: str, base: dict[str, Any], metadata_map: dict[str, dict[str, Any]]) -> None:
        metadata = metadata_map.get(symbol) if isinstance(metadata_map, dict) else None
        if not isinstance(metadata, dict):
            return
        for field in (
            "name",
            "asset_type",
            "asset_class",
            "sector",
            "region",
            "data_source",
            "is_custom_asset",
            "valuation_method",
        ):
            if metadata.get(field) is not None:
                base[field] = metadata.get(field)

    def _finalize_holdings_payload(
        self,
        *,
        holdings: dict[str, dict[str, Any]],
        transactions: list[dict[str, Any]],
        prices_updated_at: str | None = None,
        account_cash: dict[str, float] | None = None,
        return_components_override: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        total_market_value = 0.0
        total_cost = 0.0
        manual_prices = self._manual_prices_by_symbol()
        base_currency, fx_rates = self._fx_rates_data()

        for holding in holdings.values():
            symbol = self._normalize_symbol(holding.get("symbol"))
            currency = str(holding.get("currency") or base_currency).strip().upper() or base_currency
            fx_rate_to_base = self._fx_rate_to_base(currency, base_currency=base_currency, rates=fx_rates)
            manual_price_entry = manual_prices.get(symbol) if symbol else None
            current_price_native = holding.get("current_price_native")
            if current_price_native is None and holding.get("current_price") is not None:
                current_price_native = _safe_float(holding.get("current_price"), None) / fx_rate_to_base
            if isinstance(manual_price_entry, dict):
                current_price_native = _safe_float(manual_price_entry.get("price"), current_price_native)
                holding["price_source"] = "MANUAL"
            elif current_price_native is not None:
                holding["price_source"] = "LIVE"
            else:
                holding["price_source"] = None

            quantity = round(_safe_float(holding.get("quantity"), 0.0), 8)
            cost_basis_native = holding.get("cost_basis_native")
            if cost_basis_native is None:
                cost_basis_native = _safe_float(holding.get("cost_basis"), 0.0) / fx_rate_to_base
            cost_basis_native = round(_safe_float(cost_basis_native, 0.0), 2)
            cost_basis = round(cost_basis_native * fx_rate_to_base, 2)
            avg_cost_per_share_native = round((cost_basis_native / quantity), 8) if quantity > 0 else 0.0
            avg_cost_per_share = round(avg_cost_per_share_native * fx_rate_to_base, 8)

            current_value_native = holding.get("current_value_native")
            if current_price_native is not None:
                current_value_native = round(quantity * _safe_float(current_price_native, 0.0), 2)
                holding["current_price_native"] = round(_safe_float(current_price_native, 0.0), 4)
                holding["current_value_native"] = current_value_native
                holding["current_price"] = round(_safe_float(current_price_native, 0.0) * fx_rate_to_base, 4)
                holding["current_value"] = round(current_value_native * fx_rate_to_base, 2)
            elif current_value_native is not None:
                current_value_native = round(_safe_float(current_value_native, 0.0), 2)
                holding["current_value_native"] = current_value_native
                holding["current_value"] = round(current_value_native * fx_rate_to_base, 2)
                holding["current_price"] = None
            else:
                holding["current_price_native"] = None
                holding["current_value_native"] = None
                holding["current_price"] = None
                holding["current_value"] = None

            dividends_native = holding.get("dividends_received_native")
            if dividends_native is None:
                dividends_native = _safe_float(holding.get("dividends_received"), 0.0) / fx_rate_to_base
            realized_native = holding.get("realized_gains_native")
            if realized_native is None:
                realized_native = _safe_float(holding.get("realized_gains"), 0.0) / fx_rate_to_base
            fees_native = holding.get("fees_paid_native")
            if fees_native is None:
                fees_native = _safe_float(holding.get("fees_paid"), 0.0) / fx_rate_to_base

            normalized_lots: list[dict[str, Any]] = []
            raw_lots = holding.get("lots") if isinstance(holding.get("lots"), list) else []
            for lot in raw_lots:
                if not isinstance(lot, dict):
                    continue
                lot_qty = round(_safe_float(lot.get("quantity"), 0.0), 8)
                lot_remaining = round(_safe_float(lot.get("remaining_quantity"), lot_qty), 8)
                if lot_remaining <= 1e-9:
                    continue
                unit_cost_native = lot.get("unit_cost_native")
                if unit_cost_native is None:
                    unit_cost_native = _safe_float(lot.get("unit_cost"), avg_cost_per_share_native) / fx_rate_to_base
                unit_cost_native = round(_safe_float(unit_cost_native, avg_cost_per_share_native), 8)
                normalized_lots.append(
                    {
                        "lot_id": str(lot.get("lot_id") or ""),
                        "acquired_date": str(lot.get("acquired_date") or ""),
                        "quantity": lot_qty,
                        "remaining_quantity": lot_remaining,
                        "unit_cost_native": unit_cost_native,
                        "unit_cost": round(unit_cost_native * fx_rate_to_base, 8),
                    }
                )

            holding["currency"] = currency
            holding["base_currency"] = base_currency
            holding["fx_rate_to_base"] = round(fx_rate_to_base, 8)
            holding["quantity"] = quantity
            holding["cost_basis_native"] = cost_basis_native
            holding["cost_basis"] = cost_basis
            holding["avg_cost_per_share_native"] = avg_cost_per_share_native
            holding["avg_cost_per_share"] = avg_cost_per_share
            holding["dividends_received_native"] = round(_safe_float(dividends_native, 0.0), 2)
            holding["dividends_received"] = round(_safe_float(dividends_native, 0.0) * fx_rate_to_base, 2)
            holding["realized_gains_native"] = round(_safe_float(realized_native, 0.0), 2)
            holding["realized_gains"] = round(_safe_float(realized_native, 0.0) * fx_rate_to_base, 2)
            holding["fees_paid_native"] = round(_safe_float(fees_native, 0.0), 2)
            holding["fees_paid"] = round(_safe_float(fees_native, 0.0) * fx_rate_to_base, 2)
            holding["lots"] = normalized_lots
            holding["lot_count"] = len(normalized_lots)

            if holding.get("current_value") is not None:
                total_market_value += float(holding["current_value"])
            total_cost += float(cost_basis)

        normalized_account_cash = self._normalize_account_cash_payload(account_cash)
        total_cash = round(sum(normalized_account_cash.values()), 2)
        total_portfolio_value = round(total_market_value + total_cash, 2)
        converted_transactions: list[dict[str, Any]] = []
        for transaction in transactions:
            currency = str(transaction.get("currency") or base_currency).strip().upper() or base_currency
            fx_rate_to_base = self._fx_rate_to_base(currency, base_currency=base_currency, rates=fx_rates)
            converted_transactions.append(
                {
                    **transaction,
                    "currency": base_currency,
                    "unit_price": round(_safe_float(transaction.get("unit_price"), 0.0) * fx_rate_to_base, 8),
                    "fee": round(_safe_float(transaction.get("fee"), 0.0) * fx_rate_to_base, 8),
                }
            )

        payload = self._default_holdings_payload()
        payload["holdings"] = holdings
        payload["holdings_by_symbol"] = self._summarize_holdings_by_symbol(holdings)
        payload["account_cash"] = normalized_account_cash
        payload["account_totals"] = self._summarize_account_totals(holdings, account_cash=normalized_account_cash)
        payload["allocation_breakdowns"] = self._summarize_allocation_breakdowns(
            holdings,
            total_market_value=total_market_value,
            total_cash=total_cash,
        )
        payload["manual_prices"] = manual_prices
        payload["base_currency"] = base_currency
        payload["fx_rates"] = fx_rates
        payload["total_value"] = round(total_market_value, 2)
        payload["total_cash"] = total_cash
        payload["total_portfolio_value"] = total_portfolio_value
        payload["total_cost_basis"] = round(total_cost, 2)
        payload["net_performance"] = round(total_market_value - total_cost, 2)
        payload["net_performance_pct"] = (
            round((total_market_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0.0
        )
        payload["performance"] = calculate_portfolio_performance(
            transactions=converted_transactions,
            holdings=holdings,
            as_of=prices_updated_at or _utc_now(),
            return_components_override=return_components_override,
        )
        payload["prices_updated_at"] = prices_updated_at
        payload["asset_metadata_updated_at"] = self._read_asset_metadata_payload().get("updated_at")
        payload["cost_basis_methods"] = self._read_cost_basis_methods_payload()
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
        normalized_action = self._normalize_action(action, "BUY")
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol and normalized_action in SYMBOL_OPTIONAL_ACTIONS:
            normalized_symbol = "CASH"

        txn = Transaction(
            id=str(uuid.uuid4())[:8],
            date=str(date),
            symbol=normalized_symbol,
            action=normalized_action,
            quantity=float(quantity),
            unit_price=float(unit_price),
            fee=float(fee),
            currency=str(currency).strip().upper() or DEFAULT_CURRENCY,
            account=str(account_record.get("id") or DEFAULT_ACCOUNT_ID),
            note=note,
            lot_method=self._normalize_cost_basis_method(lot_method, "FIFO"),
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
        if normalized_symbol and normalized_symbol != "CASH" and any(value for value in metadata_payload.values()):
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
            action = self._normalize_action(item.get("action", "BUY"), "BUY")
            symbol = self._normalize_symbol(item.get("symbol"))
            if not symbol and action in SYMBOL_OPTIONAL_ACTIONS:
                symbol = "CASH"
            if not symbol:
                continue

            txn = Transaction(
                id=str(uuid.uuid4())[:8],
                date=str(item.get("date", "")),
                symbol=symbol,
                action=action,
                quantity=float(item.get("quantity", 0)),
                unit_price=float(item.get("unit_price", 0)),
                fee=float(item.get("fee", 0)),
                currency=str(item.get("currency", DEFAULT_CURRENCY)).strip().upper() or DEFAULT_CURRENCY,
                account=str(account_record.get("id") or DEFAULT_ACCOUNT_ID),
                note=str(item.get("note", "")),
                lot_method=self._normalize_cost_basis_method(item.get("lot_method"), "FIFO"),
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
            if symbol != "CASH" and any(value for value in metadata_payload.values()):
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
        base_currency, fx_rates = self._fx_rates_data()
        payload["accounts"] = self.get_accounts()
        payload["cost_basis_methods"] = self.get_cost_basis_methods()
        payload["manual_prices"] = self._manual_prices_by_symbol()
        payload["base_currency"] = base_currency
        payload["fx_rates"] = fx_rates
        return payload

    @staticmethod
    def _lot_sort_key(lot: dict[str, Any]) -> tuple[str, str]:
        return str(lot.get("acquired_date") or ""), str(lot.get("lot_id") or "")

    def _consume_lots(
        self,
        lots: list[dict[str, Any]],
        quantity_to_sell: float,
        method: str,
        *,
        unit_cost_key: str = "unit_cost",
    ) -> float:
        remaining = quantity_to_sell
        consumed_cost = 0.0

        reverse = method == "LIFO"
        lots.sort(key=self._lot_sort_key, reverse=reverse)

        for lot in lots:
            lot_remaining = _safe_float(lot.get("remaining_quantity"), 0.0)
            if lot_remaining <= 0:
                continue
            take = min(lot_remaining, remaining)
            if take <= 0:
                continue

            unit_cost = _safe_float(lot.get(unit_cost_key), 0.0)
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
        methods_payload = self._read_cost_basis_methods_payload()
        base_currency, fx_rates = self._fx_rates_data()

        positions: dict[str, dict[str, Any]] = {}
        account_cash: dict[str, float] = {}
        sorted_txns = sorted(
            txns,
            key=lambda t: (str(t.get("date", "")), str(t.get("created_at", "")), str(t.get("id", ""))),
        )

        for txn in sorted_txns:
            account_record = self._ensure_account(str(txn.get("account") or DEFAULT_ACCOUNT_ID), create_if_missing=True)
            account_id = str(account_record.get("id") or DEFAULT_ACCOUNT_ID)
            action = self._normalize_action(txn.get("action"), "BUY")
            symbol = self._normalize_symbol(txn.get("symbol"))
            if not symbol and action in SYMBOL_OPTIONAL_ACTIONS:
                symbol = "CASH"

            quantity = abs(_safe_float(txn.get("quantity"), 0.0))
            txn_currency = str(txn.get("currency") or account_record.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
            txn_rate_to_base = self._fx_rate_to_base(txn_currency, base_currency=base_currency, rates=fx_rates)
            price_native = abs(_safe_float(txn.get("unit_price"), 0.0))
            fee_native = abs(_safe_float(txn.get("fee"), 0.0))
            gross_native = self._transaction_gross_amount(quantity, price_native, fee_native)
            gross_base = gross_native * txn_rate_to_base

            def apply_cash_delta(delta: float) -> None:
                if abs(delta) <= 1e-9:
                    return
                account_cash[account_id] = account_cash.get(account_id, 0.0) + float(delta)

            if action in {"TRANSFER_IN", "CASH_DEPOSIT"}:
                apply_cash_delta(gross_base)
                continue
            if action in {"TRANSFER_OUT", "CASH_WITHDRAW"}:
                apply_cash_delta(-gross_base)
                continue

            if not symbol:
                continue

            key = f"{account_id}:{symbol}"
            lot_method = str(txn.get("lot_method") or "FIFO").strip().upper() or "FIFO"

            if key not in positions:
                preserved = existing_holdings.get(key, {}) if isinstance(existing_holdings, dict) else {}
                preserved_currency = (
                    str(preserved.get("currency") or txn_currency or account_record.get("currency") or base_currency).strip().upper()
                    or base_currency
                )
                preserved_rate_to_base = self._fx_rate_to_base(
                    preserved_currency,
                    base_currency=base_currency,
                    rates=fx_rates,
                )
                preserved_price_native = preserved.get("current_price_native")
                if preserved_price_native is None and preserved.get("current_price") is not None:
                    preserved_price_native = _safe_float(preserved.get("current_price"), None) / preserved_rate_to_base
                positions[key] = {
                    "symbol": symbol,
                    "account": account_id,
                    "currency": preserved_currency,
                    "base_currency": base_currency,
                    "fx_rate_to_base": preserved_rate_to_base,
                    "quantity": 0.0,
                    "dividends_native": 0.0,
                    "realized_gains_native": 0.0,
                    "fees_native": 0.0,
                    "lots": [],
                    "cost_basis_method": str(preserved.get("cost_basis_method") or lot_method or "FIFO").upper(),
                    "current_price_native": preserved_price_native,
                    "price_source": preserved.get("price_source"),
                }

            position = positions[key]
            position_currency = str(position.get("currency") or base_currency).strip().upper() or base_currency
            position_rate_to_base = self._fx_rate_to_base(position_currency, base_currency=base_currency, rates=fx_rates)
            position["fx_rate_to_base"] = position_rate_to_base
            price_in_position_currency = self._convert_amount_between_currencies(
                price_native,
                from_currency=txn_currency,
                to_currency=position_currency,
                base_currency=base_currency,
                rates=fx_rates,
            )
            fee_in_position_currency = self._convert_amount_between_currencies(
                fee_native,
                from_currency=txn_currency,
                to_currency=position_currency,
                base_currency=base_currency,
                rates=fx_rates,
            )
            position["cost_basis_method"] = self._resolve_cost_basis_method(
                methods_payload=methods_payload,
                account_id=account_id,
                symbol=symbol,
                transaction_method=lot_method,
                preserved_method=position.get("cost_basis_method"),
            )
            resolved_method = str(position.get("cost_basis_method") or "FIFO")

            if action == "BUY":
                if quantity <= 0:
                    continue
                if resolved_method == "AVERAGE":
                    existing_qty = sum(_safe_float(lot.get("remaining_quantity"), 0.0) for lot in position["lots"])
                    existing_cost = sum(
                        _safe_float(lot.get("remaining_quantity"), 0.0) * _safe_float(lot.get("unit_cost_native"), 0.0)
                        for lot in position["lots"]
                    )
                    buy_cost = (quantity * price_in_position_currency) + fee_in_position_currency
                    new_qty = existing_qty + quantity
                    if new_qty <= 0:
                        continue
                    avg_unit_cost = (existing_cost + buy_cost) / new_qty
                    position["quantity"] = new_qty
                    position["lots"] = [
                        {
                            "lot_id": str(txn.get("id") or f"{key}-avg"),
                            "acquired_date": str(txn.get("date") or ""),
                            "quantity": round(new_qty, 8),
                            "remaining_quantity": round(new_qty, 8),
                            "unit_cost_native": round(avg_unit_cost, 8),
                        }
                    ]
                else:
                    unit_cost = price_in_position_currency + (fee_in_position_currency / quantity if quantity > 0 else 0.0)
                    position["quantity"] += quantity
                    position["lots"].append(
                        {
                            "lot_id": str(txn.get("id") or f"{key}-{len(position['lots']) + 1}"),
                            "acquired_date": str(txn.get("date") or ""),
                            "quantity": round(quantity, 8),
                            "remaining_quantity": round(quantity, 8),
                            "unit_cost_native": round(unit_cost, 8),
                        }
                    )
                apply_cash_delta(-(((quantity * price_native) + fee_native) * txn_rate_to_base))
            elif action == "SELL":
                available_qty = sum(_safe_float(lot.get("remaining_quantity"), 0.0) for lot in position["lots"])
                sell_qty = min(quantity, available_qty)
                if sell_qty <= 0:
                    continue

                if resolved_method == "AVERAGE":
                    total_cost = sum(
                        _safe_float(lot.get("remaining_quantity"), 0.0) * _safe_float(lot.get("unit_cost_native"), 0.0)
                        for lot in position["lots"]
                    )
                    avg_unit = (total_cost / available_qty) if available_qty > 0 else 0.0
                    consumed_cost = sell_qty * avg_unit
                    remaining_qty = max(available_qty - sell_qty, 0.0)
                    if position["lots"]:
                        position["lots"][0]["remaining_quantity"] = round(remaining_qty, 8)
                        position["lots"][0]["quantity"] = round(remaining_qty, 8)
                        if remaining_qty <= 1e-9:
                            position["lots"] = []
                    else:
                        position["lots"] = []
                else:
                    consumed_cost = self._consume_lots(
                        position["lots"],
                        sell_qty,
                        resolved_method,
                        unit_cost_key="unit_cost_native",
                    )
                proceeds = (sell_qty * price_in_position_currency) - fee_in_position_currency
                realized_gain = proceeds - consumed_cost

                position["quantity"] = max(position["quantity"] - sell_qty, 0.0)
                position["realized_gains_native"] += realized_gain
                position["fees_native"] += fee_in_position_currency
                apply_cash_delta(((sell_qty * price_native) - fee_native) * txn_rate_to_base)
            elif action in {"DIVIDEND", "INTEREST"}:
                income = (quantity * price_in_position_currency) - fee_in_position_currency
                position["dividends_native"] += income
                apply_cash_delta(((quantity * price_native) - fee_native) * txn_rate_to_base)
            elif action == "FEE":
                charge_position_currency = (
                    fee_in_position_currency
                    if fee_in_position_currency > 0
                    else self._convert_amount_between_currencies(
                        gross_native,
                        from_currency=txn_currency,
                        to_currency=position_currency,
                        base_currency=base_currency,
                        rates=fx_rates,
                    )
                )
                charge_base = (fee_native * txn_rate_to_base) if fee_native > 0 else gross_base
                position["fees_native"] += abs(charge_position_currency)
                position["realized_gains_native"] -= abs(charge_position_currency)
                apply_cash_delta(-abs(charge_base))
            elif action == "STOCK_SPLIT":
                split_factor = quantity
                if split_factor <= 0:
                    continue
                position["quantity"] *= split_factor
                for lot in position["lots"]:
                    lot_qty = _safe_float(lot.get("quantity"), 0.0)
                    lot_remaining = _safe_float(lot.get("remaining_quantity"), 0.0)
                    unit_cost = _safe_float(lot.get("unit_cost_native"), 0.0)
                    lot["quantity"] = round(lot_qty * split_factor, 8)
                    lot["remaining_quantity"] = round(lot_remaining * split_factor, 8)
                    lot["unit_cost_native"] = round(unit_cost / split_factor, 8) if split_factor > 0 else round(unit_cost, 8)
            elif action == "MERGER":
                available_qty = sum(_safe_float(lot.get("remaining_quantity"), 0.0) for lot in position["lots"])
                merge_qty = min(quantity if quantity > 0 else available_qty, available_qty)
                if merge_qty <= 0:
                    continue

                if resolved_method == "AVERAGE":
                    total_cost = sum(
                        _safe_float(lot.get("remaining_quantity"), 0.0) * _safe_float(lot.get("unit_cost_native"), 0.0)
                        for lot in position["lots"]
                    )
                    avg_unit = (total_cost / available_qty) if available_qty > 0 else 0.0
                    consumed_cost = merge_qty * avg_unit
                    remaining_qty = max(available_qty - merge_qty, 0.0)
                    if position["lots"]:
                        position["lots"][0]["remaining_quantity"] = round(remaining_qty, 8)
                        position["lots"][0]["quantity"] = round(remaining_qty, 8)
                        if remaining_qty <= 1e-9:
                            position["lots"] = []
                    else:
                        position["lots"] = []
                else:
                    consumed_cost = self._consume_lots(
                        position["lots"],
                        merge_qty,
                        resolved_method,
                        unit_cost_key="unit_cost_native",
                    )

                proceeds = (merge_qty * price_in_position_currency) - fee_in_position_currency
                realized_gain = proceeds - consumed_cost
                position["quantity"] = max(position["quantity"] - merge_qty, 0.0)
                position["realized_gains_native"] += realized_gain
                position["fees_native"] += fee_in_position_currency
                apply_cash_delta(((merge_qty * price_native) - fee_native) * txn_rate_to_base)

        holdings: dict[str, dict[str, Any]] = {}
        for key, position in positions.items():
            quantity = _safe_float(position.get("quantity"), 0.0)
            if quantity <= 1e-6:
                continue

            position_currency = str(position.get("currency") or base_currency).strip().upper() or base_currency
            fx_rate_to_base = self._fx_rate_to_base(position_currency, base_currency=base_currency, rates=fx_rates)
            remaining_lots = [
                {
                    "lot_id": str(lot.get("lot_id") or ""),
                    "acquired_date": str(lot.get("acquired_date") or ""),
                    "quantity": round(_safe_float(lot.get("quantity"), 0.0), 8),
                    "remaining_quantity": round(_safe_float(lot.get("remaining_quantity"), 0.0), 8),
                    "unit_cost_native": round(_safe_float(lot.get("unit_cost_native"), 0.0), 8),
                    "unit_cost": round(_safe_float(lot.get("unit_cost_native"), 0.0) * fx_rate_to_base, 8),
                }
                for lot in position.get("lots", [])
                if _safe_float(lot.get("remaining_quantity"), 0.0) > 1e-9
            ]

            cost_basis_native = sum(
                _safe_float(lot.get("remaining_quantity"), 0.0) * _safe_float(lot.get("unit_cost_native"), 0.0)
                for lot in remaining_lots
            )
            cost_basis = cost_basis_native * fx_rate_to_base
            avg_cost_per_share_native = (cost_basis_native / quantity) if quantity > 0 else 0.0
            avg_cost_per_share = avg_cost_per_share_native * fx_rate_to_base

            current_price_native = position.get("current_price_native")
            if current_price_native is not None:
                current_price_native = round(_safe_float(current_price_native, 0.0), 4)
                current_price = round(current_price_native * fx_rate_to_base, 4)
                current_value_native = round(quantity * current_price_native, 2)
                current_value = round(current_value_native * fx_rate_to_base, 2)
            else:
                current_price = None
                current_value = None
                current_value_native = None

            holding = {
                "symbol": position["symbol"],
                "account": position["account"],
                "currency": position_currency,
                "base_currency": base_currency,
                "fx_rate_to_base": round(fx_rate_to_base, 8),
                "quantity": round(quantity, 8),
                "cost_basis_native": round(cost_basis_native, 2),
                "cost_basis": round(cost_basis, 2),
                "avg_cost_per_share_native": round(avg_cost_per_share_native, 8),
                "avg_cost_per_share": round(avg_cost_per_share, 8),
                "cost_basis_method": str(position.get("cost_basis_method") or "FIFO"),
                "dividends_received_native": round(_safe_float(position.get("dividends_native"), 0.0), 2),
                "dividends_received": round(_safe_float(position.get("dividends_native"), 0.0) * fx_rate_to_base, 2),
                "realized_gains_native": round(_safe_float(position.get("realized_gains_native"), 0.0), 2),
                "realized_gains": round(_safe_float(position.get("realized_gains_native"), 0.0) * fx_rate_to_base, 2),
                "fees_paid_native": round(_safe_float(position.get("fees_native"), 0.0), 2),
                "fees_paid": round(_safe_float(position.get("fees_native"), 0.0) * fx_rate_to_base, 2),
                "lots": remaining_lots,
                "lot_count": len(remaining_lots),
                "current_price_native": current_price_native,
                "current_price": current_price,
                "current_value_native": current_value_native,
                "current_value": current_value,
                "price_source": position.get("price_source"),
                "name": None,
                "asset_type": None,
                "asset_class": None,
                "sector": None,
                "region": None,
                "data_source": None,
                "is_custom_asset": False,
                "valuation_method": None,
            }

            self._apply_metadata(position["symbol"], holding, metadata_map)
            holdings[key] = holding

        return_components_override = {
            "realized_gains_usd": round(
                sum(
                    _safe_float(pos.get("realized_gains_native"), 0.0)
                    * self._fx_rate_to_base(
                        str(pos.get("currency") or base_currency),
                        base_currency=base_currency,
                        rates=fx_rates,
                    )
                    for pos in positions.values()
                ),
                2,
            ),
            "income_received_usd": round(
                sum(
                    _safe_float(pos.get("dividends_native"), 0.0)
                    * self._fx_rate_to_base(
                        str(pos.get("currency") or base_currency),
                        base_currency=base_currency,
                        rates=fx_rates,
                    )
                    for pos in positions.values()
                ),
                2,
            ),
            "fees_paid_usd": round(
                sum(
                    _safe_float(pos.get("fees_native"), 0.0)
                    * self._fx_rate_to_base(
                        str(pos.get("currency") or base_currency),
                        base_currency=base_currency,
                        rates=fx_rates,
                    )
                    for pos in positions.values()
                ),
                2,
            ),
        }

        try:
            prices_updated_at = self._read_holdings_payload().get("prices_updated_at")
        except Exception:
            prices_updated_at = None

        data = self._finalize_holdings_payload(
            holdings=holdings,
            transactions=txns,
            prices_updated_at=prices_updated_at,
            account_cash=account_cash,
            return_components_override=return_components_override,
        )
        self._write_json(self._holdings_path, data)
        return data

    def update_prices(self, prices: dict[str, float]) -> dict[str, Any]:
        """Update current prices for holdings and compute values."""
        data = self._read_holdings_payload()
        holdings = data.get("holdings", {})
        performance_seed = data.get("performance") if isinstance(data.get("performance"), dict) else {}

        for holding in holdings.values():
            symbol = self._normalize_symbol(holding.get("symbol"))
            if not symbol:
                continue
            price = prices.get(symbol)
            if price is not None:
                holding["current_price_native"] = round(float(price), 4)

        data = self._finalize_holdings_payload(
            holdings=holdings,
            transactions=self._read_transactions(),
            prices_updated_at=_utc_now(),
            account_cash=self._normalize_account_cash_payload(data.get("account_cash")),
            return_components_override={
                "realized_gains_usd": _safe_float(performance_seed.get("realized_gains_usd"), 0.0),
                "income_received_usd": _safe_float(performance_seed.get("income_received_usd"), 0.0),
                "fees_paid_usd": _safe_float(performance_seed.get("fees_paid_usd"), 0.0),
            },
        )
        self._write_json(self._holdings_path, data)
        return data

    # ---- Accounts ----

    def get_accounts(self) -> list[dict[str, Any]]:
        data = self._read_accounts_payload()
        accounts = data.get("accounts", [])
        return accounts if isinstance(accounts, list) else []

    # ---- Cost basis methods ----

    def get_cost_basis_methods(self) -> dict[str, Any]:
        return self._read_cost_basis_methods_payload()

    def set_cost_basis_method(
        self,
        *,
        method: str,
        account: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        normalized_method = self._normalize_cost_basis_method(method, "")
        if not normalized_method:
            raise ValueError(f"Unsupported cost basis method: {method}")

        payload = self._read_cost_basis_methods_payload()

        if account and symbol:
            account_record = self._ensure_account(account, create_if_missing=True)
            account_id = str(account_record.get("id") or DEFAULT_ACCOUNT_ID)
            symbol_value = self._normalize_symbol(symbol)
            if not symbol_value:
                raise ValueError("symbol is required when setting a position cost basis method")
            payload.setdefault("by_position", {})[f"{account_id}:{symbol_value}"] = normalized_method
        elif account:
            account_record = self._ensure_account(account, create_if_missing=True)
            account_id = str(account_record.get("id") or DEFAULT_ACCOUNT_ID)
            payload.setdefault("by_account", {})[account_id] = normalized_method
        elif symbol:
            symbol_value = self._normalize_symbol(symbol)
            if not symbol_value:
                raise ValueError("symbol is required")
            payload.setdefault("by_symbol", {})[symbol_value] = normalized_method
        else:
            payload["global"] = normalized_method

        payload["updated_at"] = _utc_now()
        self._write_json(self._cost_basis_methods_path, payload)
        self._rebuild_holdings()
        return payload

    # ---- Manual prices ----

    def get_manual_prices(self) -> dict[str, Any]:
        return self._read_manual_prices_payload()

    # ---- FX rates ----

    def get_fx_rates(self) -> dict[str, Any]:
        return self._read_fx_rates_payload()

    def set_fx_rate(
        self,
        *,
        currency: str,
        rate: float,
        base_currency: str | None = None,
    ) -> dict[str, Any]:
        normalized_currency = str(currency or "").strip().upper()
        if not normalized_currency:
            raise ValueError("currency is required")

        normalized_rate = float(rate)
        if normalized_rate <= 0:
            raise ValueError("rate must be greater than 0")

        payload = self._read_fx_rates_payload()
        resolved_base_currency = (
            str(base_currency or payload.get("base_currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        )
        rates = payload.get("rates") if isinstance(payload.get("rates"), dict) else {}

        if resolved_base_currency != str(payload.get("base_currency") or DEFAULT_CURRENCY).strip().upper():
            rates = {resolved_base_currency: 1.0}

        rates[resolved_base_currency] = 1.0
        if normalized_currency == resolved_base_currency:
            rates[normalized_currency] = 1.0
        else:
            rates[normalized_currency] = round(normalized_rate, 8)

        next_payload = {
            "schema_version": FX_RATES_SCHEMA_VERSION,
            "base_currency": resolved_base_currency,
            "rates": rates,
            "updated_at": _utc_now(),
        }
        self._write_json(self._fx_rates_path, next_payload)
        self._rebuild_holdings()
        return next_payload

    def clear_fx_rate(self, currency: str) -> bool:
        normalized_currency = str(currency or "").strip().upper()
        if not normalized_currency:
            return False

        payload = self._read_fx_rates_payload()
        base_currency = str(payload.get("base_currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        if normalized_currency == base_currency:
            return False

        rates = payload.get("rates") if isinstance(payload.get("rates"), dict) else {}
        if normalized_currency not in rates:
            return False

        rates.pop(normalized_currency, None)
        rates[base_currency] = 1.0
        payload["updated_at"] = _utc_now()
        self._write_json(self._fx_rates_path, payload)
        self._rebuild_holdings()
        return True

    def set_manual_price(
        self,
        *,
        symbol: str,
        price: float,
        note: str = "",
    ) -> dict[str, Any]:
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")
        normalized_price = float(price)
        if normalized_price <= 0:
            raise ValueError("price must be greater than 0")

        payload = self._read_manual_prices_payload()
        by_symbol = payload.setdefault("by_symbol", {})
        by_symbol[normalized_symbol] = {
            "symbol": normalized_symbol,
            "price": round(normalized_price, 4),
            "note": str(note or ""),
            "updated_at": _utc_now(),
        }
        payload["updated_at"] = _utc_now()
        self._write_json(self._manual_prices_path, payload)
        self._rebuild_holdings()
        return payload

    def clear_manual_price(self, symbol: str) -> bool:
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            return False
        payload = self._read_manual_prices_payload()
        by_symbol = payload.get("by_symbol") if isinstance(payload.get("by_symbol"), dict) else {}
        if normalized_symbol not in by_symbol:
            return False

        by_symbol.pop(normalized_symbol, None)
        payload["updated_at"] = _utc_now()
        self._write_json(self._manual_prices_path, payload)
        self._rebuild_holdings()
        return True

    # ---- Custom assets ----

    def _existing_symbols(self) -> set[str]:
        symbols: set[str] = set()
        for txn in self._read_transactions():
            symbol = self._normalize_symbol(txn.get("symbol"))
            if symbol:
                symbols.add(symbol)
        for symbol in self.get_asset_metadata_map().keys():
            normalized = self._normalize_symbol(symbol)
            if normalized:
                symbols.add(normalized)
        return symbols

    def _generate_custom_asset_symbol(self, name: str, existing_symbols: set[str]) -> str:
        slug = self._slugify(name).upper()
        base = f"MANUAL_{slug}" if slug else "MANUAL_ASSET"
        candidate = base
        index = 1
        while candidate in existing_symbols:
            index += 1
            candidate = f"{base}_{index}"
        return candidate

    def list_custom_assets(self) -> list[dict[str, Any]]:
        holdings = self.get_holdings()
        by_symbol = holdings.get("holdings_by_symbol", {})
        if not isinstance(by_symbol, dict):
            return []

        items: list[dict[str, Any]] = []
        for symbol, row in by_symbol.items():
            if not isinstance(row, dict):
                continue
            data_source = str(row.get("data_source") or "").upper()
            is_custom = bool(row.get("is_custom_asset")) or data_source == "MANUAL"
            if not is_custom:
                continue
            items.append(
                {
                    "symbol": symbol,
                    "name": row.get("name") or symbol,
                    "asset_type": row.get("asset_type"),
                    "asset_class": row.get("asset_class"),
                    "sector": row.get("sector"),
                    "region": row.get("region"),
                    "data_source": data_source or None,
                    "valuation_method": row.get("valuation_method"),
                    "price_source": row.get("price_source"),
                    "quantity": round(_safe_float(row.get("quantity"), 0.0), 8),
                    "current_price": row.get("current_price"),
                    "current_value": round(_safe_float(row.get("current_value"), 0.0), 2),
                    "position_count": int(row.get("position_count") or 0),
                }
            )
        items.sort(key=lambda item: float(item.get("current_value") or 0.0), reverse=True)
        return items

    def create_custom_asset(
        self,
        *,
        name: str,
        value: float,
        account: str = DEFAULT_ACCOUNT_ID,
        asset_type: str = "custom_asset",
        asset_class: str | None = None,
        sector: str | None = None,
        region: str | None = None,
        symbol: str | None = None,
        date: str | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("name is required")

        normalized_value = float(value)
        if normalized_value <= 0:
            raise ValueError("value must be greater than 0")

        account_record = self._ensure_account(account, create_if_missing=True)
        account_id = str(account_record.get("id") or DEFAULT_ACCOUNT_ID)
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            normalized_symbol = self._generate_custom_asset_symbol(normalized_name, self._existing_symbols())

        metadata_payload = {
            "name": normalized_name,
            "asset_type": str(asset_type or "custom_asset"),
            "asset_class": asset_class,
            "sector": sector,
            "region": region,
            "data_source": "MANUAL",
            "is_custom_asset": True,
            "valuation_method": "MANUAL_PRICE_OVERRIDE",
        }
        self.upsert_asset_metadata(normalized_symbol, metadata_payload)

        activity_date = str(date or _utc_now().split("T")[0])
        self.add_transaction(
            date=activity_date,
            symbol=normalized_symbol,
            action="BUY",
            quantity=1.0,
            unit_price=normalized_value,
            fee=0.0,
            account=account_id,
            currency=str(account_record.get("currency") or DEFAULT_CURRENCY),
            note=str(note or ""),
            name=normalized_name,
            asset_type=str(asset_type or "custom_asset"),
            asset_class=asset_class,
            sector=sector,
            region=region,
        )
        self.set_manual_price(symbol=normalized_symbol, price=normalized_value, note=note)

        return {
            "symbol": normalized_symbol,
            "name": normalized_name,
            "account": account_id,
            "value": round(normalized_value, 2),
            "asset_type": str(asset_type or "custom_asset"),
            "asset_class": asset_class,
            "sector": sector,
            "region": region,
            "data_source": "MANUAL",
            "valuation_method": "MANUAL_PRICE_OVERRIDE",
        }

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
