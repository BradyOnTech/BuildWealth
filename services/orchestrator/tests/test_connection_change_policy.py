from buildwealth_orchestrator.services.connection_change_policy import (
    CONNECTION_CHANGE_POLICY_VERSION,
    evaluate_connection_changes,
)


def test_versioned_change_policy_flags_material_changes_but_not_market_noise() -> None:
    previous = {
        "accounts": [
            {"provider_account_id": "acct", "current_balance": 10_000.0}
        ],
        "holdings": [
            {
                "provider_account_id": "acct",
                "provider_security_id": "vti",
                "symbol_or_identifier": "VTI",
                "quantity": 10.0,
            }
        ],
    }
    current = {
        "accounts": [
            {"provider_account_id": "acct", "current_balance": 10_500.0}
        ],
        "holdings": [
            {
                "provider_account_id": "acct",
                "provider_security_id": "vti",
                "symbol_or_identifier": "VTI",
                "quantity": 10.5,
            }
        ],
    }

    ordinary = evaluate_connection_changes(previous, current)
    assert ordinary["policy_version"] == CONNECTION_CHANGE_POLICY_VERSION
    assert ordinary["review_required"] is False

    current["holdings"][0]["quantity"] = 14.0
    material = evaluate_connection_changes(previous, current)
    assert material["review_required"] is True
    assert material["large_quantity_changes"] == 1
