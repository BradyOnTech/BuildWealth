from buildwealth_orchestrator.services.tax_engine import estimate_federal_tax


def test_tax_engine_estimates_wage_only_case() -> None:
    result = estimate_federal_tax(
        tax_year=2026,
        filing_status="single",
        earned_income_usd=100000,
        tax_withholding_usd=15000,
    )

    assert result["gross_income_usd"] == 100000.0
    assert result["taxable_ordinary_income_usd"] == 83900.0
    assert result["federal_income_tax_usd"] == 13170.0
    assert result["capital_gains_tax_usd"] == 0.0
    assert result["niit_tax_usd"] == 0.0
    assert result["total_fica_tax_usd"] == 7650.0
    assert result["total_estimated_tax_usd"] == 20820.0
    assert result["amount_due_usd"] == 5820.0
    assert result["refund_usd"] == 0.0


def test_tax_engine_handles_capital_gains_stacking_and_niit() -> None:
    result = estimate_federal_tax(
        tax_year=2026,
        filing_status="single",
        earned_income_usd=220000,
        long_term_capital_gains_usd=50000,
        qualified_dividends_usd=10000,
        interest_income_usd=5000,
    )

    assert result["taxable_ordinary_income_usd"] == 208900.0
    assert result["taxable_capital_gains_income_usd"] == 60000.0
    assert result["federal_income_tax_usd"] == 43304.0
    assert result["capital_gains_tax_usd"] == 9000.0
    assert result["niit_income_subject_usd"] == 65000.0
    assert result["niit_tax_usd"] == 2470.0
    assert result["total_fica_tax_usd"] == 16830.0
    assert result["total_estimated_tax_usd"] == 71604.0


def test_tax_engine_computes_taxable_social_security_income() -> None:
    result = estimate_federal_tax(
        tax_year=2026,
        filing_status="single",
        ordinary_income_usd=20000,
        social_security_income_usd=30000,
    )

    assert result["taxable_social_security_income_usd"] == 5350.0
    assert result["taxable_ordinary_income_usd"] == 9250.0
    assert result["federal_income_tax_usd"] == 925.0
    assert result["total_fica_tax_usd"] == 0.0


def test_tax_engine_falls_back_to_2026_when_year_unknown() -> None:
    result = estimate_federal_tax(
        tax_year=2032,
        filing_status="single",
        earned_income_usd=50000,
    )

    assert result["tax_year"] == 2032
    assert result["standard_deduction_usd"] == 16100.0
    assert any("using 2026 federal assumptions" in warning.lower() for warning in result["warnings"])


def test_tax_engine_adds_state_tax_and_irmaa_when_configured() -> None:
    result = estimate_federal_tax(
        tax_year=2026,
        filing_status="single",
        earned_income_usd=220000,
        social_security_income_usd=36000,
        state_tax_rate=0.05,
        age=67,
        include_irmaa=True,
    )

    assert result["state_tax_rate"] == 0.05
    assert result["state_taxable_income_usd"] == 234500.0
    assert result["state_income_tax_usd"] == 11725.0
    assert result["irmaa_applied"] is True
    assert result["irmaa_bracket_label"] == ">205k-<500k"
    assert result["irmaa_part_b_monthly_surcharge_usd"] == 446.3
    assert result["irmaa_part_d_monthly_surcharge_usd"] == 83.3
    assert result["irmaa_annual_surcharge_usd"] == 6355.2
    assert result["total_estimated_tax_usd"] == 86406.2


def test_tax_engine_skips_irmaa_when_disabled() -> None:
    result = estimate_federal_tax(
        tax_year=2026,
        filing_status="single",
        earned_income_usd=220000,
        social_security_income_usd=36000,
        state_tax_rate=0.05,
        age=67,
        include_irmaa=False,
    )

    assert result["irmaa_applied"] is False
    assert result["irmaa_annual_surcharge_usd"] == 0.0
    assert result["total_estimated_tax_usd"] == 80051.0
