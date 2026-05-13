# BuildWealth Native Capability Strategy

**Date**

2026-05-08

**Status**

Active planning companion to [BuildWealth Future State Product Plan](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md), [BuildWealth v2 Information Architecture and UX Strategy](./V2_INFORMATION_ARCHITECTURE_UX_STRATEGY_2026-05-08.md), and [ADR 0003](./adr/0003-buildwealth-native-capability-ownership.md).

**Decision**

BuildWealth should provide the full portfolio and planning workflow inside BuildWealth. A user should import data, review a portfolio, compare simulations, save decisions, and ask Copilot for help without needing another application surface or another product mental model.

**Target Product Model**

- **BuildWealth Orchestrator:** owns persistence, APIs, migrations, calculations, Copilot tools, and audit history.
- **BuildWealth v2 UI:** the single future product surface.
- **Primary navigation:** Today, Inbox, Plan, Portfolio, Profile, Copilot.
- **Data & Tools:** lower-frequency utilities such as Import & Sync, Accounts & Transactions, Prices & FX, Workflows, Activity Log, Data & Recovery, and Advanced Settings.
- **Implementation detail boundary:** optional calculation services can exist during migration, but they must not appear as user destinations, product labels, recommendation text, or Copilot answers.

**Feature Delta**

The remaining work is grouped by user job, not by old application boundary.

| User job | BuildWealth already has | BuildWealth should add | UI home |
| --- | --- | --- | --- |
| Get transactions and holdings into clean local state | CSV/statement import services, aliases, broker templates, portfolio store | Mapping review, duplicate resolution, account matching, dry-run diff, bulk accept/reject, import audit reports | Data & Tools -> Import & Sync, with alerts from Today |
| Find, classify, and maintain assets | Seed metadata, custom assets, manual prices, watchlist, research quote/history | First-class asset registry, symbol search, provider enrichment, metadata quality flags, delisted/unknown handling | Portfolio -> Assets, Data & Tools -> Prices & FX, Research |
| Understand return quality | Local performance, benchmark, attribution endpoints | Period presets, TWR/MWR/ROAI style views, cash-flow-adjusted performance, benchmark comparator, drawdown and contributor drilldowns | Portfolio -> Performance |
| Understand portfolio exposure and guardrails | Risk policy, risk alerts, fit assessment, trade simulation | Custom rule UI, asset-class/sector/region/account guardrails, pre-trade risk preview, alert-to-recommendation loop | Portfolio -> Watch/Risk, Inbox |
| Trust and inspect portfolio state | Backups, review packets, git activity, local files | Transaction export bundles, import reports, lot/cost-basis audit trail, corporate action logs, reconciliation history | Data & Tools -> Activity Log/Data & Recovery, Portfolio -> Audit |
| Explore common life events quickly | Branch templates, assumption sets, scenario branch endpoint | Template gallery, preview before apply, richer starter simulations, template-to-decision flow | Plan -> Branches/Templates |
| Model tax-aware retirement outcomes | Tax engine, RMD, Social Security, Roth conversion, filing status, state flat-rate support | Better control UX, glide path, SEPP, home sale exclusion, richer local tax settings, tax assumption quality warnings | Plan -> Assumptions/Timeline/Withdrawals, Profile -> Taxes |
| Decide where the next dollar goes | Contribution allocation engine and plan contribution rules | Visual order editor, employer match explanation, shared-limit diagnostics, max-balance and mega-backdoor explanation | Plan -> Contributions |
| Choose a retirement drawdown strategy | Withdrawal comparison route and v2 Plan section | Multi-chart comparison, tax/cash-flow depletion views, failure-mode summaries, strategy explainers | Plan -> Withdrawals |
| Understand why a projection changed | Scenario engine, scenario diff, plan tracking, artifacts | Percentile fan charts, cash-flow/tax/withdrawal timelines, metric extractors, what-changed explanation cards | Plan -> Trajectory/Scenarios |
| Preserve and compare decision states | Plan artifacts, decisions, active plan, tracking | Immutable simulation snapshots, side-by-side compare, stale-assumption review, saved decision bundles | Plan -> Scenarios/Decisions |

**Implementation Direction**

The replacement work should create BuildWealth modules with clear interfaces and local implementations.

- **Import Workbench:** owns import preview, reconciliation, apply, and audit reports.
- **Asset Registry:** owns symbol search, metadata, enrichment, manual overrides, and classification quality.
- **Portfolio Analysis:** owns performance, benchmark, attribution, allocation, and risk outputs.
- **Portfolio Audit:** owns export bundles, import history, transaction audit, and lot/cost-basis audit.
- **Plan Template and Snapshot:** owns starter templates, branches, immutable simulation snapshots, and comparisons.
- **Simulation Explainers:** own metric extraction, chart-ready outputs, and plain-English deltas.
- **Plan Strategy Lab:** owns contribution ordering, withdrawal comparisons, retirement tax controls, and strategy diagnostics.

Each module should expose one small interface to API routes, Copilot tools, and v2 UI components. This keeps the user workflow, backend logic, and tests evolving together.

**Removal Sequence**

1. Freeze the target language around BuildWealth-owned workflows.
2. Remove user-facing links to non-BuildWealth product surfaces.
3. Rename implementation labels to BuildWealth-owned terms.
4. Keep default startup and test data BuildWealth-only.
5. Make local services first-class.
6. Delete unused bridges, settings, contracts, and probes only after tests prove no active workflow depends on them.
7. Clean stale provenance and license wording from files that now describe BuildWealth-native logic.

**Workflow Acceptance Criteria**

BuildWealth is complete enough to retire the remaining migration scaffolding when:

- A user can import a real broker statement, review inferred mappings, resolve duplicates, apply the import, and inspect an import report without leaving BuildWealth.
- A user can search or create an asset, enrich metadata, set manual pricing, and understand whether the asset is suitable for their portfolio without leaving BuildWealth.
- A user can review portfolio performance, compare against benchmarks, inspect attribution, and understand allocation/risk rules in Portfolio.
- A user can create a life-event simulation from a template, compare it against the active plan, save a snapshot, and record a decision in Plan.
- A user can compare contribution orders and withdrawal strategies with tax/cash-flow explanations in Plan.
- Copilot can access the same BuildWealth-native APIs and route important changes through review/apply flows instead of becoming a hidden parallel UI.
- No primary or utility navigation item sends the user outside BuildWealth for portfolio or planning work.

**Main Risk**

The main risk is half-migration: powerful backend services that still require the user to jump through classic views, external links, JSON editors, or Copilot-only flows. New slices should therefore be vertical: backend interface, persisted state, API route, v2 UI, Copilot access where useful, and tests.
