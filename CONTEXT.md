# BuildWealth

BuildWealth is a local-first financial decision system that helps one user understand current financial reality, evaluate possible futures, and review evidence-backed next actions.

## Language

**Context Intelligence**:
The capability that captures, selects, retrieves, and audits the financial context used by Copilot and recommendations.
_Avoid_: Memory, chatbot memory, AI memory

**Canonical State**:
The authoritative BuildWealth data stored in Profile, Portfolio, Plan, Recommendations, Research artifacts, and related system-owned stores.
_Avoid_: Memory, vector store, prompt context

**BuildWealth-Native Capability**:
A capability whose data, calculations, UI, UX, Copilot access, review flow, and audit trail are owned and expressed as part of BuildWealth.
_Avoid_: Portfolio feature, Plan feature, adapter feature, external product parity

**v2 Product Surface**:
The canonical BuildWealth user interface for all current and future user workflows.
_Avoid_: Classic UI, v1 fallback, old dashboard

**Outcome Parity**:
The standard that BuildWealth matches or exceeds the user result of a reference capability without copying its screens, terminology, or internal workflow.
_Avoid_: Feature parity, screen parity, clone

**Workflow Replacement**:
The v2 migration standard that replaces user jobs and outcomes rather than cloning every v1 feature or screen.
_Avoid_: Feature migration, screen migration, parity checklist

**Classic Removal Gate**:
The workflow coverage and approval threshold that must be met before v1/classic UI is removed.
_Avoid_: Automatic cleanup, incidental deletion, old UI deprecation

**Portfolio Analysis**:
The BuildWealth-native capability that explains portfolio performance, benchmarks, attribution, allocation, risk, and trade impact.
_Avoid_: Portfolio adapter, benchmark adapter, attribution adapter

**Portfolio Audit**:
The BuildWealth-native evidence trail that explains changes to, or interpretation of, portfolio financial state.
_Avoid_: System log, app activity feed, git history

**Import Workbench**:
The BuildWealth-native capability that previews, reconciles, applies, and audits imported financial data before it becomes portfolio state.
_Avoid_: Portfolio import, external import flow, CSV uploader

**Import Report**:
A durable source-evidence record that explains how one import preview and apply operation affected Canonical State.
_Avoid_: Import state, transaction ledger, CSV result

**Asset Registry**:
The BuildWealth-native capability that resolves, classifies, enriches, prices, and audits investable assets used by Portfolio, Plan, Research, and Copilot.
_Avoid_: Symbol metadata adapter, Portfolio symbol search, ticker cache

**Asset Review Item**:
A review item for an unresolved, ambiguous, weakly classified, or manually overridden asset that could affect portfolio interpretation or plan quality.
_Avoid_: Broken ticker, bad symbol, metadata warning

**Simulations**:
The BuildWealth-native capability that runs projections, scenario comparisons, Monte Carlo simulations, historical backtests, and failure-mode analysis for financial plans.
_Avoid_: Plan adapter, planning adapter, scenario adapter

**Scenario**:
A named set of assumptions used to compare possible financial outcomes.
_Avoid_: Simulation, plan, branch

**Branch**:
A scenario created from a life event, what-if template, or focused change to the active plan.
_Avoid_: Simulation, active plan, recommendation

**Simulation Run**:
A tracked execution of a plan projection, scenario comparison, Monte Carlo simulation, or historical backtest.
_Avoid_: Calculation response, transient chart data, hidden Copilot math

**Simulation Artifact**:
A durable source-evidence record of a Simulation Run that was saved because it materially supported a review, recommendation, Copilot answer, or Plan Decision.
_Avoid_: Temporary run, chart cache, raw output dump

**Saved Simulation**:
The user-facing name for a durable Simulation Artifact.
_Avoid_: Artifact, evidence object, stored run

**Plan Resilience**:
The user-facing assessment of how reliably a plan funds required expenses, goals, liabilities, and reserve needs across modeled futures.
_Avoid_: Success probability, safe retirement number, guarantee

**Plan Strength**:
The preferred plain-language UI label for Plan Resilience.
_Avoid_: Success probability, guarantee, safe-to-retire score

