# BuildWealth Product Roadmap (Source of Truth)

## Date
2026-04-15

## Status
Active canonical roadmap for post-Phase-3.7 execution.

This document replaces `docs/NEXT_EXECUTION_STEPS_2026-04-14.md` as the active planning sequence and supersedes roadmap sections in `docs/STANDALONE_BUILD_PLAN.md` that are now stale or already complete.

## Progress Log

### 2026-04-15 (Completed - Phase 5.0 Slice 4, Household/Couple Planning Mode)
1. Added household-mode planning controls and persistence across planning contracts:
- `household_mode`, partner-income/retirement/Social-Security fields, shared-goal target fields, and filing-status fields are now available in scenario request + plan settings surfaces.
- Plan Workspace settings validation now enforces valid household mode and filing-status enumerations.
2. Added household-aware projection adjustments to planning execution:
- couple mode now layers partner-income growth and partner Social Security into income projections.
- shared-goal targets are converted into annual funding runways and injected into expense projections through target year.
- household defaults now resolve filing status to `married_filing_jointly` when couple mode is active and filing status is unset/invalid.
3. Added household context explainability in planning results:
- planning responses now carry a first-class `household` context object (mode, filing, partner assumptions, modeled first-year/total partner-income lift, shared-goal annual funding).
- scenario assumptions are annotated with household/filing fields so diff/branch comparisons preserve assumption provenance.
4. Extended Plan Workspace UX visibility:
- settings and scenario-diff editors include household mode + filing status selectors and partner/shared-goal numeric controls.
- diff/branch output rendering now includes household context sections and summary-line transitions (`mode`/`filing` base->candidate).
5. Source-provenance note:
- approach follows Ignidash-style assumption layering (explicit scenario assumption overlays) and tax-filing semantics from Ignidash tax model structure while keeping BuildWealth API/UI contracts first-class.
6. Added regression coverage:
- household projection adjustments and filing-status defaults (`test_household_planning.py`)
- plan settings household/filing validation (`test_plan_workspace.py`)
- sidecar metadata forwarding + Copilot settings-contract coverage remain in place (`test_planning_sidecar.py`, `test_copilot_tool_updates.py`).
7. Verification: `pytest -q services/orchestrator/tests` passes (`424 passed`).

### 2026-04-15 (Completed - Phase 5.0 Slice 3, Configurable Drawdown Ordering)
1. Added configurable drawdown-order controls in the planning simulation engine:
- introduced drawdown buckets/presets (`cash`, `taxable`, `tax_deferred`, `tax_free`) and alias normalization.
- added `drawdown_order` parsing for both preset and explicit list forms.
- wired drawdown order into account-withdrawal priority selection while preserving legacy age-aware behavior when unset.
2. Extended planning contracts and persistence:
- added `drawdown_order` to scenario request and plan settings/timeline schemas.
- persisted and sanitized drawdown order in Plan Workspace settings and retirement timeline payloads.
- included drawdown-order context in plan markdown/context summaries.
3. Wired drawdown-order execution through API, sidecar, and Copilot surfaces:
- threaded drawdown order through plan scenario run paths (plan scenarios, diff, strategy compare, branch compute, and context baseline run).
- added sidecar metadata forwarding for drawdown order.
- expanded Copilot tool contract for `run_planning_scenarios` to accept `drawdown_order`.
4. Extended Plan Workspace UI:
- added retirement timeline drawdown-order input and editor wiring for load/save/disabled states.
5. Source-provenance note:
- decumulation-order override structure follows Ignidash simulation-engine style assumption layering (explicit assumption override on top of default strategy behavior).
- BuildWealth-specific schema/API/UI contracts remain first-class and are not a runtime fork of upstream apps.
6. Added regression coverage:
- scenario-engine drawdown-order override behavior (`test_scenario_engine.py`)
- plan workspace settings/timeline drawdown-order persistence (`test_plan_workspace.py`)
- sidecar metadata forwarding (`test_planning_sidecar.py`)
- Copilot planning tool contract field coverage (`test_copilot_tool_updates.py`).
7. Verification: `pytest -q services/orchestrator/tests` passes (`420 passed`).

