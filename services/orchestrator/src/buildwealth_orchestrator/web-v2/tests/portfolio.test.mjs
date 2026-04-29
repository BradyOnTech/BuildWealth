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
    evidence: {
      freshness_status: 'partial',
      confidence: 'medium',
      packet_id: 'research-evidence:yfinance:VTI:6mo:1d',
    },
    portfolio_impact: {
      existing_position: true,
      current_weight_pct: 12.5,
      single_holding_max_pct: 10,
      single_holding_policy_source: 'profile.investment_policy',
      candidate_sector: 'Technology',
      sector_weight_after_trade_pct: 31.43,
      sector_max_pct: 30,
      sector_policy_source: 'profile.investment_policy',
      investment_policy: {
        minimum_research_confidence: 'high',
        tax_sensitivity: 'high',
        max_sector_exposure_pct: 30,
        restricted_symbols: ['NVDA'],
        restricted_sectors: ['Crypto'],
      },
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
  assert.match(markup, /10% · Personal policy/);
  assert.match(markup, /Research High · Tax High · Sector cap 30% · Avoid NVDA · Avoid Crypto/);
  assert.match(markup, /Technology 31\.4% · cap 30%/);
  assert.match(markup, /Taxable, Tax Free/);
  assert.match(markup, /Taxable Brokerage · Taxable · \$1,250 gain\/loss · Mixed lots/);
  assert.match(markup, /href="#research\?symbol=VTI&amp;packet=research-evidence%3Ayfinance%3AVTI%3A6mo%3A1d"/);
  assert.match(markup, /Active plan horizon is long \(25 years\)\./);
  assert.match(markup, /research:partial/);
});
