# BuildWealth Future State Product Plan

## Date
2026-04-26

## Status
Active canonical product plan for future-state strategy and high-level implementation sequencing.

This document supersedes the execution-priority role previously held by:
- `docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md`
- `docs/PRODUCT_BACKLOG.md`
- `docs/STANDALONE_BUILD_PLAN.md`
- `docs/NEXT_EXECUTION_STEPS_2026-04-14.md`
- `docs/NEXT_STEPS_PLAN.md`

Those documents remain useful as historical progress logs, implementation records, and domain-specific references. They should not be used as the primary source for deciding what to build next unless this plan explicitly points to them.

Domain expansion plans:
- [Investment Fit and Market Research Plan (2026-04-26)](./INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md)

## Product Thesis

BuildWealth is a local-first financial decision operating system for a single user.

It is not just a portfolio tracker, planning calculator, research tool, or chatbot. Its purpose is to help the user understand their financial reality, evaluate possible futures, choose the highest-value next actions, and learn from the outcomes of those actions.

The product should help answer four daily questions:

1. Where am I financially?
2. What changed?
3. What should I do next?
4. What happened after I acted?

The durable product loop is:

1. Collect and normalize user financial reality.
2. Measure completeness, freshness, quality, and risk.
3. Generate evidence-backed recommendations.
4. Let the user inspect, simulate, apply, reject, or defer.
5. Capture outcomes.
6. Improve future prioritization and guidance.

## Non-Negotiable Product Principles

1. Local-first and private by default.
2. The Python orchestrator remains the system of record for persistent state, migrations, API contracts, and product behavior.
3. Optional sidecars are stateless compute specialists, not product surfaces or durable data owners.
4. BuildWealth UI and API are the single user entrypoint.
5. Copilot operates through the same contracts as the rest of the app.
6. Copilot may draft important financial changes, but the user reviews and applies them.
7. Recommendations must be inspectable, evidence-backed, deduplicated, and outcome-trackable.
8. Degraded compute, stale data, and missing profile context must be visible when they affect decisions.
9. The v2 UI should become the primary product experience; classic views are transitional or advanced fallback.
10. Each shipped slice should connect backend behavior, API contract, UI, and tests where user value crosses those boundaries.

## Future State Experience

### Today

Today is the daily command center. It should answer:

- Am I okay?
- What changed?
- What needs review?
- What data is missing or stale?
- What is my top action?
- What did Copilot or the system prepare for me?

Today should eventually include:

- financial health snapshot
- profile readiness
- active plan status
- cash runway and emergency fund status
- portfolio risk summary
- recommendation priority stack
- recent changes
- stale-data and degraded-mode warnings
- pending Copilot drafts
- direct links into review flows

### Profile

Profile is the living model of the user's financial reality.

It should contain:

- household structure
- income
- expenses
- debt
- tax basics
- goals
- physical assets
- preferences
- constraints
- field-level freshness and provenance
- completion/readiness status

Profile data should not behave like a one-time onboarding form. It should be continuously reviewed, refined, and used to improve recommendation quality.

### Portfolio

Portfolio explains current capital, exposure, risk, and trade implications.

It should include:

- holdings
- accounts
- cash
- transactions
- lots and cost basis
- asset allocation
- concentration
- benchmark and attribution
- watchlist
- custom assets
- trade simulation
- portfolio-aware research links

The portfolio experience should move from "what do I own?" to "what does my current capital imply?"

### Plan

Plan is the user's living financial thesis.

It should include:

- active plan summary
- goals
- assumptions
- contribution rules
- timeline events
- scenario comparisons
- life-event branches
- withdrawal strategy comparisons
- research artifacts
- plan decisions
- recommendation closure effects
- stale assumption warnings

The Plan workspace should make tradeoffs legible. It should show what assumptions drive the future state and where the user has made decisions.

### Inbox

Inbox is the ranked financial action queue.

Each recommendation should answer:

- What triggered this?
- What data was used?
- How fresh is the data?
- What is the expected impact?
- What is the confidence?
- What is the downside?
- Is it reversible?
- Can it be simulated?
- Can it be applied?
- How will we know whether it worked?

The Inbox should become less like a generic task list and more like a decision review system.

### Copilot

Copilot is the natural-language operator over the BuildWealth system.

It should:

- retrieve grounded portfolio, profile, plan, recommendation, and research context
- explain what data it used
- expose missing or stale context
- ask targeted follow-up questions
- draft profile updates
- draft plan updates
- draft recommendations
- simulate changes before application
- route important changes into review flows
- preserve tool traces and decision context

