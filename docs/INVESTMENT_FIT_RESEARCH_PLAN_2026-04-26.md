# BuildWealth Investment Fit and Market Research Plan

## Date
2026-04-26

## Status
Active domain plan for the investment research, market data, portfolio-fit, and research-backed recommendation side of BuildWealth.

This document expands the Portfolio-Aware Research and Decision-Grade Recommendations pillars in:
- [BuildWealth Future State Product Plan (2026-04-26)](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)

Use this document when deciding how BuildWealth should use market data providers, OpenBB, research dossiers, watchlists, portfolio simulation, and investment-related recommendation factories.

## Core Thesis

The investment side of BuildWealth should answer:

> Does this investment fit me?

It should not primarily answer:

> Is this stock good?

Generic stock quality is not enough. A symbol can be high quality and still be wrong for the user because it worsens concentration, conflicts with goals, exceeds risk tolerance, creates tax friction, duplicates existing exposure, does not match time horizon, or depends on incomplete profile data.

BuildWealth should therefore treat market research as an input to a personal decision system, not as the decision system itself.

## Product Boundary

BuildWealth should provide personalized, context-aware recommendations and decision support.

BuildWealth should not provide:

- automatic trading
- hidden "AI says buy" actions
- unreviewed portfolio mutation
- ungrounded buy/sell calls
- generic stock tips detached from the user's profile, portfolio, plan, and risk policy
- provider data treated as inherently complete or authoritative

The app can recommend research, comparison, simulation, review, contribution routing, rebalancing consideration, thesis refresh, or risk reduction. Stronger investment actions should require explicit evidence, simulation where available, and user review.

Regulatory and legal posture should be reviewed before distributing this functionality beyond local personal use.

## Role of OpenBB

OpenBB should be used as a market data and research access layer, not as the investment recommendation engine.

OpenBB is useful because its Open Data Platform provides a modular way to access data through provider extensions. Its provider model can expose financial data locally and through Python/REST workflows, and provider extensions can be installed or removed independently.

Relevant OpenBB references:

- [OpenBB ODP overview](https://openbb.co/products/odp/)
- [OpenBB provider extensions](https://docs.openbb.co/odp/python/extensions/providers)
- [OpenBB equity reference](https://docs.openbb.co/odp/python/reference/equity)
- [OpenBB equity historical price endpoint](https://docs.openbb.co/odp/python/reference/equity/price/historical)
- [OpenBB equity estimates reference](https://docs.openbb.co/odp/python/reference/equity/estimates)

Important constraints:

- OpenBB provider availability depends on installed packages, configured credentials, provider subscriptions, and provider behavior.
- OpenBB does not host the underlying data and provider output should carry warnings/freshness/provenance.
- OpenBB ODP is currently described by OpenBB as AGPL licensed, so license/provenance posture must be explicit before deeper integration or distribution.
- BuildWealth should keep a provider abstraction so OpenBB can be replaced, supplemented, or bypassed without changing product logic.

## Architecture Recommendation

Use this flow:

1. Market data providers and OpenBB fetch raw research data.
2. BuildWealth normalizes the data into provider-aware research evidence packets.
3. BuildWealth combines evidence with profile, portfolio, plan, goals, risk policy, and cash context.
4. BuildWealth computes investment fit.
5. BuildWealth creates recommendations through the existing Recommendation Factory and Inbox lifecycle.
6. The user reviews, simulates, discusses with Copilot, applies/rejects/defers, and records outcomes.

The decision boundary is:

- OpenBB answers: what does available market/provider data say?
- BuildWealth answers: does this action fit this user's financial life?

## Layer 1: Market Data Gateway

Purpose: keep market data access standardized, swappable, and provenance-aware.

Future state:

- BuildWealth has a market data gateway owned by the orchestrator.
- OpenBB is one provider path behind that gateway.
- The gateway records provider, endpoint, timestamp, credentials/coverage status, warnings, and data freshness.
- The gateway degrades gracefully when OpenBB or a provider is unavailable.
- BuildWealth contracts do not expose raw OpenBB response shapes directly to product logic.

Initial data categories:

- price history
- latest quote
- company profile
- fundamentals and ratios
- estimates and consensus
- analyst price targets where available
- ETF info and holdings where available
- news/company events where available
- macro/benchmark/index context where useful

High-level implementation:

- keep the current `OpenBBResearchService` as the starting adapter
- add a clearer provider-gateway boundary around it
- normalize response metadata and warnings
- define supported data categories independent of OpenBB endpoint names
- maintain provider capability/status reporting
- cache expensive or rate-limited research responses with freshness metadata
- make missing provider coverage explicit to downstream recommendation quality

## Layer 2: Research Evidence Packets

Purpose: convert raw market data into stable, inspectable evidence that BuildWealth can reason over.

Future state:

Each symbol or comparison can produce a research evidence packet with:

- symbol and asset identity
- provider coverage summary
- freshness status
- price trend
- volatility
- drawdown or downside-risk context
- valuation metrics where available
- growth metrics where available
- estimate/consensus signals where available
- dividend/income metrics where available
- ETF exposure/holdings where relevant
- news/event context where available
- data gaps and warnings
- confidence/quality score for the packet itself

Evidence packets are not recommendations. They are structured inputs that can be reused by:

- research compare
- dossiers
- watchlist ranking
- Copilot context
- plan artifacts
- portfolio-fit analysis
- recommendation factories

High-level implementation:

- define a research evidence packet contract
- map current quote/history outputs into that contract first, then migrate compare/dossier/watchlist consumers over time
- preserve raw provider references only as trace/provenance
- calculate simple quality and freshness fields
- make packet quality visible in Copilot and recommendation evidence
- store plan-attached dossiers as artifacts when the user chooses to save them

Current implementation:

- `ResearchEvidencePacket` and `ResearchEvidencePacketRequest` define the first stable packet contract.
- `OpenBBResearchService.evidence_packet(...)` builds a single-symbol packet from quote and price-history responses.
- `/api/research/evidence-packet` exposes the packet for downstream Today, Copilot, dossier, and recommendation work.
- The first packet includes identity, provider coverage, freshness, metrics, risk context, quality/confidence, blocking gaps, and provenance summaries.
- Portfolio-fit is intentionally not part of the packet; that remains the next layer.

## Layer 3: Portfolio-Fit Engine

Purpose: evaluate whether an investment candidate makes sense for this user.

Future state:

An investment candidate should be evaluated against:

- current holdings
- account structure
- current cash
- emergency fund/cash runway
- debt obligations
- contribution plan
- active financial goals
- active plan time horizon
- risk policy
- concentration thresholds
- asset class exposure
- sector exposure
- region exposure
- factor/style exposure when available
- overlapping ETF/holding exposure where available
- tax lots and taxable-account implications where available
- user preferences and restrictions
- profile completeness and stale-data status

The output should be a fit assessment, not a buy/sell verdict.

Example fit assessment fields:

- `fit_status`: fits, mixed, does_not_fit, needs_more_context
- `fit_score`: normalized score for ranking and display
- `fit_reasons`: concise positive reasons
- `fit_risks`: concise negative reasons
- `blocking_gaps`: missing data that prevents confidence
- `portfolio_impact`: concentration/allocation/cash impact
- `plan_impact`: goal/time-horizon/contribution impact where available
- `simulation_required`: whether the next step should be simulation before any recommendation
- `recommended_next_step`: research_more, compare_alternatives, simulate_trade, review_concentration, update_profile, create_dossier, discuss_in_copilot

High-level implementation:

- start with existing portfolio concentration and trade simulation data
- incorporate cash/liquidity and profile readiness before suggesting new investment actions
- calculate simple fit rules before adding complex scoring
- make negative fit reasons just as visible as positive ones
- treat missing profile/tax/cash context as a reason to pause rather than guess
- avoid producing "buy" language in fit outputs

Current implementation:

- `PortfolioFitAssessmentRequest` and `PortfolioFitAssessmentResponse` define the first reusable fit contract.
- `assess_portfolio_fit(...)` combines evidence packet quality, current holdings, risk thresholds, cash runway, profile readiness, active plan/time-horizon context, tax-lot/account-location context, and optional trade simulation.
- `/api/portfolio/fit-assessment` assembles current BuildWealth context and returns a fit assessment for API, Copilot, and v2 Portfolio review surfaces.
- First statuses cover `mixed`, `does_not_fit`, and `needs_more_context`; direct trade recommendations remain out of scope.
- Tax-lot/account-location context now surfaces account treatment, unrealized gain/loss, lot-term mix, proposed-account review, and missing account/lot confidence gaps where available; deeper tax-lot optimization remains out of scope.
- The first Personal Investment Policy slices add profile-backed investment guardrails, keep them in lightweight BuildWealth context, let the profile max single-symbol exposure override the generic portfolio threshold in fit assessment, gate research-backed fit when evidence confidence is below the user's minimum, make high tax sensitivity raise taxable-exposure/tax-context review constraints, let sector caps plus symbol/sector restrictions block fit, and review proposed accounts against preferred account-location policy. Today/Copilot surface missing guardrails, and Portfolio/Copilot fit review cards cite the active policy guardrails.

## Layer 4: Investment Recommendation Factory

Purpose: convert research and fit signals into safe, reviewable next actions.

Future state:

The Recommendation Factory can generate investment-related recommendations such as:

- refresh a stale watchlist thesis
- compare candidate investments before deciding
- simulate a trade before adding exposure
- avoid adding a candidate because it worsens concentration
- review whether new contributions should be routed away from an overconcentrated holding
- create a dossier for a watchlist item with enough preliminary evidence
- update profile/risk policy because fit cannot be assessed confidently
- review a holding whose evidence changed materially
- review ETF overlap before adding a fund
- revisit a saved research thesis after a price/estimate/news change

Initial recommendation types should be research and review actions, not direct trade actions.

Allowed language:

- "Review whether..."
- "Compare..."
- "Simulate..."
- "This would increase..."
- "This may fit because..."
- "This does not currently fit because..."
- "More context is needed before..."

Avoid:

- "Buy..."
- "Sell..."
- "This is a good stock..."
- "AI recommends purchasing..."
- "Automatically rebalance..."

High-level implementation:

- add a research/watchlist recommendation generator after the existing profile/readiness and recommendation-quality work
- use evidence packets and portfolio-fit outputs as generator inputs
- dedupe by symbol, signal type, and fit concern
- require evidence freshness for research-backed recommendations
- include source provider, data freshness, and fit reasons in `action_payload.evidence`
- route all actions through the existing Inbox lifecycle
- make "Discuss in Copilot" a first-class next step

Current implementation:

- `generator:watchlist_research` creates the first safe review rows from watchlist evidence and portfolio-fit context.
- Generated actions are limited to refresh research evidence, gather missing context, review policy/fit conflicts, simulate/compare, or discuss in Copilot.
- Rows include evidence packet id, provider, freshness, confidence, coverage score, provider coverage metadata, fit status, fit score, fit reasons, fit risks, fit blocking gaps, account-location context, and applied investment policy.
- Policy-aware rows now distinguish research confidence below the user's minimum and high tax-sensitivity fit reviews, while remaining review-only and avoiding direct trade language.
- The generator is available through `/api/recommendations/generate/watchlist-research` and participates in the run-all factory endpoint.

## Layer 5: Copilot Investment Guidance

Purpose: let the user ask natural investment questions while keeping the same evidence and safety boundaries.

Future state:

Copilot should be able to answer:

- "Does AAPL fit my portfolio?"
- "Should I compare VTI and SCHB for my goals?"
- "What happens if I put $5,000 into NVDA?"
- "Which watchlist items deserve research?"
- "What would this do to my concentration?"
- "What data do you need before you can answer?"

Copilot should:

- use BuildWealth tools for market data, portfolio-fit, and simulation
- cite the evidence packet/dossier used
- call out missing or stale data
- avoid ungrounded buy/sell language
- draft recommendations or research tasks for review
- never place trades or silently mutate portfolio state

High-level implementation:

- group Copilot tools around research, compare, dossier, portfolio impact, and recommendation drafting
- update system guidance to prefer fit assessment language
- require Copilot to explain when the answer is blocked by missing profile, risk, cash, or tax context
- render investment-fit trace cards in v2 Copilot
- allow Copilot to create a reviewed recommendation draft rather than direct action

## Investment-Fit Decision Loop

The end-to-end loop should be:

1. User adds or imports watchlist symbols.
2. BuildWealth fetches market data through the gateway.
3. BuildWealth creates or refreshes research evidence packets.
4. BuildWealth evaluates fit against user context.
5. BuildWealth generates safe recommendations or says more context is needed.
6. User reviews the recommendation in Inbox.
7. User opens compare/dossier/simulation/Copilot as needed.
8. User applies, rejects, defers, or records an outcome.
9. BuildWealth uses the outcome to improve future ranking.

This keeps the investment side aligned with the broader BuildWealth operating loop.

## v2 Product Surface

### Today

Today should surface investment-fit only when it matters.

Examples:

- "Two watchlist items need thesis refresh."
- "Adding NVDA would worsen technology concentration."
- "Research data for your top watchlist items is stale."
- "Your profile is missing risk/time-horizon context needed for investment-fit recommendations."

### Portfolio

Portfolio should show:

- current exposure
- concentration risk
- watchlist ranking
- trade simulation entry points
- candidate fit warnings
- research links for holdings and watchlist items

### Inbox

Inbox should own investment recommendations.

Each investment-related row should show:

- candidate symbol(s)
- recommendation kind
- evidence freshness
- provider/source summary
- portfolio-fit result
- next step
- confidence
- "Discuss in Copilot"

### Plan

Plan should receive research artifacts when the user intentionally saves them.

Examples:

- saved thesis for a planned allocation change
- research bridge artifact for a scenario branch
- comparison artifact supporting a contribution strategy

### Copilot

Copilot should be the best way to explore:

- why a candidate fits or does not fit
- what data was used
- which alternatives to compare
- what simulation says
- what the next safe action should be

## Data Quality and Confidence

Investment-fit outputs should be conservative when data quality is low.

Confidence should consider:

- provider availability
- endpoint warnings
- data freshness
- completeness of research evidence packet
- completeness of user profile
- portfolio snapshot freshness
- plan freshness
- whether a simulation was run
- whether a dossier exists
- whether outcome history exists for similar recommendations

If confidence is low, the recommended action should usually be to gather more context, refresh data, compare alternatives, or run a simulation.

## Recommendation Examples

Good examples:

- "Simulate adding $5,000 to NVDA before deciding. Your current technology exposure is already above policy, and this would likely increase concentration."
- "Refresh the MSFT thesis. The saved dossier is older than 30 days and new estimate data is available."
- "Compare VTI and SCHB for broad-market exposure. Both appear relevant to your long-term plan, but BuildWealth should compare overlap, expense ratio, and current portfolio fit before you choose."
- "Do not make an investment recommendation yet. Your risk tolerance and cash reserve targets are missing, so BuildWealth cannot judge fit confidently."

Bad examples:

- "Buy NVDA."
- "MSFT is a good stock."
- "Sell AAPL now."
- "AI recommends adding this to your portfolio."

## No-Code Implementation Roadmap

### Phase 1: Research Boundary and Provider Governance

Goal: make OpenBB useful without coupling product logic to OpenBB internals.

Work:

- document OpenBB as a provider path, not the recommendation engine
- define provider metadata requirements
- inventory current research endpoints and provider dependencies
- define missing-data/degraded-provider behavior
- add license/provenance notes for OpenBB and provider extensions

Done when:

- BuildWealth can clearly explain what data came from which provider
- provider failure produces warnings instead of bad recommendations
- future providers can be added behind the same gateway concept

### Phase 2: Research Evidence Packets

Goal: standardize research outputs before generating new investment recommendations.

Work:

- define the evidence packet shape
- map current quote/history data into evidence packets
- add freshness and coverage quality
- migrate compare/dossier/watchlist data to consume or cite packets
- identify which evidence fields are required for different recommendation types
- expose evidence quality to Today, Copilot, and Inbox

Current progress:

- Today research readiness samples the top holding and watchlist symbols through evidence packets.
- Partial/degraded evidence now appears as a Today command-center warning or critical card before investment-fit advice is built on it.
- Today research readiness uses a bounded in-memory packet cache, reports cached research age, and exposes a refresh action that clears/rebuilds the sampled evidence.
- Watchlist ranking now consumes evidence packets first, preserves packet references/freshness/provider coverage on each row, and keeps legacy market metrics available for existing scoring/display paths.
- Research dossiers now cite evidence packets in the response and dossier markdown, so saved plan artifacts preserve packet id, provider, freshness, confidence, coverage, and blocking-gap context.
- Research compare rows now cite evidence packet id, provider, freshness, confidence, coverage score, and blocking gaps while preserving existing compare ranking fields.
- Saved research dossiers now expose thesis review metadata in v2 Research, and expired dossiers can generate review-only thesis refresh recommendations.
- Today research readiness now includes thesis-expiry caveats for saved dossiers and watchlist theses, material watchlist price-move warnings when a thesis reference price is available, policy-material-change thesis warnings from proposed review rows, and direct v2 thesis-review links when there is a single thesis action.

Done when:

- a symbol can produce a reusable evidence packet
- recommendations can cite packet freshness and provider coverage
- missing research data is visible as a confidence factor

### Phase 3: Portfolio-Fit Assessment

Goal: answer "does this fit me?" for a symbol or set of symbols.

Work:

- define fit statuses and fit reasons
- use current portfolio exposure and risk thresholds
- include cash reserve and profile readiness checks
- include active plan/time-horizon context where available
- call trade simulation when a proposed amount is supplied
- produce a next-step recommendation without buy/sell language

Current progress:

- The first contract and API route exist.
- Concentration conflicts, missing profile/cash/research context, and simulation-required next steps are covered.
- Plan/time-horizon context is included in the API, Copilot tool, and v2 Portfolio fit review.
- Tax-lot/account-location context is included in the API, v2 Portfolio fit review, Copilot fit cards, and generated investment/research recommendation evidence.

Done when:

- BuildWealth can explain why a candidate fits, conflicts, or needs more context
- fit assessment uses user context, not only market data
- the output can be reused by Copilot, Inbox, and Research

### Phase 4: Watchlist and Research Recommendation Generator

Goal: turn investment-fit signals into safe, ranked actions.

Work:

- generate recommendations for stale dossiers, stale watchlist research, concentration conflicts, promising comparison candidates, and missing profile context
- dedupe recommendations by symbol and signal
- include evidence packet references
- route generated rows through the existing factory review center
- keep actions phrased as review, compare, simulate, refresh, or update-profile

Current progress:

- `generator:research_thesis_expiration` creates deduped review-only rows for saved dossier artifacts whose thesis review window has expired.
- v2 Inbox routes thesis-expiration rows back to the saved dossier review surface instead of treating them as generic workflow rows.
- `generator:watchlist_research` can create review-only rows for stale watchlist theses and material price moves from a stored thesis reference price.
- Applying a `review_research_thesis` row now refreshes thesis metadata where possible: watchlist rows update `thesis_reviewed_at`, `thesis_expires_at`, and `thesis_reference_price_usd`; saved dossiers receive a thesis-review metadata section.
- Thesis review triggers now include policy material changes from current portfolio-fit context: cash-floor conflicts, asset-class exposure caps, and high-simplicity review gaps can create review-only thesis refresh rows for saved watchlist theses and current saved dossier artifacts.

Done when:

- watchlist/research signals can create reviewable Inbox rows
- rows include evidence, freshness, fit status, and next step
- personal investment policy can generate review-only research-confidence and tax-sensitive fit rows
- no generated recommendation uses direct trade language

### Phase 5: v2 Research and Portfolio Integration

Goal: make investment-fit visible where the user naturally works.

Work:

- add v2 watchlist/research surfaces or migrate the most important classic research flows
- show portfolio-fit summaries on candidate symbols
- add compare/dossier/simulate links from Inbox and Portfolio
- make research artifacts visible from Plan when saved
- expose stale research warnings in Today when important

Current progress:

- v2 Research has a packet-native evidence view at `#research?symbol=...`.
- v2 Research has a small-set compare view at `#research?compare=NVDA,MSFT` that calls the compare contract for ranking context while rendering each symbol through evidence packet cards.
- v2 Research has saved dossier lookup/detail at `#research?dossiers=1` and `#research?dossier=...`, with packet citations parsed from saved plan artifacts and linked back to packet evidence.
- Inbox investment/research rows now route research and compare links into v2 Research instead of the classic research route.
- v2 Portfolio fit review and Copilot investment-fit trace cards link evidence packet ids into v2 Research.
- Today research readiness and v2 Plan look-closer links now route saved dossier/thesis work into v2 Research rather than only broad classic artifact browsing.
- v2 Plan now owns the normal artifact/evidence path: saved research, scenario reports, decision packets, closure artifacts, and generic artifact links stay inside v2 Plan or v2 Research, with classic Plan retained only for advanced branch/withdrawal planning.

Done when:

- the user can move from Today or Inbox into research, simulation, and Copilot without falling into disconnected classic views
- investment-fit context is visible before the user acts

### Phase 6: Copilot Investment-Fit Workflows

Goal: make Copilot a grounded guide for investment questions.

Work:

- add or refine tools for fit assessment, compare, dossier lookup, and simulation
- update Copilot guidance to avoid direct buy/sell language
- make missing data and stale evidence explicit in answers
- let Copilot draft research/review recommendations
- render investment-fit traces in v2 Copilot

Current progress:

- Copilot can call the portfolio-fit assessment tool with plan/time-horizon, research evidence, portfolio exposure, profile readiness, cash runway, and optional simulation context.
- v2 Copilot renders `assess_portfolio_fit` results as investment-fit review cards instead of raw tool JSON.
- Focused investment-fit prompts from Inbox keep the discussion framed around fit review, research, comparison, simulation, or missing context, not hidden buy/sell advice.
- Copilot can draft proposed review-only investment/research Inbox rows from investment-fit discussions via `draft_investment_research_recommendation`.
- Today surfaces Copilot-drafted investment/research reviews as command-center cards linked back to the focused Inbox item.

Done when:

- Copilot can answer "does this fit me?" with cited BuildWealth context
- Copilot can create a reviewable next action instead of making hidden decisions
- Copilot refuses or redirects when context is insufficient

### Phase 7: Outcome Learning and Calibration

Goal: make investment recommendations improve over time.

Work:

- capture outcomes for research/investment recommendations (started: Copilot-drafted investment-fit rows now record process outcomes)
- track whether simulation/research/review actions were useful (started: useful review, insufficient evidence, deferred, acted elsewhere, and not useful)
- calibrate confidence for similar future recommendation classes (started: process outcomes feed source/type scoring calibration)
- show which investment recommendation types have historically helped (started: Today and Inbox now surface investment/research process calibration)
- keep outcome tracking separate from market performance chasing

Done when:

- outcome history affects ranking/confidence
- BuildWealth can distinguish useful decision processes from noisy signals
- the app learns without becoming an automatic trading system

## Prioritization Rules

1. Build fit assessment before stronger investment recommendations.
2. Build evidence packets before research-backed generators.
3. Prefer "review/compare/simulate" actions before "change allocation" actions.
4. Treat missing profile, cash, tax, or risk data as a first-class blocker.
5. Never let raw provider data bypass BuildWealth evidence and fit layers.
6. Prefer v2 surfaces for high-frequency research decisions.
7. Keep trade execution out of scope.

## Success Metrics

Near-term:

- every research-backed recommendation includes provider/freshness metadata
- watchlist research can identify stale or insufficient evidence
- Copilot can explain why context is insufficient for an investment-fit answer

Mid-term:

- investment-fit assessments include portfolio, plan, profile, and evidence context
- watchlist/research generators create safe reviewable recommendations
- v2 Inbox can route investment rows to compare, dossier, simulate, and Copilot flows

Long-term:

- BuildWealth consistently answers "does this fit me?" with inspectable evidence
- research-backed recommendations improve through outcome calibration
- market data providers remain swappable behind BuildWealth contracts
- no investment flow requires automatic trading or hidden AI decision-making

## Immediate Next Investment-Side Work

Do not start by adding direct buy/sell recommendation logic.

Recommended sequence:

1. Keep provider/freshness/coverage metadata explicit around OpenBB-backed research outputs as provider depth increases.
2. Continue migrating v2 research/portfolio surfaces away from classic fallbacks where high-frequency investment decisions happen.
3. Continue Personal Investment Policy by expanding beyond single-symbol exposure, research confidence, tax sensitivity, sector caps, symbol/sector restrictions, and account-location preferences into cash, asset-class, and simplicity preferences. Cash floor, asset-class exposure caps, and simplicity preference are now profile-backed and wired into portfolio-fit plus generated review-only watchlist/research rows.
4. Deepen account-location context later with account-type-specific contribution guidance and richer tax-policy preferences.

## Relationship to Existing Plans

This plan complements:

- `docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md`
- `docs/RECOMMENDATION_FACTORY_PLAN.md`
- `docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md`

The older roadmap already completed important research foundations, including compare, dossier, watchlist ranking, and research citation quality. This plan reframes the next phase around personal investment fit and safe recommendation loops.
