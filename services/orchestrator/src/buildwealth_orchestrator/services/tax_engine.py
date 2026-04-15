"""Tax estimate engine for standalone planning workflows.

Adapted from Ignidash (MIT):
- src/lib/calc/taxes.ts
- src/lib/calc/tax-data/federal-income-tax-brackets.ts
- src/lib/calc/tax-data/capital-gains-tax-brackets.ts
- src/lib/calc/tax-data/standard-deduction.ts
- src/lib/calc/tax-data/niit-thresholds.ts
- src/lib/calc/tax-data/social-security-tax-brackets.ts

BuildWealth extensions:
- flat-rate state income tax modeling
- IRMAA surcharge estimation (2026 CMS tables)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from buildwealth_orchestrator.services.value_coercion import safe_float


FilingStatus = Literal[
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
]


@dataclass(frozen=True)
class TaxBracket:
    min_income: float
    max_income: float
    rate: float


@dataclass(frozen=True)
class IrmaaBracket:
    min_magi: float
    max_magi: float | None
    min_inclusive: bool
    max_inclusive: bool
    part_b_monthly_surcharge: float
    part_d_monthly_surcharge: float
    label: str


@dataclass(frozen=True)
class TaxYearConfig:
    standard_deduction: dict[FilingStatus, float]
    federal_income_brackets: dict[FilingStatus, tuple[TaxBracket, ...]]
    capital_gains_brackets: dict[FilingStatus, tuple[TaxBracket, ...]]
    niit_thresholds: dict[FilingStatus, float]
    social_security_thresholds: dict[FilingStatus, tuple[float, float]]
    irmaa_brackets: dict[FilingStatus, tuple[IrmaaBracket, ...]]
    fica_social_security_rate: float = 0.062
    fica_medicare_rate: float = 0.0145


# 2026 values adapted from Ignidash tax-data constants.
# 2026 IRMAA values are sourced from CMS (Nov 14, 2025):
# https://www.cms.gov/newsroom/fact-sheets/2026-medicare-parts-b-premiums-deductibles
TAX_YEAR_2026 = TaxYearConfig(
    standard_deduction={
        "single": 16100.0,
        "married_filing_jointly": 32200.0,
        "married_filing_separately": 16100.0,
        "head_of_household": 24150.0,
    },
    federal_income_brackets={
        "single": (
            TaxBracket(0.0, 12400.0, 0.10),
            TaxBracket(12400.0, 50400.0, 0.12),
            TaxBracket(50400.0, 105700.0, 0.22),
            TaxBracket(105700.0, 201775.0, 0.24),
            TaxBracket(201775.0, 256225.0, 0.32),
            TaxBracket(256225.0, 640600.0, 0.35),
            TaxBracket(640600.0, float("inf"), 0.37),
        ),
        "married_filing_jointly": (
            TaxBracket(0.0, 24800.0, 0.10),
            TaxBracket(24800.0, 100800.0, 0.12),
            TaxBracket(100800.0, 211400.0, 0.22),
            TaxBracket(211400.0, 403550.0, 0.24),
            TaxBracket(403550.0, 512450.0, 0.32),
            TaxBracket(512450.0, 768700.0, 0.35),
            TaxBracket(768700.0, float("inf"), 0.37),
        ),
        "married_filing_separately": (
            TaxBracket(0.0, 12400.0, 0.10),
            TaxBracket(12400.0, 50400.0, 0.12),
            TaxBracket(50400.0, 105700.0, 0.22),
            TaxBracket(105700.0, 201775.0, 0.24),
            TaxBracket(201775.0, 256225.0, 0.32),
            TaxBracket(256225.0, 640600.0, 0.35),
            TaxBracket(640600.0, float("inf"), 0.37),
        ),
        "head_of_household": (
            TaxBracket(0.0, 17700.0, 0.10),
            TaxBracket(17700.0, 67450.0, 0.12),
            TaxBracket(67450.0, 105700.0, 0.22),
            TaxBracket(105700.0, 201775.0, 0.24),
            TaxBracket(201775.0, 256200.0, 0.32),
            TaxBracket(256200.0, 640600.0, 0.35),
            TaxBracket(640600.0, float("inf"), 0.37),
        ),
    },
    capital_gains_brackets={
        "single": (
            TaxBracket(0.0, 49450.0, 0.00),
            TaxBracket(49450.0, 545500.0, 0.15),
            TaxBracket(545500.0, float("inf"), 0.20),
        ),
        "married_filing_jointly": (
            TaxBracket(0.0, 98900.0, 0.00),
            TaxBracket(98900.0, 613700.0, 0.15),
            TaxBracket(613700.0, float("inf"), 0.20),
        ),
        "married_filing_separately": (
            TaxBracket(0.0, 49450.0, 0.00),
            TaxBracket(49450.0, 306850.0, 0.15),
            TaxBracket(306850.0, float("inf"), 0.20),
        ),
        "head_of_household": (
            TaxBracket(0.0, 66200.0, 0.00),
            TaxBracket(66200.0, 579600.0, 0.15),
            TaxBracket(579600.0, float("inf"), 0.20),
        ),
    },
    niit_thresholds={
        "single": 200000.0,
        "married_filing_jointly": 250000.0,
        "married_filing_separately": 125000.0,
        "head_of_household": 200000.0,
    },
    social_security_thresholds={
        "single": (25000.0, 34000.0),
        "married_filing_jointly": (32000.0, 44000.0),
        "married_filing_separately": (25000.0, 34000.0),
        "head_of_household": (25000.0, 34000.0),
    },
    irmaa_brackets={
        "single": (
            IrmaaBracket(0.0, 109000.0, True, True, 0.0, 0.0, "<=109k"),
            IrmaaBracket(109000.0, 137000.0, False, True, 81.20, 14.50, ">109k-137k"),
            IrmaaBracket(137000.0, 171000.0, False, True, 202.90, 37.50, ">137k-171k"),
            IrmaaBracket(171000.0, 205000.0, False, True, 324.60, 60.40, ">171k-205k"),
            IrmaaBracket(205000.0, 500000.0, False, False, 446.30, 83.30, ">205k-<500k"),
            IrmaaBracket(500000.0, None, True, True, 487.00, 91.00, ">=500k"),
        ),
        "married_filing_jointly": (
            IrmaaBracket(0.0, 218000.0, True, True, 0.0, 0.0, "<=218k"),
            IrmaaBracket(218000.0, 274000.0, False, True, 81.20, 14.50, ">218k-274k"),
            IrmaaBracket(274000.0, 342000.0, False, True, 202.90, 37.50, ">274k-342k"),
            IrmaaBracket(342000.0, 410000.0, False, True, 324.60, 60.40, ">342k-410k"),
            IrmaaBracket(410000.0, 750000.0, False, False, 446.30, 83.30, ">410k-<750k"),
            IrmaaBracket(750000.0, None, True, True, 487.00, 91.00, ">=750k"),
        ),
        "married_filing_separately": (
            IrmaaBracket(0.0, 109000.0, True, True, 0.0, 0.0, "<=109k"),
            IrmaaBracket(109000.0, 391000.0, False, False, 446.30, 83.30, ">109k-<391k"),
            IrmaaBracket(391000.0, None, True, True, 487.00, 91.00, ">=391k"),
        ),
        "head_of_household": (
            IrmaaBracket(0.0, 109000.0, True, True, 0.0, 0.0, "<=109k"),
            IrmaaBracket(109000.0, 137000.0, False, True, 81.20, 14.50, ">109k-137k"),
            IrmaaBracket(137000.0, 171000.0, False, True, 202.90, 37.50, ">137k-171k"),
            IrmaaBracket(171000.0, 205000.0, False, True, 324.60, 60.40, ">171k-205k"),
            IrmaaBracket(205000.0, 500000.0, False, False, 446.30, 83.30, ">205k-<500k"),
            IrmaaBracket(500000.0, None, True, True, 487.00, 91.00, ">=500k"),
        ),
    },
)

TAX_CONFIG_BY_YEAR: dict[int, TaxYearConfig] = {
    2026: TAX_YEAR_2026,
}

NIIT_RATE = 0.038


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _round_rate(value: float) -> float:
    return round(float(value), 6)


def _progressive_tax(amount: float, brackets: tuple[TaxBracket, ...]) -> tuple[float, float]:
    if amount <= 0:
        return 0.0, 0.0

    tax = 0.0
    top_rate = 0.0
    for bracket in brackets:
        if amount <= bracket.min_income:
            break
        taxable_in_bracket = min(amount, bracket.max_income) - bracket.min_income
        if taxable_in_bracket <= 0:
            continue
        tax += taxable_in_bracket * bracket.rate
        top_rate = bracket.rate
    return tax, top_rate


def _stacked_capital_gains_tax(
    *,
    taxable_ordinary_income: float,
    taxable_capital_gains_income: float,
    brackets: tuple[TaxBracket, ...],
) -> tuple[float, float]:
    if taxable_capital_gains_income <= 0:
        return 0.0, 0.0

    total_taxable_income = taxable_ordinary_income + taxable_capital_gains_income
    tax = 0.0
    top_rate = 0.0
    for bracket in brackets:
        if total_taxable_income <= bracket.min_income:
            break

        income_in_bracket = min(total_taxable_income, bracket.max_income) - bracket.min_income
        ordinary_income_in_bracket = max(
            0.0,
            min(taxable_ordinary_income, bracket.max_income) - bracket.min_income,
        )
        capital_gains_in_bracket = max(0.0, income_in_bracket - ordinary_income_in_bracket)
        if capital_gains_in_bracket <= 0:
            continue

        tax += capital_gains_in_bracket * bracket.rate
        top_rate = bracket.rate

    return tax, top_rate


def _taxable_social_security_income(
    *,
    social_security_income: float,
    provisional_income: float,
    lower_threshold: float,
    upper_threshold: float,
) -> float:
    if social_security_income <= 0:
        return 0.0
    if provisional_income <= lower_threshold:
        return 0.0
    if provisional_income <= upper_threshold:
        excess = provisional_income - lower_threshold
        return min(excess * 0.5, social_security_income * 0.5)

    tier_1_amount = min((upper_threshold - lower_threshold) * 0.5, social_security_income * 0.5)
    tier_2_excess = provisional_income - upper_threshold
    tier_2_amount = tier_2_excess * 0.85
    return min(tier_1_amount + tier_2_amount, social_security_income * 0.85)


def _irmaa_monthly_surcharge(
    *,
    modified_adjusted_gross_income: float,
    filing_status: FilingStatus,
    config: TaxYearConfig,
) -> tuple[float, float, str | None]:
    brackets = config.irmaa_brackets.get(filing_status) or config.irmaa_brackets["single"]
    for bracket in brackets:
        lower_pass = (
            modified_adjusted_gross_income >= bracket.min_magi
            if bracket.min_inclusive
            else modified_adjusted_gross_income > bracket.min_magi
        )
        if not lower_pass:
            continue
        if bracket.max_magi is None:
            return (
                bracket.part_b_monthly_surcharge,
                bracket.part_d_monthly_surcharge,
                bracket.label,
            )
        if bracket.max_inclusive and modified_adjusted_gross_income <= bracket.max_magi:
            return (
                bracket.part_b_monthly_surcharge,
                bracket.part_d_monthly_surcharge,
                bracket.label,
            )
        if not bracket.max_inclusive and modified_adjusted_gross_income < bracket.max_magi:
            return (
                bracket.part_b_monthly_surcharge,
                bracket.part_d_monthly_surcharge,
                bracket.label,
            )
    return 0.0, 0.0, None


def estimate_federal_tax(
    *,
    tax_year: int,
    filing_status: FilingStatus,
    earned_income_usd: float = 0.0,
    ordinary_income_usd: float = 0.0,
    short_term_capital_gains_usd: float = 0.0,
    long_term_capital_gains_usd: float = 0.0,
    qualified_dividends_usd: float = 0.0,
    interest_income_usd: float = 0.0,
    social_security_income_usd: float = 0.0,
    tax_exempt_interest_income_usd: float = 0.0,
    pre_tax_contributions_usd: float = 0.0,
    state_tax_rate: float = 0.0,
    state_tax_deduction_usd: float = 0.0,
    age: int | None = None,
    include_irmaa: bool = True,
    medicare_months_covered: int = 12,
    tax_withholding_usd: float = 0.0,
) -> dict[str, float | int | str | bool | None | list[str]]:
    warnings: list[str] = []
    config = TAX_CONFIG_BY_YEAR.get(int(tax_year))
    if config is None:
        config = TAX_YEAR_2026
        warnings.append(
            f"Tax year {tax_year} is not configured; using 2026 federal assumptions."
        )

    earned_income = safe_float(earned_income_usd)
    ordinary_income = safe_float(ordinary_income_usd)
    short_term_capital_gains = safe_float(short_term_capital_gains_usd)
    long_term_capital_gains = safe_float(long_term_capital_gains_usd)
    qualified_dividends = safe_float(qualified_dividends_usd)
    interest_income = safe_float(interest_income_usd)
    social_security_income = safe_float(social_security_income_usd)
    tax_exempt_interest_income = max(0.0, safe_float(tax_exempt_interest_income_usd))
    pre_tax_contributions = max(0.0, safe_float(pre_tax_contributions_usd))
    resolved_state_tax_rate = max(0.0, min(1.0, safe_float(state_tax_rate)))
    state_tax_deduction = max(0.0, safe_float(state_tax_deduction_usd))
    resolved_age = (
        max(0, min(120, int(safe_float(age, 0.0))))
        if age is not None
        else None
    )
    try:
        irmaa_months_value = int(medicare_months_covered)
    except (TypeError, ValueError):
        irmaa_months_value = 12
    irmaa_months = max(0, min(12, irmaa_months_value))
    tax_withholding = max(0.0, safe_float(tax_withholding_usd))

    filing_key = filing_status
    if filing_key not in config.standard_deduction:
        filing_key = "single"
        warnings.append(f"Unsupported filing status '{filing_status}'; using single.")

    lower_ss_threshold, upper_ss_threshold = config.social_security_thresholds[filing_key]
    base_income_excluding_ss = (
        earned_income
        + ordinary_income
        + interest_income
        + short_term_capital_gains
        + long_term_capital_gains
        + qualified_dividends
    )
    provisional_income = base_income_excluding_ss + (social_security_income * 0.5)
    taxable_social_security_income = _taxable_social_security_income(
        social_security_income=social_security_income,
        provisional_income=provisional_income,
        lower_threshold=lower_ss_threshold,
        upper_threshold=upper_ss_threshold,
    )

    capital_income_after_losses = long_term_capital_gains + qualified_dividends
    capital_loss_deduction = 0.0
    if capital_income_after_losses < 0:
        capital_loss_deduction = min(3000.0, abs(capital_income_after_losses))
        carryover = abs(capital_income_after_losses) - capital_loss_deduction
        capital_income_after_losses = 0.0
        if carryover > 0:
            warnings.append(
                "Capital loss carryover above $3,000 is not persisted in this estimate."
            )

    income_taxed_as_ordinary = (
        earned_income
        + ordinary_income
        + interest_income
        + short_term_capital_gains
        + taxable_social_security_income
        - capital_loss_deduction
    )
    adjusted_income_taxed_as_ordinary = max(
        income_taxed_as_ordinary - pre_tax_contributions,
        0.0,
    )
    adjusted_income_taxed_as_capital_gains = max(capital_income_after_losses, 0.0)
    adjusted_gross_income = (
        adjusted_income_taxed_as_ordinary + adjusted_income_taxed_as_capital_gains
    )
    modified_adjusted_gross_income = adjusted_gross_income + tax_exempt_interest_income

    standard_deduction = config.standard_deduction[filing_key]
    deduction_used_for_ordinary = min(standard_deduction, adjusted_income_taxed_as_ordinary)
    deduction_used_for_capital = max(0.0, standard_deduction - deduction_used_for_ordinary)
    taxable_ordinary_income = max(
        adjusted_income_taxed_as_ordinary - deduction_used_for_ordinary,
        0.0,
    )
    taxable_capital_gains_income = max(
        adjusted_income_taxed_as_capital_gains - deduction_used_for_capital,
        0.0,
    )

    federal_income_tax, top_marginal_federal_income_tax_rate = _progressive_tax(
        taxable_ordinary_income,
        config.federal_income_brackets[filing_key],
    )
    capital_gains_tax, top_marginal_capital_gains_tax_rate = _stacked_capital_gains_tax(
        taxable_ordinary_income=taxable_ordinary_income,
        taxable_capital_gains_income=taxable_capital_gains_income,
        brackets=config.capital_gains_brackets[filing_key],
    )

    state_taxable_income = max(
        0.0,
        taxable_ordinary_income + taxable_capital_gains_income - state_tax_deduction,
    )
    state_income_tax = state_taxable_income * resolved_state_tax_rate

    net_investment_income = max(
        0.0,
        interest_income
        + short_term_capital_gains
        + long_term_capital_gains
        + qualified_dividends
        - capital_loss_deduction,
    )
    niit_threshold = config.niit_thresholds[filing_key]
    magi_over_threshold = max(0.0, adjusted_gross_income - niit_threshold)
    niit_income_subject = min(net_investment_income, magi_over_threshold)
    niit_tax = niit_income_subject * NIIT_RATE

    irmaa_applied = bool(include_irmaa) and (
        (resolved_age is not None and resolved_age >= 65) or (resolved_age is None and social_security_income > 0)
    )
    irmaa_part_b_monthly = 0.0
    irmaa_part_d_monthly = 0.0
    irmaa_bracket_label: str | None = None
    if irmaa_applied and irmaa_months > 0:
        (
            irmaa_part_b_monthly,
            irmaa_part_d_monthly,
            irmaa_bracket_label,
        ) = _irmaa_monthly_surcharge(
            modified_adjusted_gross_income=modified_adjusted_gross_income,
            filing_status=filing_key,
            config=config,
        )
    irmaa_total_monthly = irmaa_part_b_monthly + irmaa_part_d_monthly
    irmaa_annual_surcharge = irmaa_total_monthly * irmaa_months

    fica_social_security_tax = earned_income * config.fica_social_security_rate
    fica_medicare_tax = earned_income * config.fica_medicare_rate
    total_fica_tax = fica_social_security_tax + fica_medicare_tax

    gross_income = max(
        0.0,
        earned_income
        + ordinary_income
        + short_term_capital_gains
        + long_term_capital_gains
        + qualified_dividends
        + interest_income
        + social_security_income,
    )
    total_estimated_tax = (
        federal_income_tax
        + capital_gains_tax
        + state_income_tax
        + niit_tax
        + total_fica_tax
        + irmaa_annual_surcharge
    )
    effective_tax_rate = (total_estimated_tax / gross_income) if gross_income > 0 else None
    amount_due = max(0.0, total_estimated_tax - tax_withholding)
    refund = max(0.0, tax_withholding - total_estimated_tax)

    return {
        "tax_year": int(tax_year),
        "filing_status": filing_key,
        "gross_income_usd": _round_money(gross_income),
        "adjusted_gross_income_usd": _round_money(adjusted_gross_income),
        "modified_adjusted_gross_income_usd": _round_money(modified_adjusted_gross_income),
        "standard_deduction_usd": _round_money(standard_deduction),
        "taxable_ordinary_income_usd": _round_money(taxable_ordinary_income),
        "taxable_capital_gains_income_usd": _round_money(taxable_capital_gains_income),
        "taxable_social_security_income_usd": _round_money(taxable_social_security_income),
        "federal_income_tax_usd": _round_money(federal_income_tax),
        "capital_gains_tax_usd": _round_money(capital_gains_tax),
        "state_taxable_income_usd": _round_money(state_taxable_income),
        "state_income_tax_usd": _round_money(state_income_tax),
        "state_tax_rate": _round_rate(resolved_state_tax_rate),
        "niit_tax_usd": _round_money(niit_tax),
        "niit_income_subject_usd": _round_money(niit_income_subject),
        "niit_threshold_usd": _round_money(niit_threshold),
        "irmaa_applied": bool(irmaa_applied and irmaa_months > 0),
        "irmaa_bracket_label": irmaa_bracket_label,
        "irmaa_medicare_months": irmaa_months,
        "irmaa_part_b_monthly_surcharge_usd": _round_money(irmaa_part_b_monthly),
        "irmaa_part_d_monthly_surcharge_usd": _round_money(irmaa_part_d_monthly),
        "irmaa_total_monthly_surcharge_usd": _round_money(irmaa_total_monthly),
        "irmaa_annual_surcharge_usd": _round_money(irmaa_annual_surcharge),
        "fica_social_security_tax_usd": _round_money(fica_social_security_tax),
        "fica_medicare_tax_usd": _round_money(fica_medicare_tax),
        "total_fica_tax_usd": _round_money(total_fica_tax),
        "total_estimated_tax_usd": _round_money(total_estimated_tax),
        "effective_tax_rate": _round_rate(effective_tax_rate) if effective_tax_rate is not None else None,
        "top_marginal_federal_income_tax_rate": _round_rate(top_marginal_federal_income_tax_rate),
        "top_marginal_capital_gains_tax_rate": _round_rate(top_marginal_capital_gains_tax_rate),
        "tax_withholding_usd": _round_money(tax_withholding),
        "amount_due_usd": _round_money(amount_due),
        "refund_usd": _round_money(refund),
        "warnings": warnings,
    }