Copilot should not become a parallel source of truth. It should make the product easier to operate while preserving explicit review boundaries.

### Atelier and Admin

Atelier remains the lower-frequency operations area.

It should contain:

- imports
- sync
- settings
- storage and backup
- protection policy
- git checkpoints
- research utilities
- workflow templates
- advanced maintenance tools

Over time, high-frequency user workflows should move out of Atelier/classic views and into v2 product surfaces.

## Core Product Domains

### 1. Profile Readiness

Purpose: ensure the app knows enough about the user to make high-quality recommendations.

Future state:

- every important profile field has status: missing, user-confirmed, imported, inferred, stale, or system-generated
- profile readiness is visible in Today and Copilot
- missing profile data can generate ranked recommendations
- Copilot can fill profile sections through chat or guided quiz
- material profile changes use draft/review/apply

High-level implementation:

- extend onboarding/profile status into a richer readiness model
- define profile sections and field-level metadata
- add Copilot prompts for one profile section at a time
- preserve profile draft traces in Copilot responses
- merge approved drafts through existing profile update contracts
- surface readiness in Today and Recommendation Factory inputs
- add browser tests for draft, review, apply, and readiness refresh

### 2. Decision-Grade Recommendations

Purpose: move from passive analytics to evidence-backed next actions.

Future state:

- recommendations are generated from portfolio, plan, cash, profile, research, and data-quality signals
- each recommendation includes evidence, expected impact, confidence, reversibility, time horizon, and freshness
- pre-apply preview is available when a recommendation can mutate state
- outcomes are captured after action
- closure analytics improve future ranking

High-level implementation:

- define a common recommendation quality contract for generated payloads
- normalize generator metadata across existing factories
- add new generators for profile completeness, stale assumptions, debt/cash-flow stress, goal funding gaps, and research/watchlist signals
- make simulation the default path before apply where supported
- improve v2 Inbox review/apply/outcome surfaces
- feed closure analytics into score/ranking inputs
- add workflow tests for preview, apply, reject, archive, and outcome capture

### 3. Today Command Center

Purpose: make the app immediately useful every time it opens.

Future state:

- Today provides a concise financial health and action summary
- top recommendations are explained with evidence and urgency
- profile readiness, stale data, and degraded compute are visible
- pending Copilot drafts and reviewable batches are discoverable

High-level implementation:

- extend the Today dashboard contract with profile readiness, freshness, top-action explanation, and pending-review counts
- reuse existing recommendation ranking rather than inventing a second priority model
- add cards for readiness, cash runway, plan drift, portfolio risk, and recent changes
- link each card to the correct v2 review flow
- add browser tests for an end-to-end daily review path

### 4. Living Plan Workspace

Purpose: turn planning into a navigable financial thesis.

Future state:

- v2 Plan owns the main plan experience
- classic plan links are reduced to advanced fallback only
- plan settings, timeline events, contribution rules, scenario diffs, branches, decisions, and artifacts are visible in the v2 vocabulary
- plan decisions and recommendation outcomes are connected

High-level implementation:

- inventory classic plan surfaces by frequency and importance
- migrate high-frequency surfaces into focused v2 modules
- keep advanced or rarely used tools in Atelier until they justify migration
- preserve existing API contracts where possible
- add v2 workflow tests for editing settings, reviewing timeline events, running scenario diffs, and appending decisions

### 5. Portfolio-Aware Research

Purpose: make research relevant to the user's actual finances.

Future state:

- BuildWealth answers "does this investment fit me?" rather than "is this stock good?"
- research compares symbols in context
- watchlist ranking reflects portfolio, plan, and user goals
- dossiers include provenance and freshness
- research can become plan artifacts or recommendations
- trade simulation shows how a researched asset affects allocation and concentration

High-level implementation:

- use OpenBB as a market/research data access layer behind BuildWealth-owned contracts, not as the recommendation engine
- strengthen multi-symbol comparison and dossier retrieval flows
- add portfolio-impact hooks to research outputs
- route selected research results into plan artifacts
- allow research findings to generate recommendations through the factory contract
- expose provenance and freshness in Today and Copilot context (started: Today research readiness now uses cached evidence packets for top/watchlist symbols with an explicit refresh action)
- test research-to-plan and research-to-recommendation flows

Detailed domain plan:
- [Investment Fit and Market Research Plan (2026-04-26)](./INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md)

