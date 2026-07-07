"""Peer benchmarking from SCF 2022 — honest estimates, honest refusals."""

from __future__ import annotations

from buildwealth_orchestrator.services.peer_benchmark import (
    bracket_for_age,
    build_peer_benchmark,
    estimate_percentile,
)


def _profile(birth_year: int | None) -> dict:
    members = []
    if birth_year is not None:
        members.append({"id": "m1", "display_name": "Me", "relationship": "self", "birth_year": birth_year})
    return {"household_members": members}


def test_brackets_cover_every_adult_age() -> None:
    assert bracket_for_age(22)["bracket"] == "under_35"
    assert bracket_for_age(35)["bracket"] == "35_44"
    assert bracket_for_age(54)["bracket"] == "45_54"
    assert bracket_for_age(80)["bracket"] == "75_plus"


def test_percentile_estimate_behaves_like_a_distribution() -> None:
    median, mean = 39_040, 183_500  # under-35 bracket
    at_median = estimate_percentile(39_040, median_usd=median, mean_usd=mean)
    assert at_median == 50
    # The mean sits far above the median in a heavy tail.
    at_mean = estimate_percentile(183_500, median_usd=median, mean_usd=mean)
    assert at_mean > 65
    # Monotonic, clamped, and honest about non-positive net worth.
    assert estimate_percentile(5_000, median_usd=median, mean_usd=mean) < 50
    assert estimate_percentile(50_000_000, median_usd=median, mean_usd=mean) == 99
    assert estimate_percentile(0, median_usd=median, mean_usd=mean) is None
    assert estimate_percentile(-10_000, median_usd=median, mean_usd=mean) is None


def test_ready_payload_for_a_22_year_old() -> None:
    payload = build_peer_benchmark(
        net_worth_usd=55_000.0,
        profile_payload=_profile(2004),
        current_year=2026,
    )
    assert payload["status"] == "ready"
    assert payload["age"] == 22
    assert payload["bracket_label"] == "under 35"
    assert payload["median_usd"] == 39_040
    # $55k > the under-35 median → "ahead of roughly N%".
    assert payload["percentile_estimate"] > 50
    assert "ahead of roughly" in payload["sentence"]
    assert "estimate" in payload["sentence"]
    # Milestones ladder up from the current bracket for chart overlays.
    labels = [m["label"] for m in payload["milestones"]]
    assert labels[0] == "median under 35"
    assert labels[-1] == "median 75+"
    # Comparability caveat always rides along.
    assert any("home equity" in caveat for caveat in payload["caveats"])


def test_negative_net_worth_gets_a_band_not_a_fake_number() -> None:
    payload = build_peer_benchmark(
        net_worth_usd=-12_000.0,
        profile_payload=_profile(2000),
        current_year=2026,
    )
    assert payload["status"] == "ready"
    assert payload["percentile_estimate"] is None
    assert "building from below zero" in payload["sentence"]


def test_missing_birth_year_asks_instead_of_guessing() -> None:
    payload = build_peer_benchmark(
        net_worth_usd=100_000.0,
        profile_payload=_profile(None),
        current_year=2026,
    )
    assert payload["status"] == "needs_age"
    assert "Profile" in payload["detail"]
