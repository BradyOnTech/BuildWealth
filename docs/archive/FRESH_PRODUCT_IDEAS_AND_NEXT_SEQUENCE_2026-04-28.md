# BuildWealth Fresh Product Ideas and Next Build Sequence

## Date
2026-04-28

## Status
Active idea backlog and near-term sequencing companion to:

- `docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md`
- `docs/INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md`

Use this document to preserve the newest product ideas before they are decomposed into implementation slices.

## Product Alignment

BuildWealth should remain a local-first financial decision operating system.

The core product question is not "what data can we show?" It is:

> What does my current financial reality imply, what should I review next, and what happened after I acted?

For investments, the core question remains:

> Does this investment fit me?

The next work should keep strengthening the decision loop:

1. Understand the user's financial reality.
2. Measure freshness, quality, risk, and missing context.
3. Generate evidence-backed recommendations.
4. Let the user review, compare, simulate, discuss, apply, reject, or defer.
5. Capture outcomes.
6. Improve future ranking and guidance.

## Agreed Next Build Sequence

### 1. Tax-Lot and Account-Location Fit Context

Goal: make portfolio-fit more personal and more realistic without drifting into automatic trading or tax advice.

First slice:

- identify which account holds the candidate or overlapping exposure
- classify account location when available: taxable, traditional retirement, Roth, cash, unknown
- surface unrealized gain/loss where available
- distinguish short-term vs long-term lots where available
- review a proposed account against preferred account-location policy
- flag missing tax-lot/account-location data as a confidence gap
- include this context in `assess_portfolio_fit(...)`, v2 Portfolio fit review, Copilot fit cards, and investment recommendation evidence

Important boundary:

- do not optimize trades automatically
- do not say "sell this lot"
- frame output as review context, tax friction awareness, or missing context

### 2. v2 Research Surface Migration

Goal: reduce classic-route dependence for high-frequency investment research workflows.

First slices should focus on:

- v2 research evidence packet display (started: `#research?symbol=...` renders packet freshness, coverage, metrics, risk, quality, gaps, and provenance)
- v2 compare surface for a small symbol set (started: `#research?compare=...` adds compare ranking context while reusing packet evidence cards)
- v2 dossier lookup/detail surface for saved plan artifacts (started: `#research?dossiers=1` lists saved research dossiers and `#research?dossier=...` renders packet citations from the saved artifact)
- direct route targets from Inbox, Portfolio, Today, and Copilot (started: Inbox, Portfolio fit review, and Copilot fit cards now link to v2 Research evidence)
- provider/freshness/warning visibility on every research surface

Done when:

- an investment recommendation can route to fit, compare, dossier, simulation, and Copilot without feeling disconnected
- classic research routes are advanced fallback, not the normal decision path

### 3. Copilot and Investment Outcome Calibration

Goal: learn whether Copilot-drafted investment/research reviews actually helped the user make better decisions.

First slices:

- tag outcomes for `copilot:investment_fit` recommendation rows (started)
- distinguish useful review, insufficient evidence, deferred, acted elsewhere, and not useful (started)
- feed that source/type outcome history into confidence and ranking (started)
- show calibration hints in Inbox and Today (started)

Important boundary:

- do not calibrate based only on market performance
- calibrate whether the decision process was useful, timely, and evidence-backed

## Fresh Product Ideas

### 1. Personal Investment Policy

Create a living "rules of the road" layer for investment-fit decisions.

Possible policy fields:

- max single-symbol exposure
- max sector exposure
- max speculative/watchlist allocation
- cash floor and emergency fund target
- preferred account locations by asset type
- tax sensitivity
- dividend/income preference
- risk tolerance
- excluded assets or sectors
- simplicity preference
- minimum evidence quality before recommendations are decision-grade

Why it matters:

- portfolio-fit can cite explicit user policy instead of relying only on generic thresholds
- Copilot can ask targeted questions when policy is missing
- recommendations become more personal and more defensible

Example:

> NVDA does not currently fit because it would exceed your 10% single-symbol policy and your taxable account already has high unrealized gains.

Likely first slice:

