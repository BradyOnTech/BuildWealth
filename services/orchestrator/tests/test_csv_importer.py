from pathlib import Path

from buildwealth_orchestrator.services.csv_importer import parse_transaction_csv


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
