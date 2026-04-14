from __future__ import annotations

import csv
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
    "buytocover": "BUY",
    "exchangebuy": "BUY",
    "sell": "SELL",
    "sold": "SELL",
    "yousold": "SELL",
    "selltoclose": "SELL",
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
    "deposit": "CASH_DEPOSIT",
    "cashcontribution": "CASH_DEPOSIT",
    "cashcontributioncurrentyear": "CASH_DEPOSIT",
    "cashcontributionprioryear": "CASH_DEPOSIT",
    "cashdeposit": "CASH_DEPOSIT",
    "cash_deposit": "CASH_DEPOSIT",
    "moneylinkdeposit": "CASH_DEPOSIT",
    "wirefundsreceived": "CASH_DEPOSIT",
    "withdraw": "CASH_WITHDRAW",
    "withdrawal": "CASH_WITHDRAW",
    "distribution": "CASH_WITHDRAW",
    "cashwithdraw": "CASH_WITHDRAW",
    "cash_withdraw": "CASH_WITHDRAW",
    "moneylinkwithdrawal": "CASH_WITHDRAW",
    "wirefundssent": "CASH_WITHDRAW",
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
            return output

        for row_num, raw_row in enumerate(reader, start=2):
            output.parsed_rows += 1
            row = _canonical_row_for_template(raw_row, selected_template)

            action = _parse_action(row.get("action"))
            if not action:
                output.errors.append(f"Row {row_num}: Unsupported or missing action '{row.get('action')}'.")
                continue

            date = _parse_date(row.get("date"))
            if not date:
                output.errors.append(f"Row {row_num}: Invalid or missing date '{row.get('date')}'.")
                continue

            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol and action in CASH_SYMBOL_OPTIONAL_ACTIONS:
                symbol = "CASH"
            if not symbol:
                output.errors.append(f"Row {row_num}: Missing symbol/ticker.")
                continue

            quantity = _parse_number(row.get("quantity"))
            unit_price = _parse_number(row.get("unit_price"))
            amount = _parse_number(row.get("amount"))
            fee = _parse_number(row.get("fee")) or 0.0

            if quantity is None and amount is not None and unit_price not in (None, 0):
                quantity = abs(amount) / abs(unit_price)

            if unit_price is None and amount is not None and quantity not in (None, 0):
                unit_price = abs(amount) / abs(quantity)

            if action in {"DIVIDEND", "INTEREST", "FEE", "TRANSFER_IN", "TRANSFER_OUT", "CASH_DEPOSIT", "CASH_WITHDRAW"}:
                quantity = quantity if quantity is not None else 1.0
                if unit_price is None and amount is not None:
                    unit_price = abs(amount)
            elif action == "STOCK_SPLIT":
                if quantity is None and amount is not None:
                    quantity = abs(amount)
                unit_price = unit_price if unit_price is not None else 0.0

            if quantity is None or unit_price is None:
                output.errors.append(
                    f"Row {row_num}: Could not infer quantity/unit price for {action}. quantity={row.get('quantity')} unit_price={row.get('unit_price')} amount={row.get('amount')}"
                )
                continue

            currency = (row.get("currency") or default_currency).strip().upper()
            data_source = (row.get("data_source") or default_data_source).strip().upper()

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

            output.activities.append(activity)

    return output


def archive_import_file(source_path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = archive_dir / f"{source_path.stem}-{timestamp}{source_path.suffix}"
    shutil.move(str(source_path), str(target))
    return target
