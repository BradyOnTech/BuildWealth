from __future__ import annotations

# Import reconciliation and duplicate-signal behavior is informed by Ghostfolio
# import-service workflows:
# apps/api/src/app/import/import.service.ts

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d.%m.%Y",
    "%Y%m%d",
    "%Y%m%d;%H%M%S",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d %Y",
)

ACTION_MAP = {
    "buy": "BUY",
    "bought": "BUY",
    "purchase": "BUY",
    "reinvest": "BUY",
    "reinvestshares": "BUY",
    "reinvestdividend": "BUY",
    "reinvestment": "BUY",
    "youbought": "BUY",
    "buytoopen": "BUY",
    "buytoclose": "BUY",
    "buytocover": "BUY",
    "bto": "BUY",
    "btc": "BUY",
    "bot": "BUY",
    "exchangebuy": "BUY",
    "sell": "SELL",
    "sold": "SELL",
    "yousold": "SELL",
    "selltoclose": "SELL",
    "selltoopen": "SELL",
    "stc": "SELL",
    "sto": "SELL",
    "sld": "SELL",
    "div": "DIVIDEND",
    "dividend": "DIVIDEND",
    "cashdividend": "DIVIDEND",
    "qualifieddividend": "DIVIDEND",
    "ordinarydividend": "DIVIDEND",
    "dividendreceived": "DIVIDEND",
    "capitalgaindistribution": "DIVIDEND",
    "interest": "INTEREST",
    "bankinterest": "INTEREST",
    "fee": "FEE",
    "fees": "FEE",
    "commission": "FEE",
    "advisoryfee": "FEE",
    "servicefee": "FEE",
    "transferin": "TRANSFER_IN",
    "transferredin": "TRANSFER_IN",
    "transfer_in": "TRANSFER_IN",
    "transferout": "TRANSFER_OUT",
    "transferredout": "TRANSFER_OUT",
    "transfer_out": "TRANSFER_OUT",
    "acatin": "TRANSFER_IN",
    "acatout": "TRANSFER_OUT",
    "acatreceived": "TRANSFER_IN",
    "acatsent": "TRANSFER_OUT",
    "journalin": "TRANSFER_IN",
    "journalout": "TRANSFER_OUT",
    "incomingtransfer": "TRANSFER_IN",
    "outgoingtransfer": "TRANSFER_OUT",
    "deposit": "CASH_DEPOSIT",
    "cashcontribution": "CASH_DEPOSIT",
    "cashcontributioncurrentyear": "CASH_DEPOSIT",
    "cashcontributionprioryear": "CASH_DEPOSIT",
    "cashdeposit": "CASH_DEPOSIT",
    "cash_deposit": "CASH_DEPOSIT",
    "moneylinkdeposit": "CASH_DEPOSIT",
    "wirefundsreceived": "CASH_DEPOSIT",
    "wirein": "CASH_DEPOSIT",
    "achcredit": "CASH_DEPOSIT",
    "credit": "CASH_DEPOSIT",
    "contribution": "CASH_DEPOSIT",
    "withdraw": "CASH_WITHDRAW",
    "withdrawal": "CASH_WITHDRAW",
    "distribution": "CASH_WITHDRAW",
    "cashwithdraw": "CASH_WITHDRAW",
    "cash_withdraw": "CASH_WITHDRAW",
    "moneylinkwithdrawal": "CASH_WITHDRAW",
    "wirefundssent": "CASH_WITHDRAW",
    "wireout": "CASH_WITHDRAW",
    "achdebit": "CASH_WITHDRAW",
    "debit": "CASH_WITHDRAW",
    "stocksplit": "STOCK_SPLIT",
    "stock_split": "STOCK_SPLIT",
    "forwardsplit": "STOCK_SPLIT",
    "reversesplit": "STOCK_SPLIT",
    "split": "STOCK_SPLIT",
    "journaledshares": "TRANSFER_IN",
    "journal": "TRANSFER_IN",
    "merger": "MERGER",
}