- add a small investment policy profile section (started: profile storage/API, Copilot draft/review cards, and readiness summary now include investment policy)
- expose policy readiness in Profile, Today, and Copilot (started: onboarding/profile readiness, Today command-center policy guardrail card, Copilot investment-policy prompt, and Copilot profile draft display include policy)
- use policy fields in portfolio-fit before expanding to a broader policy engine (started: max single-symbol exposure overrides generic portfolio risk threshold; sector caps and symbol/sector restrictions can block fit; preferred account-location policy can flag proposed account mismatches; minimum research confidence gates weak evidence; high tax sensitivity flags taxable exposure or missing tax context; cash floor, asset-class exposure caps, and simplicity preference now shape fit assessment; policy-aware watchlist recommendations create review-only Inbox rows; Portfolio/Copilot fit review cards cite the active policy guardrails)

### 2. Decision Pre-Mortem

Before accepting or applying an important recommendation, ask what would make the decision look wrong later.

Possible fields:

- expected benefit
- main risk
- disconfirming signal
- review date
- what to monitor
- what would cause the user to reverse or pause

Why it matters:

- outcome capture becomes less vague
- decisions get explicit success criteria
- the app learns from the quality of the decision process, not just market movement

Example:

> If this thesis is wrong, we would expect concentration risk to rise without improved plan confidence. Review again in 60 days or if allocation moves above policy.

Likely first slice:

- add optional pre-mortem prompts to high-impact Inbox recommendations (started: proposed high-priority/high-impact apply forms now ask for expected benefit, main risk, disconfirming signal, monitoring plan, and review date)
- store the result in recommendation `action_payload.decision_closure` (started: apply now saves `decision_closure.pre_mortem` and writes it into the closure artifact)
- show it during outcome capture (started: the outcome form now displays the saved pre-mortem baseline before realized outcome entry)
- use it in calibration and Today follow-up (started: closure analytics now reports pre-mortem coverage/realized coverage, and Today outcome-loop cards prioritize pending pre-mortem checks with the original risk signal)

### 3. What Changed Since Last Review

Create a Today card that compares current state to the last completed daily review.

Possible signals:

- portfolio value and concentration changed materially
- cash runway changed
- profile readiness changed
- plan assumptions aged
- research evidence became stale
- Copilot drafted something new
- recommendation priority stack changed
- provider or compute health degraded

Why it matters:

- Today becomes more than a static dashboard
- the app can answer "what changed?" immediately
- the user does not have to inspect every domain manually

Likely first slice:

- store a lightweight daily review checkpoint (started: `TODAY_REVIEW_CHECKPOINT_PATH` stores the latest local Today review checkpoint)
- compare current Today summary against the latest checkpoint (started: portfolio value, top holding/concentration, profile readiness, active plan update time, high-priority recommendation count, cash runway/financial health, research readiness, Copilot drafts, and the top recommendation stack)
- surface 1-3 meaningful deltas in Today (started: the `What changed` command card links to `#today?review=complete`, records the checkpoint, and refreshes back to the normal Today route)

### 4. Confidence Heat Map

Add a compact view of which decision domains are strong or weak.

Domains:

- Profile
- Cash
- Taxes
- Plan
- Portfolio
- Research
- Provider data
- Trust/release readiness
- Recommendations/outcomes

Possible statuses:

- decision-grade
- usable with caveats
- stale
- missing context
- degraded

Why it matters:

- makes missing or weak context visible without hunting through diagnostics
- helps explain why BuildWealth will or will not make stronger recommendations
- gives Copilot a simple shared vocabulary for caveats

Likely first slice:

- compute domain statuses from existing readiness, freshness, provider, trust/release-readiness, and recommendation quality data (started: Today now returns `confidence_domains` for Profile, Cash, Taxes, Plan, Portfolio, Research, Provider data, Trust, and Recommendations)
- render as a Today command-center card or compact panel (started: v2 Today renders a compact Confidence Heat Map under the command-card grid)
- link each weak domain to the correct review flow (started: weak domains route to Copilot profile completion, Plan, Portfolio, Research, Atelier, or Inbox as appropriate)

### 5. Research Thesis Expiration

Saved dossiers and watchlist theses should expire or need review when evidence changes.

Possible expiration triggers:

- dossier older than a configured age
- evidence packet freshness becomes stale/degraded
- price movement exceeds threshold since thesis
- estimates, dividends, or fundamentals changed when available
- portfolio context changed enough to affect fit
- user policy changed
- plan horizon or cash runway changed

Why it matters:

- saved research stops pretending to be permanently valid
- stale thesis reviews become a natural recommendation class
- investment-fit remains grounded in current context

