# BuildWealth Product Backlog (Current)

## Product Goal
Build a production-grade all-in-one financial command center that combines:
- financial picture clarity (portfolio + cash/debt/goals/profile),
- planning and projection depth (scenario/withdrawal/tax-aware modeling),
- research context,
- LLM workflows grounded in structured BuildWealth context.

## Planning Source of Truth
Detailed implementation sequencing lives in:
- [Standalone Build Plan](./STANDALONE_BUILD_PLAN.md)
- [Next Execution Steps (2026-04-14)](./NEXT_EXECUTION_STEPS_2026-04-14.md)

## Active Product Workstreams
1. Unified context productionization and quality hardening.
2. Portfolio/planning depth parity expansion where high leverage remains.
3. Copilot decision workflows and evidence/freshness UX hardening.
4. Sidecar contract governance, compatibility, and observability.
5. Data migration safety and operator runbook quality.

## Execution Principles
1. Ship vertical slices with tests and UI/API integration, not isolated internals.
2. Reuse Ghostfolio/Ignidash logic where it increases correctness/time-to-value.
3. Keep Python orchestrator as system of record and single product entrypoint.
4. Preserve explicit degraded-mode behavior when sidecars are unavailable.
