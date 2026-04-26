import test from 'node:test';
import assert from 'node:assert/strict';
import { renderFitResult, renderFitReview } from '../views/portfolio.js';

test('portfolio fit review renders safe empty state', () => {
  const markup = String(renderFitReview());

  assert.match(markup, /Fit review/);
  assert.match(markup, /Review fit/);
  assert.match(markup, /Ask whether a candidate belongs in this portfolio/);
});

test('portfolio fit result renders plan horizon and research evidence', () => {
  const markup = String(renderFitResult({
    symbol: 'VTI',
    fit_status: 'mixed',
    fit_score: 72,
    recommended_next_step: 'discuss_in_copilot',
    fit_reasons: ['Active plan horizon is long (25 years).'],
    fit_risks: ['Research evidence is partial.'],
    blocking_gaps: ['research:partial'],
    plan_impact: { time_horizon: 'long', years: 25 },
    evidence: { freshness_status: 'partial', confidence: 'medium' },
    portfolio_impact: { existing_position: false },
  }));

  assert.match(markup, /Mixed/);
  assert.match(markup, /72\/100/);
  assert.match(markup, /Discuss In Copilot/);
  assert.match(markup, /Long · 25y/);
  assert.match(markup, /partial · medium/);
  assert.match(markup, /Active plan horizon is long \(25 years\)\./);
  assert.match(markup, /research:partial/);
});
