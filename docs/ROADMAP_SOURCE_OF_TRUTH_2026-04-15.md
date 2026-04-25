# BuildWealth Product Roadmap (Source of Truth)

## Date
2026-04-15

## Status
Active canonical roadmap for post-Phase-3.7 execution.

This document replaces `docs/NEXT_EXECUTION_STEPS_2026-04-14.md` as the active planning sequence and supersedes roadmap sections in `docs/STANDALONE_BUILD_PLAN.md` that are now stale or already complete.

## Progress Log

### 2026-04-25 (Completed - Recommendation Factory, Portfolio Risk Signals)
1. Added a first Recommendation Factory slice that turns active portfolio risk alerts into concrete recommendation candidates:
- new `recommendation_factory.py` service builds specific, evidence-backed recommendation payloads from portfolio risk alerts.
- generated payloads include `generator`, `evidence`, `suggested_action`, and `expected_outcome` metadata.
- stable `generator.dedupe_key` values prevent repeated active recommendations for the same risk signal.
2. Added API + UI surfaces:
- `POST /api/recommendations/generate/portfolio-risk` supports dry-run preview and apply mode.
- Recommendation Inbox now includes a Recommendation Factory panel with preview/create controls, generation limit, optional plan attachment, candidate rendering, created-row rendering, and skipped-duplicate visibility.
- generated recommendation rows explain their source signal and suggested action details inline.
3. Tests:
- backend factory dry-run/apply/dedupe coverage in `test_recommendation_factory.py`.
- frontend template coverage for the Recommendation Factory panel.
4. Verification:
- full orchestrator suite passes (`523 passed`).

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Neutral Helper Placement Threshold Guardrail)
1. Added a default-workflow helper-placement guardrail test:
- new `tests/test_helper_placement_thresholds.py`.
2. Automated threshold scoring for neutral helper candidates:
- tracks importer-count and line-count thresholds for:
  - `services/portfolio_metrics.py`
  - `services/timeline_defaults.py`
- fails with explicit re-score guidance when thresholds are crossed, including bounded `services/shared/` guidance when multiple helpers cross together.
3. Kept placement criteria ownership explicit:
- measurable criteria (reuse breadth + surface size) are now continuously enforced by tests.
- coupling/volatility/domain-split decisions remain explicit slice-level review when guardrail threshold crossings occur.
4. Verification:
- targeted: `pytest -q tests/test_helper_placement_thresholds.py tests/test_timeline_defaults_mirror.py tests/test_plan_scenario_branching.py` (`10 passed`)
- full: `pytest -q` (`485 passed`)

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Default-Workflow Timeline Drift Harness Enforcement)
1. Made timeline mirror drift checks non-optional in default pytest workflow:
- removed Node-dependent skip path from `tests/test_timeline_defaults_mirror.py`.
- replaced Node runtime import check with deterministic parsing of `web/lib/timeline_defaults.js`.
2. Extended drift harness to force explicit coverage when timeline constants evolve:
- added backend constant coverage assertion over `timeline_defaults.py` so new `TIMELINE_*` constants must be explicitly classified as mirrored or backend-only.
- added frontend export coverage assertion so timeline mirror export changes require explicit test updates.
3. Kept existing schema/runtime and frontend-vs-backend value parity assertions intact.
4. Verification:
- targeted: `pytest -q tests/test_timeline_defaults_mirror.py tests/test_plan_scenario_branching.py` (`8 passed`)
- full: `pytest -q` (`483 passed`)

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Shared Helper Placement Criteria + Applied Decision)
1. Defined objective move criteria for neutral helper modules (`services/` vs `services/shared/`):
- reuse breadth threshold (5+ importers across 3+ domains)
- surface-size threshold (roughly >120 LOC or >3 stable public helpers/contracts)
- coupling threshold (dependency-light, no feature-service imports)
- volatility threshold (keep local while ownership is still actively evolving)
2. Applied criteria to current neutral helper candidates:
- `portfolio_metrics.py`: 79 LOC, 3 service importers in a narrow concentration domain.
  - decision: keep in `services/` for now.
- `timeline_defaults.py`: 17 LOC, cross-layer constants with 4 backend importers plus mirror/drift tests.
  - decision: keep in `services/` for now.
