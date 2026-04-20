from __future__ import annotations

TIMELINE_EVENT_TYPE_VALUES = ("purchase", "windfall", "job_change", "retirement", "milestone")
TIMELINE_IMPACT_TYPE_VALUES = ("income", "expense", "portfolio", "contribution", "debt_payment")
TIMELINE_FREQUENCY_VALUES = ("one_time", "monthly", "yearly")

TIMELINE_EVENT_TYPES = frozenset(TIMELINE_EVENT_TYPE_VALUES)
TIMELINE_IMPACT_TYPES = frozenset(TIMELINE_IMPACT_TYPE_VALUES)
TIMELINE_FREQUENCIES = frozenset(TIMELINE_FREQUENCY_VALUES)

TIMELINE_DEFAULT_IMPACT_BY_EVENT = {
    "purchase": "expense",
    "windfall": "income",
    "job_change": "income",
    "retirement": "contribution",
    "milestone": "portfolio",
}