FIELD_ALIASES = {
    "date": {
        "date",
        "datetime",
        "tradedate",
        "activitydate",
        "transactiondate",
        "executiondate",
        "posteddate",
        "rundate",
    },
    "action": {
        "action",
        "buy/sell",
        "buysell",
        "transcode",
        "transaction code",
        "type",
        "transactiontype",
        "activitytype",
        "activity",
        "transaction",
    },
    "symbol": {"symbol", "ticker", "code", "security", "investment", "instrument"},
    "quantity": {"quantity", "qty", "shares", "units"},
    "unit_price": {
        "unitprice",
        "unit price",
        "price",
        "shareprice",
        "pricepershare",
        "price($)",
        "share price",
        "tradeprice",
    },
    "fee": {
        "fee",
        "fees",
        "commission",
        "fees&comm",
        "fees and comm",
        "commission fees",
        "commission($)",
        "fees($)",
        "ibcommission",
    },
    "amount": {
        "amount",
        "netamount",
        "value",
        "total",
        "proceeds",
        "amount($)",
        "net amount",
        "principal amount",
        "principalamount",
        "netcash",
        "trademoney",
    },
    "currency": {"currency", "curr", "currencyprimary", "ibcommissioncurrency"},
    "data_source": {"datasource", "data source", "provider", "source"},
    "account_name": {
        "account",
        "accountname",
        "account number",
        "accountnumber",
        "account type",
        "clientaccountid",
        "accountalias",
    },
    "name": {"name", "securityname", "assetname", "security name", "asset name", "description"},
    "asset_class": {"assetclass", "asset class", "class"},
    "asset_type": {"assettype", "asset type", "securitytype", "instrumenttype", "security type", "subcategory"},
    "sector": {"sector", "industrysector", "industry sector"},
    "region": {"region", "country", "geography"},
    "lot_method": {"lotmethod", "costbasismethod", "basis method", "cost basis method"},
    "comment": {"comment", "description", "memo", "notes", "notes/codes"},
}

CASH_SYMBOL_OPTIONAL_ACTIONS = {
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "CASH_DEPOSIT",
    "CASH_WITHDRAW",
}

RECONCILIATION_MAJOR_INFERENCE_FLAGS = {
    "quantity_inferred_from_amount",
    "unit_price_inferred_from_amount",
    "quantity_defaulted_one",
    "unit_price_defaulted_from_amount",
    "symbol_defaulted_cash",
}

RECONCILIATION_REASON_BY_FLAG = {
    "action_normalized": "Action normalized from alias to canonical transaction type.",
    "date_normalized": "Date normalized into UTC ISO format.",
    "quantity_inferred_from_amount": "Quantity inferred from amount and unit price.",
    "unit_price_inferred_from_amount": "Unit price inferred from amount and quantity.",
    "quantity_defaulted_one": "Quantity defaulted to 1.0 for cashflow-style activity.",
    "unit_price_defaulted_from_amount": "Unit price defaulted from amount for cashflow-style activity.",
    "symbol_defaulted_cash": "Symbol defaulted to CASH for symbol-optional cash action.",
    "currency_defaulted": "Currency defaulted from import request defaults.",
    "data_source_defaulted": "Data source defaulted from import request defaults.",
    "account_missing_mapping": "Account was not mapped to a local account ID.",
    "duplicate_existing_transaction": "Transaction fingerprint already exists in local ledger.",
}

SUPPORTED_CSV_TEMPLATES: dict[str, dict[str, str]] = {
    "auto": {
        "id": "auto",
        "name": "Auto Detect",
        "description": "Detect broker format from CSV headers; falls back to generic mapping.",
    },
    "generic": {
        "id": "generic",
        "name": "Generic",
        "description": "Flexible generic mapping for normalized trade CSVs.",
    },
    "schwab": {
        "id": "schwab",
        "name": "Charles Schwab",
        "description": "Schwab transactions export (Date/Action/Symbol/Quantity/Price/Fees & Comm/Amount).",
    },
    "fidelity": {
        "id": "fidelity",
        "name": "Fidelity",
        "description": "Fidelity account history export with Amount/Price/Action columns.",
    },
    "vanguard": {
        "id": "vanguard",
        "name": "Vanguard",
        "description": "Vanguard transaction history export with Transaction Type and Share Price.",
    },
    "robinhood": {
        "id": "robinhood",
        "name": "Robinhood",
        "description": "Robinhood account statements with activity/instrument columns.",
    },
    "etrade": {
        "id": "etrade",
        "name": "E*TRADE",
        "description": "E*TRADE transaction export with transaction date/type and net amount.",
    },
    "interactive_brokers": {
        "id": "interactive_brokers",
        "name": "Interactive Brokers",
        "description": "Interactive Brokers Activity Statement CSV (CurrencyPrimary/Symbol/TradeDate/Buy-Sell).",
    },
    "ally": {
        "id": "ally",
        "name": "Ally Invest",
        "description": "Ally Invest transaction export with trade date and activity type.",
    },
    "m1": {
        "id": "m1",
        "name": "M1 Finance",
        "description": "M1 account activity export with symbol/quantity/price columns.",
    },
    "wealthfront": {
        "id": "wealthfront",
        "name": "Wealthfront",
        "description": "Wealthfront brokerage transaction export with trade activity details.",
    },
}