**Plan Resilience Label**:
The rule-derived user-facing state that summarizes Plan Resilience before showing supporting metrics.
Allowed values: `Strong`, `Workable`, `Fragile`, `Not Ready To Rely On`
_Avoid_: Probability label, AI confidence, guarantee

**Plan Strategy Lab**:
The BuildWealth-native capability that compares contribution ordering, withdrawal strategies, retirement tax controls, and other plan-improvement levers.
_Avoid_: Plan strategy flow, tax adapter, withdrawal adapter

**Plan Lever**:
A reviewable change that can be simulated against the active plan before the user decides whether to adopt it.
_Avoid_: Recommendation, suggestion, optimization, automatic fix

**Plan Lever Impact Level**:
The deterministic review level assigned to a Plan Lever based on its financial magnitude, resilience effect, strategy class, reversibility, and constraint risk.
Allowed values: `low`, `medium`, `high`, `critical`
_Avoid_: Importance, vibes, riskiness

**Plan Lever Impact Policy**:
A versioned, testable ruleset that assigns Plan Lever Impact Level from plan-resilience delta, cash-flow change, one-time money movement, tax impact, retirement timing, strategy class, reversibility, and constraint conflicts.
_Avoid_: Manual judgment, hidden AI decision, generic severity

**Pre-Simulation Impact Level**:
The Plan Lever Impact Level assigned from the proposed change before running a projection or simulation.
_Avoid_: Initial guess, AI estimate, rough severity

**Post-Simulation Impact Level**:
The Plan Lever Impact Level assigned from simulation evidence after comparing the proposed change against the active plan.
_Avoid_: Result score, probability change, final vibes

**Plan Decision**:
A durable source-evidence record of a reviewed choice that changes, rejects, or preserves the active plan.
_Avoid_: Setting change, accepted recommendation, hidden plan mutation

**Material Financial Fact**:
A user-specific fact that can change financial advice quality, recommendation ranking, planning projections, or investment fit.
_Avoid_: Memory, note, chat fact

**Context Materiality**:
The expected impact level a context item, candidate, or conflict could have on financial advice, recommendation ranking, planning projections, investment fit, or user trust.
Allowed values: `low`, `medium`, `high`, `critical`
_Avoid_: Confidence, certainty, model score, Session Focus, user domain weights

**Session Focus**:
Conversation-scoped priorities that steer which context domains/sections Copilot expands, orders, or mutes in the Prompt Brief and retrieval ordering for that conversation.
_Avoid_: Memory weights, materiality weights, chatbot memory, user importance score, Candidate Prompt Influence

**Focus Domain**:
User-legible domain label used by Session Focus (for example `plan`, `profile.goals`, `research`).
_Avoid_: Arbitrary tag, memory category

**Focus Mode**:
How aggressively Session Focus narrows default context expansion.
Allowed values: `narrow`, `balanced`, `wide`
_Avoid_: Model temperature mode

**Prompt Brief**:
The slim Financial Context block injected into the Copilot system message (not the full assembled payload dump).
_Avoid_: Full context dump, memory blob

**Muted Domain Safety Warning**:
A short materiality-gated warning for a muted domain when safety requires it, without re-expanding the full domain dump.
_Avoid_: Full domain dump, silent suppression

**Materiality Policy**:
A deterministic, testable ruleset that assigns **Context Materiality** from target domain, source authority, financial magnitude, action proximity, time sensitivity, and conflict risk.
_Avoid_: LLM judgment, hidden ranking, intuition

**Materiality Policy Version**:
A named version of the global **Materiality Policy** used to classify candidates, context items, and conflicts.
_Avoid_: Implicit thresholds, user-specific intuition

**Profile-Aware Materiality Override**:
A future, traceable adjustment to **Context Materiality** based on confirmed profile, plan, portfolio, or investment policy context.
_Avoid_: Hidden personalization, unreviewed model preference

**Context Candidate**:
A captured but unconfirmed statement that may become **Canonical State** after user review.
_Avoid_: Fact, memory

**Candidate Review Route**:
The product surface and apply flow where a **Context Candidate** should be confirmed, edited, rejected, or deferred.
_Avoid_: Generic approval, AI suggestion bucket, memory review

