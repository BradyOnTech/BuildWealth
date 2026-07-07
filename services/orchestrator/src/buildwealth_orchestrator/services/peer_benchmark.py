"""Peer benchmarking from public survey data — "am I doing okay for my age?"

The question normal people actually bring to money. Answered locally from
the Federal Reserve's 2022 Survey of Consumer Finances (published Oct 2023):
median and mean household net worth by age of reference person. No user
data leaves the machine and no peer network is required — see
docs/FEATURE_NOTE_PEER_BENCHMARKING_2026-07-07.md for how anonymized peer
percentiles graduate from this later without changing the surface.

Percentile estimation: net worth within an age bracket is heavy-tailed, so
a lognormal fit from the published (median, mean) pair gives a usable
approximation — median pins mu, mean/median pins sigma. It is an ESTIMATE
and every surface labels it as one. Non-positive net worth sits below the
fit's support and reports the honest band instead of a fake number.

Important comparability note carried on every payload: SCF net worth
includes home equity, so the comparison uses total net worth (home
included), matching the survey's definition — not the invested-money view
the rest of the app scopes to.
"""

from __future__ import annotations

import math
from typing import Any

# SCF 2022 (Federal Reserve Bulletin, Oct 2023). Dollar figures are as
# published — 2022 dollars; the caveat notes the survey lag.
SCF_SURVEY_LABEL = "SCF 2022"
SCF_NET_WORTH_BY_AGE: list[dict[str, Any]] = [
    {"bracket": "under_35", "label": "under 35", "min_age": 0, "max_age": 34, "median_usd": 39_040, "mean_usd": 183_500},
    {"bracket": "35_44", "label": "35–44", "min_age": 35, "max_age": 44, "median_usd": 135_600, "mean_usd": 549_600},
    {"bracket": "45_54", "label": "45–54", "min_age": 45, "max_age": 54, "median_usd": 247_200, "mean_usd": 975_800},
    {"bracket": "55_64", "label": "55–64", "min_age": 55, "max_age": 64, "median_usd": 364_500, "mean_usd": 1_566_900},
    {"bracket": "65_74", "label": "65–74", "min_age": 65, "max_age": 74, "median_usd": 409_900, "mean_usd": 1_794_600},
    {"bracket": "75_plus", "label": "75+", "min_age": 75, "max_age": 200, "median_usd": 335_600, "mean_usd": 1_624_100},
]

CAVEATS = [
    "Benchmarks are the Federal Reserve's 2022 Survey of Consumer Finances (US households); "
    "values lag a few years and are not inflation-adjusted here.",
    "SCF net worth includes home equity, so the comparison uses your total net worth including the home.",
    "The percentile is an estimate from the published median and mean, not an exact survey lookup.",
]


def bracket_for_age(age: int) -> dict[str, Any] | None:
    for bracket in SCF_NET_WORTH_BY_AGE:
        if bracket["min_age"] <= age <= bracket["max_age"]:
            return bracket
    return None


def next_bracket_after(bracket: dict[str, Any]) -> dict[str, Any] | None:
    index = SCF_NET_WORTH_BY_AGE.index(bracket)
    return SCF_NET_WORTH_BY_AGE[index + 1] if index + 1 < len(SCF_NET_WORTH_BY_AGE) else None


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def estimate_percentile(net_worth_usd: float, *, median_usd: float, mean_usd: float) -> int | None:
    """Approximate within-bracket percentile via a lognormal fit.

    median = e^mu; mean = e^(mu + sigma^2/2) => sigma^2 = 2 ln(mean/median).
    Returns None for non-positive net worth (below the fit's support) —
    callers report the honest band instead of inventing a number.
    """
    if net_worth_usd <= 0 or median_usd <= 0 or mean_usd <= median_usd:
        return None
    mu = math.log(median_usd)
    sigma = math.sqrt(2.0 * math.log(mean_usd / median_usd))
    if sigma <= 0:
        return None
    percentile = round(_normal_cdf((math.log(net_worth_usd) - mu) / sigma) * 100)
    return max(1, min(99, percentile))


def _age_from_profile(profile_payload: dict[str, Any], *, current_year: int) -> int | None:
    members = profile_payload.get("household_members")
    if not isinstance(members, list):
        return None
    self_member = next(
        (m for m in members if isinstance(m, dict) and str(m.get("relationship") or "") == "self"),
        None,
    ) or next((m for m in members if isinstance(m, dict) and m.get("birth_year")), None)
    if not self_member:
        return None
    try:
        birth_year = int(self_member.get("birth_year"))
    except (TypeError, ValueError):
        return None
    if birth_year < 1900:
        return None
    age = current_year - birth_year
    return age if 0 < age < 120 else None


def build_peer_benchmark(
    *,
    net_worth_usd: float,
    profile_payload: dict[str, Any],
    current_year: int,
) -> dict[str, Any]:
    age = _age_from_profile(profile_payload, current_year=current_year)
    if age is None:
        return {
            "status": "needs_age",
            "detail": "Add your birth year in Profile → Household to compare against households your age.",
        }
    bracket = bracket_for_age(age)
    if bracket is None:
        return {"status": "needs_age", "detail": "Age could not be matched to a survey bracket."}

    percentile = estimate_percentile(
        net_worth_usd, median_usd=bracket["median_usd"], mean_usd=bracket["mean_usd"]
    )
    vs_median = net_worth_usd - bracket["median_usd"]

    if percentile is None:
        sentence = (
            f"Typical ({bracket['label']}): median household net worth is about "
            f"${bracket['median_usd']:,.0f} — building from below zero is where many start."
        )
    elif net_worth_usd >= bracket["median_usd"]:
        sentence = (
            f"You're ahead of roughly {percentile}% of US households aged {bracket['label']} "
            f"(median ~${bracket['median_usd']:,.0f}, {SCF_SURVEY_LABEL}, estimate)."
        )
    else:
        sentence = (
            f"You're around the {percentile}th percentile for US households aged {bracket['label']} "
            f"(median ~${bracket['median_usd']:,.0f}, {SCF_SURVEY_LABEL}, estimate)."
        )

    upcoming = next_bracket_after(bracket)
    return {
        "status": "ready",
        "survey": SCF_SURVEY_LABEL,
        "age": age,
        "bracket": bracket["bracket"],
        "bracket_label": bracket["label"],
        "median_usd": bracket["median_usd"],
        "mean_usd": bracket["mean_usd"],
        "net_worth_usd": round(net_worth_usd, 2),
        "vs_median_usd": round(vs_median, 2),
        "percentile_estimate": percentile,
        "sentence": sentence,
        "next_bracket": (
            {"bracket": upcoming["bracket"], "label": upcoming["label"], "median_usd": upcoming["median_usd"]}
            if upcoming
            else None
        ),
        # Milestone guides for chart overlays: this bracket's median and the
        # medians ahead of the user — "when does my plan cross the typical
        # 55–64 household?"
        "milestones": [
            {"label": f"median {b['label']}", "median_usd": b["median_usd"]}
            for b in SCF_NET_WORTH_BY_AGE[SCF_NET_WORTH_BY_AGE.index(bracket):]
        ],
        "caveats": CAVEATS,
    }