TEMPLATE_ORDER = [
    "auto",
    "generic",
    "schwab",
    "fidelity",
    "vanguard",
    "robinhood",
    "etrade",
    "interactive_brokers",
    "ally",
    "m1",
    "wealthfront",
]

TEMPLATE_ALIASES = {
    "ibkr": "interactive_brokers",
    "interactivebrokers": "interactive_brokers",
    "interactive-brokers": "interactive_brokers",
    "interactive brokers": "interactive_brokers",
    "charlesschwab": "schwab",
    "charles-schwab": "schwab",
    "charles schwab": "schwab",
    "e*trade": "etrade",
    "e-trade": "etrade",
}

TEMPLATE_FIELD_ALIASES: dict[str, dict[str, set[str]]] = {
    "schwab": {
        "date": {"date"},
        "action": {"action"},
        "symbol": {"symbol"},
        "quantity": {"quantity"},
        "unit_price": {"price"},
        "fee": {"fees&comm"},
        "amount": {"amount"},
        "name": {"description"},
    },
    "fidelity": {
        "date": {"date", "rundate", "tradedate"},
        "action": {"action", "transactiontype"},
        "symbol": {"symbol", "investment"},
        "quantity": {"quantity", "shares"},
        "unit_price": {"price($)", "price"},
        "fee": {"commission($)", "fees($)", "commission", "fees"},
        "amount": {"amount($)", "amount"},
        "account_name": {"account", "accountnumber", "account type"},
        "name": {"description"},
    },
    "vanguard": {
        "date": {"tradedate", "date"},
        "action": {"transactiontype", "action"},
        "symbol": {"symbol", "ticker"},
        "quantity": {"shares", "quantity"},
        "unit_price": {"shareprice", "price"},
        "fee": {"commissionfees", "fees"},
        "amount": {"netamount", "principalamount", "amount"},
        "account_name": {"account type", "account"},
        "name": {"name", "security"},
    },
    "interactive_brokers": {
        "date": {"tradedate", "datetime", "date"},
        "action": {"buy/sell", "buysell", "transactiontype"},
        "symbol": {"symbol", "code", "securityid"},
        "quantity": {"quantity"},
        "unit_price": {"tradeprice", "price"},
        "fee": {"ibcommission", "commission", "fee"},
        "amount": {"netcash", "proceeds", "trademoney", "amount"},
        "currency": {"currencyprimary", "currency"},
        "account_name": {"accountalias", "clientaccountid"},
        "asset_class": {"assetclass"},
        "asset_type": {"subcategory"},
        "name": {"description"},
    },
    "robinhood": {
        "date": {"activitydate", "processdate", "settledate", "date"},
        "action": {"transcode", "activity", "type", "transactiontype"},
        "symbol": {"instrument", "symbol", "ticker"},
        "quantity": {"quantity", "shares"},
        "unit_price": {"price", "tradeprice"},
        "amount": {"amount", "netamount"},
        "fee": {"fee", "fees", "commission"},
        "account_name": {"account", "accountnumber", "account name"},
        "name": {"description"},
        "comment": {"description"},
    },
    "etrade": {
        "date": {"transactiondate", "tradedate", "date"},
        "action": {"transactiontype", "activitytype", "type"},
        "symbol": {"symbol", "ticker", "security"},
        "quantity": {"quantity", "shares"},
        "unit_price": {"price", "shareprice"},
        "amount": {"amount", "netamount", "proceeds"},
        "fee": {"commission", "fee", "fees"},
        "account_name": {"account", "accountnumber", "account name"},
        "name": {"description", "security"},
    },
    "ally": {
        "date": {"tradedate", "date", "transactiondate"},
        "action": {"activitytype", "transactiontype", "type"},
        "symbol": {"symbol", "ticker", "security"},
        "quantity": {"quantity", "shares"},
        "unit_price": {"price", "shareprice"},
        "amount": {"amount", "netamount", "proceeds"},
        "fee": {"commission", "fee", "fees"},
        "account_name": {"account", "accountname", "account number"},
        "name": {"description", "security"},
    },
    "m1": {
        "date": {"date", "activitydate", "tradedate"},
        "action": {"activity", "type", "action"},
        "symbol": {"symbol", "ticker"},
        "quantity": {"shares", "quantity", "units"},
        "unit_price": {"price", "shareprice"},
        "amount": {"amount", "netamount"},
        "account_name": {"account", "accountname"},
        "name": {"description", "name"},
    },
    "wealthfront": {
        "date": {"date", "tradedate", "transactiondate"},
        "action": {"type", "activity", "transactiontype"},
        "symbol": {"symbol", "ticker", "instrument"},
        "quantity": {"quantity", "shares"},
        "unit_price": {"price", "shareprice"},
        "amount": {"amount", "netamount", "proceeds"},
        "fee": {"fee", "fees", "commission"},
        "account_name": {"account", "account name", "accountnumber"},
        "name": {"description", "security", "name"},
    },
}