**Candidate Review Item**:
A review item created or updated for a high-impact **Context Candidate** that needs user attention before BuildWealth can rely on it.
_Avoid_: AI todo, memory notification, automatic apply

**Candidate Lifecycle State**:
The review status of a **Context Candidate**.
Allowed values: `pending_review`, `deferred`, `stale_unconfirmed`, `applied`, `rejected`, `superseded`, `archived`
_Avoid_: Expired fact, forgotten memory, deleted suggestion

**Candidate Prompt Influence**:
How much an unconfirmed **Context Candidate** may shape Copilot context.
Allowed values: `none`, `mention_only`, `supporting_context`, `authoritative_after_apply`
_Avoid_: Memory confidence, hidden weight, model belief, Session Focus

Session Focus steers which *domains/sections* are expanded in the Prompt Brief. Context Materiality and Candidate Prompt Influence still govern whether *candidates/conflicts/items* may shape advice. Session Focus must not lower materiality, change candidate lifecycle, or suppress required safety surfaces.

**Context Registry**:
The rebuildable operational index that stores retrievable context items for **Context Intelligence**.
_Avoid_: Canonical store, durable snapshot, memory database

**Context Item**:
A retrievable unit in the **Context Registry**, sized according to the domain fact or evidence it represents.
_Avoid_: Raw message, memory blob

**Source Evidence**:
A saved research artifact, recommendation packet, decision record, or other reviewable record that supports a claim but is not the authoritative structured store for material financial facts.
_Avoid_: Summary, memory, embedding match

**Derived Context Item**:
A summary or transformed representation used to find or compress relevant context, not to prove a material financial claim.
_Avoid_: Source of truth, evidence

**Narrative Evidence**:
Long-form or prose context such as plan text, decisions, research artifacts, recommendation packets, outcomes, and conversation summaries.
_Avoid_: Canonical numeric fact, balance, holding

**Semantic Retrieval**:
Meaning-based retrieval over **Narrative Evidence**, usually powered by embeddings.
_Avoid_: Source of truth, calculation, policy lookup

**Context Conflict**:
A material mismatch between context items that could change advice quality, recommendation ranking, planning projections, or investment fit.
_Avoid_: Data inconsistency, contradiction, conflict error

**Plain-Language Explanation**:
A user-facing explanation that avoids financial jargon where possible and defines necessary terms in context.
_Avoid_: Technical caveat, model warning, expert-only rationale

**Plain-Language Action Readiness**:
A user-facing label derived from **Context Materiality** and context quality that tells the user what is safe to do next.
Suggested labels: `Can review later`, `Worth reviewing`, `Review before relying on this`, `Needs attention before acting`
_Avoid_: Low/medium/high/critical, severity score, internal materiality, urgency-only label

**Decision-Grade Advice**:
Advice that has enough current, non-conflicting context for BuildWealth to present it as ready for normal review or preview.
_Avoid_: Confident answer, final answer, model recommendation

**Needs Review**:
A user-facing state for advice blocked by stale, weak, missing, or conflicting context.
_Avoid_: Error, invalid, failed, non-decision-grade

**Not Ready To Act On**:
A user-facing state for advice blocked by a material **Context Conflict** or missing required data.
_Avoid_: Rejected, impossible, forbidden

**Conflict Review Item**:
A deduped review-only Inbox item created for a persistent **Context Conflict** that will keep affecting advice until resolved.
_Avoid_: Apply action, trade recommendation, error ticket

**Conflict Resolution**:
The act of making a **Context Conflict** safe by updating, confirming, or rejecting the underlying source, or by recording a scoped intentional exception.
_Avoid_: Dismiss, ignore, close warning

**Guided Conflict Review**:
A plain-language review flow that helps the user understand a **Context Conflict**, choose which source should be trusted, ask Copilot for an explanation, ask Copilot for a recommendation, or defer review without resolving it.
_Avoid_: Expert workflow, data cleanup, warning modal

**Conflict Deferral**:
A temporary snooze for a **Context Conflict** that lowers notification pressure but keeps the conflict unresolved.
_Avoid_: Dismiss, resolve later, ignore

**Context Trace**:
An on-demand record of which context shaped a Copilot answer or recommendation.
_Avoid_: Primary UI, context dashboard

