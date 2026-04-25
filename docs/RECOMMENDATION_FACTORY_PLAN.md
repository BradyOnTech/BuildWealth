# Portfolio/Plan Signal to Recommendation Generator

## Goal

Build a Recommendation Factory that scans existing BuildWealth signals and automatically creates concrete, ranked, non-duplicative recommendations.

The product should move from showing financial data to actively proposing the most important next actions implied by that data.

This plugs into the existing recommendation system:

- ranked inbox
- pre-apply preview
- expected outcomes
- outcome tracking
- closure analytics
- learning-loop calibration

## First Slice Scope

Start with portfolio risk alerts to recommendations.

This is the cleanest first source because BuildWealth already computes portfolio risk alerts and risk thresholds. The first generator should cover:

- single holding concentration
- top holdings concentration
- asset class overexposure
- sector overexposure
- region overexposure
- low effective positions or high HHI

Example generated recommendation:

> Reduce AAPL concentration from 31% toward the 25% threshold. Consider trimming approximately $14,200 or redirecting new contributions away from AAPL until allocation normalizes.

## Generated Recommendation Payload

Generated recommendations should reuse the existing recommendation row model and add richer `action_payload` metadata.

```json
{
  "generator": {
    "id": "portfolio_risk_recommendation_factory",
    "version": "v1",
    "generated_at": "2026-04-25T00:00:00Z",
    "signal_key": "single_holding:AAPL",
    "signal_type": "portfolio_risk_alert",
    "dedupe_key": "portfolio_risk_alert:single_holding:AAPL",
    "severity": "breach"
  },
  "evidence": {
    "summary": "AAPL is 31.2% of invested holdings, above the 25.0% threshold.",
    "data_keys": ["portfolio.holdings", "portfolio.risk_alerts"],
    "snapshot_as_of": "2026-04-25T00:00:00Z"
  },
  "suggested_action": {
    "kind": "reduce_concentration",
    "symbol": "AAPL",
    "current_pct": 31.2,
    "target_pct": 25.0,
    "estimated_trim_usd": 14200.0
  },
  "expected_outcome": {
    "expected_delta_risk_score": -1,
    "expected_allocation_after_pct": 25.0
  }
}
```

## Backend Design

Add a service:

`services/orchestrator/src/buildwealth_orchestrator/services/recommendation_factory.py`

Responsibilities:

- accept current portfolio holdings and risk-alert payloads
- inspect active risk alerts
- generate candidate recommendation payloads
- calculate stable dedupe keys
- skip existing active duplicates
- create recommendations through `RecommendationInbox`

Core function:

```python
generate_portfolio_risk_recommendations(
    holdings_payload: dict,
    existing_recommendations: list[dict],
    now: datetime | None = None,
    dry_run: bool = True,
    limit: int = 10,
) -> RecommendationFactoryResult
```

## API Design

Add:

`POST /api/recommendations/generate/portfolio-risk`

Request options:

- `dry_run: bool = true`
- `plan_id: str | None = None`
- `limit: int = 10`

Behavior:

- dry-run returns candidates but does not create rows
- apply mode creates recommendation rows
- dedupe prevents repeated active recommendations for the same risk signal

## Dedupe Rules

Skip generated recommendations when:

- an active `proposed` recommendation already has the same `generator.dedupe_key`
- an unresolved active recommendation exists for the same risk signal
- the risk alert is no longer active

Dedupe key examples:

- `portfolio_risk_alert:single_holding:AAPL`
- `portfolio_risk_alert:top3_holdings`
- `portfolio_risk_alert:sector:technology`
- `portfolio_risk_alert:asset_class:equity`
- `portfolio_risk_alert:hhi`

## Recommendation Quality Rules

Generated recommendations must be specific.

Bad:

> Review concentration risk.

Good:

> AAPL is 31.2% of invested holdings, above your 25.0% threshold. Consider trimming about $14,200 or directing new contributions elsewhere.

Each recommendation should include:

- what triggered it
- current value
- threshold
- suggested direction
- estimated action amount when possible
- why it matters

## UI Plan

After backend behavior is solid, add a Recommendation Inbox generator panel.

Controls:

- `Preview Portfolio Risk Recommendations`
- `Create Recommendations`
- dry-run result list
- generated/skipped summary

UI states:

- no risk alerts: no portfolio risk signals need recommendations
- preview candidates: show title, detail, severity, dedupe status
- created: show created count and reload inbox
- skipped: show skipped reason

## Ranking Integration

Generated recommendations should naturally flow into current ranking.

Set:

- `priority`: `breach` to `high`, `watch` to `medium`, informational to `low`
- `recommendation_type`: `workflow_action`
- `source`: `generator:portfolio_risk`
- `action_payload.evidence`: structured enough to boost confidence
- `action_payload.generator`: structured enough for explainability and dedupe

## Tests

Unit tests:

- generates recommendation for single holding breach
- generates recommendation for top holdings concentration breach
- skips duplicate active recommendation
- dry-run does not persist
- estimated trim amount is calculated correctly
- severity maps to priority

API tests:

- dry-run returns candidates
- apply mode creates rows
- repeated apply does not duplicate
- created recommendations appear in ranked inbox

UI smoke tests:

- preview button
- create button
- generator summary element
- generated candidate list element

## Rollout

### Slice 1: Backend factory dry-run

- Add service
- Add schema
- Add dry-run endpoint
- Add unit/API tests

### Slice 2: Apply mode and dedupe

- Persist generated recommendations
- Add duplicate detection
- Add repeat-generation tests

### Slice 3: UI preview/create panel

- Add Recommendation Inbox controls
- Render candidates/skipped reasons
- Reload recommendations after create

### Slice 4: Polish and docs

- Update roadmap/product docs
- Add concise README/design note if useful
- Run full suite

## Not Yet

Do not start with:

- fully automatic background generation
- trade execution
- rebalancing optimizer
- tax-aware sell recommendations
- research-driven generators

Those are powerful, but too easy to make noisy or overconfident before the recommendation factory is proven.

## Definition of Done

- User can preview portfolio-risk-generated recommendations
- User can create them with one click
- Duplicate recommendations are skipped
- Recommendations are specific and evidence-backed
- Generated recommendations rank correctly in the inbox
- Existing outcome tracking and learning-loop calibration work with them
- Full test suite passes
