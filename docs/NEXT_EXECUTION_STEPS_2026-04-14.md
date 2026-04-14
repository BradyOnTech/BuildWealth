# BuildWealth Next Execution Steps (2026-04-14)

## Purpose
Concrete follow-on work after Phase 1.18 completion, ordered by leverage and dependency.

## Current Snapshot
- Core Phase 1 + Phase 2 foundations are implemented and passing tests.
- Phase 1.18 broker CSV templates are implemented with template selection, auto-detection, and broker-specific parsing coverage.
- Phase 3.1 asset metadata database expansion is complete (seeded catalog + deterministic fallback + schema/UI plumbing + tests).
- Phase 3.3 sidecar boundary hardening is complete.
- Phase 3.4 UI updates are complete (portfolio account filter + allocation charts, guided plan timeline/contribution editors, profile physical assets).
- Phase 3.5 Copilot tool updates are complete.
- Phase 3.6 docs/ops cleanup is complete (standalone-first README/runbook, migration/compatibility docs, compose/make standalone defaults).
- Phase 3.7 unified context productionization is complete.

## Priority Order

### 1) Phase 3.1 Asset Metadata Database
Status: Completed

Scope:
1. Add seeded local metadata catalog for broad coverage (target: ~500+ symbols).
2. Include practical fields for portfolio/planning context: `name`, `asset_class`, `sector`, `region`, `asset_type`, `data_source`.
3. Add deterministic fallback classification for uncategorized symbols.
4. Ensure seeding does not overwrite richer user/imported metadata.
5. Add tests for seed load + fallback behavior.

Why now:
- Improves allocation quality, planning assumptions, and Copilot context in one slice.

### 2) Phase 3.3 Sidecar Boundary Hardening
Status: Completed

Scope:
1. Audit sidecar adapters/routes for strict contract-version checks.
2. Verify health/version probe behavior and degraded counters for all sidecars.
3. Add regression tests for sidecar failure modes and fallback telemetry.
4. Remove/document any remaining legacy full-app bridge assumptions.

Completed:
- Contract-version compatibility tracking in engine status.
- Route-level sidecar guards + guarded local fallback metadata for benchmark/attribution/planning.
- Versioned contract-path enforcement in adapter calls.
- Legacy full-app bridge assumptions removed from active runtime/UI settings paths.
- Regression coverage for contract mismatch, guarded fallback paths, and settings filtering.

Why next:
- Stabilizes the targeted-adapter architecture before further feature depth.

### 3) Phase 3.4 UX Consolidation / Product UX Pass
Status: Completed

Scope:
1. Replace JSON-heavy planner controls with guided forms where possible.
2. Improve dashboard/portfolio/plans flow cohesion and action loops.
3. Surface evidence/freshness/assumption context consistently in high-impact views.

Completed:
- Portfolio account selector/filter wired to holdings + allocation scope.
- Portfolio allocation chart visualizations added for asset class/sector/region.
- Plans guided editors added for timeline events, retirement assumptions, and contribution rules (while preserving advanced JSON mode).
- Profile `physical_assets` section added and wired end-to-end.
- Full orchestrator tests remain green after UI/code-path changes.

Why:
- Moves from “power-user tooling” to polished, durable product workflows.

### 4) Phase 3.5 Copilot Tool Updates
Status: Completed

Scope:
1. Validate all planned tools are present and production-ready: `get_account_balances`, `compute_tax`, `add_timeline_event`, `compare_withdrawal_strategies`, `get_asset_allocation`, `set_contribution_rules`, `get_buildwealth_context`.
2. Close any remaining tool contract gaps and system prompt routing coverage.
3. Add regression tests for high-impact tool paths (especially timeline/contribution editing flows).

Completed:
- Added the missing first-class `add_timeline_event` Copilot tool (append semantics, validation, active-plan fallback, decision logging).
- Updated Copilot prompt tool-selection guide to call `add_timeline_event` for quick life-event timeline updates.
- Added regression coverage for 3.5 tool registration completeness and `add_timeline_event` behavior in `test_copilot_tool_updates.py`.

Why:
- BuildWealth’s differentiation depends on using portfolio + planning + research context in chat reliably.

### 5) Phase 3.6 Documentation + Ops Cleanup
Status: Completed

