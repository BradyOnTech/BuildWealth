import test from 'node:test';
import assert from 'node:assert/strict';
import { renderFitResult, renderFitReview } from '../views/portfolio.js';

test('portfolio fit review renders safe empty state', () => {
  const markup = String(renderFitReview());

  assert.match(markup, /Fit review/);
  assert.match(markup, /Review fit/);
  assert.match(markup, /Ask whether a candidate belongs in this portfolio/);
});

test('portfolio fit review can be prefilled from inbox route', () => {
  const markup = String(renderFitReview(null, { initialSymbol: 'nvda' }));

  assert.match(markup, /Fit review: NVDA/);
  assert.match(markup, /value="NVDA"/);
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
    portfolio_impact: {
      existing_position: true,
      current_weight_pct: 12.5,
      account_location: {
        status: 'known',
        tax_lot_coverage: 'known',
        tax_treatments: ['taxable', 'tax_free'],
        accounts: [
          {
            account_name: 'Taxable Brokerage',
            tax_treatment: 'taxable',
            unrealized_gain_loss_usd: 1250,
            lot_term_mix: 'mixed',
          },
        ],
      },
    },
  }));

  assert.match(markup, /Mixed/);
  assert.match(markup, /72\/100/);
  assert.match(markup, /Discuss In Copilot/);
  assert.match(markup, /Long · 25y/);
  assert.match(markup, /partial · medium/);
  assert.match(markup, /12\.5% held/);
  assert.match(markup, /Taxable, Tax Free/);
  assert.match(markup, /Taxable Brokerage · Taxable · \$1,250 gain\/loss · Mixed lots/);
  assert.match(markup, /Active plan horizon is long \(25 years\)\./);
  assert.match(markup, /research:partial/);
});