3. Recorded decision + criteria in codebase-quality follow-up doc as the canonical placement rubric.
4. Verification:
- full: `pytest -q` (`482 passed`)

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Timeline Defaults Mirror Audit + Drift Harness)
1. Consolidated backend timeline default vocab into canonical `timeline_defaults.py`:
- added ordered value tuples plus set views for event types, impact types, and frequencies.
- migrated schema/runtime validators to shared defaults in `schemas.py`, `plan_workspace.py`, and `main.py`.
2. Standardized branch/timeline default behavior on shared defaults:
- branch event normalization now defaults missing `impact_type` via event-map defaults.
- branch event normalization now defaults missing `recurring_frequency` to `one_time`.
3. Isolated frontend timeline defaults into dedicated mirror module:
- added `web/lib/timeline_defaults.js`.
- updated `web/views/plan-editor.js` to consume timeline defaults from the shared frontend module.
4. Added drift-test harness for runtime/schema/frontend mirror alignment:
- new `tests/test_timeline_defaults_mirror.py` compares:
  - runtime defaults vs schema literal contracts.
  - runtime defaults vs frontend mirror constants (via Node ESM import).
- expanded branch normalization coverage in `tests/test_plan_scenario_branching.py` for default-field application.
5. Verification:
- style: `ruff check` on touched python modules/tests (`All checks passed`).
- targeted: `pytest -q tests/test_portfolio_metrics.py tests/test_coordinator.py tests/test_workflow_runner.py tests/test_today_dashboard.py tests/test_timeline_defaults_mirror.py tests/test_plan_scenario_branching.py tests/test_plan_workspace.py tests/test_copilot_tool_updates.py tests/test_timeline_projection.py` (`69 passed`).
- full: `pytest -q` (`482 passed`).

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Typed Portfolio Metrics Contract)
1. Replaced untyped concentration return payloads with explicit shared typed contracts in `portfolio_metrics.py`:
- added `ConcentrationPosition` and `ConcentrationMetrics` `TypedDict` contracts.
- updated `concentration_metrics(...)` to return `ConcentrationMetrics` directly.
2. Removed duplicated concentration type definitions/casts from downstream services:
- `coordinator.py` now consumes typed concentration results directly.
- `workflow_runner.py` now consumes typed concentration results directly.
- `today_dashboard.py` now reads typed concentration fields directly.
3. Added focused concentration-metrics regression tests:
- new `tests/test_portfolio_metrics.py` covering empty payloads, numeric coercion/order, and top-10 truncation behavior.
4. Verification:
- style: `ruff check .../portfolio_metrics.py .../coordinator.py .../workflow_runner.py .../today_dashboard.py tests/test_portfolio_metrics.py`
- targeted: `pytest -q tests/test_portfolio_metrics.py tests/test_coordinator.py tests/test_workflow_runner.py tests/test_today_dashboard.py` (`13 passed`)
- full: `pytest -q` (`479 passed`)

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Schema Base Clarity)
1. Added clearly marked internal shared-base sections in `schemas.py`:
- `_EngineContractResponseBase` (engine response envelope)
- `_PlanSettingsBase` (plan settings payload)
- `_PlanScenarioComparisonRequestBase` (scenario comparison request payload)
2. Documented inheritance ownership directly on each internal base model:
- `_EngineContractResponseBase` -> `PortfolioBenchmarkResponse`, `PortfolioAttributionResponse`
- `_PlanSettingsBase` -> `PlanSettings`, `PlanSettingsUpdateRequest`
- `_PlanScenarioComparisonRequestBase` -> `PlanScenarioDiffRequest`, `PlanWithdrawalStrategyCompareRequest`, `PlanScenarioBranchRequest`
3. Added explicit one-layer inheritance guardrail comments to keep base depth flat.
4. Verification:
- style: `ruff check src/buildwealth_orchestrator/schemas.py`
- full: `pytest -q` (`476 passed`)

