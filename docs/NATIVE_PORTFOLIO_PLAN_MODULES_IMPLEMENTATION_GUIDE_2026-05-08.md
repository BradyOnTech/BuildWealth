# Native Portfolio and Plan Modules Implementation Guide

**Date**

2026-05-08

**Status**

Active implementation guide for BuildWealth-native Portfolio, Plan, and Data & Tools workflows.

This guide follows [ADR 0003](./adr/0003-buildwealth-native-capabilities-replace-upstream-sidecars.md) and [ADR 0004](./adr/0004-v2-is-the-only-future-product-surface.md). Do not use external app names, sidecar labels, or classic/v1 fallback language for new product surfaces.

**Guiding Idea**

The user should not need to know which former upstream app inspired a feature. They should only know the financial job they are trying to do:

- get clean data into BuildWealth
- understand current capital
- inspect risk and performance
- compare possible futures
- choose the next action
- preserve the decision trail

BuildWealth should expose these jobs where the user naturally looks for them:

- **Today:** what changed, what is stale, what needs review
- **Inbox:** what decision is waiting
- **Portfolio:** what the current capital implies
- **Plan:** what the future could look like
- **Profile:** what personal facts and assumptions drive the model
- **Copilot:** natural-language access to the same reviewed workflows
- **Data & Tools:** lower-frequency import, maintenance, recovery, and audit utilities

**Implementation Principles**

Each replacement should be a BuildWealth Module with:

- a narrow backend Interface
- a local Implementation under the orchestrator
- persisted state owned by BuildWealth
- v2 UI access from the correct user workflow
- Copilot access only through the same API contracts
- tests that cover service behavior, API shape, and the main UI path

Do not create new top-level sidebar entries unless the user would return to that surface weekly. Import, audit, asset maintenance, and settings belong in Data & Tools or contextual Portfolio/Plan sections. Portfolio analytics belong in Portfolio. Scenario templates and simulation explainers belong in Plan.

**Settled Product Language**

| Domain concept | User-facing language |
| --- | --- |
| Import Workbench | Import & Review |
| Import Report | Import report |
| Asset Registry | Investments & Assets |
| Asset Review Item | Asset needs review |
| Portfolio Analytics Engine | Portfolio Analysis |
| Portfolio Audit | Portfolio History |
| Plan Simulation Engine | Simulations |
| Simulation Run | Simulation |
| Simulation Artifact | Saved Simulation |
| Plan Resilience | Plan Strength |
| Plan Lever | What-if change |
| Plan Lever Impact Level | Review level |
| Plan Strategy Lab | Strategy Comparison |
| Plan Decision | Plan decision |

Use "simulation" intentionally in the UI. A plan is the user's real working financial thesis; a simulation is an experiment against it.

**Current Code Homes**

Use existing locality before creating new directories.

| Area | Existing home | Implementation guidance |
| --- | --- | --- |
| Backend services | `services/orchestrator/src/buildwealth_orchestrator/services/` | Add focused service modules here. Keep orchestration in services, not UI or Copilot prompts. |
| API routes | `services/orchestrator/src/buildwealth_orchestrator/main.py` | Keep existing route families stable. Add routes near related portfolio/import/plan routes until route modules are introduced. |
| API schemas | `services/orchestrator/src/buildwealth_orchestrator/schemas.py` | Add typed request/response models for new user-facing contracts. |
| v2 UI shell | `services/orchestrator/src/buildwealth_orchestrator/web-v2/app.js` | Keep primary nav small. Data & Tools is the utility entrypoint. |
| v2 API client | `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js` | Add thin wrappers for every new endpoint. Do not call fetch inline from view modules. |
| v2 Import UI | `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/import_sync.js` | Split into `views/import_sync/` helpers once the workbench grows. |
| v2 Portfolio UI | `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/portfolio.js` and `views/portfolio/` | Add sub-sections for Performance, Assets, Transactions, Accounts, Risk, and Audit without turning the main page into an admin console. |
| v2 Plan UI | `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js` and `views/plan/` | Extend the existing Plan movements: assumptions, trajectory, scenarios, branches, withdrawals, timeline, contributions, decisions. |
| Frontend tests | `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/` | Add unit tests for render helpers and browser specs for critical flows. |
| Backend tests | `services/orchestrator/tests/` | Add service tests first, then route tests for contracts with user-facing impact. |

