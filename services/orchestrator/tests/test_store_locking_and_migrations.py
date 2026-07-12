from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from buildwealth_orchestrator.services import json_store_migrations
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.json_store_migrations import (
    migrate_payload,
    register_migration,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.store_locks import locked_store, synchronized_store


def test_concurrent_transactions_are_not_lost(tmp_path: Path) -> None:
    """20 threads adding transactions against fresh store instances (as
    per-request handlers do) must not lose writes to read-modify-write races."""
    workers = 20

    def add_one(index: int) -> None:
        store = PortfolioStore(tmp_path)  # fresh instance per "request"
        store.add_transaction(
            date="2026-07-10",
            symbol=f"SYM{index}",
            action="BUY",
            quantity=1.0,
            unit_price=100.0,
            fee=0.0,
            account="taxable-brokerage",
            currency="USD",
            note="",
            lot_method="FIFO",
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(add_one, range(workers)))

    transactions = PortfolioStore(tmp_path).list_transactions(limit=1000)
    symbols = {t["symbol"] for t in transactions}
    assert len([t for t in transactions if t["symbol"].startswith("SYM")]) == workers
    assert {f"SYM{i}" for i in range(workers)} <= symbols


def test_concurrent_recommendation_updates_are_not_lost(tmp_path: Path) -> None:
    inbox_path = tmp_path / "inbox.json"
    seed = RecommendationInbox(inbox_path)
    ids = [
        seed.create(
            title=f"rec {i}",
            detail="detail",
            priority="medium",
            recommendation_type="rebalance",
        )["id"]
        for i in range(12)
    ]

    def archive_one(rec_id: str) -> None:
        RecommendationInbox(inbox_path).set_status(rec_id, "archived")

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(archive_one, ids))

    payload = json.loads(inbox_path.read_text())
    archived = [r for r in payload["recommendations"] if r.get("status") == "archived"]
    assert len(archived) == 12


def test_locked_store_serializes_critical_sections(tmp_path: Path) -> None:
    counter_path = tmp_path / "counter.json"
    counter_path.write_text("0")

    def bump() -> None:
        with locked_store(counter_path):
            value = int(counter_path.read_text())
            counter_path.write_text(str(value + 1))

    with ThreadPoolExecutor(max_workers=16) as pool:
        for _ in range(200):
            pool.submit(bump)
        pool.shutdown(wait=True)

    assert counter_path.read_text() == "200"


def test_synchronized_store_reentrant_public_methods(tmp_path: Path) -> None:
    @synchronized_store("path")
    class Store:
        def __init__(self, path: Path):
            self.path = path
            self.calls: list[str] = []

        def outer(self) -> None:
            self.calls.append("outer")
            self.inner()

        def inner(self) -> None:
            self.calls.append("inner")

    store = Store(tmp_path / "x.json")
    store.outer()  # must not deadlock on the re-entrant lock
    assert store.calls == ["outer", "inner"]


@pytest.fixture()
def _isolated_migrations(monkeypatch):
    monkeypatch.setattr(json_store_migrations, "_MIGRATIONS", {})


def test_migration_runner_applies_in_order_and_stamps_version(_isolated_migrations) -> None:
    register_migration("demo_store", 2, lambda p: {**p, "a": 1})
    register_migration("demo_store", 3, lambda p: {**p, "b": p["a"] + 1})

    payload, changed = migrate_payload("demo_store", {"schema_version": 1})
    assert changed is True
    assert payload["a"] == 1 and payload["b"] == 2
    assert payload["schema_version"] == 3

    again, changed = migrate_payload("demo_store", payload)
    assert changed is False
    assert again["schema_version"] == 3


def test_migration_runner_rejects_gaps(_isolated_migrations) -> None:
    register_migration("gap_store", 2, lambda p: p)
    with pytest.raises(ValueError):
        register_migration("gap_store", 4, lambda p: p)


def test_registered_store_migrations_run_on_load(tmp_path: Path, _isolated_migrations) -> None:
    """A registered migration for the recommendations inbox runs once on load
    and is persisted with the new schema_version."""
    register_migration(
        "recommendations_inbox",
        2,
        lambda p: {**p, "recommendations": [{**r, "migrated": True} for r in p["recommendations"]]},
    )

    inbox_path = tmp_path / "inbox.json"
    inbox_path.write_text(json.dumps({
        "schema_version": 1,
        "recommendations": [
            {"id": "rec-1", "title": "t", "detail": "d", "priority": "low",
             "status": "proposed", "recommendation_type": "rebalance"},
        ],
    }))

    inbox = RecommendationInbox(inbox_path)
    rows = inbox.list(limit=10, include_archived=True)
    assert rows and rows[0].get("migrated") is True

    persisted = json.loads(inbox_path.read_text())
    assert persisted["schema_version"] == 2


def test_financial_profile_load_applies_ordered_migrations(tmp_path: Path, _isolated_migrations) -> None:
    from buildwealth_orchestrator.services.financial_profile import PROFILE_SCHEMA_VERSION

    # The profile store already stamps its own schema version; ordered
    # migrations continue from there.
    for offset in range(2, PROFILE_SCHEMA_VERSION + 2):
        marker = offset == PROFILE_SCHEMA_VERSION + 1
        register_migration(
            "financial_profile",
            offset,
            (lambda p: {**p, "flags": {**p.get("flags", {}), "v_next": True}}) if marker else (lambda p: p),
        )
    store = FinancialProfileStore(tmp_path / "profile.json")
    payload = store.get()
    assert payload["flags"]["v_next"] is True
    assert payload["schema_version"] == PROFILE_SCHEMA_VERSION + 1