### 2026-04-14 (Completed - Phase 5.0 Slice 1-2, Tax Realism + Roth Conversion Controls)
1. Expanded tax realism layer in planning simulation surfaces:
- added state-tax and IRMAA fields to tax-estimate and scenario contracts (`schemas.py`)
- added state/IRMAA breakdown outputs in scenario timeline points and plan compare responses
- added profile/plan settings support for state tax in persistence and UI controls.
2. Implemented Roth conversion planning controls and simulation behavior:
- new plan/scenario controls: `roth_conversion_annual_amount_usd`, `roth_conversion_start_age`, `roth_conversion_end_age`
- scenario engine now executes yearly tax-deferred -> Roth transfers in-window, adds conversion dollars to ordinary taxable income, and records conversion totals in assumptions/timeline/account outputs
- conversion metadata now flows through API and Copilot planning-tool contracts, including sidecar metadata payloads.
3. Extended planning UX and compare output visibility:
- Plan Workspace settings now includes Roth conversion controls for both saved settings and diff overlays
- withdrawal-strategy comparison output now surfaces total Roth conversions by strategy row.
4. Source-provenance note:
- tax/simulation extension follows Ignidash tax and simulation-engine structure patterns (`src/lib/calc/taxes.ts`, `src/lib/calc/simulation-engine.ts`)
- conversion control wiring remains within BuildWealth contracts and does not fork/embed upstream app runtime.
5. Added regression coverage:
- scenario conversion behavior (`test_scenario_engine.py`)
- assumption set parsing/application updates (`test_plan_assumption_sets.py`)
- plan workspace settings/assumption persistence/validation (`test_plan_workspace.py`)
- sidecar metadata forwarding (`test_planning_sidecar.py`)
- Copilot planning tool contract updates (`test_copilot_tool_updates.py`).
6. Verification: `pytest -q services/orchestrator/tests` passes (`419 passed`).

### 2026-04-14 (Completed - Phase 4.2 Follow-up, Recommendation Quality Trend Views)
1. Added Recommendation Quality Trend panel to Today Dashboard:
- one-click `Refresh Trend` control
- global (`all`) and rolling (`30d`, `90d`) closure calibration summaries
- active-plan scoped trend row when an active plan exists.
2. Added Plan Workspace closure trend panel:
- new “Closure Trend (30/90d)” section in plan editor
- one-click `Refresh Trend` control
- per-window measured coverage, directional match rate, and MAE visibility.
3. Wired trend state and refresh lifecycle:
- added `dashboardClosureTrend` and `planClosureTrend` state nodes
- plan trend automatically refreshes after closure-summary artifact generation
- plan detail render path now lazy-loads plan-scoped trend when cache is stale or missing.
4. Source-provenance note:
- trend/calibration window packaging reuses the previously added closure analytics model (Ignidash-style quality windows)
- actionability and explainability surfaces remain aligned with Ghostfolio-style transparent dashboard conventions.
5. Verification: `pytest -q services/orchestrator/tests` passes (`413 passed`).

### 2026-04-14 (Completed - Phase 4.2 Follow-up, Plan Workspace Closure-Analytics Artifacts)
1. Added plan-scoped closure analytics summaries for longitudinal review workflows:
- closure analytics now supports `plan_id` scoping in both API and Copilot tool surfaces.
2. Added one-click plan summary artifact generation:
- new endpoint `POST /api/plans/{plan_id}/recommendation-closure-summary`
- generates plan-scoped calibration summary payload and optionally persists markdown artifact (`recommendation_closure_analytics`)
- writes a plan decision-log entry documenting the review event.
3. Added Copilot execution surface:
- new tool `create_plan_recommendation_closure_summary` to create plan-scoped closure calibration artifacts directly from chat.
4. Expanded Plan Workspace UI:
- added “Closure Calibration Summary” panel in plan editor
- added one-click “Generate Artifact” control that writes artifact + decision log and renders calibration stats inline.
5. Source-provenance note:
- summary/calibration packaging follows Ignidash-style analyzer segment reporting
- artifact and audit trail behavior remains aligned with Ghostfolio-style explainability and review traceability conventions.
6. Added regression coverage:
- plan-scoped filtering and summary artifact generation tests in `test_recommendation_closure_analytics.py`
- Copilot contract/invocation coverage for new plan-closure-summary tool in `test_copilot_tool_updates.py`.
7. Verification: `pytest -q services/orchestrator/tests` passes (`413 passed`).