**User Workflow 1: First Real Data Import**

The user starts in Today and sees a stale-data warning, or opens Data & Tools -> Import & Sync directly. They drop a broker CSV or statement into the inbox, preview what BuildWealth recognized, fix mappings, choose accounts, resolve duplicates, apply the import, and receive a durable import report.

**Module:** Import Workbench.

**User-facing label:** Import & Review.

**Backend home:**

- Extend `csv_importer.py` and `statement_importer.py` for parsing and inference.
- Add `import_workbench.py` for session orchestration, preview, duplicate resolution, and apply planning.
- Add an import report store if reports outgrow the existing import file listing. Use the same local-first storage patterns as `versioned_workspace.py` and portfolio stores.

**API shape:**

- Keep existing routes: `/api/import/statement`, `/api/import/statement/apply`, `/api/import/csv`, `/api/import/upload-csv`, `/api/import/files`, `/api/import/csv-templates`.
- Add workbench routes only when they represent durable sessions, for example `/api/import/workbench/preview`, `/api/import/workbench/sessions`, `/api/import/workbench/{session_id}/apply`, and `/api/import/workbench/{session_id}/report`.

**UI/UX home:**

- Data & Tools -> Import & Sync is the primary home.
- Today links here when data is stale or an import is waiting.
- Portfolio links here from Transactions and Accounts when data quality blocks analysis.
- Copilot may prepare an import preview, but the apply step must remain a reviewed UI action.

**UX requirements:**

- Show a four-step flow: file, mapping, reconciliation, apply.
- Use confidence labels for inferred fields and broker templates.
- Put duplicate handling and account matching before apply.
- After apply, show imported, skipped, merged, and unresolved counts.
- Save an import report and link it from Activity Log or Portfolio Audit.

**Tests:**

- backend parsing and reconciliation tests in `test_csv_importer.py` or new `test_import_workbench.py`
- route tests for preview/apply/report
- v2 render tests for mapping and reconciliation states
- one browser workflow for preview -> resolve -> apply -> report

**User Workflow 2: Maintaining Asset Truth**

The user imports an unknown ticker, reviews a watchlist candidate, or researches a potential investment. BuildWealth should let them resolve the asset, enrich metadata, override price/classification when needed, and see where the asset participates in holdings, risk, and plan assumptions.

**Module:** Asset Registry.

**User-facing label:** Investments & Assets.

**Backend home:**

- Add `asset_registry.py` as the Interface over seeded metadata, `portfolio_store.py`, `asset_metadata_seed.py`, `price_updater.py`, custom assets, manual prices, and research lookup.
- Keep market data provider details behind the registry. Portfolio and Plan should ask for resolved assets, not provider-specific payloads.

**API shape:**

- Prefer portfolio-scoped routes unless the asset is clearly cross-domain: `/api/portfolio/assets/search`, `/api/portfolio/assets/{symbol}`, `/api/portfolio/assets/{symbol}/metadata`, `/api/portfolio/assets/{symbol}/price-override`.
- Keep existing manual price, FX, custom asset, and watchlist routes stable while the registry is introduced.

**UI/UX home:**

- Portfolio -> Assets for asset search, classification, custom assets, and metadata quality.
- Data & Tools -> Prices & FX for price/FX maintenance.
- Research can deep-link into Portfolio Assets when a symbol lacks trusted metadata.
- Import Workbench should route unresolved symbols here before apply when possible.

**UX requirements:**

- Show whether metadata is seeded, imported, manually overridden, or provider-enriched.
- Make manual overrides explicit and reversible.
- Keep asset detail tied to user consequences: holdings, allocation, risk rules, watchlist thesis, research evidence, and plan exposure.

**Tests:**

