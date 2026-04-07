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
        "2026-01-01,transfer,VTI,1,1\n",
        encoding="utf-8",
    )

    result = parse_transaction_csv(
        file_path=csv_file,
        default_data_source="YAHOO",
        default_currency="USD",
    )

    assert len(result.activities) == 0
    assert len(result.errors) == 1