### 2026-04-14 (Completed - Phase 4.2 Follow-up, Recommendation Calibration Reporting by Type/Source)
1. Expanded closure analytics payload into a first-class calibration report:
- added `calibration_model_version` (`calibration_v1`)
- added `calibration_summary` with measured coverage, directional-match quality, error metrics, and bias classification
- added `calibration_by_type` and `calibration_by_source` with per-segment measured count, match rate, MAE, and aggregate gap/error totals.
2. Added rolling calibration window summaries:
- `calibration_windows` now returns `30d`, `90d`, and `all` slices for quick trend monitoring and later dashboard/workspace visualizations.
3. Preserved backward compatibility:
- existing `summary`, `by_status`, `by_type`, `by_source`, and `items` fields remain intact
- closure analytics route and Copilot tool contract are unchanged (`get_recommendation_closure_analytics`), with richer response content.
4. Updated Inbox UI analytics panel:
- now surfaces calibration-by-type and calibration-by-source quality stats
- adds calibration window trend card and calibration bias in the analytics summary line.
5. Source-provenance note:
- calibration packaging follows Ignidash-style analyzer segment/quality reporting patterns
- actionable explainability remains aligned with Ghostfolio-style transparent metric surfaces.
6. Added regression coverage:
- extended `test_recommendation_closure_analytics.py` assertions for calibration summary, segmented calibration rows, and calibration windows.
7. Verification: `pytest -q services/orchestrator/tests` passes (`408 passed`).

### 2026-04-14 (Completed - Phase 4.2 Slice 4, Top 3 Next Actions in Dashboard and Plan Workspace)
1. Added shared Top Next Actions contract:
- new `TopNextAction` schema for ranked action cards (priority, type, source, score/rank, score reasons, action hint)
- added `top_next_actions` to both `TodayDashboardResponse` and `PlanDetailResponse`.
2. Added recommendation-driven Top 3 selector in `main.py`:
- uses ranked recommendation scoring output (existing `recommendation_scoring.py` pipeline)
- scopes actions for Plan Workspace to `{plan_id, global}` recommendations
- falls back to global ranked list if plan-scoped results are empty.
3. Wired Top 3 actions into dashboard API payload:
- `build_today_dashboard_response()` now injects ranked Top 3 actions
- when no inbox recommendations are available, falls back to existing dashboard heuristics.
4. Wired Top 3 actions into plan-detail API responses:
- plan create/get/update/settings/decision/refresh responses now include `top_next_actions` via shared detail builder.
5. Updated UI surfaces:
- Today Dashboard now has a dedicated “Top 3 Next Actions” card with rank/score/type/source visibility and one-click inbox navigation
- Plan Workspace now renders plan-scoped “Top 3 Next Actions” with one-click inbox navigation.
6. Source-provenance note:
- ranking and score-factor transparency continues to reuse Ignidash-style analyzer packaging patterns already in recommendation scoring
- action prioritization display remains aligned with Ghostfolio-inspired “actionable risk/explainability” presentation conventions used elsewhere in dashboard surfaces.
7. Added regression coverage:
- plan-scoped next-action selection and plan-detail enrichment tests in `test_recommendation_ranking_integration.py`.
8. Verification: `pytest -q tests/test_recommendation_ranking_integration.py tests/test_today_dashboard.py tests/test_recommendation_actions.py tests/test_copilot_tool_updates.py tests/test_buildwealth_context.py` passes (`49 passed`).

