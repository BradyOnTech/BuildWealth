# BuildWealth Context Intelligence Implementation Plan

## Date
2026-05-07

## Status
Active domain plan for high-fidelity Copilot context capture, retrieval, and auditability.

This document expands the Profile Readiness, Portfolio-Aware Research, Copilot as Guided Operator, and Trust pillars in:
- [BuildWealth Future State Product Plan (2026-04-26)](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)
- [BuildWealth Investment Fit and Market Research Plan (2026-04-26)](./INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md)

Use this document when deciding how BuildWealth should capture profile, investment, plan, recommendation, research, and conversation context for LLM use.

## Core Thesis

BuildWealth needs Context Intelligence, not generic chatbot memory.

The app already has strong structured sources of truth: portfolio state, financial profile, active plan, plan artifacts, recommendations, research dossiers, and conversation traces. The next step is not to throw all of that into embeddings. The next step is to create a governed context layer that can answer:

- what facts are authoritative?
- what context is relevant to this question?
- what context is stale, inferred, incomplete, or user-confirmed?
- what evidence did Copilot use?
- what should be retrieved semantically because it is narrative or historical?

Embeddings should help retrieve narrative and evidence context. They should not become the source of truth for balances, tax assumptions, contribution amounts, holdings, restrictions, or plan settings.

## Product Boundary

BuildWealth should use context intelligence to improve explanation, retrieval, and recommendation quality.

BuildWealth should not:

- let embedding matches override structured financial facts
- mutate profile, plan, portfolio, or recommendation state without explicit review
- treat conversation statements as confirmed profile facts without capture metadata
- hide stale, low-confidence, or missing context from the user
- make investment or planning recommendations without citing the profile, portfolio, plan, research, and recommendation context that materially shaped the answer

The strongest rule is:

> Structured BuildWealth state is authoritative. Semantic retrieval is supporting evidence.

Copilot, imports, recommendation workflows, and research review may create context candidates, but any material financial fact must be reviewed into the right canonical store before BuildWealth treats it as authoritative.

Every context candidate should include:

- source domain
- source ref
- extracted claim
- target canonical field or plan area
- confidence
- materiality
- materiality rationale
- review route
- lifecycle state
- prompt influence

The review route should point to the product surface that can safely apply or reject the candidate, such as Profile, Plan, Research, Recommendations, Inbox, or a Copilot-guided review flow.

Materiality should be determined by a deterministic Materiality Policy first, with optional LLM assistance for explanation or initial hints. Copilot may say why a candidate or conflict appears important, but the final materiality value must be produced by rules the product can test.

The first implementation should use global, versioned materiality defaults. Each classification should store a materiality policy version and enough rule ids or rationale to explain why it received its level. Profile-aware overrides can come later, after the global policy is stable.

Materiality is not confidence. A low-confidence note can still be high materiality if it would change important advice. A high-confidence note can still be low materiality if it only affects personalization.

Initial materiality levels:

- `low`: improves personalization or explanation, but should not change projections, recommendation ranking, investment fit, or action readiness
- `medium`: may change follow-up questions, research priority, scenario framing, or recommendation ranking
- `high`: may change plan projections, tax assumptions, income/expense assumptions, contribution strategy, allocation, investment policy fit, risk posture, or an open recommendation
- `critical`: could make current advice unsafe, misleading, urgent, or directly contrary to confirmed user constraints, active plan decisions, liquidity needs, tax/legal deadlines, or action-ready recommendations

Users should not see raw materiality labels. Product surfaces should translate materiality into plain-language action readiness:

- `low` -> **Can review later**
- `medium` -> **Worth reviewing**
- `high` -> **Review before relying on this**
- `critical` -> **Needs attention before acting**

The exact copy may vary by surface, but it should explain what the user can safely do next. For conflicts, the label should make clear whether the advice is blocked until review. Raw materiality values belong in traces, diagnostics, logs, and tests.

Materiality drivers:

