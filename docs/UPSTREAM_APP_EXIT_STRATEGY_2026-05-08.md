# BuildWealth Upstream App Exit Strategy

**Date**

2026-05-08

**Status**

Active planning companion to [BuildWealth Future State Product Plan](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md) and [BuildWealth v2 Information Architecture and UX Strategy](./V2_INFORMATION_ARCHITECTURE_UX_STRATEGY_2026-05-08.md).

**Decision**

BuildWealth should absorb the high-value product ideas from Ghostfolio and Ignidash as BuildWealth-native modules, then remove Ghostfolio and Ignidash from runtime navigation, user-facing settings, default infrastructure, and the active product mental model.

Ghostfolio and Ignidash should become reference/provenance history, not application surfaces. The user should open BuildWealth, import data into BuildWealth, review portfolios in BuildWealth, compare plans in BuildWealth, and ask Copilot to operate over BuildWealth-owned state.

**Important License Note**

Ghostfolio and Ignidash are currently licensed as AGPL-3.0 projects. Changing implementation language or technology does not automatically eliminate derivative-work or license obligations. This document is not legal advice, but the durable product posture should be:

- avoid blind copy/paste ports
- implement against BuildWealth's own domain model and user workflows
- preserve provenance notes where existing adapted logic remains
- use upstream projects as product and test references, not as runtime product dependencies
- keep public/distributed scenarios in mind even if the current goal is a proof of concept

**Current Reality**

BuildWealth has already moved past the original sidecar idea in several important ways.

The Python orchestrator is the system of record for portfolio, profile, plan, recommendations, research artifacts, Copilot context, and durable local state. The current architecture docs still describe optional Ghostfolio and Ignidash compute sidecars, but the default local mode does not require full upstream app containers.

The remaining value of Ghostfolio and Ignidash is mostly product depth:

- Ghostfolio is useful as a reference for portfolio import, reconciliation, performance analysis, risk rules, asset metadata, and exports.
- Ignidash is useful as a reference for scenario templates, tax-aware retirement controls, contribution ordering, withdrawal strategy comparison, simulation explainers, and plan snapshots.

The sidecar label should shrink over time. It should not mean "the user can jump into another app." It should only mean "a temporary implementation adapter may exist behind a BuildWealth-owned interface until a local BuildWealth implementation replaces it."

**Target Product Model**

The long-term product model is:

- **BuildWealth Orchestrator:** owns persistence, APIs, migrations, calculations, Copilot tools, and audit history.
- **BuildWealth v2 UI:** the single product surface.
- **Primary navigation:** Today, Inbox, Plan, Portfolio, Profile, Copilot.
- **Data & Tools:** lower-frequency utilities such as Import & Sync, Accounts & Transactions, Prices & FX, Workflows, Activity Log, Data & Recovery, and Advanced Settings.
- **No Ghostfolio/Ignidash product links:** external upstream apps should not appear in the main app experience.
- **Attribution only where needed:** provenance belongs in docs and file headers, not in day-to-day UX labels.

**Feature Delta**

The useful upstream ideas should be grouped by user job, not by upstream app name.

| Source reference | User job | BuildWealth already has | BuildWealth should add | UI home |
| --- | --- | --- | --- | --- |
| Ghostfolio import/reconciliation | Get transactions and holdings into clean local state | CSV/statement import services, aliases, broker templates, portfolio store | Mapping review, duplicate resolution, account matching, dry-run diff, bulk accept/reject, import audit reports | Data & Tools -> Import & Sync, with alerts from Today |
| Ghostfolio asset metadata/search | Find, classify, and maintain assets | Seed metadata, custom assets, manual prices, watchlist, research quote/history | First-class asset registry, symbol search, provider enrichment, metadata quality flags, delisted/unknown handling | Portfolio -> Assets, Data & Tools -> Prices & FX, Research |
| Ghostfolio performance/benchmark | Understand return quality | Local performance, benchmark, attribution endpoints | Period presets, TWR/MWR/ROAI style views, cash-flow-adjusted performance, benchmark comparator, drawdown and contributor drilldowns | Portfolio -> Performance |
| Ghostfolio allocation/risk rules | Understand portfolio exposure and guardrails | Risk policy, risk alerts, fit assessment, trade simulation | Custom rule UI, asset-class/sector/region/account guardrails, pre-trade risk preview, alert-to-recommendation loop | Portfolio -> Watch/Risk, Inbox |
| Ghostfolio export/audit | Trust and inspect portfolio state | Backups, review packets, git activity, local files | Transaction export bundles, import reports, lot/cost-basis audit trail, corporate action logs, reconciliation history | Data & Tools -> Activity Log/Data & Recovery, Portfolio -> Audit |
| Ignidash scenario templates | Explore common life events quickly | Branch templates, assumption sets, scenario branch endpoint | Template gallery, preview before apply, richer starter scenarios, template-to-decision flow | Plan -> Branches/Templates |
| Ignidash retirement/tax controls | Model tax-aware retirement outcomes | Tax engine, RMD, Social Security, Roth conversion, filing status, state flat-rate support | Better control UX, glide path, SEPP, home sale exclusion, richer local tax settings, tax assumption quality warnings | Plan -> Assumptions/Timeline/Withdrawals, Profile -> Taxes |
| Ignidash contribution ordering | Decide where the next dollar goes | Contribution allocation engine and plan contribution rules | Visual order editor, employer match explanation, shared-limit diagnostics, max-balance and mega-backdoor explanation | Plan -> Contributions |
| Ignidash withdrawal comparison | Choose a retirement drawdown strategy | Withdrawal comparison route and v2 Plan section | Multi-chart comparison, tax/cash-flow depletion views, failure-mode summaries, strategy explainers | Plan -> Withdrawals |
| Ignidash simulation explainers | Understand why a projection changed | Scenario engine, scenario diff, plan tracking, artifacts | Percentile fan charts, cash-flow/tax/withdrawal timelines, metric extractors, "what changed" explanation cards | Plan -> Trajectory/Scenarios |
| Ignidash plan snapshots | Preserve and compare decision states | Plan artifacts, decisions, active plan, tracking | Immutable scenario snapshots, side-by-side compare, stale-assumption review, saved decision bundles | Plan -> Scenarios/Decisions |