**Default Context Path**:
The primary path Copilot uses to assemble context for answers and tool use.
_Avoid_: Experimental mode, optional context mode

**Durable Snapshot**:
A checksum-verified recovery snapshot of file-backed **Canonical State**.
_Avoid_: Context Registry, live index

## Relationships

- **Context Intelligence** retrieves from **Canonical State**.
- A **BuildWealth-Native Capability** may be inspired by external products, but the user should experience it only through BuildWealth language, BuildWealth workflows, and BuildWealth-owned state.
- The **v2 Product Surface** is the only future user interface; v1/classic UI is temporary migration scaffolding and should be removed after native v2 workflow coverage exists.
- **Outcome Parity** is the replacement standard for external-app parity; exact feature or screen matching is required only when it improves the user's financial decision result.
- **Workflow Replacement** is the migration standard from v1/classic to the **v2 Product Surface**; old controls move only when they support a current user job or better outcome.
- The **Classic Removal Gate** requires v2 end-to-end coverage for import/review, portfolio maintenance, portfolio review, portfolio history, plan workspace, Inbox, Profile, Data & Recovery, and Copilot workflows.
- Passing the **Classic Removal Gate** requires explicit product-owner approval; v1/classic should not be removed only because implementation tasks appear complete.
- The **Portfolio Analysis**, **Import Workbench**, and **Asset Registry** belong to the Portfolio and Data & Tools workflows.
- The **Import Workbench** owns ingestion, mapping, reconciliation, duplicate review, account matching, unknown asset resolution, apply preview, and import reports; Portfolio owns the resulting transactions, accounts, assets, holdings, performance, risk, and audit interpretation after apply.
- An **Import Report** is **Source Evidence** for an import operation, while the resulting transactions, accounts, assets, and holdings belong in **Canonical State**.
- An unresolved import asset may become a limited asset record only with visible uncertainty; if the uncertainty could affect portfolio interpretation or planning quality, BuildWealth creates or updates an **Asset Review Item**.
- The **Portfolio Analysis** may value a limited asset when price and quantity are usable, but allocation, concentration, sector, region, risk, and plan outputs must show **Needs Review** where missing classification changes interpretation.
- **Portfolio Audit** contains events that change or explain portfolio financial state; Data & Recovery contains system operations needed to trust, restore, or operate the app.
- **Portfolio Audit** includes import reports, transaction changes, account changes, asset resolutions, manual price changes, FX overrides, cost-basis method changes, lot rebuilds, corporate actions, review packets, and saved trade simulations.
- **Portfolio Audit** excludes ordinary view loads, generic sync status, git checkpoints, provider settings, and health checks unless they directly changed or explain portfolio state.
- The **Simulations** and **Plan Strategy Lab** belong to the Plan workflow and may create evidence for Inbox recommendations and Plan decisions.
- A plan is the user's working financial thesis; a **Scenario** defines comparable assumptions; a **Branch** is a scenario created from a life event, template, or focused what-if change; a simulation tests a plan, scenario, or branch; a **Saved Simulation** preserves the result; a **Plan Decision** decides whether anything changes in the real plan.
- A **Simulation Run** should have a stable run id and lifecycle status even when the first implementation completes synchronously.
- **Simulation Run** statuses are `queued`, `running`, `completed`, `failed`, and `cancelled`.
- Copilot may discuss simulation results only when it can cite a **Simulation Run** or **Saved Simulation**.
- A **Simulation Artifact** is durable **Source Evidence**; exploratory **Simulation Runs** may expire unless saved, used by a recommendation, cited by a material Copilot answer, or attached to a **Plan Decision**.
- User-facing copy should prefer plain terms such as "saved simulation" or "saved plan review" instead of **Simulation Artifact**.
- The active plan should track the last decision-grade **Simulation Artifact**, not merely the last **Simulation Run**.
- User-facing simulation language should preserve the boundary between a real plan and an experiment: a plan is the user's working financial thesis, while a simulation is a what-if experiment against that plan.
- Use **Saved Simulation** in the UI for durable simulation evidence.
- A **Saved Simulation** is immutable evidence; changing one creates a new simulation based on the saved one rather than mutating the original.
- **Plan Resilience** is the preferred user-facing simulation concept; raw probability of success is an internal or supporting metric, not the main product promise.
- Use **Plan Strength** as the primary UI label for **Plan Resilience**, with supporting copy explaining resilience across simulations.
- **Plan Resilience Label** leads the simulation UI, while funded-trial percentage, percentile balances, fragile years, liquidity gap risk, goal funding risk, and input-quality warnings support the label.
- A **Plan Resilience Label** is rule-derived: `Strong` means high funding reliability with no near-term liquidity gap or critical input gap; `Workable` means acceptable funding reliability with reviewable weak points; `Fragile` means material failure modes or major sensitivity; `Not Ready To Rely On` means critical missing/conflicting inputs or modeled failure in action-sensitive years.
- A modeled future weakens **Plan Resilience** when required expenses cannot be funded, reserve floors are breached during action-sensitive periods, account depletion violates active plan assumptions, or required goals and liabilities cannot be funded when due.
- A modeled future does not automatically fail just because investment assets reach zero late in life if guaranteed income covers required expenses and the user's confirmed goals do not require remaining assets.
- A **Plan Lever** may change contributions, spending, income timing, retirement age, Social Security claiming, Roth conversions, withdrawal strategy, tax assumptions, asset allocation assumptions, goal timing, debt payoff, or major life events.
- A **Plan Lever** is simulated and compared before apply; a recommendation is the review prompt that explains why the user should consider a lever.
- A **Plan Lever Impact Policy** assigns the highest **Plan Lever Impact Level** triggered by any rule dimension and escalates when a lever affects an active recommendation, open decision, tax-sensitive event, liquidity floor, confirmed user constraint, or required goal.
- A **Plan Lever** receives a **Pre-Simulation Impact Level** before compute and a **Post-Simulation Impact Level** after evidence is available; the final **Plan Lever Impact Level** is the higher of the two.
- **Pre-Simulation Impact Level** determines the minimum review path before expensive compute; **Post-Simulation Impact Level** can escalate review requirements when evidence shows a material resilience, tax, goal, liquidity, or failure-mode effect.
- A single backend **Plan Lever Impact Policy** service should classify impact for Plan UI, Recommendation Factory, and Copilot so review paths do not drift across surfaces.
- Low-impact **Plan Levers** may use direct review/apply; medium-impact levers require preview and confirmation; high-impact levers require saved simulation evidence, proposed patch, and **Plan Decision**; critical levers must start as branch or decision draft and cannot be directly applied by Copilot.
- Initial **Plan Lever Impact Policy** dimensions are plan-resilience delta, recurring cash-flow change, one-time money movement, tax impact, retirement timing, strategy class, reversibility, and constraint conflict.
- Accepting a **Plan Lever** saves supporting evidence, presents an explicit active-plan patch, updates **Canonical State** only after user confirmation, and records a **Plan Decision** linking the lever, evidence, patch, risks, review date, and any originating recommendation.
- High-impact **Plan Levers** should default to a branch or decision draft before active-plan mutation.
- Copilot may operate a **BuildWealth-Native Capability** only through the same reviewed BuildWealth API and review/apply boundaries as the UI.
- **Context Intelligence** may index or summarize **Canonical State**, but it does not replace it.
- A **Material Financial Fact** must live in **Canonical State** before BuildWealth treats it as authoritative.
- **Context Materiality** is separate from confidence; a low-confidence candidate can still be high materiality if it would change important advice.
- **Context Materiality** should be assigned by a **Materiality Policy** first. Copilot may suggest a materiality hint and plain-language rationale, but it should not be the final authority.
- **Context Materiality** should control review urgency, prompt influence, whether a candidate can fade from normal UI, and whether a conflict blocks **Decision-Grade Advice**.
- Users should see **Plain-Language Action Readiness**, not raw **Context Materiality** values.
- Raw **Context Materiality** may appear in **Context Trace**, diagnostics, logs, and tests.
- The first **Materiality Policy** should use global versioned defaults.
- **Profile-Aware Materiality Overrides** may be added later, but only from confirmed **Canonical State** and with traceable rule ids.
- A **Context Candidate** becomes **Canonical State** only through the correct review/apply flow.
- Copilot, imports, recommendation workflows, and research review may draft **Context Candidates**.
- Every **Context Candidate** should carry source domain, source ref, extracted claim, target canonical field or plan area, confidence, **Context Materiality**, materiality rationale, and **Candidate Review Route**.
- **Context Candidates** should not silently delete themselves; record retention is separate from prompt influence.
- Unreviewed **Context Candidates** may become `stale_unconfirmed` or `archived`, but important material candidates should stay visible or escalate until reviewed.
- High and critical **Context Candidates** should create or update **Candidate Review Items** in the right product surface or Inbox.
- Medium **Context Candidates** may appear in the owning view or Copilot-guided review flow.
- Low **Context Candidates** may stay in audit or context capture unless they become relevant later.
- **Candidate Prompt Influence** determines whether Copilot can ignore a candidate, mention it as unconfirmed, use it as supporting context, or treat it as authoritative only after apply.
- No unconfirmed **Context Candidate** should be `authoritative_after_apply`; that influence level is available only after the candidate has become **Canonical State**.
- The **Context Registry** indexes **Canonical State** as **Context Items** for retrieval and can be rebuilt.
- **Context Items** are field-level for material profile and policy facts, event-level for plan timeline events, decision-level for plan decisions, recommendation-level for recommendations, and section-level for narrative research or plan evidence.
- **Source Evidence** can support Copilot answers, but material financial facts still resolve to **Canonical State**.
- A **Derived Context Item** can help retrieve or compress context, but it should point back to **Canonical State** or **Source Evidence** for material claims.
- **Semantic Retrieval** applies to **Narrative Evidence** only by default.
- **Semantic Retrieval** should not retrieve authoritative balances, holdings, tax rates, contribution amounts, policy limits, or plan settings as the source of truth.
- A **Context Conflict** should be surfaced to the user with a **Plain-Language Explanation** and a suggested review action.
- An unresolved **Context Conflict** blocks **Decision-Grade Advice**.
- A persistent **Context Conflict** should create or update a **Conflict Review Item**.
- A **Context Conflict** is resolved only through **Conflict Resolution**, not by dismissing a warning.
- Deferring a **Context Conflict** can hide or snooze the review prompt, but the conflict remains unresolved and still blocks **Decision-Grade Advice**.
- **Conflict Deferral** should support both a time trigger and a relevance trigger: resurface when the snooze ends, or sooner if the conflict affects a live recommendation, Copilot answer, planning projection, or investment-fit review.
- "Explain to me" and "Recommend to me" are support actions inside **Guided Conflict Review**; they do not mutate **Canonical State** without user confirmation.
- A user may record an intentional exception, but it must be scoped and saved as reviewable **Source Evidence**, such as a plan decision or recommendation resolution note.
- User-facing states should prefer **Needs Review** or **Not Ready To Act On** over internal terms like "decision-grade" or "context conflict."
- **Context Trace** is accessible on demand; existing BuildWealth surfaces remain the primary visual view of **Context Intelligence**.
- The **Default Context Path** should use **Context Intelligence** once implemented, because BuildWealth has no production users and can improve the better architecture in place.
- A **Durable Snapshot** supports recovery and migration; it is not the **Context Registry**.
- Copilot uses **Context Intelligence** to answer questions and explain what context shaped an answer.