- target domain and field, such as tax profile, income, debt, risk tolerance, investment policy, holdings, plan decision, recommendation, or research thesis
- authority of the source it affects or conflicts with
- estimated financial magnitude, such as percent of portfolio, percent of income, monthly cash-flow impact, debt obligation, or tax impact
- action proximity, such as whether the context affects a live recommendation, planning projection, or investment-fit review
- time sensitivity, such as near-term deadlines, stale research, old assumptions, or soon-to-expire plan windows
- conflict risk, especially conflict with confirmed profile fields, investment policy, plan decisions, or active recommendations
- user-stated constraints, such as "do not buy single stocks," "preserve cash," or "avoid taxable sales"

Candidates should not silently delete themselves. Record retention is separate from prompt influence:

- record retention decides whether the candidate remains in audit history
- lifecycle state decides where the candidate sits in review workflow
- prompt influence decides whether Copilot can use the candidate in answers

Candidate lifecycle states:

- `pending_review`
- `deferred`
- `stale_unconfirmed`
- `applied`
- `rejected`
- `superseded`
- `archived`

Prompt influence levels:

- `none`: do not include in normal Copilot context
- `mention_only`: may mention as an older or unconfirmed note
- `supporting_context`: may use as background evidence, with caveats
- `authoritative_after_apply`: available only after the candidate is applied into Canonical State

Important material candidates should escalate rather than expire. Examples include plan decisions, investment policy changes, income changes, tax assumptions, risk tolerance changes, major life events, or material investment restrictions. Lower-value candidates may become dormant or archived for normal UI, while still remaining in audit history.

High and critical candidates should create or update review items in the right product surface or Inbox. Medium candidates can appear in the owning view or a Copilot-guided review flow. Low candidates can stay in audit or context capture unless they become relevant later.

The first implementation should use domain defaults and conservative escalation rules:

- hard constraints and policy violations start at `high` and may escalate to `critical` when tied to live advice
- active recommendation, plan, tax, liquidity, debt, contribution, allocation, or risk-tolerance changes start at `high`
- research thesis and watchlist changes start at `medium`, escalating to `high` when they affect an open recommendation or current holding
- casual preference and learning-interest candidates start at `low`
- conflicts between two material sources should take the higher materiality of the involved items and escalate when the conflict blocks action readiness

Later profile-aware overrides may adjust thresholds from confirmed Canonical State, such as user-defined investment policy limits, cash runway targets, contribution goals, tax profile, debt priorities, risk tolerance, plan time horizon, active plan phase, or portfolio concentration. Overrides should be traceable, versioned, and conservative: they can raise urgency readily, but lowering materiality should require an explicit rule.

Use this authority ladder when deciding what Copilot may rely on:

1. Canonical State
2. Source Evidence, such as research artifacts, recommendation packets, and plan decisions
3. Derived Context Items, such as summaries and transformed retrieval records
4. Context Candidates, which are unconfirmed and not authoritative

Derived summaries are retrieval aids. They may help find or compress relevant context, but material claims should cite the underlying canonical record or source evidence.

When retrieved context conflicts, BuildWealth should not auto-resolve the conflict. The Context Assembler should identify the higher-authority item, include the conflicting item, downgrade confidence, and add a review action. User-facing explanations must be plain-language first, because BuildWealth is designed for users who may not already understand financial terminology.

An unresolved material conflict blocks decision-grade advice. Copilot may still explain the situation, compare options, and suggest review steps, but the user-facing state should be **Needs review** or **Not ready to act on**, not "decision-grade false" or "context conflict."

Persistent material conflicts should create or update deduped, review-only Inbox items. Inline warnings are enough for answer-specific conflicts, but durable conflicts should stay visible until resolved.

Material conflicts should not be dismissible as resolved. The product can let the user defer the review, but deferral only snoozes or lowers the notification pressure. It does not remove the conflict, and it does not unblock decision-grade advice.

Deferral should be both time-based and relevance-based. A deferred conflict should resurface when the snooze period ends, and it should also resurface sooner if the unresolved conflict affects a live recommendation, Copilot answer, planning projection, or investment-fit review.

Conflict review should be easy and guided:

- accept or update the source that should now be trusted
- reject a context candidate or stale statement that should not be trusted
- defer the review for later while keeping the advice state blocked
- ask "Explain to me" for a plain-language explanation of why the mismatch matters
- ask "Recommend to me" for Copilot's suggested resolution, based on source authority, recency, financial impact, and plan fit
- record a scoped intentional exception when the user knowingly wants a one-off or bounded departure from the normal plan

