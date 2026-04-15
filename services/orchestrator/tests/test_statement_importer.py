from buildwealth_orchestrator.services.statement_importer import (
    parse_statement_csv,
    _normalize_merchant,
    _infer_category,
    _parse_amount,
)


CHASE_CSV = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
01/05/2026,01/06/2026,NETFLIX.COM,Entertainment,Sale,-15.99,
01/05/2026,01/06/2026,TRADER JOE'S #123,Groceries,Sale,-87.43,
01/10/2026,01/11/2026,SPOTIFY USA,Entertainment,Sale,-10.99,
01/12/2026,01/13/2026,XCEL ENERGY,Utilities,Sale,-142.50,
01/15/2026,01/16/2026,COSTCO WHSE #1234,Groceries,Sale,-215.60,
01/20/2026,01/21/2026,NETFLIX.COM,Entertainment,Sale,-15.99,
01/22/2026,01/23/2026,STARBUCKS #5678,Food & Drink,Sale,-6.25,
01/25/2026,01/26/2026,TRADER JOE'S #123,Groceries,Sale,-92.10,
02/01/2026,02/02/2026,RENT PAYMENT,Bills & Utilities,Sale,-1800.00,
02/05/2026,02/06/2026,NETFLIX.COM,Entertainment,Sale,-15.99,
02/05/2026,02/06/2026,SPOTIFY USA,Entertainment,Sale,-10.99,
02/10/2026,02/11/2026,XCEL ENERGY,Utilities,Sale,-138.75,
02/15/2026,02/16/2026,TRADER JOE'S #123,Groceries,Sale,-105.20,
02/20/2026,02/21/2026,COSTCO WHSE #1234,Groceries,Sale,-189.40,
"""

AMEX_CSV = """Date,Description,Amount
01/15/2026,AMAZON.COM*1A2B3C,$45.99
01/20/2026,WHOLE FOODS MKT,$112.30
02/01/2026,COMCAST CABLE,$89.99
02/05/2026,AMAZON.COM*4D5E6F,$23.50
02/10/2026,WHOLE FOODS MKT,$98.75
"""

BANK_CSV = """Date,Description,Amount,Type
01/02/2026,PAYROLL - ACME CORP,4250.00,Credit
01/05/2026,RENT AUTOPAY,-1800.00,Debit
01/10/2026,XCEL ENERGY,-145.00,Debit
01/15/2026,TARGET #1234,-67.50,Debit
01/16/2026,PAYROLL - ACME CORP,4250.00,Credit
02/01/2026,RENT AUTOPAY,-1800.00,Debit
02/02/2026,PAYROLL - ACME CORP,4250.00,Credit
"""


class TestChaseFormat:
    def test_parses_transactions(self):
        result = parse_statement_csv(CHASE_CSV)
        assert len(result.transactions) > 10
        assert result.parse_errors == []

    def test_detects_date_range(self):
        result = parse_statement_csv(CHASE_CSV)
        assert result.date_range_start is not None
        assert result.date_range_end is not None
        assert result.date_range_start < result.date_range_end

    def test_generates_expense_suggestions(self):
        result = parse_statement_csv(CHASE_CSV)
        assert len(result.expense_suggestions) > 0
        labels = [s.label.lower() for s in result.expense_suggestions]
        assert any("netflix" in label for label in labels)

    def test_recurring_marked_fixed(self):
        result = parse_statement_csv(CHASE_CSV)
        netflix = next((s for s in result.expense_suggestions if "netflix" in s.label.lower()), None)
        assert netflix is not None
        assert netflix.is_fixed is True
        assert netflix.transaction_count >= 2

    def test_categories_from_csv(self):
        result = parse_statement_csv(CHASE_CSV)
        # Chase CSV has Category column — Netflix is "entertainment" in the CSV data
        netflix = next((s for s in result.expense_suggestions if "netflix" in s.label.lower()), None)
        assert netflix is not None
        assert netflix.category == "entertainment"

    def test_categories_inferred_without_column(self):
        # Without a Category column, inference kicks in
        csv_no_cat = "Date,Description,Amount\n01/05/2026,NETFLIX.COM,-15.99\n01/10/2026,SPOTIFY USA,-10.99\n"
        result = parse_statement_csv(csv_no_cat)
        netflix = next((s for s in result.expense_suggestions if "netflix" in s.label.lower()), None)
        assert netflix is not None
        assert netflix.category == "subscriptions"


class TestAmexFormat:
    def test_parses_positive_amounts(self):
        result = parse_statement_csv(AMEX_CSV)
        assert len(result.transactions) == 5
        assert all(t.amount > 0 for t in result.transactions)

    def test_generates_suggestions(self):
        result = parse_statement_csv(AMEX_CSV)
        assert len(result.expense_suggestions) > 0


class TestBankFormat:
    def test_separates_income_and_expenses(self):
        result = parse_statement_csv(BANK_CSV)
        assert len(result.income_suggestions) > 0
        assert len(result.expense_suggestions) > 0

    def test_detects_payroll_as_income(self):
        result = parse_statement_csv(BANK_CSV)
        payroll = next((s for s in result.income_suggestions if "payroll" in s.label.lower() or "acme" in s.label.lower()), None)
        assert payroll is not None
        assert payroll.monthly_amount_usd > 4000

    def test_negative_amounts_are_expenses(self):
        result = parse_statement_csv(BANK_CSV)
        rent = next((s for s in result.expense_suggestions if "rent" in s.label.lower()), None)
        assert rent is not None
        assert rent.monthly_amount_usd > 1000


class TestColumnDetection:
    def test_custom_headers(self):
        csv_text = "Booking Date,Narrative,Total\n01/05/2026,GROCERY STORE,-50.00\n"
        result = parse_statement_csv(csv_text)
        assert len(result.transactions) == 1

    def test_missing_date_column(self):
        csv_text = "Merchant,Cost\nGrocery,50.00\n"
        result = parse_statement_csv(csv_text)
        # Should still parse if amount column found
        assert len(result.transactions) == 1

    def test_missing_amount_column(self):
        csv_text = "Date,Description\n01/05/2026,Something\n"
        result = parse_statement_csv(csv_text)
        assert len(result.parse_errors) > 0


class TestMerchantNormalization:
    def test_strips_trailing_numbers(self):
        assert _normalize_merchant("TRADER JOE'S #12345") == "trader joe's"

    def test_strips_state_codes(self):
        assert _normalize_merchant("STARBUCKS MN") == "starbucks"

    def test_strips_dates(self):
        assert _normalize_merchant("AMAZON 01/15") == "amazon"


class TestCategoryInference:
    def test_groceries(self):
        assert _infer_category("TRADER JOE'S") == "groceries"
        assert _infer_category("COSTCO WHOLESALE") == "groceries"

    def test_subscriptions(self):
        assert _infer_category("NETFLIX.COM") == "subscriptions"
        assert _infer_category("SPOTIFY USA") == "subscriptions"

    def test_utilities(self):
        assert _infer_category("XCEL ENERGY") == "utilities"

    def test_unknown_defaults_general(self):
        assert _infer_category("RANDOM STORE XYZ") == "general"


class TestAmountParsing:
    def test_negative(self):
        assert _parse_amount("-50.00") == -50.00

    def test_dollar_sign(self):
        assert _parse_amount("$123.45") == 123.45

    def test_commas(self):
        assert _parse_amount("1,234.56") == 1234.56

    def test_parenthesized_negative(self):
        assert _parse_amount("(100.00)") == -100.00

    def test_empty(self):
        assert _parse_amount("") is None
        assert _parse_amount("-") is None


class TestEdgeCases:
    def test_empty_csv(self):
        result = parse_statement_csv("")
        assert result.parse_errors != []

    def test_header_only(self):
        result = parse_statement_csv("Date,Description,Amount\n")
        assert len(result.transactions) == 0

    def test_small_amounts_filtered(self):
        csv_text = "Date,Description,Amount\n01/05/2026,Tiny charge,-1.50\n"
        result = parse_statement_csv(csv_text)
        assert len(result.expense_suggestions) == 0  # Below $5 threshold

    def test_months_covered_calculation(self):
        result = parse_statement_csv(CHASE_CSV)
        assert result.months_covered >= 1.0
