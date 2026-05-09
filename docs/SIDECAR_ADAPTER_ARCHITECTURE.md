# Sidecar Adapter Architecture

**Status**

Superseded by [ADR 0003: BuildWealth-native capabilities replace upstream sidecars](./adr/0003-buildwealth-native-capabilities-replace-upstream-sidecars.md).

**Historical Context**

This document originally described a hybrid runtime where selected high-complexity calculations could run in optional sidecars while the Python orchestrator remained the data owner.

That architecture is no longer the product target. BuildWealth should now implement the same or better user outcomes as BuildWealth-native capabilities, expressed through BuildWealth-owned data, services, v2 UI workflows, Copilot routes, and audit trails.

**Current Direction**

Use these native module names instead of sidecar or upstream-app language:

- **Portfolio Analytics Engine** for performance, benchmark, attribution, allocation, risk, and trade impact
- **Import Workbench** for import preview, reconciliation, apply, and Import Reports
- **Asset Registry** for asset resolution, classification, enrichment, manual overrides, and Asset Review Items
- **Plan Simulation Engine** for scenarios, branches, simulations, Saved Simulations, Plan Strength, and failure-mode analysis
- **Plan Strategy Lab** for contribution ordering, withdrawal strategy comparison, retirement tax controls, and Plan Lever comparison

**Migration Guidance**

Existing sidecar adapters, contracts, settings, tests, and Docker profiles should be treated as migration scaffolding or historical references. Do not expand them as a long-term architecture. New implementation should prefer native orchestrator services and v2 UI routes.

Removal should happen only after native workflows cover the relevant user jobs and tests prove no active workflow depends on the old adapter path.

**Do Not Use This Document For New Work**

For new implementation, use:

- [Architecture](./ARCHITECTURE.md)
- [BuildWealth Upstream App Exit Strategy](./UPSTREAM_APP_EXIT_STRATEGY_2026-05-08.md)
- [Native Portfolio and Plan Modules Implementation Guide](./NATIVE_PORTFOLIO_PLAN_MODULES_IMPLEMENTATION_GUIDE_2026-05-08.md)
- [Monte Carlo Decision Simulation Plan](./MONTE_CARLO_DECISION_SIMULATION_PLAN_2026-05-08.md)