"Recommend to me" should never auto-resolve the conflict. It should produce a suggested action and a plain-language rationale, then ask the user to confirm before any profile, plan, research, or recommendation source changes.

Example:

> Your plan says not to add more money to one company right now, but your recent note says you are interested in NVDA. That mismatch needs review before BuildWealth treats an NVDA idea as ready to act on.

## Existing Baseline

Current useful primitives:

- `build_buildwealth_context_payload(...)` builds a unified context package with portfolio, profile, plan, research, recommendations, cache metadata, warnings, freshness, and quality fields.
- `build_context_summary_with_metadata(...)` creates a compact LLM-facing summary.
- `shape_context_payload(...)` supports `light` and `full` payload shaping.
- `FinancialProfileStore` persists structured profile sections.
- `PlanWorkspace.refresh_context(...)` materializes `context.md` from plan markdown, settings, timeline, contribution rules, assumption sets, branch templates, and recent decisions.
- Research dossiers can be saved as plan artifacts.
- Recommendation quality metadata already captures confidence, actionability, freshness, blocking context, and decision-grade status.
- Copilot tool traces are persisted in conversation metadata.

Current limitations:

- context selection is mostly static and limit-based
- profile fields have coarse freshness and no field-level provenance
- plan context is generated as markdown and trimmed, not retrieved by relevance
- research dossier lookup is mostly list/limit based
- conversation history is not summarized into durable context facts
- the current cache improves speed but does not improve retrieval quality
- Copilot responses do not expose a compact "context used" record as a first-class contract

## Target Architecture

Use a layered context system:

1. Canonical source stores remain unchanged as the source of truth.
2. A Context Registry indexes authoritative structured facts and narrative evidence.
3. A Retrieval Planner classifies the user request and decides which context domains are required.
4. A Context Assembler builds the LLM payload from required structured facts, retrieved narrative evidence, and freshness/quality warnings.
5. Copilot stores a context-use trace with each answer.

The initial architecture should stay local-first and file/SQLite-friendly. It should not require a remote vector database.

## Layer 1: Context Registry

Purpose: create one product-owned inventory of retrievable context without moving ownership away from existing stores.

Future state:

- every indexed context item has a stable id, source domain, source path/entity id, text representation, optional structured payload, freshness, provenance, and confidence
- profile fields, investment policies, plan decisions, artifacts, recommendations, and conversation summaries can be retrieved through the same interface
- the registry can answer both exact structured lookups and semantic/narrative lookups
- derived context can be rebuilt from canonical stores

Initial context domains:

- `profile`: income, expenses, debts, goals, physical assets, tax profile, investment policy, notes
- `portfolio`: snapshot summary, holdings, allocation, account balances, concentration/risk alerts, watchlist
- `plan`: active plan metadata, settings, timeline events, contribution rules, assumption sets, branch templates, decisions
- `recommendation`: open recommendations, closed outcomes, decision packets, pre-mortems, closure analytics
- `research`: evidence packets, watchlist theses, research dossiers, thesis revisions, provider/freshness metadata
- `conversation`: compact user-confirmed facts, unresolved questions, durable preferences, pending drafts

Initial item shape:

```json
{
  "id": "ctx_profile_investment_policy_max_single_symbol",
  "domain": "profile",
  "entity_type": "investment_policy_field",
  "entity_id": "max_single_symbol_exposure_pct",
  "source_ref": "profile/financial_profile.json#investment_policy.max_single_symbol_exposure_pct",
  "authority": "canonical",
  "text": "Investment policy: max single-symbol exposure is 10%.",
  "structured_payload": {
    "field": "investment_policy.max_single_symbol_exposure_pct",
    "value": 10.0,
    "unit": "percent"
  },
  "provenance": {
    "source": "profile_editor",
    "captured_by": "user",
    "confirmed_by_user": true
  },
  "quality": {
    "confidence": "high",
    "freshness": "current",
    "stale_after_days": 180
  },
  "timestamps": {
    "created_at": "2026-05-07T00:00:00Z",
    "updated_at": "2026-05-07T00:00:00Z",
    "last_confirmed_at": "2026-05-07T00:00:00Z",
    "expires_at": null
  }
}
```