### 2026-04-14 (Completed - Phase 4.2 Slice 3, Expected-vs-Realized Outcomes and Closure Analytics)
1. Added first-class expected-vs-realized outcome tracking on recommendation closure:
- apply/reject flows now persist `expected_outcome` and `expected_vs_realized` metadata in `decision_closure`
- expected values are derived from scenario-diff baseline deltas when available.
2. Added realized-outcome update surface for closed recommendations:
- `POST /api/recommendations/{recommendation_id}/outcome`
- records realized deltas, observation metadata, and recomputed expected-vs-realized metrics
- writes refreshed closure artifacts when plan context is available.
3. Added closure analytics API and Copilot retrieval surface:
- `GET /api/recommendations/closure-analytics`
- Copilot tool `get_recommendation_closure_analytics`
- analytics summarize coverage, measured counts, directional match rate, and outcome deltas by status/type/source.
4. Added Copilot outcome logging tool:
- `update_recommendation_outcome` for one-call realized-outcome capture.
5. Expanded Inbox UI outcome visibility:
- Closure Analytics panel with summary and grouped counts
- closed recommendations now surface expected outcomes, realized outcomes, and expected-vs-realized gap details
- added one-click `Log Outcome` action for applied/rejected rows.
6. Source-provenance note:
- outcome packaging follows Ignidash-style analyzer/calibration summary patterns
- closure artifact persistence remains consistent with Ghostfolio-style auditability and decision traceability.
7. Added regression coverage:
- outcome update and analytics behavior in `test_recommendation_closure_analytics.py`
- updated closure expectations in `test_recommendation_actions.py`
- Copilot tool contract/invocation coverage in `test_copilot_tool_updates.py`.
8. Verification: `pytest -q services/orchestrator/tests` passes (`406 passed`).

### 2026-04-14 (Completed - Phase 4.1 Slice 4, Copilot Recommendation Evidence-Citation Enforcement)
1. Added research dossier retrieval surfaces for recommendation evidence workflows:
- `GET /api/research/dossiers` (plan-scoped dossier artifact lookup)
- Copilot tool `research_dossier_lookup` for artifact-aware evidence retrieval in recommendation loops.
2. Added recommendation evidence-citation quality model (`citation_v1`) in creation flow:
- recommendation action payloads now normalize `evidence.citations`
- recommendation evidence now includes `citation_quality` (`required`, `status`, required/cited/missing symbols, missing dossier symbols).
3. Enforced dossier-backed citations for Copilot research-backed recommendations:
- when source is Copilot and research symbols are present, dossier-backed citations are required
- system auto-cites from latest plan dossier artifacts when available
- requests fail with explicit guidance when dossier citation coverage is still missing.
4. Updated workflow recommendation packaging to use the same citation-normalization pipeline for consistency.
5. Updated recommendation scoring and UI to surface citation quality:
- confidence scoring now rewards satisfied dossier citation coverage and penalizes missing required coverage
- Inbox recommendation detail now displays citation status with cited/missing symbols.
6. Source-provenance note:
- analyzer-style evidence quality packaging remains aligned with Ignidash scoring/reporting patterns
- artifact-centric research traceability stays consistent with Ghostfolio-style structured data provenance expectations.
7. Added regression coverage:
- dossier lookup and citation-enforcement tests in `test_recommendation_evidence_citations.py`
- Copilot tool contract/invocation coverage in `test_copilot_tool_updates.py`
- citation quality scoring behavior in `test_recommendation_scoring.py`.
8. Verification: `pytest -q services/orchestrator/tests` passes (`400 passed`).

### 2026-04-14 (Completed - Phase 4.1 Slice 3, Watchlist Ranking Endpoint and UI Score Surfacing)
1. Expanded watchlist API contract into a first-class ranking response shape:
- added `WatchlistRankItem` / `WatchlistRankResponse` schemas
- watchlist rows now include composite score factors, ranked position, reason codes, and history-record count.
2. Added watchlist scoring/ranking orchestration in `main.py`:
- score model `watchlist_v1` combines momentum, trend, target-gap, data quality, and risk-balance factors
- supports `sort` controls (`ranked`, `symbol`, `updated_at`) and `limit` controls for large lists
- warnings are normalized and deduplicated for cleaner operator output.
3. Added first-class ranking endpoint and Copilot retrieval tool:
- `GET /api/research/watchlist-rank`
- Copilot tool `research_watchlist_rank` with period/interval/limit controls.
4. Updated Portfolio UI watchlist surface:
- watchlist table now shows rank and score
- summary line surfaces ranking model and top symbol
- note column includes score-driver hints and upside-to-target context.
5. Added regression coverage:
- ranking/sort behavior tests in `test_portfolio_watchlist.py`
- tool registry/contract/invocation coverage in `test_copilot_tool_updates.py`.
6. Source-provenance note:
- score packaging and factor transparency mirrors Ignidash analyzer-style output conventions
- watchlist signal framing remains aligned with Ghostfolio watchlist/market-condition presentation patterns.
7. Verification: `pytest -q services/orchestrator/tests` passes (`393 passed`).

