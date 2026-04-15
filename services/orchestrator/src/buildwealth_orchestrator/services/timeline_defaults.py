from __future__ import annotations

TIMELINE_EVENT_TYPES = {"purchase", "windfall", "job_change", "retirement", "milestone"}
TIMELINE_IMPACT_TYPES = {"income", "expense", "portfolio", "contribution", "debt_payment"}
TIMELINE_FREQUENCIES = {"one_time", "monthly", "yearly"}

TIMELINE_DEFAULT_IMPACT_BY_EVENT = {
    "purchase": "expense",
    "windfall": "income",
    "job_change": "income",
    "retirement": "contribution",
    "milestone": "portfolio",
}