Granularity rules:

- profile and investment policy: field-level for material fields
- portfolio: snapshot, holding, allocation, and risk-summary items by default; not every transaction
- plan: section-level for plan markdown, field-level for plan settings, event-level for timeline events, decision-level for decisions
- research: artifact-level metadata plus section-level items for thesis, risks, catalysts, evidence, and revision history
- recommendations: recommendation-level plus outcome and pre-mortem items when present
- conversation: summary-level and candidate-level only; raw message-level indexing is not the default

Implementation notes:

- store registry rows in a separate SQLite database at `DURABLE_STORAGE_DIR/context_index.db`
- keep `DURABLE_STORAGE_DIR/buildwealth_durable.db` reserved for durable snapshot and migration behavior
- storage split is recorded in [ADR 0001](./adr/0001-separate-context-registry-from-durable-snapshot.md)
- make the registry rebuildable from canonical files and stores
- keep embeddings optional per row, not required for every context item
- never embed raw account credentials, secrets, or unnecessary personally sensitive text

## Layer 2: Profile Field Metadata

Purpose: make profile context trustworthy enough for high-stakes recommendations.

Future state:

- profile fields carry source, status, freshness, confidence, and review dates
- Copilot can distinguish "the user said this in chat" from "the user reviewed and applied this profile update"
- missing or stale profile data generates targeted follow-up questions and recommendation quality caveats

Field metadata should support:

- `missing`
- `user_confirmed`
- `imported`
- `inferred`
- `copilot_drafted`
- `stale`
- `rejected`

Suggested profile metadata shape:

```json
{
  "profile_metadata": {
    "investment_policy.max_single_symbol_exposure_pct": {
      "status": "user_confirmed",
      "source": "profile_editor",
      "confidence": "high",
      "last_confirmed_at": "2026-05-07T00:00:00Z",
      "stale_after_days": 365
    },
    "tax_profile.marginal_tax_rate": {
      "status": "stale",
      "source": "copilot_profile_draft",
      "confidence": "medium",
      "last_confirmed_at": "2026-01-01T00:00:00Z",
      "stale_after_days": 120
    }
  }
}
```

First slice:

- add metadata for tax profile and investment policy fields only
- preserve backward compatibility by making metadata optional
- include profile metadata in context quality checks
- update Copilot profile draft/apply flows to write provenance for changed fields

## Layer 3: Semantic Retrieval

Purpose: retrieve relevant long-form evidence without bloating every prompt.

Use embeddings for:

- plan markdown
- plan decisions and rationale
- research dossier content
- watchlist thesis text
- recommendation decision packets
- recommendation closure artifacts
- conversation summaries
- user preference notes

Embeddings should be limited to narrative evidence by default. They should not index raw transaction history, full account payloads, secrets, or authoritative numeric facts unless there is a specific reviewed reason.

Do not use embeddings as the primary source for:

- portfolio balances
- account balances
- holdings
- allocation percentages
- tax rates
- contribution amounts
- plan settings
- investment policy limits
- recommendation statuses

Local embedding options:

- `disabled`: default mode; structured and lexical retrieval only
- `ollama`: preferred first local provider because embedding models can run behind a localhost API outside the Python orchestrator
- `sentence_transformers`: Python-native local provider with stronger in-process control but heavier ML dependencies
- `llama_cpp`: later local provider for GGUF embedding models if BuildWealth needs that runtime
- OpenAI-compatible remote provider: optional future adapter only, never default for local-first financial data

Initial settings:

- `CONTEXT_EMBEDDINGS_ENABLED=false`
- `CONTEXT_EMBEDDING_PROVIDER=disabled`
- `CONTEXT_EMBEDDING_MODEL=`
- `CONTEXT_EMBEDDING_BASE_URL=`

If embeddings are enabled, the UI should explain what categories of text will be embedded and provide a delete/rebuild action for the embedding index.

The opt-in default is recorded in [ADR 0002](./adr/0002-embeddings-are-opt-in-for-context-intelligence.md). This can be revisited if local or remote embeddings prove a clear improvement in research and query quality.

Embedding default promotion requires a retrieval-quality evaluation. The eval set should include real BuildWealth questions, expected source refs, and must-not-use sources, then compare:

1. structured plus lexical retrieval
2. structured plus lexical plus local embeddings
3. structured plus lexical plus remote embeddings, only if remote provider use is being considered

Promotion criteria:

- source recall improves by at least 20% on the eval set
- incorrect-source retrieval does not increase
- conflict detection improves or stays stable
- answer grounding cites the expected source refs more often
- privacy controls, delete/rebuild actions, and provider visibility are already shipped

Retrieval should be hybrid:

- exact filters first: domain, plan id, symbol, artifact id, recommendation id, status
- lexical search for ids, symbols, field names, and exact phrases
- semantic search for narrative relevance
- recency/freshness scoring
- quality scoring

Example scoring inputs:

- domain match
- active plan match
- symbol match
- user question similarity
- item freshness
- item confidence
- item authority
- recommendation status
- artifact type
- whether the item was user-confirmed

## Layer 4: Retrieval Planner

Purpose: decide which context to retrieve for a user request before assembling the LLM payload.

The planner can start as deterministic rules before adding any LLM classifier.

Example intents:

- `daily_review`
- `profile_completion`
- `investment_fit`
- `portfolio_risk`
- `plan_tracking`
- `scenario_question`
- `recommendation_review`
- `research_thesis_review`
- `memory_question`
- `mutation_request`

Each intent should declare:

- required structured context
- optional semantic domains
- max retrieved items
- freshness requirements
- mutation safety rules
- recommended tools

Example:

```json
{
  "intent": "investment_fit",
  "required_structured_context": [
    "profile.investment_policy",
    "profile.tax_profile",
    "portfolio.holdings",
    "portfolio.allocation",
    "plan.active_summary",
    "recommendations.open_for_symbol"
  ],
  "semantic_domains": [
    "research",
    "plan",
    "recommendation"
  ],
  "filters": {
    "symbols": ["NVDA"],
    "plan_id": "active"
  },
  "freshness": {
    "portfolio_snapshot_max_age_hours": 24,
    "research_max_age_days": 30
  }
}
```

## Layer 5: Context Assembler

Purpose: build the actual LLM context packet from selected structured and retrieved context.

The assembler should produce:

- `structured_context`: canonical facts and typed payloads
- `retrieved_context`: relevant narrative/evidence items with citations
- `quality`: freshness, coverage, warnings, missing sections, confidence
- `conflicts`: material context conflicts with plain-language explanations and review actions
- `context_budget`: item counts, chars/tokens, truncation status
- `citations`: stable context item ids and source refs
- `suggested_tools`: tools the model should call next when direct computation is needed

The assembler should become the default Copilot context path once implemented. There are no production users yet, so BuildWealth should move to the better architecture directly and improve it in place. The first version can still wrap the existing `build_buildwealth_context_payload(...)` for structured context and add a `retrieved_context` section.

## Layer 6: Context-Use Trace

Purpose: make answers auditable.

Every Copilot response should be able to show what context shaped the answer.

Trace shape:

```json
{
  "context_trace": {
    "intent": "investment_fit",
    "snapshot_as_of": "2026-05-07T14:00:00Z",
    "plan_id": "plan-1",
    "context_item_ids": [
      "ctx_profile_investment_policy",
      "ctx_portfolio_holding_nvda",
      "ctx_research_dossier_nvda_msft_2026_04_30"
    ],
    "artifact_refs": [
      {
        "plan_id": "plan-1",
        "artifact_id": "artifact-dossier-nvda-msft"
      }
    ],
    "warnings": [
      "Research dossier expires in 3 days."
    ]
  }
}
```

The UI does not need to show this in full immediately. It can start in tool trace metadata, then become a compact "Context used" drawer in v2 Copilot.

Context Intelligence should not become a standalone primary user surface. The application itself is the visual view of Context Intelligence: Profile, Portfolio, Plan, Inbox, Research, and Today show the underlying context in user-meaningful forms. Only trust-impacting states, source references, conflicts, and review actions should surface directly. Full traces and index diagnostics should be accessible on demand for debugging, audit, and power-user inspection.

## Proposed Module Ownership

Add these modules under `services/orchestrator/src/buildwealth_orchestrator/services/`:

- `context_registry.py`: persistence, rebuild, upsert, delete, list, exact filters
- `context_indexer.py`: creates registry items from profile, plan, portfolio, recommendations, research, conversations
- `context_retrieval.py`: deterministic retrieval planner, hybrid ranking, context assembly
- `embedding_clients.py`: local/provider embedding adapter with disabled fallback
- `context_trace.py`: answer trace shaping and persistence helpers

Keep `buildwealth_context.py` as the compatibility layer for the existing unified context contract while the richer system comes online.

## API and Tool Surface

Initial backend endpoints:

- `GET /api/context/registry/status`
- `POST /api/context/registry/rebuild`
- `GET /api/context/search`
- `POST /api/context/assemble`
- `GET /api/copilot/conversations/{conversation_id}/context-trace`

Initial Copilot tools:

- `search_context`: retrieve relevant registered context with domain filters
- `assemble_context`: build a high-fidelity packet for a specific intent/question
- `capture_context_fact`: draft a possible context fact for user review
- `apply_context_fact`: apply a reviewed context fact to the right canonical store or registry

Mutation rules:

- `capture_context_fact` may draft from conversation
- `apply_context_fact` requires explicit user confirmation
- profile facts should usually become profile draft/apply flows, not registry-only facts
- plan facts should usually become plan decisions, settings, timeline events, or artifacts
- registry-only facts are acceptable for low-risk preferences and conversation summaries

## Implementation Sequence

### Slice 1: Registry Skeleton

Goal: create a durable, rebuildable registry without changing Copilot behavior.

- [x] Define `ContextItem` schema and persistence adapter.
- [x] Implement registry rebuild from financial profile, plan context, recommendations, and research dossier artifact metadata.
- [x] Add status and rebuild endpoints.
- [x] Add tests for id stability, rebuild idempotency, and source refs.
- [x] Add telemetry counts for indexed rows by domain.

Done when:

- a local rebuild creates queryable context items
- no LLM prompt path depends on the registry yet
- registry can be deleted and rebuilt from canonical state

### Slice 2: Profile Metadata

Goal: make profile context provenance-aware.

- [x] Extend profile payload with optional `profile_metadata`.
- [x] Add migration defaults that preserve old profile files.
- [x] Update direct profile save to mark changed fields as `user_confirmed`.
- [x] Update Copilot profile draft/apply to mark changed fields as `copilot_drafted` then `user_confirmed`.
- [x] Add readiness checks for stale tax and investment-policy fields.
- [x] Add tests for metadata migration, save, and context quality output.

Done when:

- Copilot can tell whether material profile fields are missing, stale, inferred, or user-confirmed
- recommendation quality can reference stale profile fields by field path

### Slice 3: Search Without Embeddings

Goal: add useful retrieval before introducing embedding complexity.

- [x] Implement `search_context` with exact filters, lexical matching, recency, and quality scoring.
- [x] Index plan decisions, recommendation titles/details, profile policy fields, watchlist theses, and dossier metadata.
- [x] Add `/api/context/search`.
- [x] Add Copilot tool contract for `search_context`.
- [x] Add tests for symbol, plan id, domain, recommendation status, and profile-field retrieval.

Done when:

- investment-fit prompts can retrieve relevant plan decisions and research artifacts by symbol
- profile questions can retrieve field-level facts and metadata

### Slice 4: Context Assembler

Goal: make the high-fidelity Context Intelligence path the default Copilot context path while preserving current quality and warning behavior.

- [x] Build deterministic intent classification.
- [x] Add `assemble_context(question, plan_id, symbols, intent)` service.
- [x] Wrap existing `build_buildwealth_context_payload(...)` for structured context.
- [x] Add `retrieved_context`, `citations`, and `context_budget` sections.
- [x] Add `conflicts` with plain-language explanations and review actions.
- [x] Route Copilot chat through the assembler by default.
- [x] Keep the existing unified context builder as compatibility/helper code until the assembler fully replaces it.
- [x] Add tests proving stale/missing context is carried forward.
- [x] Add trace metadata from the first default-on slice.

Done when:

- Copilot receives structured context plus relevant retrieved evidence
- context truncation is visible and tested
- default Copilot answers carry context trace metadata