## Authority Ladder

1. **Canonical State**
2. **Source Evidence**
3. **Derived Context Item**
4. **Context Candidate**

## Example Dialogue

> **Dev:** "Should we store the user's tax rate in memory so Copilot remembers it?"
> **Domain expert:** "No. The tax rate belongs in **Canonical State**. **Context Intelligence** can retrieve it and cite it when Copilot needs it."
>
> **Dev:** "The user said they feel aggressive about NVDA, but their plan says not to add single-stock risk. Which one wins?"
> **Domain expert:** "That is a **Context Conflict**. Show it in plain language: 'Your plan says to avoid adding more money to one company, but your recent note says you are interested in NVDA. Review this before treating the idea as ready.'"
>
> **Dev:** "Can Copilot still recommend the NVDA action?"
> **Domain expert:** "It can explain the tradeoff, but the advice is **Not Ready To Act On** until the conflict is reviewed."
>
> **Dev:** "What if that conflict will affect future advice too?"
> **Domain expert:** "Create a **Conflict Review Item** so it stays visible in Inbox until the user resolves it."
>
> **Dev:** "Can the user dismiss that review item?"
> **Domain expert:** "They can defer it, ask for an explanation, or ask Copilot for a recommendation. But the conflict is not resolved until they choose which source BuildWealth should trust, update the source, reject the candidate, or record a scoped exception."