- service tests for search, resolve, enrich, manual override, and unknown symbols
- route tests for stable asset metadata contracts
- v2 tests proving unresolved imports and research flows deep-link to the asset registry

**User Workflow 3: Understanding Portfolio Performance And Risk**

The user opens Portfolio from Today or Inbox after a performance, risk, or recommendation alert. They need to know what happened, why it happened, whether it matters, and what action is available.

**Module:** Portfolio Analytics Engine.

**User-facing label:** Portfolio Analysis.

**Backend home:**

- Keep `portfolio_performance.py`, `portfolio_benchmark.py`, `portfolio_attribution.py`, `portfolio_metrics.py`, `portfolio_risk_alerts.py`, and `portfolio_simulator.py`.
- Add `portfolio_analytics.py` only if it becomes useful as a shallow Interface that composes those services for UI/API responses.
- Avoid leaking sidecar terms through the response body unless debugging metadata is explicitly requested.

**API shape:**

- Keep existing routes: `/api/portfolio/holdings`, `/api/portfolio/benchmark`, `/api/portfolio/attribution`, `/api/portfolio/risk-policy`, `/api/portfolio/simulate-trade`, `/api/portfolio/fit-assessment`.
- Add chart-ready routes only when the current payloads become too broad, for example `/api/portfolio/performance`, `/api/portfolio/risk-review`, or `/api/portfolio/allocation`.

**UI/UX home:**

- Portfolio remains the primary destination.
- The first view should stay executive: standing, composition, watch, fit review.
- Advanced work should sit behind Portfolio sub-sections: Performance, Allocation, Risk, Transactions, Accounts, Assets, Audit.
- Inbox links directly to a focused Portfolio section when a recommendation was triggered by risk, concentration, or performance drift.

**UX requirements:**

- Use common time periods: Today, WTD, MTD, YTD, 1Y, 5Y, Max.
- Show portfolio return against at least one benchmark.
- Separate price return, income return, contribution/cash-flow effects, and fees where data allows.
- Explain top contributors, detractors, concentration, asset-class drift, sector/region exposure, and account-level risks.
- Let the user simulate a trade before accepting a recommendation.

**Tests:**

- service tests for return periods, benchmark comparisons, attribution, and risk rule edge cases
- route tests for performance and risk contracts
- v2 tests for period switching, benchmark rendering, risk alerts, and trade simulation entry

**User Workflow 4: Auditing And Exporting Portfolio State**

The user wants to trust the numbers. They need to inspect how imports changed transactions, how lots were rebuilt, whether manual prices affected values, and what exportable record exists.

**Module:** Portfolio Audit.

**User-facing label:** Portfolio History.

**Backend home:**

- Keep `portfolio_review_packets.py` for review packet generation.
- Add `portfolio_audit.py` if audit events become first-class.
- Add `portfolio_export.py` if export bundles need more than ad hoc route helpers.
- Store audit records close to portfolio state, with stable IDs that can be linked from import reports and recommendations.

**API shape:**

- Keep `/api/portfolio/review-packets`.
- Add `/api/portfolio/audit`, `/api/portfolio/audit/{event_id}`, and `/api/portfolio/export` when needed.

**UI/UX home:**

- Portfolio -> Audit for portfolio-specific audit history.
- Data & Tools -> Activity Log/Data & Recovery for cross-system trust and restore workflows.

**UX requirements:**

- Show imports, transaction edits, deletes, lot/cost-basis changes, manual price overrides, FX changes, and generated review packets.
- Let a user export transactions, holdings, lots, metadata, and audit reports as a bundle.
- Keep destructive actions reviewable and reversible where local storage supports it.

**User Workflow 5: Starting From A Plan Template**

The user does not want to build every scenario from scratch. They want to ask "what if I retire early?" or "what if I buy a house?" and get a branch they can inspect before it touches the active plan.

**Module:** Plan Template and Saved Simulation.

**Backend home:**