### 2026-04-14 (Completed - Phase 4.2 Slice 2, Pre-Apply Recommendation Preview)
1. Added first-class pre-apply recommendation preview contract:
- `POST /api/recommendations/{recommendation_id}/preview`
- request supports `plan_id`, `plan_settings_updates`, `capture_scenario_diff`, and `decision_status`.
2. Added orchestration path `preview_recommendation(...)`:
- enforces pre-apply status (`proposed` only)
- returns action preview by recommendation type (`plan_settings_update`, `workflow_action`, `general`)
- reuses scenario-diff capture flow for plan-setting recommendations before mutation.
3. Added Copilot tool `preview_recommendation` with matching argument surface.
4. Added Inbox one-click Preview UX:
- proposed rows now include a `Preview` action
- added preview panel showing action summary, scenario delta when captured, and warnings.
5. Added regression coverage:
- preview behavior tests in `test_recommendation_actions.py`
- tool contract + invocation coverage in `test_copilot_tool_updates.py`.
6. Verification: `pytest -q services/orchestrator/tests` passes (`389 passed`).

### 2026-04-14 (Completed - Phase 4.2 Slice 1, Recommendation Scoring Engine)
1. Added a dedicated recommendation scoring service (`recommendation_scoring.py`) with transparent factor outputs:
- impact
- confidence
- urgency
- reversibility
- weighted total and rank metadata (`model_version: v1`).
2. Switched recommendation list flow to ranked ordering by default:
- open/proposed recommendations are ranked by score
- non-open recommendations are ordered by recency.
3. Extended recommendation contracts to expose score transparency:
- `RecommendationItem` now carries a structured `score` object with factor breakdown and score drivers.
4. Added API/tool sorting controls:
- `/api/recommendations` now accepts `sort` (`ranked` default, `created_at` fallback).
- Copilot `list_recommendations` tool now accepts `sort`.
5. Updated Inbox UI to surface ranking:
- new sort selector (Ranked/Newest)
- score column with rank
- score breakdown and driver hints in recommendation detail rows.
6. Added regression coverage:
- scoring engine behavior (`test_recommendation_scoring.py`)
- inbox list sort controls (`test_recommendation_inbox.py`)
- main integration for ranked/default sorting and score-bearing route output (`test_recommendation_ranking_integration.py`)
- Copilot tool contract update (`test_copilot_tool_updates.py`).
7. Source-provenance note:
- analyzer-style weighted summary packaging aligns with Ignidash `src/lib/calc/data-analyzers/*` output conventions.
8. Verification: `pytest -q services/orchestrator/tests` passes.

### 2026-04-14 (Completed - Phase 4.1 Slice 2, Research Dossier Artifacts)
1. Added first-class research dossier contract and orchestration path:
- `POST /api/research/dossier` with thesis/risks/catalysts, baseline controls, and optional plan artifact persistence.
- `research_dossier` Copilot tool with matching parameters and system-prompt guidance.
2. Added dossier generation service flow in `research.py`:
- compare-driven scorecard embedding
- key-takeaway synthesis and freshness metadata (`fresh` / `partial` / `degraded`)
- portfolio-fit framing using current symbol weights.
3. Added plan artifact integration for dossiers:
- optional `save_to_plan` support with `research_dossier` artifact kind.
- graceful warning path when no active/valid plan is available.
4. Expanded `Research` UI with dossier controls and outputs:
- thesis/risks/catalysts inputs
- dossier generation action
- rendered takeaways, freshness status, markdown payload, and artifact status.
5. Added regression coverage for service and Copilot tool contracts:
- dossier shape/freshness/portfolio-fit tests in `test_research_service.py`
- tool contract and invocation tests in `test_copilot_tool_updates.py`.
6. Source-provenance note:
- output packaging follows Ignidash-style analyzer summary structure (`src/lib/calc/data-analyzers/*`) and uses Ghostfolio-aligned symbol normalization conventions already in active BuildWealth research flows.
7. Verification: `pytest -q services/orchestrator/tests` passes (`376 passed`).