# Header signatures are based on Ghostfolio import fixture patterns and
# common broker export schemas. They are used only for lightweight matching.
TEMPLATE_HEADER_SIGNATURES: dict[str, set[str]] = {
    "schwab": {"date", "action", "symbol", "quantity", "price", "feescomm", "amount"},
    "fidelity": {"date", "action", "symbol", "quantity", "price", "amount", "accruedinterest"},
    "vanguard": {"tradedate", "transactiontype", "symbol", "shares", "shareprice", "principalamount", "netamount"},
    "robinhood": {"activitydate", "processdate", "settledate", "instrument", "transcode", "quantity", "price", "amount"},
    "etrade": {"transactiondate", "transactiontype", "symbol", "quantity", "price", "commission", "netamount"},
    "interactive_brokers": {"currencyprimary", "symbol", "tradedate", "buysell", "quantity", "tradeprice", "ibcommission", "netcash"},
    "ally": {"tradedate", "activitytype", "symbol", "description", "quantity", "price", "amount"},
    "m1": {"date", "activity", "symbol", "shares", "price", "amount"},
    "wealthfront": {"date", "account", "type", "symbol", "shares", "price", "amount"},
}


@dataclass
class CsvParseOutput:
    parsed_rows: int = 0
    activities: list[dict] = field(default_factory=list)
    activity_fingerprints: list[str] = field(default_factory=list)
    reconciliation_rows: list[dict[str, Any]] = field(default_factory=list)
    reconciliation_report: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    selected_template: str = "generic"
    detected_template: str = "generic"


def list_csv_templates() -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    for template_id in TEMPLATE_ORDER:
        descriptor = SUPPORTED_CSV_TEMPLATES.get(template_id)
        if descriptor:
            templates.append(descriptor)
    return templates


def _normalize_template_id(template_id: str | None) -> str:
    value = str(template_id or "").strip().lower()
    if not value:
        return "auto"
    return TEMPLATE_ALIASES.get(value, value)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _normalize_aliases(aliases: set[str]) -> set[str]:
    return {_normalize_header(alias) for alias in aliases if alias}


FIELD_ALIASES_NORMALIZED = {
    target: _normalize_aliases(aliases)
    for target, aliases in FIELD_ALIASES.items()
}

TEMPLATE_FIELD_ALIASES_NORMALIZED: dict[str, dict[str, set[str]]] = {
    template_id: {
        field: _normalize_aliases(aliases)
        for field, aliases in alias_map.items()
    }
    for template_id, alias_map in TEMPLATE_FIELD_ALIASES.items()
}


def _detect_csv_template(fieldnames: list[str] | None) -> str:
    if not fieldnames:
        return "generic"

    normalized_headers = {_normalize_header(field) for field in fieldnames if field}
    best_template = "generic"
    best_hits = 0
    best_ratio = 0.0

    for template_id, markers in TEMPLATE_HEADER_SIGNATURES.items():
        if not markers:
            continue
        hits = len(markers.intersection(normalized_headers))
        min_hits = max(2, int(len(markers) * 0.6))
        if hits < min_hits:
            continue
        ratio = hits / len(markers)
        if ratio > best_ratio or (ratio == best_ratio and hits > best_hits):
            best_template = template_id
            best_hits = hits
            best_ratio = ratio

    return best_template


def _parse_action(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_header(value)
    return ACTION_MAP.get(normalized)


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None

    text = value.strip()
    if text == "":
        return None

    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]
        negative = True
    cleaned = cleaned.replace("+", "")

    try:
        number = float(cleaned)
    except ValueError:
        return None

    return -number if negative else number


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue

    return None


