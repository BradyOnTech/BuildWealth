# Next Steps Plan

## Goal
Make BuildWealth the primary single-user desktop experience for financial Q&A and agentic research workflows, with Ghostfolio and Ignidash as connected data engines.

## Current Reality (2026-04-08)
- Data and service plumbing exists: Ghostfolio, Ignidash, OpenBB hooks, orchestrator API.
- Ops UI exists for sync and CSV import.
- Copilot runtime, plan workspace, workflow templates, and research tools are now implemented.
- Main gap has shifted to UX consolidation + unified money model + recommendation approval flow.

## Product Direction
1. BuildWealth UI becomes the daily entry point.
2. Ghostfolio remains system-of-record dashboard and ledger.
3. Ignidash remains long-horizon planning engine.
4. Orchestrator provides:
- context assembly
- LLM tool-calling
- workflow execution
- conversation memory

## Prioritized Build Order

### Phase 1: Copilot Core (Now)
1. Add Copilot backend runtime with tool calling.
2. Add conversation memory store (single-user, local filesystem).
3. Add first-class Copilot chat UI panel with history and new-chat.
4. Add core tool adapters:
- latest/live snapshot
- sync status/run sync
- planning scenarios
- options chain research
- account summaries

### Phase 2: Financial Workflow Templates
1. Risk concentration review workflow. ✅ Implemented
2. Contribution optimization workflow (401k/HSA/taxable). ✅ Implemented
3. Weekly financial change summary workflow. ✅ Implemented
4. Structured report outputs with assumptions and caveats. ✅ Implemented

### Phase 3: Deeper Integrations
1. Ignidash scenario diff and direct plan update actions from Copilot. ✅ Implemented in BuildWealth Plan Settings + Scenario Diff (local planner engine parity while Ignidash write APIs are limited)
2. Expand OpenBB research tools beyond options chain. ✅ Added quote + price history endpoints/tools
3. Better transaction/time-window context retrieval for analysis. ✅ Added snapshot history API/tool + UI trend panel

### Phase 4: UX Consolidation
1. BuildWealth home dashboard with embedded Copilot as default focus. ✅ Initial Today Dashboard implemented
2. Deep links into Ghostfolio/Ignidash when needed.
3. Unified context panel (portfolio, tax assumptions, data freshness).

## Next Active Workstream
See [PRODUCT_BACKLOG.md](./PRODUCT_BACKLOG.md) for current epics, acceptance criteria, and step-by-step user workflow.
- Current in-progress implementation: Epic 3 Recommendation Inbox + Approval Flow (inbox API, apply/reject/archive routes, and UI workflows).

## Immediate Implementation Scope in This Iteration
- [x] Write this plan file.
- [x] Implement Copilot runtime service and storage.
- [x] Add Copilot API endpoints.
- [x] Add Copilot UI components in current dashboard.
- [x] Wire frontend to new endpoints.
- [x] Add tests for conversation store and copilot orchestration fallback/tool path.

## Acceptance Criteria for This Iteration
1. From `http://localhost:8090`, user can ask financial questions in a chat panel.
2. Copilot can call internal tools and return grounded answers.
3. Conversations persist across page refresh and app restarts.
4. At least one tool call is visible in response metadata/log.
5. Existing sync/import functionality remains intact.