### Slice 4b: Conflict Review Items

Goal: route persistent material conflicts into the existing Inbox review loop.

- [x] Define conflict dedupe keys by conflict type, source refs, plan id, and symbol where relevant.
- [x] Add a conflict resolution state model: unresolved, deferred, resolved by source update, resolved by confirming existing source, resolved by rejecting candidate, and resolved by scoped exception.
- [x] Add review-only recommendation creation/update for persistent context conflicts.
- [x] Route conflict review items to Profile, Plan, Research, Inbox, or Copilot-guided review depending on source domain.
- [x] Add guided review actions: accept/update source, reject candidate, defer, explain, recommend, and record scoped exception.
- [x] Ensure defer only snoozes the review item and does not unblock decision-grade advice.
- [x] Store conflict deferral metadata, including deferred-until time, reason, and whether relevance-triggered resurfacing has occurred.
- [x] Resurface deferred conflicts when the snooze expires or when the conflict affects a live recommendation, Copilot answer, planning projection, or investment-fit review.
- [x] Ensure LLM-assisted recommendations explain the suggested resolution but require explicit user confirmation before mutating source state.
- [x] Ensure conflict review items block decision-grade advice until resolved.
- [x] Add tests for dedupe, plain-language detail, source refs, and review routing.
- [x] Add tests proving dismiss/defer does not mark a material conflict resolved.
- [x] Add tests proving deferred conflicts resurface on time expiry and relevance-triggered use.

Done when:

- persistent material conflicts do not disappear after a single Copilot answer
- Inbox shows a review-only item with clear language and a concrete review path
- the user can ask for explanation or recommendation without accidentally changing canonical financial context

### Slice 5: Embedding Index

Goal: add semantic retrieval for long-form narrative evidence.

- [x] Add embedding client interface and disabled fallback.
- [x] Store embeddings for eligible registry rows only.
- [x] Add local-first vector storage strategy.
- [x] Add hybrid scoring that combines exact filters, lexical score, semantic score, freshness, confidence, and authority.
- [x] Add backfill/rebuild path for embeddings.
- [x] Add tests with deterministic fake embeddings.

Done when:

- plan artifacts and conversation summaries can be retrieved by meaning, not only symbols or exact words
- disabling embeddings still leaves lexical retrieval working

### Slice 6: Context Candidate Capture

Goal: turn useful conversation, import, recommendation, and research moments into reviewed, durable context.

- [ ] Summarize long conversations into registry-only conversation summaries.
- [ ] Detect potential profile/plan facts from chat and draft them for review.
- [ ] Allow imports, recommendation workflows, and research review to draft context candidates.
- [ ] Require candidate metadata: source domain, source ref, extracted claim, target canonical field or plan area, confidence, materiality, materiality rationale, review route, lifecycle state, and prompt influence.
- [ ] Add a deterministic materiality policy for candidates and conflicts.
- [ ] Start with global versioned materiality defaults.
- [ ] Store materiality policy version and rule ids or rationale with each classification.
- [ ] Map raw materiality to plain-language action-readiness labels in user-facing surfaces.
- [ ] Keep raw materiality values limited to traces, diagnostics, logs, and tests.
- [ ] Defer profile-aware materiality overrides until the global policy is stable and tested.
- [ ] Allow LLM-assisted materiality hints only as input to the rule-based policy or plain-language explanation.
- [ ] Add candidate lifecycle states: pending review, deferred, stale unconfirmed, applied, rejected, superseded, and archived.
- [ ] Add prompt influence levels: none, mention-only, supporting context, and authoritative after apply.
- [ ] Keep candidate record retention separate from prompt influence.
- [ ] Escalate important material candidates rather than allowing them to age out silently.
- [ ] Create or update review items for high and critical context candidates.
- [ ] Route medium candidates to the owning view or Copilot-guided review flow.
- [ ] Keep low candidates in audit or context capture unless they become relevant later.
- [ ] Route profile changes through existing profile draft/apply flow.
- [ ] Route plan changes through settings/timeline/decision/artifact flows.
- [ ] Route recommendation, research, and imported candidates through their owning product surfaces.
- [ ] Add UI for reviewing pending context captures.
- [ ] Add audit events for applied context facts.
- [ ] Add tests proving unreviewed candidates cannot become authoritative prompt context.
- [ ] Add tests proving stale or archived candidates remain in audit history but lose normal prompt influence.
- [ ] Add tests for materiality defaults, escalation rules, and confidence/materiality separation.