### 2026-04-14 (Completed - Phase 4.1 Slice 1, Research Compare Vertical Slice)
1. Added first-class research compare API surface:
- `POST /api/research/compare` with symbol set, period/interval, baseline controls.
- response includes ranked items, score, period return, volatility, and baseline-relative deltas.
2. Added comparison computation logic in research service:
- quote/history metric normalization
- volatility estimation by interval
- composite ranking score and summary winners.
3. Added Copilot tool `research_compare` and system prompt guidance for multi-symbol candidate analysis.
4. Added dedicated `Research` UI view with comparison form, ranked table, summary, and warning surfaces.
5. Added regression coverage in `test_research_service.py` and `test_copilot_tool_updates.py`.
6. Verification: `pytest -q services/orchestrator/tests` passes (`372 passed`).

## Product Purpose
Build a production-grade all-in-one financial command center that unifies:
1. Financial picture clarity (portfolio + cash/debt/goals/profile).
2. Planning and projection depth (tax-aware scenarios, withdrawals, timeline modeling).
3. Investment research depth.
4. LLM workflows grounded in structured BuildWealth context and actionable decision loops.

## Architecture Invariants (Do Not Break)
1. Python orchestrator remains system of record and product entrypoint.
2. Sidecars remain optional, contract-bound compute adapters (no full-app runtime dependency).
3. Degraded mode remains explicit and safe when sidecars/providers are unavailable.
4. Vertical slices ship with API + UI + tests together.

## Upstream Review Summary (Completed 2026-04-14)

### Ghostfolio repository areas reviewed
- `apps/api/src/app/portfolio/{calculator,portfolio.service.ts,rules.service.ts}`
- `apps/api/src/app/import/*`
- `apps/api/src/app/{activities,account-balance,symbol,export}`
- `apps/api/src/services/data-provider/*`
- `apps/client/src/app/components/{portfolio-performance,benchmark-comparator,home-watchlist}`

### Ignidash repository areas reviewed
- `src/lib/calc/{simulation-engine,portfolio,account,taxes,returns,contribution-rules}`
- `src/lib/calc/returns-providers/*`
- `src/lib/calc/data-analyzers/*`
- `src/lib/schemas/inputs/*`
- `convex/{plans,timeline,tax_settings,templates,validators}`

### Feature signals from upstream still relevant to BuildWealth
1. Ghostfolio patterns to leverage further:
- richer symbol search and metadata UX flow (`symbol` module patterns)
- account-balance detail views and portfolio rules/tagging patterns
- import/export and reconciliation ergonomics
- benchmark/performance visualization polish patterns

2. Ignidash patterns to leverage further:
- simulation modes: fixed, stochastic, historical backtest, Monte Carlo variants
- analyzer/reporting layer for multi-simulation comparison
- more complete retirement/tax scenario controls (drawdown order, advanced decumulation)
- stronger plan/template/schema lifecycle controls

## Licensing and Compliance Gate (Mandatory)
As of 2026-04-14, Ghostfolio and Ignidash GitHub default branches report AGPL-3.0 licenses.

Actions required before further direct code adaptation from current upstream revisions:
1. Run explicit legal review for AGPL compatibility with BuildWealth distribution model.
2. Distinguish between:
- algorithmic re-implementation inspired by public behavior/tests, and
- direct derivative reuse from AGPL source.
3. Track provenance by file and commit hash for all upstream-informed implementations.
4. Keep `ATTRIBUTIONS.md` and file headers in sync with actual source/revision provenance.

Until legal review is complete, prioritize:
- contract-level interoperability,
- behavioral parity tests,
- clean-room Python implementations where needed.

## Current Delivered Baseline (Shipped)
1. Portfolio foundation: multi-account ledger, lot-aware holdings, configurable cost basis, total return decomposition, cash ledger, manual prices, custom assets, FX + FX history, historical backfill, watchlist, broker template import coverage, benchmark/attribution adapters.
2. Planning foundation: tax engine baseline, contribution rules, income/expense/debt/physical-asset projections, timeline events, tax-aware scenario core, withdrawal strategies, Social Security, RMD, assumption sets, scenario branching, branch templates, projection visuals.
3. BuildWealth differentiator foundation: unified context quality/coverage metadata, cache observability/reset controls, decision packets, recommendation closure metadata, research-to-planning bridge with persisted plan artifacts.
4. UX and operations foundation: guided planners/editors, standalone-first operations docs, migration/compatibility docs, sidecar contract hardening.