- Extend `plan_workspace.py` where templates and Saved Simulation references belong to a plan.
- Add `plan_templates.py` if template generation, validation, and defaults become complex.
- Add `plan_saved_simulations.py` if Saved Simulation volume or lookup needs outgrow the existing Plan evidence pattern.
- Reuse `timeline_defaults.py`, `timeline_projection.py`, `income_projection.py`, `expense_projection.py`, and `debt_projection.py` for template payloads.

**API shape:**

- Keep existing branch routes: `/api/plans/{plan_id}/branch-templates`, `/api/plans/{plan_id}/scenario-branch`, `/api/plans/{plan_id}/scenario-diff`.
- Add Saved Simulation routes aligned with the simulation plan: `/api/plans/{plan_id}/simulations/saved`, `/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}`, and `/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/decision`.

**UI/UX home:**

- Plan -> What-ifs for template gallery and branch previews.
- Plan -> Simulations for saved comparisons and Saved Simulations.
- Plan -> Decisions for the final "why we chose this" record.
- Inbox may deep-link into a specific branch template when a recommendation needs plan simulation.

**UX requirements:**

- Show templates as user jobs, not technical presets: early retirement, job change, home purchase, one-income household, Roth conversion ladder, market stress, high-tax retirement.
- Preview assumptions before running.
- Save scenario outputs as immutable Saved Simulations.
- Let the user compare Saved Simulation vs active plan and attach the result to a decision.

**Tests:**

- backend tests for template validation, branch payload construction, Saved Simulation immutability, and comparison deltas
- v2 tests for template selection, branch preview, Saved Simulation save, and decision attachment

**User Workflow 6: Understanding Simulation Results**

The user runs a scenario and sees a projection. They need to understand what drove the result, what changed compared with the active plan, and which assumptions matter most.

**Module:** Plan Simulation Engine.

**User-facing label:** Simulations.

**Backend home:**

- Keep `scenario_engine.py`, `tax_engine.py`, `contribution_rules.py`, `rmd_projection.py`, `social_security_projection.py`, and projection services.
- Treat `planning_sidecar.py` as migration scaffolding while native simulation coverage is built.
- Add `plan_simulation_analyzer.py` to extract chart-ready metrics, phase summaries, drivers, warnings, and explanation payloads from raw simulation results.
- Add `plan_lever_impact.py` for two-stage Plan Lever Impact Policy classification.
- Use existing `test_simulation_delta.py` patterns for comparison behavior.

**API shape:**

- Keep `/api/planning/scenarios`, `/api/plans/{plan_id}/scenario-diff`, and withdrawal comparison routes.
- Add `/api/plans/{plan_id}/simulation-explain` only if explanation needs a stable contract separate from scenario execution.

**UI/UX home:**

- Plan -> Overview for active Plan Strength.
- Plan -> Simulations for simulation runs, comparison output, and Saved Simulations.
- Plan -> Withdrawals for drawdown strategy comparison.
- Plan -> Assumptions for driver review.

**UX requirements:**

- Show percentile bands when stochastic or Monte Carlo simulations are active.
- Show year-by-year cash flow, taxes, contributions, withdrawals, account balances, and RMD effects.
- Explain deltas in plain language: "this scenario improves the median ending value because expenses fall in 2031 and taxable withdrawals start later."
- Distinguish model weakness from bad outcome. Missing tax data, stale profile fields, and low simulation confidence should be visible.
- Make every recommendation trace back to the simulation inputs that produced it.
- Saved Simulations are immutable; changing one creates a new simulation based on the saved one.

**Tests:**

- service tests for metric extraction and delta explanation
- route tests for explanation contracts
- v2 tests for chart sections, warnings, and linked assumptions

**User Workflow 7: Choosing Contribution And Withdrawal Strategies**

The user wants to know where the next dollar should go before retirement and how retirement withdrawals should happen later.

**Module:** Plan Strategy Lab.

**User-facing label:** Strategy Comparison.

**Backend home:**

- Keep `contribution_rules.py`, `tax_engine.py`, `scenario_engine.py`, and withdrawal comparison routes.
- Add small explanation helpers rather than bloating the engines. The engines should calculate. The explainer should translate.