### 6. Copilot As Guided Operator

Purpose: make BuildWealth easier to operate without weakening trust boundaries.

Future state:

- Copilot can guide profile completion, decision review, planning questions, portfolio questions, research comparison, and recommendation follow-up
- Copilot uses tools rather than guessing when structured data is available
- important mutations are drafted, reviewed, and applied explicitly
- Copilot traces remain available for audit and debugging

High-level implementation:

- group tools by user intent: profile, daily review, planning, portfolio, research, recommendations, operations
- improve system instructions around data use, missing context, and mutation safety
- standardize draft trace rendering in v2
- add structured guided prompts for each major profile/readiness gap
- let Copilot create recommendation drafts where appropriate
- add browser tests for Copilot-guided completion and decision review

### 7. Trust, Durability, and Auditability

Purpose: make the app safe to rely on for personal financial decisions.

Future state:

- backup, restore, protection, and checkpoint status are visible in v2
- user-facing decision surfaces show degraded compute and stale context
- profile changes and Copilot-applied changes are auditable
- critical workflows have browser-level tests
- storage reliability has repeatable smoke validation

High-level implementation:

- expose existing storage/protection/git status in a v2 trust surface
- add audit/history records for profile and Copilot-applied mutations
- thread engine/degraded metadata into Today, Plan, Inbox, and Copilot when relevant
- keep storage smoke tests in the default verification path
- define release readiness checks for backup/restore and critical browser workflows

## v2 and Classic Ownership Strategy

The v2 app should become the primary product surface.

Ownership targets:

- Today: v2 owned
- Copilot: v2 owned
- Inbox: v2 owned
- Profile readiness: v2 owned
- Portfolio summary and decision flows: v2 owned
- Plan summary and high-frequency edits: v2 owned
- Import/sync/settings/storage: Atelier or classic until migrated
- Advanced research/workflows: Atelier until they become frequent decision loops

Classic views should be treated as:

1. historical implementation surfaces
2. advanced fallback
3. temporary migration bridges

They should not define the future information architecture.

## Phased Execution Plan

### Phase 1: Planning Reset and Source-of-Truth Cleanup

Goal: make this plan the clear product direction.

High-level tasks:

- create this future-state plan
- mark older planning docs as historical or domain-specific
- update README documentation links
- update backlog language to point here
- keep implementation progress logs available for traceability
- create a current v2/classic ownership matrix

Done when:

- all planning docs point to this document for active product direction
- no old roadmap claims to be the current execution source of truth
- future work can be prioritized against this plan

### Phase 2: Profile Readiness Loop

Goal: make profile completeness visible, actionable, and Copilot-fillable.

High-level tasks:

- finish current physical-assets Copilot profile flow
- add tax-basics guided profile filling
- add debt/no-debt confirmation
- add income and expense confidence review
- expand onboarding status into profile readiness
- surface profile readiness in Today and Copilot
- create profile-completeness recommendations

Done when:

- profile gaps are visible in Today
- Copilot can fill key sections with draft/review/apply
- missing profile data can outrank weaker financial recommendations
- browser tests cover profile draft application and readiness refresh

### Phase 3: Recommendation Decision Loop

Goal: make recommendations consistently decision-grade.

High-level tasks:

- standardize recommendation quality metadata
- normalize evidence/impact/confidence across existing factories
- add profile-completeness and stale-assumption generators
- improve v2 preview/apply/outcome capture
- feed outcome analytics into ranking inputs
- add browser tests for recommendation lifecycle flows (started: v2 now covers Today daily review, Copilot profile completion, and Inbox preview/apply/outcome)

Done when:

- generated recommendations consistently explain source, evidence, impact, and freshness
- applicable recommendations can be previewed before applying
- outcome capture is easy from v2
- closure analytics influence future prioritization

### Phase 4: Today Command Center

Goal: make Today the default daily review experience.

High-level tasks:

- add profile readiness to Today (started: command card now shows profile completion and next gap)
- add top-action explanation (started: top actions show quality summary and action hint)
- add data freshness/degraded-mode warnings (started: command cards now show snapshot/data-trust and engine-health posture)
- add pending draft/review indicators (started: Today now surfaces pending recommendation outcome capture)
- add recent financial changes (started: Today now surfaces recent portfolio change from snapshot history)
- add cash runway and emergency fund status (started: Today now surfaces cash runway from financial health)
- connect each card to a concrete review flow
- extend command cards beyond profile/data/plan/portfolio into research readiness and pending drafts