## Remaining Strategic Build (What Is Left)
The highest-leverage missing work is no longer raw parity checkboxes. It is decision-grade integration quality across portfolio, planning, research, and Copilot loops.

### A) Research Intelligence Depth
1. Multi-symbol compare with normalized metrics, thesis context, and portfolio-fit framing.
2. Fundamental + estimate + earnings + news/sentiment packaging into reusable research dossiers.
3. Watchlist scoring/ranking with explicit reason codes and freshness metadata.
4. Research provenance and evidence scoring in Copilot-visible context.

### B) Decision Intelligence Operating Loop
1. Recommendation prioritization by expected impact, confidence, reversibility, and time horizon.
2. One-click "simulate before apply" for recommendation classes.
3. Post-decision outcome tracking and calibration (did expected delta materialize?).
4. Decision history analytics: what action classes actually improved outcomes.

### C) Planning Realism Expansion
1. State/local tax layer, IRMAA surcharge modeling, and tax-friction realism.
2. Roth conversion planning and configurable drawdown ordering.
3. Household/couple planning constraints and shared-goal modeling.
4. Simulation mode expansion (historical/stochastic/Monte Carlo variants) with comparable output summaries.

### D) Portfolio and Data Operations Hardening
1. Import quality framework: deterministic parser confidence, reconciliation reports, and corrective UX.
2. Corporate actions depth and lot-audit explainability.
3. Expanded risk analytics (factor/sector/geography concentration trajectories and drift alerts).
4. Export/reporting surfaces for advisor-style portfolio and plan snapshots.

### E) Productization and Platform Reliability
1. Persistence hardening beyond ad-hoc JSON stores for higher durability and concurrency safety.
2. Backup/restore workflow and data integrity checks.
3. Local security hardening for sensitive financial and conversation data.
4. Performance budgets and observability SLOs (API latency, cache behavior, snapshot freshness).

## Execution Plan (Phased)

### Phase 4.0 - Truth Reset and Platform Baseline (1 week)
Goal: remove doc drift and reduce architecture entropy before adding major surface area.

Slices:
1. Adopt this roadmap as canonical and convert older planning docs to historical pointers.
2. Correct stale capability audit references and parity assumptions in legacy docs.
3. Add license/compliance checklist to engineering workflow for upstream reuse.
4. Start route/module decomposition plan for `main.py` and large UI view files.

Definition of done:
1. Every planning doc points to one canonical active roadmap.
2. Stale or contradictory parity statements are marked historical.
3. No new feature work starts without explicit source-provenance note.

### Phase 4.1 - Research Intelligence Foundation (2 to 4 weeks)
Goal: make research a first-class decision input, not a thin quote endpoint.

Slices:
1. Add `POST /api/research/compare` for multi-symbol analysis.
2. Add research dossier artifacts (`research_dossier`) with thesis, metrics, risks, catalysts, and freshness.
3. Add watchlist ranking endpoint and UI list sorted by score/priority.
4. Add Copilot tools for compare + dossier retrieval and enforce evidence citations in recommendations.

Upstream reuse targets:
1. Ghostfolio symbol/data-provider patterns for normalized market metadata retrieval.
2. Ignidash analyzer output structuring patterns for multi-scenario comparison style summaries.

Definition of done:
1. Research compare flows are accessible via API, UI, and Copilot.
2. At least one recommendation class consumes dossier evidence directly.
3. Research context quality is visible in unified context and recommendation payloads.

### Phase 4.2 - Decision Intelligence Engine (2 to 3 weeks)
Goal: move from "suggestion inbox" to ranked, outcome-aware action system.

Slices:
1. Add recommendation scoring service (`impact`, `confidence`, `urgency`, `reversibility`).
2. Add one-click pre-apply simulation for each supported recommendation type.
3. Persist expected vs realized outcome fields and expose closure analytics.
4. Add "Top 3 Next Actions" card in dashboard and plans workspace.

Upstream reuse targets:
1. Ignidash simulation/compare patterns for expected delta calculation.
2. Ghostfolio portfolio risk/presentation conventions for action explainability.