### 2026-04-20 (Completed - Cross-Cutting Follow-up, Slice D Planning Sidecar Decomposition)
1. Decomposed planning sidecar orchestration into focused internal helper boundaries in `planning_sidecar.py`:
- added `_ScenarioRunInputs` dataclass to centralize run-time input state.
- split local execution, local-envelope updates, sidecar request execution, sidecar merge envelope assembly, and degraded fallback assembly into dedicated helper methods.
2. Kept public API/contracts unchanged:
- `IgnidashScenarioService.run(...)` signature and response contract remain stable.
- sidecar request/response schema models and metadata semantics remain unchanged.
3. Added focused regression coverage for local-path projection payload preservation:
- expanded `tests/test_planning_sidecar.py` with local-path projection payload assertions.
4. Verification:
- targeted: `pytest -q tests/test_planning_sidecar.py` (`8 passed`).
- full: `pytest -q` (`476 passed`).

### 2026-04-15 (Completed - Cross-Cutting Follow-up, Slice B Frontend Field Schema Isolation)
1. Isolated plan-setting schema metadata from runtime state:
- added `web/lib/plan_setting_fields.js` as canonical plan-setting field/option registry.
- removed plan-setting field/option constants from `web/lib/state.js` so it remains runtime mutable state only.
2. Rewired plan/profile view imports to dedicated schema module:
- updated `views/plan-editor.js`, `views/plans.js`, and `views/profile.js` to import plan-setting and filing-status metadata from `plan_setting_fields.js`.
3. Added explicit plan-setting helpers in `components.js`:
- added `planSettingsGridHtml`, `collectPlanSettingsPayload`, and `setPlanSettingsInputs` wrappers to keep generic component utilities while making plan-setting metadata usage explicit.
4. Added focused frontend round-trip smoke coverage:
- new frontend smoke test: `web/tests/plan_setting_fields_roundtrip.test.mjs`.
- new pytest wrapper: `tests/test_web_plan_setting_fields_smoke.py` to execute the node smoke test in CI/test workflow.
5. Verification:
- targeted: `pytest -q tests/test_web_plan_setting_fields_smoke.py` (`1 passed`).
- full: `pytest -q` (`475 passed`).

### 2026-04-15 (Completed - Cross-Cutting Follow-up, Slice A Shared Helper Cohesion)
1. Split mixed helper responsibilities into focused modules:
- added `services/value_coercion.py` for shared coercion/parsing/time helpers.
- added `services/recurring_projection.py` for recurring schedule projection logic.
- removed `services/service_utils.py` to eliminate mixed coercion/projection ownership in one module.
2. Updated service imports to explicit helper ownership:
- coercion/parsing imports now point to `value_coercion.py` in:
  - `buildwealth_context.py`
  - `debt_projection.py`
  - `portfolio_review_packets.py`
  - `portfolio_risk_alerts.py`
  - `rmd_projection.py`
  - `scenario_engine.py`
  - `tax_engine.py`
- recurring projection imports now point to `recurring_projection.py` in:
  - `income_projection.py`
  - `expense_projection.py`
3. Verification:
- targeted: `pytest -q tests/test_buildwealth_context.py tests/test_income_projection.py tests/test_expense_projection.py tests/test_debt_projection.py tests/test_rmd_projection.py tests/test_tax_engine.py tests/test_scenario_engine.py tests/test_portfolio_review_packets.py tests/test_portfolio_risk_alerts.py tests/test_plan_scenario_branching.py` (`63 passed`).
- full: `pytest -q` (`474 passed`).

### 2026-04-15 (Completed - Cross-Cutting Follow-up, Backup/Restore + Protection-Policy Scripted Reliability Smoke Validation)
1. Added scripted storage reliability smoke runner:
- new script: `scripts/reliability-smoke-storage.sh`
- new operator command: `make reliability-smoke-storage`
2. Added integrated storage smoke test coverage:
- new `tests/test_storage_reliability_smoke.py` validates, in one temp-dir scenario:
  - backup archive creation/listing
  - restore correctness with pre-restore safety backup
  - protection-policy update/apply in hardened mode with backup-archive inclusion
3. Added runbook and command-surface updates:
- updated README and standalone operations docs with `reliability-smoke-storage` command and smoke-check scope.
4. Verification:
- targeted: `pytest -q tests/test_storage_reliability_smoke.py tests/test_backup_restore.py tests/test_data_protection.py` (`5 passed`).
- full: `pytest -q` (`474 passed`).