**API shape:**

- Keep `/api/plans/{plan_id}/contribution-rules`, `/api/planning/contribution-allocation`, and existing withdrawal comparison endpoints.
- Add diagnostics to existing responses before creating new routes.

**UI/UX home:**

- Plan -> Contributions for contribution ordering and account priority.
- Plan -> Withdrawals for strategy comparison.
- Profile -> Taxes for personal tax facts.
- Plan -> Assumptions for model assumptions that affect taxes and returns.

**UX requirements:**

- Use a visual ordered list for contribution priority.
- Explain shared limits, employer match, HSA eligibility, IRA income restrictions, taxable overflow, and mega-backdoor assumptions.
- Compare withdrawal strategies by taxes, ending value, depletion risk, cash-flow stability, and account exhaustion order.
- Translate withdrawal comparisons into plain-English drivers: highest ending value, inflation-adjusted value, middle simulation result, rough downside result, taxes, withdrawals, and trade-offs.
- Let the user save the chosen strategy as a plan decision.
- Classify every what-if change with the two-stage Plan Lever Impact Policy before apply.

**Two-stage Review Level Policy:**

The user-facing label is **Review level**. Use only **Low review** and **High review** in the UI.

Stage one asks whether the change is materially large:

- High review when a dollar assumption changes by at least $10,000 per year.
- High review when a one-time branch event changes cash flow by at least $25,000.
- High review when future value or inflation-adjusted value changes by at least $50,000 or at least 5% of the active-plan result.
- High review when success probability changes by at least five percentage points.
- High review when a return, inflation, or tax-rate assumption changes by at least one percentage point.
- High review when the planning horizon changes by at least two years.
- High review when taxes, withdrawal strategy, withdrawal order, filing status, or Roth conversion settings change.
- High review when three or more assumptions change at once.

Stage two asks whether the result is decision-ready:

- High review when the simulation has model warnings.
- High review when the explanation confidence is low.
- High review when the result weakens the active plan or has trade-offs.
- High review when the result lacks a clear active-plan comparison.

Overall Review level is High review when either stage is high. Otherwise it is Low review. Keep the language basic: "slow down before applying this" rather than "materiality threshold exceeded."

**Cross-Cutting Copilot Guidelines**

Copilot should help the user reach these workflows, not replace them.

- For imports, Copilot can identify likely templates and summarize preview issues, but apply remains a reviewed action.
- For asset metadata, Copilot can explain missing context and draft metadata changes, but the registry remains the source of truth.
- For portfolio risk, Copilot should link to the exact Portfolio section and recommendation.
- For plan changes, Copilot should create a draft scenario, branch, or decision rather than silently changing active assumptions.
- For any material change, Copilot should expose the data it used, stale fields, and what will be persisted.

**Build Order**

1. **Native framing and cleanup.** Remove external app links once replacement links exist, rename user-facing sidecar labels, and update stale license/provenance docs.
2. **Import Workbench.** This unlocks trustworthy data and removes one of the strongest reasons old external portfolio workflows remained reachable.
3. **Portfolio Analytics and Asset Registry.** This turns Portfolio into the complete capital workspace and removes another major old external portfolio workflow.
4. **Plan Templates and Saved Simulations.** This gives users a fast way into meaningful what-if work and removes another major old external planning workflow.
5. **Simulation Explainer and Strategy Lab.** This makes advanced planning legible enough for real decisions.
6. **Audit, export, and final deletion.** Once native workflows cover the daily jobs, remove dead bridge code, default infrastructure references, and legacy app navigation.

**Definition Of Done For Each Slice**

- Backend service owns the behavior.
- API route returns typed request/response models.
- v2 UI exposes the workflow from the correct home.
- Today, Inbox, Portfolio, Plan, Profile, or Data & Tools links to it when context calls for it.
- Copilot uses the same API and review boundaries.
- Tests cover service behavior, route contracts, and the main UI interaction.
- User-facing labels say BuildWealth concepts, not Ghostfolio, Ignidash, or sidecar.
