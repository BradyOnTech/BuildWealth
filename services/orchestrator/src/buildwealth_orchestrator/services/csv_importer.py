from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d %Y",
)

ACTION_MAP = {
    "buy": "BUY",
    "bought": "BUY",
    "purchase": "BUY",
    "reinvest": "BUY",
    "sell": "SELL",
    "sold": "SELL",
    "div": "DIVIDEND",
    "dividend": "DIVIDEND",
    "interest": "INTEREST",
    "fee": "FEE",
    "commission": "FEE",
}

FIELD_ALIASES = {
    "date": {"date", "tradedate", "activitydate", "transactiondate", "executiondate", "posteddate"},
    "action": {"action", "type", "transactiontype", "activitytype"},
    "symbol": {"symbol", "ticker", "security", "investment"},
    "quantity": {"quantity", "qty", "shares"},
    "unit_price": {"unitprice", "unit price", "price", "shareprice", "pricepershare"},
    "fee": {"fee", "fees", "commission"},
    "amount": {"amount", "netamount", "value", "total", "proceeds"},
    "currency": {"currency", "curr"},
    "data_source": {"datasource", "data source", "provider", "source"},
    "account_name": {"account", "accountname", "account number", "accountnumber"},
    "name": {"name", "securityname", "assetname", "security name", "asset name"},
    "asset_class": {"assetclass", "asset class", "class"},
    "asset_type": {"assettype", "asset type", "securitytype", "instrumenttype", "security type"},
    "sector": {"sector", "industrysector", "industry sector"},
    "region": {"region", "country", "geography"},
    "lot_method": {"lotmethod", "costbasismethod", "basis method", "cost basis method"},
    "comment": {"comment", "description", "memo", "notes"},
}


@dataclass
class CsvParseOutput:
    parsed_rows: int = 0
    activities: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)



def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())



def _parse_action(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", "", value.strip().lower())
    return ACTION_MAP.get(normalized)



def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None

    text = value.strip()
    if text == "":
        return None

    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")

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



def _canonical_row(raw_row: dict[str, str]) -> dict[str, str | None]:
    normalized = {_normalize_header(k): (v if v != "" else None) for k, v in raw_row.items()}

    result: dict[str, str | None] = {}
    for target, aliases in FIELD_ALIASES.items():
        value = None
        for alias in aliases:
            if alias in normalized:
                value = normalized[alias]
                break
            normalized_alias = _normalize_header(alias)
            if normalized_alias in normalized:
                value = normalized[normalized_alias]
                break
        result[target] = value

    return result



def parse_transaction_csv(
    file_path: Path,
    default_data_source: str,
    default_currency: str,
    delimiter: str = ",",
    account_ids_by_name: dict[str, str] | None = None,
) -> CsvParseOutput:
    output = CsvParseOutput()
    account_ids = account_ids_by_name or {}

    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)

        for row_num, raw_row in enumerate(reader, start=2):
            output.parsed_rows += 1
            row = _canonical_row(raw_row)

            action = _parse_action(row.get("action"))
            if not action:
                output.errors.append(f"Row {row_num}: Unsupported or missing action '{row.get('action')}'.")
                continue

            date = _parse_date(row.get("date"))
            if not date:
                output.errors.append(f"Row {row_num}: Invalid or missing date '{row.get('date')}'.")
                continue

            symbol = (row.get("symbol") or "").strip().upper()
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

            if action in {"DIVIDEND", "INTEREST", "FEE"}:
                quantity = quantity if quantity is not None else 1.0
                if unit_price is None and amount is not None:
                    unit_price = abs(amount)

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