def _normalize_row(raw_row: dict[str, Any]) -> dict[str, str | None]:
    normalized: dict[str, str | None] = {}
    for key, raw_value in raw_row.items():
        if not key:
            continue
        header = _normalize_header(key)
        if not header:
            continue
        if raw_value is None:
            normalized[header] = None
            continue
        value = str(raw_value).strip()
        normalized[header] = value or None
    return normalized


def _resolve_field_value(
    normalized_row: dict[str, str | None],
    field_name: str,
    template_id: str,
) -> str | None:
    template_aliases = TEMPLATE_FIELD_ALIASES_NORMALIZED.get(template_id, {}).get(field_name, set())
    for alias in template_aliases:
        value = normalized_row.get(alias)
        if value is not None:
            return value

    aliases = FIELD_ALIASES_NORMALIZED.get(field_name, set())
    for alias in aliases:
        value = normalized_row.get(alias)
        if value is not None:
            return value

    return None


def _canonical_row(raw_row: dict[str, str]) -> dict[str, str | None]:
    return _canonical_row_for_template(raw_row, "generic")


def _canonical_row_for_template(
    raw_row: dict[str, str],
    template_id: str,
) -> dict[str, str | None]:
    normalized_row = _normalize_row(raw_row)
    result: dict[str, str | None] = {}
    for field_name in FIELD_ALIASES_NORMALIZED:
        result[field_name] = _resolve_field_value(normalized_row, field_name, template_id)
    return result


def _clean_raw_row(raw_row: dict[str, Any]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_key, raw_value in raw_row.items():
        if raw_key is None:
            continue
        key = str(raw_key)
        payload[key] = "" if raw_value is None else str(raw_value)
    return payload


def _transaction_fingerprint_payload(item: dict[str, Any]) -> dict[str, Any]:
    date_text = str(item.get("date") or "").strip()
    date_value = date_text[:10] if len(date_text) >= 10 else date_text
    action_value = str(item.get("action") or item.get("type") or "").strip().upper()
    symbol_value = str(item.get("symbol") or "").strip().upper()
    quantity_raw = item.get("quantity")
    unit_price_raw = item.get("unit_price", item.get("unitPrice"))
    fee_raw = item.get("fee")
    quantity_value = round(abs(_parse_number(str(quantity_raw)) or _safe_float(quantity_raw, 0.0)), 8)
    unit_price_value = round(abs(_parse_number(str(unit_price_raw)) or _safe_float(unit_price_raw, 0.0)), 8)
    fee_value = round(abs(_parse_number(str(fee_raw)) or _safe_float(fee_raw, 0.0)), 8)
    currency_value = str(item.get("currency") or "USD").strip().upper() or "USD"
    account_value = (
        str(
            item.get("account")
            or item.get("accountId")
            or item.get("account_id")
            or item.get("accountName")
            or item.get("account_name")
            or ""
        )
        .strip()
        .lower()
    )
    return {
        "date": date_value,
        "action": action_value,
        "symbol": symbol_value,
        "quantity": quantity_value,
        "unit_price": unit_price_value,
        "fee": fee_value,
        "currency": currency_value,
        "account": account_value,
    }


def _transaction_fingerprint(item: dict[str, Any]) -> str:
    payload = _transaction_fingerprint_payload(item)
    if not payload["date"] or not payload["action"] or not payload["symbol"]:
        return ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]


def _confidence_from_row_status(
    *,
    status: str,
    normalization_flags: list[str],
    rejection_reasons: list[str],
) -> tuple[float, str, list[str]]:
    if status != "accepted":
        reasons = rejection_reasons or ["Row rejected by parser validation."]
        return 0.0, "low", reasons

    unique_flags: list[str] = []
    seen_flags: set[str] = set()
    for raw_flag in normalization_flags:
        flag = str(raw_flag).strip()
        if not flag or flag in seen_flags:
            continue
        seen_flags.add(flag)
        unique_flags.append(flag)

    if not unique_flags:
        return 1.0, "high", ["Canonical mapping with no inferred fields."]

    score = 1.0 - (0.1 * len(unique_flags))
    if any(flag in RECONCILIATION_MAJOR_INFERENCE_FLAGS for flag in unique_flags):
        score = min(score, 0.65)
    if len([flag for flag in unique_flags if flag in RECONCILIATION_MAJOR_INFERENCE_FLAGS]) > 1:
        score = min(score, 0.45)
    score = max(0.2, min(1.0, score))

    if score >= 0.85:
        flag = "high"
    elif score >= 0.55:
        flag = "medium"
    else:
        flag = "low"

    reasons = [RECONCILIATION_REASON_BY_FLAG.get(raw_flag, raw_flag.replace("_", " ")) for raw_flag in unique_flags]
    return round(score, 4), flag, reasons


