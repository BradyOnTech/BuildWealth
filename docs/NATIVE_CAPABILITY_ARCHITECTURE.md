# Native Capability Architecture

**Status**

Active companion to [ADR 0003: BuildWealth-native capability ownership](./adr/0003-buildwealth-native-capability-ownership.md).

**Direction**

BuildWealth should implement portfolio and planning depth as native capabilities, not as links, labels, or mental models from separate applications.

The main owning areas are:

- **Portfolio Analysis:** performance, benchmark comparison, attribution, allocation, risk, and trade impact.
- **Import Workbench:** import preview, reconciliation, apply, and Import Reports.
- **Asset Registry:** asset resolution, classification, enrichment, manual overrides, and review items.
- **Simulations:** scenarios, branches, saved simulations, Plan Strength, and failure-mode analysis.
- **Plan Strategy Lab:** contribution ordering, withdrawal strategy comparison, retirement tax controls, and plan lever comparison.

**Implementation Rule**

Each area should expose one small service interface to API routes, Copilot tools, and v2 UI components. The interface should accept BuildWealth-owned state, return BuildWealth-owned outputs, and record enough evidence for review, audit, and later replay.

Optional calculation services may still exist while migration is underway, but they are private implementation details. New product work should start from the user workflow and the owning BuildWealth module.

**Use For New Work**

- [Architecture](./ARCHITECTURE.md)
- [BuildWealth Native Capability Strategy](./BUILDWEALTH_NATIVE_CAPABILITY_STRATEGY_2026-05-08.md)
- [Native Portfolio and Plan Modules Implementation Guide](./NATIVE_PORTFOLIO_PLAN_MODULES_IMPLEMENTATION_GUIDE_2026-05-08.md)
- [Monte Carlo Decision Simulation Plan](./MONTE_CARLO_DECISION_SIMULATION_PLAN_2026-05-08.md)
