from buildwealth_orchestrator.main import (
    build_branch_timeline_payload,
    normalize_branch_events_payload,
)


def test_normalize_branch_events_payload_supports_monthly_temporary_event() -> None:
    events = normalize_branch_events_payload(
        raw_branch_events=[
            {
                "label": "Job Loss",
                "event_type": "job_change",
                "impact_type": "income",
                "amount_usd": -7500,
                "recurring_frequency": "monthly",
                "start_year_offset": 1,
                "duration_months": 6,
                "notes": "Temporary unemployment period",
            }
        ],
        start_year=2026,
    )

    assert len(events) == 1
    event = events[0]
    assert event["date"] == "2027-01-01"
    assert event["end_date"] == "2027-06-01"
    assert event["impact_type"] == "income"
    assert event["recurring_frequency"] == "monthly"
    assert event["amount_usd"] == -7500.0
    assert event["notes"] == "Temporary unemployment period"


def test_build_branch_timeline_payload_appends_base_and_branch_events() -> None:
    branch_timeline, branch_events = build_branch_timeline_payload(
        base_timeline_payload={
            "schema_version": 2,
            "events": [
                {
                    "id": "base-1",
                    "date": "2028-01-01",
                    "label": "Buy House",
                    "event_type": "purchase",
                    "impact_type": "expense",
                    "amount_usd": 80000,
                    "recurring_frequency": "one_time",
                    "end_date": None,
                    "account_id": None,
                    "notes": "",
                }
            ],
            "retirement": {
                "target_retirement_age": 60,
            },
        },
        raw_branch_events=[
            {
                "label": "Raise",
                "event_type": "job_change",
                "impact_type": "income",
                "amount_usd": 12000,
                "recurring_frequency": "yearly",
                "start_year_offset": 2,
            }
        ],
        start_year=2026,
    )

    assert len(branch_events) == 1
    assert len(branch_timeline["events"]) == 2
    assert branch_timeline["events"][0]["id"] == "base-1"
    assert branch_timeline["events"][1]["label"] == "Raise"
    assert branch_timeline["events"][1]["date"] == "2028-01-01"
    assert branch_timeline["retirement"]["target_retirement_age"] == 60