## Flagged Ambiguities

- "memory" was used to describe both durable financial truth and retrieval support. Resolved: use **Canonical State** for authoritative facts and **Context Intelligence** for capture, retrieval, and audit behavior.
- "learned in conversation" was used ambiguously. Resolved: conversation can create a **Context Candidate**, but any **Material Financial Fact** must be reviewed into **Canonical State** before it is authoritative.
- "durable storage" was used ambiguously. Resolved: the existing migration database is a **Durable Snapshot**; the **Context Registry** should live in a separate operational index.
- "chunk" was too generic for registry granularity. Resolved: use **Context Item**, with domain-specific grain rules.
- "summary" was used ambiguously as both evidence and compression. Resolved: summaries are **Derived Context Items** and are not authoritative evidence for material financial claims.
- "conflict" could sound like a system error. Resolved: use **Context Conflict** for material advice-impacting mismatches and explain them in user-safe financial language.
- "decision-grade" is useful internally but too technical for most users. Resolved: use **Decision-Grade Advice** internally and plain states like **Needs Review** or **Not Ready To Act On** in the UI.
- "embeddings" was too broad. Resolved: embeddings support **Semantic Retrieval** over **Narrative Evidence** and do not replace structured lookup of **Canonical State**.
- "Context Intelligence UI" implied a standalone surface. Resolved: existing product surfaces are the visual view of **Context Intelligence**; traces and diagnostics are on-demand.
- "feature flag" implied a parallel context mode. Resolved: **Context Intelligence** should become the **Default Context Path** once implemented.
- "context conflict" could be transient or persistent. Resolved: persistent material conflicts create **Conflict Review Items** in Inbox.
- "dismiss conflict" would degrade future advice by hiding uncertainty. Resolved: **Conflict Resolution** requires source-level confirmation, source update, candidate rejection, or a scoped intentional exception. Deferral is allowed but does not unblock **Decision-Grade Advice**.
- "adapter" was used to describe both temporary implementation scaffolding and long-term product architecture. Resolved: the product goal is **BuildWealth-Native Capability**; external app names should not appear in user workflows, product labels, default runtime paths, or future module boundaries.
- "classic UI" was used as an acceptable place for unfinished workflows. Resolved: use **v2 Product Surface** as the canonical UI target; classic/v1 is migration scaffolding only.
- "v2 migration" could imply copying v1 screens. Resolved: use **Workflow Replacement**, where v2 replaces user jobs and outcomes rather than cloning every old feature.
- External product names were used as shorthand for product areas. Resolved: use **Portfolio Analysis**, **Import Workbench**, **Asset Registry**, **Simulations**, and **Plan Strategy Lab** as canonical BuildWealth terms.
- "same or better" could mean cloning features, screens, or workflows. Resolved: use **Outcome Parity** as the standard, with feature-level parity only when it directly improves decision quality.
- "unknown ticker" could mean an import error, an asset metadata gap, or a planning blocker. Resolved: use **Asset Review Item** when unresolved or weak asset identity/classification could affect interpretation.
- "success probability" was too narrow for retirement planning. Resolved: use **Plan Resilience** for user-facing simulation quality, with funding reliability, fragile years, liquidity gaps, account depletion, and goal funding risk as supporting signals.
- "plan review" blurred the line between the real plan and an experiment. Resolved: use "simulation" in the UI for what-if experiments and reserve "plan" for the user's working financial thesis.
- "scenario", "branch", and "simulation" were easy to collapse into one concept. Resolved: scenarios and branches define assumptions; simulations test them; saved simulations preserve results.
- "high-impact" was too vague for plan changes. Resolved: use **Plan Lever Impact Level** assigned by a versioned **Plan Lever Impact Policy**.