**Implementation Direction**

The replacement work should create BuildWealth Modules with clear Interfaces and local Implementations.

- **Import Workbench Module:** owns import preview, reconciliation, apply, and audit reports.
- **Asset Registry Module:** owns symbol search, metadata, enrichment, manual overrides, and classification quality.
- **Portfolio Analytics Module:** owns performance, benchmark, attribution, allocation, and risk outputs.
- **Portfolio Audit Module:** owns export bundles, import history, transaction audit, and lot/cost-basis audit.
- **Plan Template and Snapshot Module:** owns starter templates, branches, immutable scenario snapshots, and comparisons.
- **Plan Simulation Explainer Module:** owns simulation metric extraction, chart-ready outputs, and plain-English deltas.
- **Plan Strategy Lab Module:** owns contribution ordering, withdrawal comparisons, retirement tax controls, and strategy diagnostics.

Each Module should expose one small Interface to API routes, Copilot tools, and v2 UI components. This improves Locality: the user workflow, backend logic, and tests can evolve together without leaking upstream app concepts.

**Removal Sequence**

1. **Freeze the target language.** Update docs to say Ghostfolio and Ignidash are reference systems, not product destinations.
2. **Remove user-facing app links.** Delete Ghostfolio/Ignidash links from v2 Data & Tools and classic navigation once native replacement links exist.
3. **Rename engine labels.** Replace user-facing sidecar names with BuildWealth-owned labels such as Portfolio Analytics Engine and Planning Projection Engine.
4. **Move legacy containers out of the default stack.** Keep full upstream app containers only in a separate reference compose file if they are still useful for parity checks.
5. **Make local engines first-class.** Keep the existing API contracts where possible, but route default behavior through BuildWealth-native services.
6. **Delete dead bridges.** Remove unused clients, exporters, sidecar settings, and contract files only after tests prove no active workflow depends on them.
7. **Clean up provenance.** Keep accurate attributions for adapted logic, fix stale license notes, and remove obsolete "MIT" references.

**Workflow Acceptance Criteria**

BuildWealth can remove Ghostfolio and Ignidash as runtime concepts when these workflows are complete:

- A user can import a real broker statement, review inferred mappings, resolve duplicates, apply the import, and inspect an import report without leaving BuildWealth.
- A user can search or create an asset, enrich metadata, set manual pricing, and understand whether the asset is suitable for their portfolio without leaving BuildWealth.
- A user can review portfolio performance, compare against benchmarks, inspect attribution, and understand allocation/risk rules in Portfolio.
- A user can create a life-event scenario from a template, compare it against the active plan, save a snapshot, and record a decision in Plan.
- A user can compare contribution orders and withdrawal strategies with tax/cash-flow explanations in Plan.
- Copilot can access the same BuildWealth-native APIs and route important changes through review/apply flows instead of becoming a hidden parallel UI.
- No primary or utility navigation item sends the user to Ghostfolio or Ignidash.

**Open Risks**

The main risk is not calculation difficulty. BuildWealth already has many of the engines. The main risk is half-migration: keeping powerful backend services while the user still has to jump through classic views, external links, JSON editors, or Copilot-only flows.

The implementation should therefore prioritize complete vertical slices. Each slice should include backend Interface, persisted state, API route, v2 UI, Copilot access where useful, and tests. Partial hidden engines are useful only when they clearly prepare the next user-visible workflow.

**Sources**

- [Ghostfolio README](https://raw.githubusercontent.com/ghostfolio/ghostfolio/main/README.md)
- [Ghostfolio LICENSE](https://github.com/ghostfolio/ghostfolio/blob/main/LICENSE)
- [Ignidash README](https://raw.githubusercontent.com/schelskedevco/ignidash/main/README.md)
- [Ignidash LICENSE](https://github.com/schelskedevco/ignidash/blob/main/LICENSE)
- [BuildWealth Architecture](./ARCHITECTURE.md)
- [BuildWealth Standalone Operations](./OPERATIONS_STANDALONE.md)
- [BuildWealth Sidecar Adapter Architecture](./SIDECAR_ADAPTER_ARCHITECTURE.md)
- [BuildWealth v2 Information Architecture and UX Strategy](./V2_INFORMATION_ARCHITECTURE_UX_STRATEGY_2026-05-08.md)