Likely first slice:

- add thesis reviewed_at/expires_at metadata to saved research artifacts where available (started: saved dossier lookup/detail now derives and displays a thesis review status from the artifact timestamp)
- generate a review-only recommendation when a thesis expires or materially changes (started: `generator:research_thesis_expiration` creates deduped review-only Inbox rows for expired saved dossiers and current dossiers affected by policy material changes; `generator:watchlist_research` also creates review-only rows for stale watchlist theses, price moves, and policy material changes)
- show expiration/freshness in dossier lookup and Today research readiness (started: v2 dossier lookup/detail and Today research readiness now surface saved-dossier thesis expiry, stale watchlist theses, material watchlist price moves, policy-material-change thesis rows, and direct thesis-review routes)

## Priority Recommendation

Completed/mostly completed agreed sequence:

1. Tax-lot and account-location fit context is implemented enough for review-grade fit assessment, recommendation evidence, Portfolio cards, and Copilot fit traces.
2. v2 research surface migration is implemented enough for the normal decision loop: packet, compare, dossier, thesis review, Today, Inbox, Portfolio, Copilot, and Plan links can stay in v2.
3. Copilot and investment outcome calibration is started and wired into Copilot-drafted investment/research recommendations, Today cards, Inbox quality, and process outcome calibration.

Current build order:

1. Product testing pass using the release-readiness backend/product contract. v2 Atelier and Today now consume orchestrator-computed readiness with backup-age thresholds, protection/checkpoint/audit/restore-preview checks, degraded/provider blockers, and persisted product workflow verification.
2. Product workflow verification UI polish. The backend can record product-testing pass/fail/partial evidence now; a later slice can add a small v2 Atelier affordance for recording the pass without using the API directly.
3. Continue hardening the Confidence Heat Map only as new signal domains mature, especially release readiness and richer provider/evidence quality.

### Release Readiness Backend/Product Contract Build Plan

Goal: make "ready to rely on this app today?" a stable BuildWealth product signal rather than UI-only checklist rendering.

Implemented first slice:

- add a backend readiness response that summarizes backup recency, protection compliance, git/checkpoint state, audit-feed availability, restore-preview evidence, critical workflow verification status, and provider/degraded-mode blockers
- include `status`, `ready_count`, `total_count`, `blocking_gaps`, `warnings`, `checks`, and `recommended_actions`
- expose it through an API route that v2 Atelier and Today can consume
- record product workflow verification through `POST /api/release-readiness/workflow-verification`
- keep full restore apply out of v2; readiness can recommend read-only preview or classic guarded restore tools without applying a restore
- update Today Trust confidence domain and v2 Atelier checklist to render from the shared contract
- add unit/backend tests plus a browser test for "not ready", "ready with warnings", and "ready" states

Product-testing follow-up:

- run the feature-by-feature manual checklist now that release readiness has landed
- fix correctness, trust, routing, and data-loss risks before adding new features
- update the checklist with any issues found during testing so it becomes a reusable release gate

### Account-Type Contribution/Fit Guidance Build Plan

Goal: make portfolio-fit explain whether a candidate or contribution route fits the user's account structure and policy, without giving automatic trading or tax advice.

First implementation slice:

- derive a compact `contribution_guidance` object inside portfolio-fit when a proposed account, contribution route, or account policy is present (done)
- classify account treatment as taxable, tax-deferred, tax-free, cash, or unknown using existing account-type helpers (done)
- flag review-only conflicts for high tax sensitivity plus taxable placement, preferred account-location mismatches, concentration or asset-class caps affected by new contributions, cash-floor conflicts, and high-simplicity new-position concerns (done)
- expose this context in `portfolio_impact` and generated watchlist/research recommendation evidence (done)
- generate review-only Inbox rows such as "Review MSFT contribution account fit" when contribution/account routing is the key concern (done)
- route the row into Portfolio fit review and Copilot discussion, not a direct apply action (done)

Testing plan:

- add portfolio-fit tests for account-type contribution guidance
- add recommendation-factory tests for review-only contribution/account-location policy rows
- extend v2 Portfolio/Copilot rendering only if the existing fit cards do not already surface the new `portfolio_impact` context clearly
- add a browser workflow after backend behavior is stable: generated row -> Inbox route -> Portfolio fit review -> Copilot explanation
