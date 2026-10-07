"""Social Security income projection helpers for planning workflows.

Timeline age/retirement patterns are written independently; design reference: Ignidash (see ATTRIBUTIONS.md):
- src/lib/schemas/inputs/timeline-form-schema.ts
- src/lib/calc/phase.ts
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


DEFAULT_FRA_AGE_YEARS = 67.0
DEFAULT_CLAIMING_AGES = (62, 67, 70)
DEFAULT_PIA_BEND_POINT_1_USD = 1226.0
DEFAULT_PIA_BEND_POINT_2_USD = 7391.0


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _fra_months_from_birth_year(birth_year: int | None) -> int:
    if birth_year is None:
        return int(DEFAULT_FRA_AGE_YEARS * 12)

    if birth_year <= 1937:
        return 65 * 12
    if birth_year == 1938:
        return (65 * 12) + 2
    if birth_year == 1939:
        return (65 * 12) + 4
    if birth_year == 1940:
        return (65 * 12) + 6
    if birth_year == 1941:
        return (65 * 12) + 8
    if birth_year == 1942:
        return (65 * 12) + 10
    if birth_year <= 1954:
        return 66 * 12
    if birth_year == 1955:
        return (66 * 12) + 2
    if birth_year == 1956:
        return (66 * 12) + 4
    if birth_year == 1957:
        return (66 * 12) + 6
    if birth_year == 1958:
        return (66 * 12) + 8
    if birth_year == 1959:
        return (66 * 12) + 10
    return 67 * 12


def _round_down_to_dime(value: float) -> float:
    if value <= 0:
        return 0.0
    return math.floor(value * 10.0) / 10.0


def _estimate_pia_monthly_from_aime(
    *,
    aime_usd: float,
    bend_point_1_usd: float,
    bend_point_2_usd: float,
) -> float:
    aime = max(0.0, float(aime_usd))
    first_band = min(aime, bend_point_1_usd)
    second_band = max(0.0, min(aime, bend_point_2_usd) - bend_point_1_usd)
    third_band = max(0.0, aime - bend_point_2_usd)
    pia = (first_band * 0.9) + (second_band * 0.32) + (third_band * 0.15)
    return _round_down_to_dime(pia)


def _monthly_benefit_for_claim_age(
    *,
    fra_monthly_benefit_usd: float,
    fra_months: int,
    claiming_age_years: int,
) -> float:
    base = max(0.0, float(fra_monthly_benefit_usd))
    claim_months = int(_clamp(float(claiming_age_years), 62, 70) * 12)

    if claim_months < fra_months:
        months_early = fra_months - claim_months
        first_36 = min(36, months_early)
        beyond_36 = max(0, months_early - 36)
        reduction = (first_36 * (5.0 / 9.0) / 100.0) + (beyond_36 * (5.0 / 12.0) / 100.0)
        return max(0.0, base * (1.0 - reduction))

    if claim_months > fra_months:
        months_late = min((70 * 12), claim_months) - fra_months
        delayed_credit = months_late * (2.0 / 3.0) / 100.0
        return max(0.0, base * (1.0 + delayed_credit))

    return base


def _normalize_claiming_ages(claiming_ages: list[int] | None) -> list[int]:
    raw = claiming_ages or list(DEFAULT_CLAIMING_AGES)
    normalized: list[int] = []
    for value in raw:
        age = max(62, min(_safe_int(value, 67), 70))
        if age not in normalized:
            normalized.append(age)
    if not normalized:
        return list(DEFAULT_CLAIMING_AGES)
    return sorted(normalized)


def _project_lifetime_benefits(
    *,
    claim_age: int,
    life_expectancy_age: int,
    annual_benefit_at_claim_usd: float,
    cola_rate: float,
) -> float:
    if claim_age > life_expectancy_age:
        return 0.0

    total = 0.0
    for age in range(claim_age, life_expectancy_age + 1):
        years_since_claim = age - claim_age
        annual_benefit = annual_benefit_at_claim_usd * ((1.0 + cola_rate) ** years_since_claim)
        total += max(0.0, annual_benefit)
    return total


def _extract_earnings_history(
    earnings_history: list[dict[str, Any]] | None,
) -> tuple[list[float], list[str]]:
    warnings: list[str] = []
    normalized: list[float] = []

    if not isinstance(earnings_history, list):
        return normalized, warnings

    for index, raw in enumerate(earnings_history, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Skipped earnings row #{index}: expected an object.")
            continue
        earnings = max(0.0, _safe_float(raw.get("earnings_usd"), -1.0))
        if earnings <= 0:
            continue
        normalized.append(earnings)

    return normalized, warnings


def _estimate_fra_monthly_benefit(
    *,
    fra_monthly_benefit_usd: float | None,
    estimated_annual_earnings_usd: float | None,
    earnings_history: list[dict[str, Any]] | None,
    bend_point_1_usd: float,
    bend_point_2_usd: float,
) -> tuple[float, float, float, list[str]]:
    warnings: list[str] = []
    explicit_fra = max(0.0, _safe_float(fra_monthly_benefit_usd, 0.0))
    if explicit_fra > 0:
        return explicit_fra, 0.0, explicit_fra, warnings

    earnings_values, earnings_warnings = _extract_earnings_history(earnings_history)
    warnings.extend(earnings_warnings)

    estimated_annual = max(0.0, _safe_float(estimated_annual_earnings_usd, 0.0))
    if not earnings_values and estimated_annual > 0:
        earnings_values = [estimated_annual for _ in range(35)]

    if not earnings_values:
        warnings.append(
            "Social Security estimate requires either fra_monthly_benefit_usd, "
            "earnings_history, or estimated_annual_earnings_usd."
        )
        return 0.0, 0.0, 0.0, warnings

    top_35 = sorted(earnings_values, reverse=True)[:35]
    while len(top_35) < 35:
        top_35.append(0.0)

    aime = sum(top_35) / 35.0 / 12.0
    pia = _estimate_pia_monthly_from_aime(
        aime_usd=aime,
        bend_point_1_usd=bend_point_1_usd,
        bend_point_2_usd=bend_point_2_usd,
    )
    return pia, aime, pia, warnings


def project_social_security_income(
    *,
    start_year: int,
    years: int,
    current_age: int = 35,
    claiming_age: int | None = None,
    life_expectancy_age: int | None = None,
    birth_year: int | None = None,
    fra_monthly_benefit_usd: float | None = None,
    estimated_annual_earnings_usd: float | None = None,
    earnings_history: list[dict[str, Any]] | None = None,
    cola_rate: float = 0.02,
    claim_age_options: list[int] | None = None,
    pia_bend_point_1_usd: float = DEFAULT_PIA_BEND_POINT_1_USD,
    pia_bend_point_2_usd: float = DEFAULT_PIA_BEND_POINT_2_USD,
) -> dict[str, Any]:
    resolved_start_year = _safe_int(start_year, datetime.now().year)
    resolved_years = max(1, min(_safe_int(years, 1), 80))
    resolved_current_age = max(0, min(_safe_int(current_age, 35), 120))
    resolved_claiming_age = max(62, min(_safe_int(claiming_age, 67), 70))
    resolved_life_expectancy = max(67, min(_safe_int(life_expectancy_age, 90), 120))
    resolved_cola = _clamp(_safe_float(cola_rate, 0.02), -0.2, 0.2)
    resolved_bend_1 = max(1.0, _safe_float(pia_bend_point_1_usd, DEFAULT_PIA_BEND_POINT_1_USD))
    resolved_bend_2 = max(
        resolved_bend_1,
        _safe_float(pia_bend_point_2_usd, DEFAULT_PIA_BEND_POINT_2_USD),
    )

    fra_months = _fra_months_from_birth_year(_safe_int(birth_year, 0) if birth_year is not None else None)
    fra_age = round(fra_months / 12.0, 4)

    fra_monthly_benefit, aime_usd, pia_monthly_usd, warnings = _estimate_fra_monthly_benefit(
        fra_monthly_benefit_usd=fra_monthly_benefit_usd,
        estimated_annual_earnings_usd=estimated_annual_earnings_usd,
        earnings_history=earnings_history,
        bend_point_1_usd=resolved_bend_1,
        bend_point_2_usd=resolved_bend_2,
    )

    options = _normalize_claiming_ages(claim_age_options)
    if resolved_claiming_age not in options:
        options.append(resolved_claiming_age)
        options = sorted(options)

    claim_option_rows: list[dict[str, Any]] = []
    for option_age in options:
        monthly_benefit = _monthly_benefit_for_claim_age(
            fra_monthly_benefit_usd=fra_monthly_benefit,
            fra_months=fra_months,
            claiming_age_years=option_age,
        )
        annual_benefit = monthly_benefit * 12.0
        cumulative_lifetime = _project_lifetime_benefits(
            claim_age=option_age,
            life_expectancy_age=resolved_life_expectancy,
            annual_benefit_at_claim_usd=annual_benefit,
            cola_rate=resolved_cola,
        )
        claim_option_rows.append(
            {
                "claiming_age": option_age,
                "monthly_benefit_usd": round(monthly_benefit, 2),
                "annual_benefit_usd": round(annual_benefit, 2),
                "cumulative_lifetime_benefits_usd": round(cumulative_lifetime, 2),
            }
        )

    optimal_claiming_age = resolved_claiming_age
    if claim_option_rows:
        best = max(claim_option_rows, key=lambda row: _safe_float(row.get("cumulative_lifetime_benefits_usd"), 0.0))
        optimal_claiming_age = _safe_int(best.get("claiming_age"), resolved_claiming_age)

    selected_monthly_benefit = _monthly_benefit_for_claim_age(
        fra_monthly_benefit_usd=fra_monthly_benefit,
        fra_months=fra_months,
        claiming_age_years=resolved_claiming_age,
    )
    selected_annual_benefit = selected_monthly_benefit * 12.0

    yearly_points: list[dict[str, Any]] = []
    cumulative_benefits = 0.0
    for offset in range(resolved_years):
        year = resolved_start_year + offset
        age = resolved_current_age + offset
        annual_benefit = 0.0
        if age >= resolved_claiming_age:
            years_since_claim = age - resolved_claiming_age
            annual_benefit = selected_annual_benefit * ((1.0 + resolved_cola) ** years_since_claim)
        annual_benefit = max(0.0, annual_benefit)
        cumulative_benefits += annual_benefit
        yearly_points.append(
            {
                "year": year,
                "age": age,
                "annual_benefit_usd": round(annual_benefit, 2),
                "cumulative_benefits_usd": round(cumulative_benefits, 2),
            }
        )

    return {
        "start_year": resolved_start_year,
        "years": resolved_years,
        "current_age": resolved_current_age,
        "birth_year": birth_year,
        "fra_age": fra_age,
        "life_expectancy_age": resolved_life_expectancy,
        "selected_claiming_age": resolved_claiming_age,
        "optimal_claiming_age": optimal_claiming_age,
        "fra_monthly_benefit_usd": round(fra_monthly_benefit, 2),
        "estimated_aime_usd": round(aime_usd, 2),
        "estimated_pia_monthly_usd": round(pia_monthly_usd, 2),
        "selected_monthly_benefit_usd": round(selected_monthly_benefit, 2),
        "selected_annual_benefit_usd": round(selected_annual_benefit, 2),
        "cola_rate": round(resolved_cola, 6),
        "pia_bend_point_1_usd": round(resolved_bend_1, 2),
        "pia_bend_point_2_usd": round(resolved_bend_2, 2),
        "claim_options": claim_option_rows,
        "yearly_points": yearly_points,
        "warnings": warnings,
    }


__all__ = ["project_social_security_income"]
