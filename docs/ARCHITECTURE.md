# Architecture

**Status**

Active architecture summary. This document supersedes earlier retired calculation module-first architecture language.

**Overview**

BuildWealth runs as a standalone local-first application with the Python orchestrator as the control plane, data owner, calculation owner, API owner, and Copilot tool boundary.

The long-term architecture is BuildWealth-native capability ownership. Portfolio analytics, import/review, asset registry, plan simulations, strategy comparisons, recommendations, audit trails, and Copilot workflows should live inside BuildWealth and use BuildWealth language.

**Core Principles**

1. Single source of truth: the orchestrator owns persistence, schema upgrades, API contracts, and durable financial state.
2. BuildWealth-native capabilities: user workflows should not depend on external app surfaces, labels, settings, or runtime paths.
3. v2 product surface: all current and future user workflows target v2; classic/v1 is temporary migration scaffolding.
4. Reviewed mutation: Copilot, recommendations, imports, simulations, and strategy comparisons may draft changes, but material changes use review/apply flows.
5. Plain-language decision support: user-facing copy should describe what is safe to do next, not expose internal model or engine jargon.

**Runtime Components**

### 1. BuildWealth Orchestrator

- FastAPI app and local web UI host
- Local stores for Profile, Portfolio, Plan, Recommendations, Research artifacts, Copilot context, and system state
- Schema migration and normalization on read/write paths
- Portfolio, planning, recommendation, research, import, audit, and storage services
- Copilot orchestration, tool routing, and context packaging

### 2. v2 Product Surface

- Primary user interface for Today, Inbox, Plan, Portfolio, Profile, Copilot, and Data & Tools
- Canonical home for all new user workflows
- Replacement target for classic/v1 workflows through Workflow Replacement, not screen cloning

### 3. BuildWealth-Native Capability Modules

- **Import Workbench:** import preview, mapping, reconciliation, duplicate review, account matching, unknown asset resolution, apply, and Import Reports
- **Asset Registry:** asset resolution, classification, metadata quality, manual overrides, price/FX support, and Asset Review Items
- **Portfolio Analysis:** portfolio performance, benchmark, attribution, allocation, risk, fit review, and trade impact
- **Portfolio Audit:** import reports, transaction changes, account changes, asset resolutions, manual price/FX overrides, lot/cost-basis changes, corporate actions, review packets, and saved trade simulations
- **Simulations:** scenarios, branches, simulations, Saved Simulations, Plan Strength, failure-mode analysis, and historical/Monte Carlo paths
- **Plan Strategy Lab:** contribution ordering, withdrawal strategy comparison, retirement tax controls, and Plan Lever comparison
- **Context Intelligence:** governed context capture, retrieval, conflict review, and context traces for Copilot and recommendations

### 4. Optional Providers

- Market/research providers such as OpenBB
- LLM providers
- Local storage, backup, protection, and git tooling

Providers enrich or operate BuildWealth-owned workflows. They do not own user-facing product surfaces or Canonical State.

**Data And Control Flow**

1. User/API writes update BuildWealth Canonical State through orchestrator-owned routes.
2. Imports produce Import Reports as Source Evidence and update Portfolio state only after review/apply.
3. Portfolio analytics read Portfolio state and produce reviewable metrics, risk signals, and evidence.
4. Plan simulations test Plans, Scenarios, and Branches without mutating the active Plan.
5. Saved Simulations and Plan Decisions become Source Evidence.
6. Recommendations route users to the relevant v2 workflow and preserve outcomes.
7. Copilot operates through the same BuildWealth APIs and review boundaries as the UI.

**Legacy And Migration Notes**

Earlier architecture used portfolio and planning modules retired calculation module language for targeted reuse. That direction is superseded by ADR 0003. External app references are historical scaffolding and should be removed from runtime paths, UI labels, module names, recommendation text, Copilot answers, and default operations.

Classic/v1 route scaffolding has been removed after product-owner approval. New user workflows must land on the v2 product surface.

See:

- [ADR 0003: BuildWealth-native capabilities replace native capability ownership](./adr/0003-buildwealth-native-capability-ownership.md)
- [ADR 0004: v2 is the only future product surface](./adr/0004-v2-is-the-only-future-product-surface.md)
- [BuildWealth BuildWealth Native Capability Strategy](./BUILDWEALTH_NATIVE_CAPABILITY_STRATEGY_2026-05-08.md)
- [Native Portfolio and Plan Modules Implementation Guide](./NATIVE_PORTFOLIO_PLAN_MODULES_IMPLEMENTATION_GUIDE_2026-05-08.md)
- [Monte Carlo Decision Simulation Plan](./MONTE_CARLO_DECISION_SIMULATION_PLAN_2026-05-08.md)