Scope:
1. Reconcile roadmap docs to current truth (capability audit is stale).
2. Update README and local run/sidecar instructions to current architecture.
3. Document migration and compatibility expectations.

Why:
- Keeps execution aligned and prevents drift in future slices.

### 6) Phase 3.7 Unified Context Packaging
Status: Completed

Scope:
1. Productionize context payload quality controls (freshness/evidence coverage, warning consistency, token-budget behavior).
2. Harden API/tool contracts for context retrieval and force-refresh paths under higher-load chat workflows.
3. Expand focused test coverage for context composition correctness across portfolio/planning/research permutations.
4. Improve operator visibility into context cache behavior and stale-context decision paths.

Completed in Slice 1:
- Added `quality` metadata envelope (freshness, coverage, warning counts, summary budget/truncation).
- Added warning normalization (dedupe + bounded output).
- Hardened `force_refresh` cache behavior to bypass reads but still repopulate cache.
- Added stale snapshot warning emission + UI metadata surfacing.
- Added regression tests for quality metadata and cache policy behavior.

Completed in Slice 2:
- Added explicit `/api/copilot/context` response contract (`CopilotContextResponse`) and runtime payload validation.
- Added context payload permutation tests (plan/no-plan, research on/off) for contract stability.
- Added lightweight cache observability endpoint `GET /api/copilot/context/cache`.
- Added cache-store stats methods + tests (`entries`, `max_entries`, `expired_pruned`).

Completed in Slice 3:
- Updated Copilot prompt/tool guidance to explicitly use `quality` + `warnings` metadata when caveating context-driven answers.
- Added prompt regression test coverage to prevent drift from quality-aware response behavior.

Completed in Slice 4:
- Added `detail_level` (`light`/`full`) to Copilot context options, API context endpoint, and `get_buildwealth_context` tool input contract.
- Unified context payload generation now applies optional light-shaping for high-volume sections while preserving summary/quality metadata.
- Copilot chat context now defaults to `light` detail for routine turns, reducing token load while keeping full detail available on demand.
- Added regression coverage for detail-level normalization, payload shaping, tool schema, and context response permutations.

Completed in Slice 5:
- Expanded cache status observability with rolling counters (`lookup_count`, `hit_count`, `miss_count`, `write_count`, `eviction_count`, `expired_pruned`, `hit_rate_pct`) for research/projection context caches.
- Updated `/api/copilot/context/cache` response contract and tests to assert trend metrics beyond point-in-time entry counts.
- Hardened cache clear semantics to support deterministic metric reset behavior (`clear(reset_metrics=True)`).

Completed in Slice 6:
- Added cache reset controls:
  - `POST /api/copilot/context/cache/reset` endpoint with target selection (`all`, `research`, `baseline_projection`) and optional metric reset.
  - Copilot UI `Reset Cache` action in Unified Context panel for local troubleshooting loops.
- Added regression coverage for reset behavior and invalid target handling.

Remaining:
- None for Phase 3.7. Unified context productionization slices are complete.

Why:
- This is the BuildWealth differentiator and the main remaining leverage point after parity foundations.

## Post-3.7 Recommended Next Workstream
1. Decision intelligence loop:
- Status: Completed (Decision Packet v1)
- Recommendation application now writes a decision packet artifact by default, including unified context snapshot metadata, selected assumptions, and cited research symbols.
- Apply flows now support `create_decision_packet` and `decision_packet_research_symbols` controls.

2. Research-to-planning bridge:
- Add UI/API flow to pin research symbols and thesis notes directly into plan branches/scenario assumptions.
- Goal: reduce friction between market research and planning model inputs.

3. Copilot action closure:
- Expand recommendation application/rejection loops with explicit before/after scenario diffs and captured decision rationale.
- Goal: tighten the feedback loop between conversation, simulation, and committed plan changes.

## Guardrails
1. Keep using Ghostfolio and Ignidash upstream logic/code patterns when beneficial.
2. Avoid over-indexing on one deep feature without finishing adjacent integration value.
3. Prefer shipping vertical slices with tests over isolated internals.

## Definition of Done for This Workstream
1. 3.1 merged with tests and visible metadata-quality improvements.
2. 3.3 merged with fallback/contract regression coverage.
3. 3.4 merged with guided UX + account/allocation visualization updates.
4. Docs reflect shipped reality and current priorities.
5. Full orchestrator test suite remains green.