Done when:

- opening Today tells the user what matters now
- top actions are understandable without visiting multiple pages
- missing data, stale data, and degraded compute are visible

### Phase 5: v2 Plan Workspace Migration

Goal: make the active plan experience native to v2.

High-level tasks:

- migrate plan settings editing
- migrate timeline events summary/editing
- migrate contribution rules
- migrate scenario diff review
- migrate plan decisions
- expose artifacts and research links
- keep rare advanced tools in Atelier until needed

Done when:

- v2 Plan can support the user's normal planning workflow
- classic Plan links are no longer required for high-frequency tasks
- plan changes and decisions are test-covered in browser workflows

### Phase 6: Portfolio-Aware Research

Goal: connect investment research to the user's real portfolio and plan.

High-level tasks:

- improve multi-symbol comparison
- add portfolio-impact simulation to research flows
- connect watchlist ranking to profile/plan context
- convert dossiers into plan artifacts
- allow research findings to generate recommendations

Done when:

- research answers "does this fit me?" rather than only "what is this symbol?"
- research outputs can flow into plan artifacts and recommendations
- Copilot can explain research conclusions with context and provenance

### Phase 7: Trust and Productization

Goal: make the app reliable enough to depend on.

High-level tasks:

- surface backup/restore/protection in v2
- add audit views for profile and Copilot-applied changes
- expose degraded-mode status in decision surfaces
- expand browser workflow coverage
- maintain storage reliability smoke validation
- define release readiness checks

Done when:

- critical data can be backed up, restored, and checked from v2
- important user-visible decisions include freshness/degraded context where relevant
- core daily, profile, recommendation, plan, and Copilot flows have browser-level tests

## Prioritization Rules

Use these rules when choosing the next slice:

1. Prefer work that improves decision quality.
2. Prefer work that connects multiple domains.
3. Prefer work that makes missing or stale data visible.
4. Prefer work that strengthens review/apply/outcome loops.
5. Prefer v2 slices for high-frequency workflows.
6. Prefer tests that exercise real user workflows.
7. Avoid adding isolated capabilities that do not feed Today, Inbox, Plan, Profile, Portfolio, Research, or Copilot loops.

## Success Metrics

Near-term:

- profile readiness appears in Today and Copilot
- Copilot profile updates always use draft/review/apply
- missing profile data can generate recommendations
- existing recommendation factories share a consistent quality contract
- v2 browser tests cover Copilot profile completion and recommendation lifecycle basics

Mid-term:

- 80% of generated recommendations include evidence, expected impact, confidence, and source freshness
- 60% of applied recommendations receive outcome capture
- Today can explain the top financial action without requiring navigation
- v2 owns normal daily, Copilot, Inbox, and Profile readiness workflows
- classic links are no longer required for common plan review and edits

Long-term:

- BuildWealth can explain what changed, why it matters, and what to do next from a single daily review
- recommendation ranking improves from closure/outcome history
- research flows are portfolio-aware by default
- backup/restore/protection status is visible and validated
- critical workflows have browser-level regression coverage

## Current Immediate Next Work

1. Add pending Copilot draft/review indicators to Today command cards.
2. Migrate compare and dossier research surfaces to cite or consume evidence packets.
3. Add richer provider freshness/coverage metadata around current OpenBB-backed research outputs.
4. Define the first portfolio-fit assessment contract before generating investment-fit recommendations.
5. Continue expanding browser coverage around Plan v2 migration as those surfaces move over.

## Documentation Governance

Use this document for active product direction and phase sequencing.

Use older documents as follows:

- `docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md`: historical roadmap and progress log through April 2026.
- `docs/STANDALONE_BUILD_PLAN.md`: historical standalone build plan and implementation progress record.
- `docs/RECOMMENDATION_FACTORY_PLAN.md`: domain-specific recommendation factory design reference.
- `docs/INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md`: investment-fit, market data, OpenBB, research evidence, and watchlist recommendation strategy.
- `docs/CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md`: codebase quality and refactor guardrail reference.
- `docs/ARCHITECTURE.md`: runtime architecture and system-of-record reference.
- `docs/OPERATIONS_STANDALONE.md`: local operations reference.
- `docs/MIGRATION_AND_COMPATIBILITY.md`: migration and compatibility reference.

When a future product decision conflicts with an older roadmap queue, prefer this document unless the older document records a still-valid architectural constraint.
