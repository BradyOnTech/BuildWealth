# Feature note: "How am I doing?" — benchmarking against the average / the top

**Recorded:** 2026-07-07, from product discussion. Not scheduled; this note
exists so the idea survives with its design constraints attached.

## The idea

Show the user where they stand relative to others: net worth, savings rate,
diversification, fees — "versus the average household" and "versus the top."
Percentile context answers the question normal people actually bring to
money ("am I okay?") and is motivating in a way absolute numbers never are.

## The honest constraints on the peer-data version

1. **Cold start.** Comparisons against our own users need a user base;
   the user base comes from features that don't need one. Peer percentiles
   are a scale-stage feature, not a growth-stage one.
2. **Privacy ceiling.** Aggregating users' financial data — even anonymized —
   is the most sensitive thing this product could ever do. Non-negotiables
   when the time comes: explicit opt-in (off by default), k-anonymity
   minimums per bracket (no bracket renders with fewer than ~50 contributors),
   aggregation server-side with no per-user retention beyond the aggregate,
   differential-privacy noise on published percentiles, and a pass through
   the legal/privacy review that gates the public launch anyway.
3. **Comparability.** Raw averages mislead (age and income dominate).
   Brackets must be at least age × income band, or the feature tells a
   22-year-old they're "behind" retirees.

## The version buildable NOW (no users, no privacy risk)

The Federal Reserve's **Survey of Consumer Finances** publishes net worth
and savings percentiles by age bracket (and income band); BLS Consumer
Expenditure Survey covers spending patterns. A local-first
"versus the average American household your age" needs only:

- a small curated dataset (seed-style JSON, cited, with survey year),
- household age from the profile (household_members exist),
- a panel/verdict line: "Median net worth for your age bracket is ~$X —
  you're around the Yth percentile," with the honest caveat that survey
  data lags a few years and includes home equity (map to our
  invested/housing split carefully).

This ships standalone, and the peer-data version later replaces the data
source without changing the product surface.

## Sequencing

1. SCF-based local benchmarking panel (buildable any time; no dependencies).
2. Peer percentiles: only after hosted multi-user launch + privacy review,
   opt-in, k-anonymous, DP-noised. The UI from step 1 carries over.
