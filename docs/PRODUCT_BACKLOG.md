# BuildWealth Product Backlog

## Product Goal
Single-user financial command center that combines:
- full money context (income + investments + plan assumptions),
- conversational Copilot with grounded tool use,
- decision workflows that can be reviewed and applied over time.

## Target User Workflow (Step-by-Step)
1. Open BuildWealth and land on Today Dashboard.
2. Confirm snapshot freshness, checklist status, and top recommendations.
3. Run sync if data is stale or missing.
4. Review concentration/trend changes and active plan health.
5. Ask Copilot a focused daily question using active plan context.
6. Run one workflow template (risk review, contribution optimization, or weekly summary).
7. Apply or reject proposed plan changes.
8. Log at least one decision in Plan Workspace.
9. Revisit weekly for trend and plan-vs-actual updates.

## Epic 1: Today Dashboard (Primary Entry UX)
Status: In progress

Outcomes:
- Daily "what changed / what matters / what should I do now" view.
- Checklist and recommendations generated from real data.

Acceptance criteria:
- `/api/dashboard/today` returns snapshot freshness, concentration, active plan summary, checklist, recommendations, and workflow steps.
- UI has a top-level dashboard section with quick actions.
- Refresh updates dashboard without page reload.

## Epic 2: Unified Financial Model
Status: In progress (initial profile APIs + onboarding UI scaffold implemented)

Outcomes:
- First-class context for income, recurring expenses, debt, and goal targets.

Acceptance criteria:
- Add canonical domain models for cashflow/debt/goals.
- Add import or form-based editing UX in app (not CLI).
- Copilot context includes these fields and cites them in responses.

## Epic 3: Recommendation Inbox + Approval Flow
Status: In progress (core inbox API + UI actions implemented)

Outcomes:
- Agent suggestions become explicit actions (`apply`, `edit`, `reject`) instead of ad hoc text output.

Acceptance criteria:
- Recommendation records stored with status and timestamps.
- UI inbox supports filtering by status/priority.
- Apply path writes plan settings and decision log atomically.

## Epic 4: Trust and Evidence UX
Status: Planned

Outcomes:
- Better confidence and explainability for agent outputs.

Acceptance criteria:
- Each recommendation shows source tools, data timestamp, and key assumptions.
- UI displays freshness and caveat banners when context is stale/incomplete.
- Copilot answers include evidence metadata for audit.

## Epic 5: Plan Versioning
Status: Planned

Outcomes:
- Safe iteration on plan changes over time.

Acceptance criteria:
- Plan versions support draft/active states.
- Compare versions by settings + scenario deltas.
- Rollback action restores prior approved version.

## Implementation Sequence
1. Finish Today Dashboard UX polish and quick-action flows.
2. Build Unified Financial Model and onboarding wizard.
3. Implement Recommendation Inbox and apply/reject actions.
4. Add evidence panel and stale-context warning system.
5. Add plan version history, compare, and rollback.

## Completed Post-Epic Work (2026-04-08)
- **Frontend modernization**: Monolithic app.js (2232 lines) broken into ES modules with hash-based routing and sidebar navigation.
- **Plan-vs-Actual tracking**: Service, API (`GET /api/plans/{plan_id}/tracking`), Copilot tool, and frontend view for comparing plan assumptions against actual portfolio performance.
- **Financial Health Summary**: Service, API (`GET /api/financial-health`), Copilot tool computing net worth, monthly cash flow, savings rate, debt-to-income ratio, emergency fund coverage, and overall health assessment. Integrated into Today Dashboard as top-level KPIs.
- **Enhanced Copilot system prompt**: Replaced generic 2-sentence prompt with detailed tool selection guide and response guidelines.

## Feature Gap Analysis
See [FEATURE_GAPS.md](./FEATURE_GAPS.md) for detailed user walkthrough analysis and prioritized feature proposals.
