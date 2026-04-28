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
- expose policy readiness in Profile, Today, and Copilot (started: onboarding/profile readiness and Copilot profile draft display include policy; Today-specific command-center policy surfacing remains future work)
- use max single-symbol exposure in portfolio-fit before expanding to other policy fields (started: profile policy cap overrides generic portfolio risk threshold and is cited in Portfolio/Copilot fit review cards)

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

- add optional pre-mortem prompts to high-impact Inbox recommendations
- store the result in recommendation `action_payload.decision_closure`
- show it during outcome capture

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

- store a lightweight daily review checkpoint
- compare current Today summary against the latest checkpoint
- surface 1-3 meaningful deltas in Today

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

- compute domain statuses from existing readiness, freshness, provider, and recommendation quality data
- render as a Today command-center card or compact panel
- link each weak domain to the correct review flow

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

- add thesis reviewed_at/expires_at metadata to saved research artifacts where available
- generate a review-only recommendation when a thesis expires
- show expiration/freshness in dossier lookup and Today research readiness

## Priority Recommendation

Start with the agreed sequence:

1. Tax-lot and account-location fit context.
2. v2 research surface migration.
3. Copilot and investment outcome calibration.

Then pull in the fresh ideas in this order:

1. Personal Investment Policy, because it improves portfolio-fit immediately.
2. What Changed Since Last Review, because it strengthens Today as the command center.
3. Research Thesis Expiration, because it extends the investment-fit evidence loop.
4. Decision Pre-Mortem, because it improves outcome learning and calibration.
5. Confidence Heat Map, because it can unify readiness/freshness once more domain signals exist.