### 2026-04-15 (Completed - Cross-Cutting Follow-up, Engine Policy/Envelope Unification + Sidecar Matrix Tests)
1. Added shared sidecar policy and degraded-envelope helper module (`engine_policy.py`) to centralize:
- sidecar call disposition decisions (guarded/disabled/adapter-missing/use-sidecar).
- canonical engine status/fallback constants and warning normalization behavior.
2. Unified benchmark/attribution/planning sidecar services on shared policy:
- `portfolio_benchmark.py`, `portfolio_attribution.py`, and `planning_sidecar.py` now resolve sidecar eligibility through one policy entrypoint.
- degraded response updates and sidecar-unavailable warning formatting are now shared helpers instead of ad hoc per-service logic.
3. Expanded sidecar execution-state matrix coverage:
- added `test_engine_policy.py` for direct policy/envelope behavior.
- added adapter-missing path coverage in:
  - `test_portfolio_benchmark.py`
  - `test_portfolio_attribution.py`
  - `test_planning_sidecar.py`
4. Verification:
- targeted: `pytest -q tests/test_engine_policy.py tests/test_portfolio_benchmark.py tests/test_portfolio_attribution.py tests/test_planning_sidecar.py` (`22 passed`).
- full: `pytest -q` (`473 passed`).

### 2026-04-15 (Completed - Phase 6.0 Slice 4, Runtime Telemetry Dashboards)
1. Added runtime telemetry service and request-latency instrumentation:
- new `runtime_telemetry.py` tracker records API latency distributions (`avg/p50/p95/p99/max`), server-error rates, and per-route rollups.
- orchestrator now uses HTTP middleware to capture latency for API routes at runtime.
2. Added runtime telemetry API surface:
- `GET /api/telemetry/runtime` returns:
  - API latency summary + slowest-route rollups.
  - context freshness summary (latest context snapshot age/stale state, coverage, warning count).
  - cache quality rollups for research/projection caches (hit rates, utilization, evictions, quality status).
3. Added Today Dashboard runtime telemetry panel:
- new `Runtime Telemetry` section shows p95 latency, API error rate, context freshness status, cache hit rate, per-store cache diagnostics, and per-route latency rows.
4. Added operator/documentation surfaces:
- Make target: `make telemetry-runtime`.
- updated standalone operations/migration runbooks and README endpoint list.
5. Verification:
- targeted: `pytest -q tests/test_runtime_telemetry.py tests/test_runtime_telemetry_endpoint.py tests/test_copilot_context_payload.py` (`19 passed`).
- full: `pytest -q` (`465 passed`).

### 2026-04-15 (Completed - Phase 6.0 Slice 3, Local Data Protection Options)
1. Added policy-driven local data-protection service (`data_protection.py`) for sensitive local stores:
- supports protection levels: `standard` and `hardened`.
- supports optional backup-archive inclusion and auto-apply-on-startup policy behavior.
- scans target paths and reports non-compliant files/directories against active policy.
2. Added data-protection API surfaces:
- `GET /api/storage/protection/status`
- `PUT /api/storage/protection/policy`
- `POST /api/storage/protection/apply`
3. Added Settings UI entrypoint:
- Settings now includes a `Data Protection` section with policy controls (level/include-backups/auto-apply), compliance summary, and one-click apply action.
4. Added operator command surfaces:
- Make targets:
  - `make protection-status`
  - `make protection-apply LEVEL=hardened INCLUDE_BACKUPS=true`
5. Added settings/env surface:
- new setting/env: `PROTECTION_POLICY_PATH` (default `data/security/protection_policy.json`).
6. Verification:
- targeted: `pytest -q tests/test_data_protection.py tests/test_backup_restore.py tests/test_durable_storage.py` (`6 passed`).
- full: `pytest -q` (`459 passed`).

