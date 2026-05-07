# BuildWealth

BuildWealth is a local-first financial decision system that helps one user understand current financial reality, evaluate possible futures, and review evidence-backed next actions.

## Language

**Context Intelligence**:
The capability that captures, selects, retrieves, and audits the financial context used by Copilot and recommendations.
_Avoid_: Memory, chatbot memory, AI memory

**Canonical State**:
The authoritative BuildWealth data stored in Profile, Portfolio, Plan, Recommendations, Research artifacts, and related system-owned stores.
_Avoid_: Memory, vector store, prompt context

**Material Financial Fact**:
A user-specific fact that can change financial advice quality, recommendation ranking, planning projections, or investment fit.
_Avoid_: Memory, note, chat fact

**Context Materiality**:
The expected impact level a context item, candidate, or conflict could have on financial advice, recommendation ranking, planning projections, investment fit, or user trust.
Allowed values: `low`, `medium`, `high`, `critical`
_Avoid_: Confidence, certainty, model score

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
_Avoid_: Memory confidence, hidden weight, model belief

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