def _rebuild_reconciliation_report(output: CsvParseOutput) -> None:
    accepted_rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []

    for row in output.reconciliation_rows:
        normalization_flags = [
            str(flag).strip()
            for flag in row.get("normalization_flags", [])
            if str(flag).strip()
        ]
        rejection_reasons = [
            str(reason).strip()
            for reason in row.get("rejection_reasons", [])
            if str(reason).strip()
        ]
        score, confidence_flag, confidence_reasons = _confidence_from_row_status(
            status=str(row.get("status") or "rejected"),
            normalization_flags=normalization_flags,
            rejection_reasons=rejection_reasons,
        )
        row["normalization_flags"] = normalization_flags
        row["rejection_reasons"] = rejection_reasons
        row["confidence_score"] = score
        row["confidence_flag"] = confidence_flag
        row["confidence_reasons"] = confidence_reasons

        public_row = {key: value for key, value in row.items() if key != "_activity_index"}
        if str(row.get("status") or "") == "accepted":
            accepted_rows.append(public_row)
            if normalization_flags:
                normalized_rows.append(public_row)
        else:
            rejected_rows.append(public_row)

    total_rows = len(output.reconciliation_rows)
    accepted_count = len(accepted_rows)
    normalized_count = len(normalized_rows)
    rejected_count = len(rejected_rows)

    if total_rows == 0:
        parser_score = 0.0
    else:
        acceptance_ratio = accepted_count / total_rows
        normalization_ratio = (normalized_count / accepted_count) if accepted_count else 1.0
        parser_score = acceptance_ratio - (0.2 * normalization_ratio)
        parser_score = max(0.0, min(1.0, parser_score))

    parser_flags: list[str] = []
    if output.selected_template != output.detected_template and output.detected_template != "generic":
        parser_flags.append("template_override_mismatch")
    if rejected_count:
        parser_flags.append("contains_rejected_rows")
    if normalized_count:
        parser_flags.append("contains_normalized_rows")

    if parser_score >= 0.85:
        parser_confidence_flag = "high"
    elif parser_score >= 0.55:
        parser_confidence_flag = "medium"
    else:
        parser_confidence_flag = "low"

    output.reconciliation_report = {
        "schema_version": 1,
        "parser_confidence_flag": parser_confidence_flag,
        "parser_confidence_score": round(parser_score, 4),
        "parser_confidence_flags": parser_flags,
        "total_rows": total_rows,
        "accepted_count": accepted_count,
        "normalized_count": normalized_count,
        "rejected_count": rejected_count,
        "accepted_rows": accepted_rows,
        "normalized_rows": normalized_rows,
        "rejected_rows": rejected_rows,
    }


def apply_existing_transaction_reconciliation(
    output: CsvParseOutput,
    *,
    existing_transactions: list[dict[str, Any]],
) -> CsvParseOutput:
    existing_fingerprints = {
        _transaction_fingerprint(item)
        for item in existing_transactions
        if isinstance(item, dict)
    }
    existing_fingerprints.discard("")
    if not existing_fingerprints:
        _rebuild_reconciliation_report(output)
        return output

    duplicate_count = 0
    for row in output.reconciliation_rows:
        if str(row.get("status") or "") != "accepted":
            continue
        fingerprint = str(row.get("transaction_fingerprint") or "").strip()
        if not fingerprint or fingerprint not in existing_fingerprints:
            continue
        duplicate_count += 1
        row["status"] = "rejected"
        rejection_reasons = row.setdefault("rejection_reasons", [])
        if "duplicate_existing_transaction" not in rejection_reasons:
            rejection_reasons.append("duplicate_existing_transaction")

    if duplicate_count:
        output.warnings.append(
            f"Rejected {duplicate_count} row(s) because matching transactions already exist in the local ledger."
        )

    original_activities = list(output.activities)
    original_fingerprints = list(output.activity_fingerprints)
    filtered_activities: list[dict[str, Any]] = []
    filtered_fingerprints: list[str] = []
    for row in output.reconciliation_rows:
        if str(row.get("status") or "") != "accepted":
            continue
        activity_index = row.get("_activity_index")
        if not isinstance(activity_index, int):
            continue
        if activity_index < 0 or activity_index >= len(original_activities):
            continue
        filtered_activities.append(original_activities[activity_index])
        if activity_index < len(original_fingerprints):
            filtered_fingerprints.append(original_fingerprints[activity_index])

    output.activities = filtered_activities
    output.activity_fingerprints = filtered_fingerprints
    _rebuild_reconciliation_report(output)
    return output