### 2026-04-15 (Completed - Phase 6.0 Slice 2, Backup/Restore Command + UI Entrypoint)
1. Added first-class backup/restore service (`backup_restore.py`) for local data stores:
- creates timestamped tar archives under `BACKUP_ARCHIVE_DIR` with per-file + aggregate checksum manifest verification.
- restore flow validates archive integrity before replacing live data.
- restore can create a pre-restore safety backup by default.
2. Added backup API surfaces:
- `GET /api/storage/backups`
- `POST /api/storage/backups`
- `POST /api/storage/backups/restore`
3. Added operator command surfaces:
- Make targets:
  - `make backup`
  - `make backup-list`
  - `make backup-restore BACKUP_ID=...`
4. Added Settings UI entrypoint:
- Settings view now supports backup list refresh, one-click backup creation, and restore of selected backup with explicit confirmation and pre-restore safety toggle.
5. Added settings/env surface:
- new setting/env: `BACKUP_ARCHIVE_DIR` (default `data/backups`).
6. Verification:
- targeted: `pytest -q tests/test_backup_restore.py tests/test_durable_storage.py` (`4 passed`).
- full: `pytest -q` (`455 passed`).

### 2026-04-15 (Completed - Phase 6.0 Slice 1, Durable Storage Upgrade Path)
1. Added first-class durable storage migration service (`durable_storage.py`) to stage file-backed stores into a SQLite snapshot with verification:
- migrates portfolio, snapshots, conversations, plans, profile, and recommendation stores from `data/` into `buildwealth_durable.db`.
- verifies migrated checksum parity between source documents and SQLite rows before activation.
2. Added rollback-path safety checks:
- migration run now writes timestamped backup + report artifacts under `DURABLE_STORAGE_DIR/migrations/...`.
- rollback simulation checks run during migration (default enabled) to validate restorable backups.
- rollback endpoint can restore latest migration backup and restore/remove the durable database based on pre-migration state.
3. Added API and configuration surfaces:
- new endpoints:
  - `GET /api/storage/durable/status`
  - `POST /api/storage/durable/migrate`
  - `POST /api/storage/durable/rollback`
- new setting/env: `DURABLE_STORAGE_DIR` (default `data/storage`).
4. Documentation updates:
- updated standalone operations and migration compatibility runbooks with durable migration/rollback workflow.
- normalized roadmap filename/date references to `docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md`.
5. Verification:
- targeted: `pytest -q tests/test_durable_storage.py` (`2 passed`).
- full: `pytest -q` (`455 passed`).

### 2026-04-15 (Completed - Phase 5.1 Slice 4, Portfolio Review Packet Export Endpoints)
1. Added first-class periodic review packet export endpoints:
- `POST /api/portfolio/review-packets` to generate a packet from local portfolio/planning/recommendation data.
- `GET /api/portfolio/review-packets` to list generated packet exports.
- `GET /api/portfolio/review-packets/{packet_id}` to read a specific packet payload + markdown report.
2. Added deterministic review packet service/store:
- new `portfolio_review_packets.py` builds structured packet payloads and markdown reports with period windows, holdings/performance/risk summaries, transaction/audit trends, snapshot deltas, watchlist state, and recommendation status rollups.
- new file-backed store persists JSON/Markdown packet pairs and provides list/read APIs.
3. Added optional plan-artifact bridge:
- review packet generation can optionally persist markdown into Plan Workspace artifacts (`kind=portfolio_review_packet`) when `plan_id` is provided.
4. Added contract and settings surfaces:
- new schemas for request/list/detail responses (`PortfolioReviewPacket*`).
- new settings path `PORTFOLIO_REVIEW_PACKET_DIR` (default `data/reports/portfolio_review_packets`).
5. Source-provenance note:
- packet packaging structure follows Ghostfolio export/activity/account-balance service patterns (`apps/api/src/app/export/export.service.ts`, `apps/api/src/app/activities/activities.service.ts`, `apps/api/src/app/account-balance/account-balance.service.ts`) while preserving BuildWealth standalone contracts.
6. Verification:
- targeted: `pytest -q tests/test_portfolio_review_packets.py` (`3 passed`).
- full: `pytest -q` (`444 passed`).