Definition of done:
1. Recommendation inbox defaults to ranked actions with transparent scores.
2. Apply/reject flows include expected impact and post-closure realized impact where available.
3. Copilot can answer "what should I do next" with ranked, evidence-backed actions.

### Phase 5.0 - Planning Realism Expansion (3 to 5 weeks)
Goal: upgrade retirement and tax realism from foundation to robust planning depth.

Slices:
1. Add state tax and IRMAA modeling surfaces in tax engine and scenario outputs.
2. Add Roth conversion plan controls and scenario-aware conversion simulation.
3. Add configurable drawdown ordering in withdrawal strategies.
4. Add household/couple planning mode with shared goals and filing assumptions.
5. Add simulation mode selector (fixed/stochastic/historical/Monte Carlo variants) and comparison outputs.

Upstream reuse targets:
1. Ignidash `returns-providers/*` and `simulation-engine.ts` patterns for simulation modes.
2. Ignidash `taxes.ts` structures for extended tax-processing design.

Definition of done:
1. New tax and decumulation controls are editable in plan workspace and reflected in outputs.
2. Scenario compare clearly reports impact deltas from each realism toggle.
3. Tests cover mode selection, tax extensions, and conversion edge cases.

### Phase 5.1 - Portfolio Industrialization (3 to 5 weeks)
Goal: raise portfolio operations from feature-rich to audit-grade reliability.

Slices:
1. Add import reconciliation report (accepted/rejected/normalized rows and confidence flags).
2. Expand corporate actions and lot-audit explainability artifacts.
3. Add portfolio drift/risk alerts tied to allocation and concentration thresholds.
4. Add export/report package endpoints for periodic review packets.

Upstream reuse targets:
1. Ghostfolio import/export and activities/account-balance module patterns.
2. Ghostfolio calculator and rules patterns for risk and classification logic.

Definition of done:
1. Import UX produces deterministic reconciliation output for every run.
2. Lot/position changes are explainable through persisted audit artifacts.
3. Portfolio review packet can be generated end-to-end from local data.

### Phase 6.0 - Productization and Trust Layer (2 to 4 weeks)
Goal: make BuildWealth operationally durable as a real software product.

Slices:
1. Implement durable storage strategy upgrade path (with migration and rollback checks).
2. Add backup/restore command + UI entrypoint.
3. Add local data protection options for sensitive stores.
4. Add runtime telemetry dashboards for API latency, context freshness, and cache quality.

Definition of done:
1. Recovery path is tested and documented.
2. Operational failures are visible via built-in telemetry.
3. Security and data-integrity controls are verified in tests and runbook.

## Prioritization Logic
Use this scoring when selecting the next slice:
1. User decision quality impact (highest).
2. Cross-domain leverage (portfolio + planning + research + Copilot together).
3. Reuse ROI from upstream references.
4. Operational risk reduction.
5. Implementation complexity.

## Immediate Next 3 Slices
1. Start Phase 5.0 Slice 4: add household/couple planning mode with shared goals and filing assumptions.
2. Start Phase 5.0 Slice 5: add simulation mode selector (fixed/stochastic/historical/Monte Carlo variants) and comparison outputs.
3. Start Phase 5.1 Slice 1: add import reconciliation report (accepted/rejected/normalized rows and confidence flags).

## Guardrails
1. Do not fork or embed full Ghostfolio/Ignidash apps into BuildWealth runtime path.
2. Reuse upstream logic selectively where it improves correctness and speed.
3. Keep BuildWealth UX/API contracts stable while internals evolve.
4. Ship each slice with tests and operator-facing observability.
5. Keep this document updated at slice completion time.

## Success Metrics
1. Decision utility:
- at least 80% of recommendations include quantified expected impact and evidence links.
- at least 60% of applied recommendations have closure outcome capture.

2. Research utility:
- multi-symbol compare used in at least 50% of research-driven recommendation flows.
- watchlist ranking freshness under 24 hours for tracked symbols.

3. Planning utility:
- scenario engine supports multiple simulation modes with deterministic compare outputs.
- tax/withdrawal realism settings materially alter scenario outputs with transparent deltas.

4. Product reliability:
- full test suite remains green on each slice.
- no silent degraded sidecar failures.
- backup/restore validation passes in CI or scripted local checks.