def parse_transaction_csv(
    file_path: Path,
    default_data_source: str,
    default_currency: str,
    delimiter: str = ",",
    account_ids_by_name: dict[str, str] | None = None,
    broker_template: str = "auto",
) -> CsvParseOutput:
    requested_template = _normalize_template_id(broker_template)
    output = CsvParseOutput(selected_template=requested_template)
    account_ids = account_ids_by_name or {}

    if requested_template not in SUPPORTED_CSV_TEMPLATES:
        output.errors.append(
            f"Unsupported broker_template '{broker_template}'. Supported templates: {', '.join(TEMPLATE_ORDER)}"
        )
        output.selected_template = "generic"
        output.detected_template = "generic"
        _rebuild_reconciliation_report(output)
        return output

    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)

        detected_template = _detect_csv_template(reader.fieldnames)
        output.detected_template = detected_template

        selected_template = detected_template if requested_template == "auto" else requested_template
        if selected_template == "auto":
            selected_template = "generic"
        output.selected_template = selected_template

        if requested_template == "auto" and detected_template == "generic":
            output.warnings.append("Could not detect a broker template from headers. Falling back to generic mapping.")
        elif requested_template != "auto" and detected_template != "generic" and requested_template != detected_template:
            output.warnings.append(
                f"Using template '{requested_template}' (header auto-detect suggested '{detected_template}')."
            )

        if not reader.fieldnames:
            output.errors.append("CSV header row is missing.")
            _rebuild_reconciliation_report(output)
            return output

        for row_num, raw_row in enumerate(reader, start=2):
            output.parsed_rows += 1
            raw_row_payload = _clean_raw_row(raw_row)
            row = _canonical_row_for_template(raw_row_payload, selected_template)
            normalization_flags: list[str] = []

            normalized_row_payload: dict[str, Any] = {
                "date": row.get("date"),
                "action": row.get("action"),
                "symbol": row.get("symbol"),
                "quantity": row.get("quantity"),
                "unit_price": row.get("unit_price"),
                "amount": row.get("amount"),
                "fee": row.get("fee"),
                "currency": row.get("currency"),
                "data_source": row.get("data_source"),
                "account_name": row.get("account_name"),
            }

            def append_rejected(reason: str) -> None:
                output.reconciliation_rows.append(
                    {
                        "row_number": row_num,
                        "status": "rejected",
                        "normalization_flags": list(normalization_flags),
                        "rejection_reasons": [reason],
                        "transaction_fingerprint": None,
                        "raw_row": raw_row_payload,
                        "normalized_row": normalized_row_payload,
                    }
                )

            raw_action = row.get("action")
            action = _parse_action(raw_action)
            if action and raw_action and _normalize_header(raw_action) != _normalize_header(action):
                normalization_flags.append("action_normalized")
            if not action:
                reason = f"unsupported_or_missing_action:{row.get('action')}"
                output.errors.append(f"Row {row_num}: Unsupported or missing action '{row.get('action')}'.")
                append_rejected(reason)
                continue
            normalized_row_payload["action"] = action

            raw_date = row.get("date")
            date = _parse_date(raw_date)
            if date and raw_date and str(raw_date).strip()[:10] != date[:10]:
                normalization_flags.append("date_normalized")
            if not date:
                reason = f"invalid_or_missing_date:{row.get('date')}"
                output.errors.append(f"Row {row_num}: Invalid or missing date '{row.get('date')}'.")
                append_rejected(reason)
                continue
            normalized_row_payload["date"] = date

            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol and action in CASH_SYMBOL_OPTIONAL_ACTIONS:
                symbol = "CASH"
                normalization_flags.append("symbol_defaulted_cash")
            if not symbol:
                reason = "missing_symbol"
                output.errors.append(f"Row {row_num}: Missing symbol/ticker.")
                append_rejected(reason)
                continue
            normalized_row_payload["symbol"] = symbol

            quantity = _parse_number(row.get("quantity"))
            unit_price = _parse_number(row.get("unit_price"))
            amount = _parse_number(row.get("amount"))
            fee = _parse_number(row.get("fee")) or 0.0

            if quantity is None and amount is not None and unit_price not in (None, 0):
                quantity = abs(amount) / abs(unit_price)
                normalization_flags.append("quantity_inferred_from_amount")

            if unit_price is None and amount is not None and quantity not in (None, 0):
                unit_price = abs(amount) / abs(quantity)
                normalization_flags.append("unit_price_inferred_from_amount")

            if action in {"DIVIDEND", "INTEREST", "FEE", "TRANSFER_IN", "TRANSFER_OUT", "CASH_DEPOSIT", "CASH_WITHDRAW"}:
                if quantity is None:
                    quantity = 1.0
                    normalization_flags.append("quantity_defaulted_one")
                if unit_price is None and amount is not None:
                    unit_price = abs(amount)
                    normalization_flags.append("unit_price_defaulted_from_amount")
            elif action == "STOCK_SPLIT":
                if quantity is None and amount is not None:
                    quantity = abs(amount)
                    normalization_flags.append("quantity_inferred_from_amount")
                unit_price = unit_price if unit_price is not None else 0.0

            if quantity is None or unit_price is None:
                reason = "unable_to_infer_quantity_or_unit_price"
                output.errors.append(
                    f"Row {row_num}: Could not infer quantity/unit price for {action}. quantity={row.get('quantity')} unit_price={row.get('unit_price')} amount={row.get('amount')}"
                )
                append_rejected(reason)
                continue

            raw_currency = str(row.get("currency") or "").strip()
            raw_data_source = str(row.get("data_source") or "").strip()
            currency = (raw_currency or default_currency).strip().upper()
            data_source = (raw_data_source or default_data_source).strip().upper()
            if not raw_currency:
                normalization_flags.append("currency_defaulted")
            if not raw_data_source:
                normalization_flags.append("data_source_defaulted")

            activity = {
                "currency": currency,
                "dataSource": data_source,
                "date": date,
                "fee": round(abs(fee), 6),
                "quantity": round(abs(quantity), 8),
                "symbol": symbol,
                "type": action,
                "unitPrice": round(abs(unit_price), 8),
            }

            comment = (row.get("comment") or "").strip()
            if comment:
                activity["comment"] = comment

            account_name = (row.get("account_name") or "").strip()
            if account_name:
                activity["accountName"] = account_name
                account_id = account_ids.get(account_name.lower())
                if account_id:
                    activity["accountId"] = account_id
                else:
                    normalization_flags.append("account_missing_mapping")
                    output.warnings.append(
                        f"Row {row_num}: Account '{account_name}' was not found in local accounts. Importing without accountId."
                    )

            name = (row.get("name") or "").strip()
            if name:
                activity["name"] = name

            asset_class = (row.get("asset_class") or "").strip()
            if asset_class:
                activity["assetClass"] = asset_class

            asset_type = (row.get("asset_type") or "").strip()
            if asset_type:
                activity["assetType"] = asset_type

            sector = (row.get("sector") or "").strip()
            if sector:
                activity["sector"] = sector

            region = (row.get("region") or "").strip()
            if region:
                activity["region"] = region

            lot_method = (row.get("lot_method") or "").strip().upper()
            if lot_method:
                activity["lotMethod"] = lot_method

            normalized_row_payload.update(
                {
                    "date": date,
                    "action": action,
                    "symbol": symbol,
                    "quantity": round(abs(quantity), 8),
                    "unit_price": round(abs(unit_price), 8),
                    "amount": amount,
                    "fee": round(abs(fee), 6),
                    "currency": currency,
                    "data_source": data_source,
                    "account_name": account_name or None,
                }
            )

            activity_index = len(output.activities)
            output.activities.append(activity)
            transaction_fingerprint = _transaction_fingerprint(activity)
            output.activity_fingerprints.append(transaction_fingerprint)
            output.reconciliation_rows.append(
                {
                    "row_number": row_num,
                    "status": "accepted",
                    "normalization_flags": normalization_flags,
                    "rejection_reasons": [],
                    "transaction_fingerprint": transaction_fingerprint or None,
                    "raw_row": raw_row_payload,
                    "normalized_row": normalized_row_payload,
                    "_activity_index": activity_index,
                }
            )

    _rebuild_reconciliation_report(output)
    return output


def archive_import_file(source_path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = archive_dir / f"{source_path.stem}-{timestamp}{source_path.suffix}"
    shutil.move(str(source_path), str(target))
    return target
