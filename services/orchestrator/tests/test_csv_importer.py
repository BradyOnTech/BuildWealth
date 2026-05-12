from pathlib import Path

from buildwealth_orchestrator.services.csv_importer import (
    apply_existing_transaction_reconciliation,
    list_csv_templates,
    parse_transaction_csv,
)


def test_parse_transaction_csv_with_aliases_and_account_mapping(tmp_path: Path) -> None:
    csv_file = tmp_path / "broker.csv"
    csv_file.write_text(
        "Trade Date,Action,Ticker,Shares,Price,Commission,Account Name\n"
        "2026-01-10,Buy,VTI,10,250.50,1.25,Taxable Brokerage\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
        account_ids_by_name={"taxable brokerage": "acc-1"},
    )

    assert result.selected_template == "generic"
    assert result.detected_template == "generic"
    assert result.parsed_rows == 1
    assert len(result.errors) == 0
    assert len(result.activities) == 1

    activity = result.activities[0]
    assert activity["type"] == "BUY"
    assert activity["symbol"] == "VTI"
    assert activity["accountId"] == "acc-1"
    assert activity["accountName"] == "Taxable Brokerage"
    assert activity["quantity"] == 10
    assert activity["unitPrice"] == 250.5


def test_parse_transaction_csv_infers_dividend_values_from_amount(tmp_path: Path) -> None:
    csv_file = tmp_path / "dividends.csv"
    csv_file.write_text(
        "date,action,symbol,amount\n"
        "03/01/2026,dividend,SCHD,42.15\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert len(result.activities) == 1

    activity = result.activities[0]
    assert activity["type"] == "DIVIDEND"
    assert activity["quantity"] == 1
    assert activity["unitPrice"] == 42.15


def test_parse_transaction_csv_reports_unsupported_action(tmp_path: Path) -> None:
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(
        "date,action,symbol,quantity,unit_price\n"
        "2026-01-01,spin_off,VTI,1,1\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert len(result.activities) == 0
    assert len(result.errors) == 1


def test_parse_transaction_csv_supports_symbol_optional_cash_actions(tmp_path: Path) -> None:
    csv_file = tmp_path / "cash.csv"
    csv_file.write_text(
        "date,action,amount,account\n"
        "2026-01-01,deposit,5000,Taxable Brokerage\n"
        "2026-01-02,withdrawal,1500,Taxable Brokerage\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert len(result.activities) == 2
    assert result.activities[0]["type"] == "CASH_DEPOSIT"
    assert result.activities[0]["symbol"] == "CASH"
    assert result.activities[0]["quantity"] == 1
    assert result.activities[0]["unitPrice"] == 5000
    assert result.activities[1]["type"] == "CASH_WITHDRAW"
    assert result.activities[1]["symbol"] == "CASH"


def test_parse_transaction_csv_extracts_asset_metadata_columns(tmp_path: Path) -> None:
    csv_file = tmp_path / "metadata.csv"
    csv_file.write_text(
        "date,action,symbol,quantity,unit_price,name,asset class,sector,country,lot method\n"
        "2026-01-10,buy,QQQ,2,450,Invesco QQQ,US Stocks,Technology,US,FIFO\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert len(result.activities) == 1
    activity = result.activities[0]
    assert activity["name"] == "Invesco QQQ"
    assert activity["assetClass"] == "US Stocks"
    assert activity["sector"] == "Technology"
    assert activity["region"] == "US"
    assert activity["lotMethod"] == "FIFO"


def test_parse_transaction_csv_auto_detects_schwab(tmp_path: Path) -> None:
    csv_file = tmp_path / "schwab.csv"
    csv_file.write_text(
        "Date,Action,Symbol,Quantity,Price,Fees & Comm,Amount,Account\n"
        "2026-01-10,Buy,VTI,10,250.50,1.25,2506.25,Taxable Brokerage\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "schwab"
    assert result.detected_template == "schwab"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "BUY"


def test_parse_transaction_csv_auto_detects_fidelity(tmp_path: Path) -> None:
    csv_file = tmp_path / "fidelity.csv"
    csv_file.write_text(
        "Date,Account,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date\n"
        "01/15/2026,Taxable Brokerage,You Bought,VTI,Vanguard Total Stock Market,Cash,3,290.00,0,0,0,870.00,01/20/2026\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "fidelity"
    assert result.detected_template == "fidelity"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "BUY"


def test_parse_transaction_csv_auto_detects_vanguard(tmp_path: Path) -> None:
    csv_file = tmp_path / "vanguard.csv"
    csv_file.write_text(
        "Trade Date,Settlement Date,Transaction Type,Symbol,Name,Shares,Share Price,Principal Amount,Commission Fees,Net Amount,Account Type\n"
        "2026-02-01,2026-02-03,Dividend Received,SCHD,Schwab US Dividend Equity ETF,,,,0,45.25,Roth IRA\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "vanguard"
    assert result.detected_template == "vanguard"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "DIVIDEND"
    assert result.activities[0]["unitPrice"] == 45.25
    assert result.activities[0]["quantity"] == 1
    assert result.activities[0]["accountName"] == "Roth IRA"


def test_parse_transaction_csv_auto_detects_interactive_brokers(tmp_path: Path) -> None:
    csv_file = tmp_path / "ibkr.csv"
    csv_file.write_text(
        "CurrencyPrimary,Symbol,TradeDate,Buy/Sell,Quantity,TradePrice,IBCommission,NetCash,ClientAccountID,Description,AssetClass,SubCategory\n"
        "USD,VTI,20230403,BUY,17,204.3473,-1,-3474.9041,U1234567,VANGUARD TOTAL STOCK MKT ETF,STK,ETF\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "interactive_brokers"
    assert result.detected_template == "interactive_brokers"
    assert len(result.activities) == 1
    activity = result.activities[0]
    assert activity["type"] == "BUY"
    assert activity["date"].startswith("2023-04-03T")
    assert activity["fee"] == 1
    assert activity["quantity"] == 17
    assert activity["unitPrice"] == 204.3473
    assert activity["accountName"] == "U1234567"
    assert activity["assetClass"] == "STK"
    assert activity["assetType"] == "ETF"


def test_parse_transaction_csv_allows_template_override(tmp_path: Path) -> None:
    csv_file = tmp_path / "override.csv"
    csv_file.write_text(
        "CurrencyPrimary,Symbol,TradeDate,Buy/Sell,Quantity,TradePrice,IBCommission,NetCash\n"
        "USD,VTI,20230403,BUY,17,204.3473,-1,-3474.9041\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
        broker_template="generic",
    )

    assert not result.errors
    assert result.selected_template == "generic"
    assert result.detected_template == "interactive_brokers"
    assert any("auto-detect suggested" in warning for warning in result.warnings)


def test_parse_transaction_csv_rejects_unknown_template(tmp_path: Path) -> None:
    csv_file = tmp_path / "unknown.csv"
    csv_file.write_text(
        "date,action,symbol,quantity,unit_price\n"
        "2026-01-01,buy,VTI,1,1\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
        broker_template="unknown-template",
    )

    assert not result.activities
    assert result.errors
    assert "Unsupported broker_template" in result.errors[0]


def test_parse_transaction_csv_auto_detects_robinhood(tmp_path: Path) -> None:
    csv_file = tmp_path / "robinhood.csv"
    csv_file.write_text(
        "Activity Date,Process Date,Settle Date,Instrument,Description,Trans Code,Quantity,Price,Amount,Account\n"
        "2026-03-01,2026-03-01,2026-03-03,AAPL,Apple Inc,BTO,2,180,360,RH Taxable\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "robinhood"
    assert result.detected_template == "robinhood"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "BUY"
    assert result.activities[0]["symbol"] == "AAPL"


def test_parse_transaction_csv_auto_detects_etrade(tmp_path: Path) -> None:
    csv_file = tmp_path / "etrade.csv"
    csv_file.write_text(
        "Transaction Date,Transaction Type,Symbol,Description,Quantity,Price,Commission,Net Amount,Account\n"
        "2026-03-02,Sold,VTI,Vanguard Total Stock Market,1,300,0,300,Etrade Brokerage\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "etrade"
    assert result.detected_template == "etrade"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "SELL"
    assert result.activities[0]["accountName"] == "Etrade Brokerage"


def test_parse_transaction_csv_auto_detects_ally(tmp_path: Path) -> None:
    csv_file = tmp_path / "ally.csv"
    csv_file.write_text(
        "Trade Date,Activity Type,Symbol,Description,Quantity,Price,Amount,Account\n"
        "2026-03-03,Dividend,SCHD,Schwab US Dividend Equity ETF,,,25.10,Ally IRA\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "ally"
    assert result.detected_template == "ally"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "DIVIDEND"
    assert result.activities[0]["unitPrice"] == 25.1
    assert result.activities[0]["quantity"] == 1


def test_parse_transaction_csv_auto_detects_m1(tmp_path: Path) -> None:
    csv_file = tmp_path / "m1.csv"
    csv_file.write_text(
        "Date,Activity,Symbol,Description,Shares,Price,Amount,Account\n"
        "2026-03-04,BUY,QQQ,Invesco QQQ,0.5,430,215,M1 Invest\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "m1"
    assert result.detected_template == "m1"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "BUY"
    assert result.activities[0]["quantity"] == 0.5
    assert result.activities[0]["unitPrice"] == 430


def test_parse_transaction_csv_auto_detects_wealthfront(tmp_path: Path) -> None:
    csv_file = tmp_path / "wealthfront.csv"
    csv_file.write_text(
        "Date,Account,Type,Symbol,Description,Shares,Price,Amount,Fee\n"
        "2026-03-05,Wealthfront Taxable,Fee,CASH,Advisory Fee,,,3.25,3.25\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert not result.errors
    assert result.selected_template == "wealthfront"
    assert result.detected_template == "wealthfront"
    assert len(result.activities) == 1
    assert result.activities[0]["type"] == "FEE"
    assert result.activities[0]["symbol"] == "CASH"
    assert result.activities[0]["unitPrice"] == 3.25


def test_list_csv_templates_includes_required_brokers() -> None:
    templates = list_csv_templates()
    template_ids = {item["id"] for item in templates}

    assert "auto" in template_ids
    assert "generic" in template_ids
    assert "schwab" in template_ids
    assert "fidelity" in template_ids
    assert "vanguard" in template_ids
    assert "robinhood" in template_ids
    assert "etrade" in template_ids
    assert "interactive_brokers" in template_ids
    assert "ally" in template_ids
    assert "m1" in template_ids
    assert "wealthfront" in template_ids
    schwab = next(item for item in templates if item["id"] == "schwab")
    assert schwab["mapping_confidence"] == "known"
    assert "date" in schwab["required_columns"]
    assert "amount" in schwab["optional_columns"]


def test_parse_transaction_csv_emits_reconciliation_report_with_confidence_flags(tmp_path: Path) -> None:
    csv_file = tmp_path / "reconciliation.csv"
    csv_file.write_text(
        "date,action,symbol,quantity,unit_price,amount,account\n"
        "2026-01-10,buy,VTI,10,250.50,2505,Taxable Brokerage\n"
        "01/11/2026,dividend,SCHD,,,42.15,Taxable Brokerage\n"
        "2026-01-12,spin_off,VTI,1,1,1,Taxable Brokerage\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
        account_ids_by_name={"taxable brokerage": "acc-1"},
    )

    report = result.reconciliation_report
    assert report["total_rows"] == 3
    assert report["accepted_count"] == 2
    assert report["normalized_count"] == 2
    assert report["rejected_count"] == 1

    accepted = report["accepted_rows"]
    normalized = report["normalized_rows"]
    rejected = report["rejected_rows"]
    assert len(accepted) == 2
    assert len(normalized) == 2
    assert len(rejected) == 1
    normalized_by_row = {item["row_number"]: item for item in normalized}
    assert 3 in normalized_by_row
    assert normalized_by_row[3]["confidence_flag"] in {"medium", "low"}
    assert "quantity_defaulted_one" in normalized_by_row[3]["normalization_flags"]
    assert "unit_price_defaulted_from_amount" in normalized_by_row[3]["normalization_flags"]
    assert rejected[0]["row_number"] == 4
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["confidence_flag"] == "low"
    assert rejected[0]["rejection_reasons"]
    assert accepted[0]["transaction_fingerprint"]


def test_apply_existing_transaction_reconciliation_marks_duplicates_as_rejected(tmp_path: Path) -> None:
    csv_file = tmp_path / "duplicates.csv"
    csv_file.write_text(
        "date,action,symbol,quantity,unit_price,account\n"
        "2026-01-10,buy,VTI,10,250.5,Taxable Brokerage\n",
        encoding="utf-8",
    )

    parsed = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
        account_ids_by_name={"taxable brokerage": "acc-1"},
    )
    assert len(parsed.activities) == 1
    fingerprint = parsed.reconciliation_report["accepted_rows"][0]["transaction_fingerprint"]

    reconciled = apply_existing_transaction_reconciliation(
        parsed,
        existing_transactions=[
            {
                "date": "2026-01-10T00:00:00Z",
                "action": "BUY",
                "symbol": "VTI",
                "quantity": 10.0,
                "unit_price": 250.5,
                "fee": 0.0,
                "currency": "USD",
                "account": "acc-1",
            }
        ],
    )

    report = reconciled.reconciliation_report
    assert len(reconciled.activities) == 0
    assert report["accepted_count"] == 0
    assert report["rejected_count"] == 1
    assert report["rejected_rows"][0]["transaction_fingerprint"] == fingerprint
    assert "duplicate_existing_transaction" in report["rejected_rows"][0]["rejection_reasons"]
    assert any("already exist in the local ledger" in warning for warning in reconciled.warnings)