### 2026-04-15 (Completed - Phase 5.1 Slice 3, Portfolio Drift/Risk Alerts)
1. Added a dedicated portfolio risk-alert sidecar service (`portfolio_risk_alerts.py`) with Ghostfolio-style threshold semantics:
- concentration thresholds (`single_holding`, `top3`, `HHI`, `effective_positions`)
- allocation/cluster thresholds (`account`, `asset_class`, `sector`, `region`)
- deterministic alert states (`breach`/`watch`), severity, drift-from-threshold, and remediation guidance.
2. Added persistent risk-threshold policy storage and migration:
- new local `risk_policy.json` payload with normalized bounds and schema versioning.
- added `PortfolioStore` methods to read/update thresholds and trigger deterministic holdings rebuild.
3. Extended portfolio holdings contract:
- bumped holdings schema version to `8`.
- holdings payload now includes first-class `risk_policy` and computed `risk_alerts` blocks.
- fixed allocation-risk normalization to use invested-holdings weights (avoids denominator distortion when cash balances are negative).
4. Added API + UI surfaces:
- new endpoints: `GET /api/portfolio/risk-policy`, `PUT /api/portfolio/risk-policy`.
- Portfolio view now includes threshold controls and a risk-alert table with severity/state badges and drift visibility.
5. Source-provenance note:
- threshold-band and cluster-risk patterns adapted from Ghostfolio rule modules (`account-cluster-risk/current-investment.ts`, `asset-class-cluster-risk/equity.ts`, `regional-market-cluster-risk/north-america.ts`) while preserving BuildWealth standalone contracts.
6. Verification:
- targeted: `pytest -q tests/test_portfolio_risk_alerts.py tests/test_portfolio_store.py` (`58 passed`).
- full: `pytest -q` (`441 passed`).

### 2026-04-15 (Completed - Phase 5.1 Slice 2, Corporate Actions + Lot Audit Explainability)
1. Expanded local portfolio holdings contract with persisted audit payloads:
- added first-class `lot_audit` and `corporate_actions` payload blocks to holdings responses.
- bumped holdings schema version to `7` with migration defaults for legacy payloads.
2. Added deterministic replay-time event artifacts in `portfolio_store.py`:
- BUY/SELL/STOCK_SPLIT/MERGER now emit lot-audit events with quantity before/after, lot method, and cash delta.
- SELL/MERGER now include consumed-lot breakdowns (lot id, acquired date, consumed quantity, cost, and remaining balances).
- STOCK_SPLIT/MERGER now emit corporate-action events and per-symbol action summaries.
3. Added corporate-action note parsing for explainability metadata:
- merger notes can now carry optional `target_symbol` / `exchange_ratio` hints that are persisted in action artifacts for operator review.
4. Expanded Portfolio UI visibility:
- added `Corporate Actions` section with impact summaries for split/merger events.
- added `Lot Audit Trail` section with account-filter-aware event rendering and lot-consumption details.
5. Source-provenance note:
- event-oriented activity/cashflow packaging follows Ghostfolio activity and account-balance service patterns (`apps/api/src/app/activities/activities.service.ts`, `apps/api/src/app/account-balance/account-balance.service.ts`) while preserving BuildWealth standalone contracts.
6. Verification:
- targeted: `pytest -q tests/test_portfolio_store.py tests/test_portfolio_performance.py` (`58 passed`).
- full: `pytest -q` (`436 passed`).

### 2026-04-15 (Completed - Phase 5.1 Slice 1, Import Reconciliation Report)
1. Added deterministic reconciliation output to CSV import responses:
- row-level status (`accepted`, `rejected`)
- normalized-row subset and normalized-field flags
- row confidence (`high`/`medium`/`low`) with score and reasons
- stable transaction fingerprints for auditability.
2. Added duplicate-aware reconciliation before import write:
- parsed activities now reconcile against existing ledger transaction fingerprints
- duplicates are rejected into reconciliation output and excluded from insert.
3. Expanded import contract and UX:
- `CsvImportResponse` now returns `reconciliation_report` with parser confidence rollups and accepted/normalized/rejected row collections.
- Sync & Import view now renders latest reconciliation summary and row-detail panels directly after inbox/upload runs.
4. Source-provenance note:
- implementation follows Ghostfolio import-service duplicate/error handling patterns (`apps/api/src/app/import/import.service.ts`) while keeping BuildWealth standalone local-store authority and contract-first API shape.
5. Added regression coverage:
- reconciliation confidence/report semantics and duplicate rejection behavior in `test_csv_importer.py`.
6. Verification:
- targeted: `pytest -q tests/test_csv_importer.py` (`19 passed`).
- full: `pytest -q` (`434 passed`).

