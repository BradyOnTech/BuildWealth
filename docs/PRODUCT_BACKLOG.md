# BuildWealth Product Backlog

## Product Goal
Build a production-grade all-in-one financial command center that combines:
- financial picture clarity (portfolio + cash/debt/goals/profile),
- planning and projection depth (scenario/withdrawal/tax-aware modeling),
- research context,
- LLM workflows grounded in structured BuildWealth context.

## Planning Source of Truth
Active product direction and high-level phase sequencing now live in:
- [BuildWealth Future State Product Plan (2026-04-26)](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)

Historical implementation sequencing and progress logs remain in:
- [BuildWealth Product Roadmap (historical source of truth, 2026-04-15)](./ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md)
- [Standalone Build Plan (historical progress log)](./STANDALONE_BUILD_PLAN.md)
- [Next Execution Steps (2026-04-14, historical)](./NEXT_EXECUTION_STEPS_2026-04-14.md)

## Product Workstreams

The future-state plan reframes these workstreams around operating loops instead of isolated feature queues. Keep this list as a backlog lens, not as the active prioritization source.

1. Research intelligence depth (multi-symbol compare, dossiers, ranked watchlist context).
2. Decision intelligence engine (ranked recommendations, pre-apply simulation, closure analytics).
3. Planning realism expansion (advanced tax/withdrawal/simulation modes and household modeling).
4. Portfolio industrialization (import reconciliation, lot/corporate-action audit depth, reporting).
5. Productization and trust layer (durability, backup/restore, security and observability).

## Execution Principles
1. Ship vertical slices with tests and UI/API integration, not isolated internals.
2. Reuse Ghostfolio/Ignidash logic where it increases correctness/time-to-value.
3. Keep Python orchestrator as system of record and single product entrypoint.
4. Preserve explicit degraded-mode behavior when sidecars are unavailable.