Done when:

- Copilot can remember reviewed preferences and prior decisions without treating every drafted candidate as truth
- the user can inspect and reject proposed captures
- material candidates remain reviewable until resolved, while low-value candidates can fade from normal UI without being erased

### Slice 7: Context-Use Trace in v2 Copilot

Goal: make high-fidelity context visible and debuggable.

- [ ] Persist `context_trace` with assistant messages.
- [ ] Render a compact context-used summary in v2 Copilot.
- [ ] Link trace items to Profile, Portfolio, Plan artifacts, Research, and Inbox where possible.
- [ ] Add browser tests for investment-fit and profile-completion traces.

Done when:

- the user can see which profile fields, plan, snapshot, research artifacts, and recommendations shaped an answer
- stale or missing context warnings are visible next to the answer

## Testing Strategy

Backend tests:

- registry rebuild is idempotent
- registry rows carry stable source refs
- profile metadata migration preserves existing files
- search ranking respects domain, plan id, symbol, authority, freshness, and confidence
- context assembler carries warnings and missing sections
- embeddings can be disabled without breaking retrieval
- fake embeddings make semantic ranking deterministic
- context traces store item ids and source refs

Frontend/browser tests:

- Copilot investment-fit flow shows retrieved dossier and policy context
- Copilot profile flow shows missing/stale field context
- v2 Copilot renders context-used trace without exposing full sensitive payloads
- context capture review can approve or reject a drafted fact

Manual smoke tests:

- rebuild registry from a populated local workspace
- ask "does NVDA fit my plan?"
- ask "what did we decide about contribution routing?"
- ask "what profile context is missing before recommendations are decision-grade?"
- ask "why did you recommend this?"

## Security and Privacy

Default posture:

- local-first
- no remote vector database
- embedding provider disabled unless configured
- no secrets in registry text or embeddings
- redact account identifiers where full values are unnecessary
- store source refs and structured ids instead of duplicating sensitive payloads when possible

If remote embeddings are enabled:

- document provider, model, and data sent
- make it opt-in
- expose status in settings/trust surfaces
- allow rebuild/delete of embedding index

## Open Decisions

1. Storage backend: resolved. Use a separate operational SQLite index at `DURABLE_STORAGE_DIR/context_index.db`; do not add live registry tables to the durable snapshot database.
2. Embedding provider: resolved. Embeddings are optional, disabled by default, and limited to narrative evidence. Prefer Ollama as the first local provider when enabling embeddings; keep remote providers opt-in only.
3. Context item granularity: resolved. Use mixed granularity by domain: field-level where financial correctness matters, event/decision/recommendation-level for structured product records, and section-level for narrative evidence.
4. UI surface: resolved. Do not create a standalone Context Intelligence UI. Surface trust-impacting states through existing product views; make context traces and diagnostics available on demand.
5. Copilot default path: resolved. Use the Context Intelligence engine by default once implemented. There are no production users yet, so BuildWealth should take the better architecture path now and improve it in place rather than maintaining parallel context modes.
6. Materiality thresholds: resolved. Start with global versioned defaults, then add profile-aware overrides later once the baseline policy is explainable, tested, and traceable.
7. Materiality display: resolved. Show plain-language action-readiness labels to users rather than raw low/medium/high/critical materiality labels.
8. Candidate review routing: resolved. High and critical candidates create or update review items, medium candidates stay in the owning review surface or Copilot-guided flow, and low candidates remain in audit/context capture unless relevant later.

## Recommended First Build

Start with Slices 1 through 4 before adding embeddings.

That gets BuildWealth most of the reliability gain:

- authoritative profile and plan facts remain structured
- search works for symbols, plans, policies, recommendations, and artifacts
- Copilot receives better selected context
- freshness and provenance improve recommendation quality
- the architecture is ready for embeddings without depending on them too early

Embeddings become valuable after the registry exists, because then the system knows what it is embedding, where it came from, whether it is fresh, and whether it is allowed to influence a financial answer.