### 2026-04-15 (Completed - Phase 5.0 Closeout/Hardening)
1. Hardened simulation-mode persistence behavior in Plan Workspace settings:
- mode-specific cleanup now removes incompatible fields during updates (`variant`, `historical_start_year`, `seed`) so stale controls do not leak across simulation-mode switches.
2. Hardened simulation compare semantics for decision workflows:
- diff/branch `simulation_delta` now canonicalizes by active simulation mode, preventing false change flags from irrelevant controls (for example fixed-mode variant/seed edits).
3. Hardened Plan Workspace UI simulation controls:
- settings and diff editors now apply mode-aware guardrails for simulation fields.
- incompatible controls are disabled and cleared on mode change to reduce stale overrides and operator error.
4. Added focused regression coverage:
- `test_simulation_delta.py` for canonical simulation-delta behavior.
- `test_plan_workspace.py` mode-switch cleanup assertions.
- `test_withdrawal_strategy_compare.py` simulation metadata assertions on compare rows.
5. Source-provenance note:
- hardening preserves the Ignidash-style simulation-mode semantics already adopted in Phase 5.0 Slice 5 while keeping BuildWealth contract/UI behavior first-class.
6. Verification:
- targeted suite: `pytest -q tests/test_plan_workspace.py tests/test_simulation_delta.py tests/test_withdrawal_strategy_compare.py` (`21 passed`).
- full suite: `pytest -q` (`432 passed`).

### 2026-04-15 (Completed - Phase 5.0 Slice 5, Simulation Mode Expansion)
1. Added full simulation mode controls across planning contracts and persistence:
- new settings/request fields: `simulation_mode`, `simulation_monte_carlo_variant`, `simulation_historical_start_year`, `simulation_seed`.
- assumption sets now support simulation controls and apply them into merged plan settings.
- plan workspace defaults/context now include simulation settings with validation/sanitization.
2. Completed mode-aware scenario execution wiring:
- planning engine now executes fixed, stochastic, historical-backtest, and Monte Carlo-variant paths with deterministic seed support and NYU historical return data.
- scenario, plan-scenarios, plan-diff, plan-branch, strategy-compare, and Copilot planning tool paths now thread simulation controls end-to-end.
3. Added compare/output surfaces:
- diff and branch responses now include `simulation_delta` payloads alongside scenario/Monte-Carlo deltas.
- withdrawal strategy compare rows now include simulation mode/variant context.
- plan editor now includes simulation selectors in settings + diff, numeric controls for historical start year/seed, and simulation sections in diff/branch/compare output text.
4. Sidecar/adapter parity updates:
- planning sidecar request metadata now includes simulation fields.
- sidecar-merged planning responses preserve local simulation summaries for consistent downstream compare/reporting behavior.
5. Source-provenance note:
- implementation follows Ignidash simulation/returns-provider patterns and historical return dataset structure (`simulation-engine.ts`, `returns-providers/*`, `historical-data/nyu-returns.ts`).
6. Verification:
- targeted suite: `pytest -q tests/test_scenario_engine.py tests/test_plan_assumption_sets.py tests/test_plan_workspace.py tests/test_planning_sidecar.py tests/test_copilot_tool_updates.py` (`70 passed`).
- full suite: `pytest -q` (`427 passed`).

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
1. If helper-placement threshold guardrail signals a crossing, complete the explicit re-score decision in the same slice and update placement docs.
2. If multiple neutral helpers cross thresholds together, do one bounded `services/shared/` introduction with domain splits.
3. Extend timeline-default drift harness to cover any future additional mirror files (beyond `web/lib/timeline_defaults.js`) if timeline vocab is reused in new frontend modules.

## Cross-Cutting Engineering Follow-Up
1. Post-refactor helper indirection and intentional sidecar complexity are documented in [`docs/CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md`](./CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md).
2. Execute those cleanup slices when they reduce operational risk or readability without displacing higher-value product slices.

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
