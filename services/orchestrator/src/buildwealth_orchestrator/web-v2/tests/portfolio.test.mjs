import test from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../lib/api.js';
import { renderAnalytics } from '../views/portfolio/analytics.js';
import { renderFitResult, renderFitReview, renderLookCloser } from '../views/portfolio.js';

test('portfolio fit review renders safe empty state', () => {
  const markup = String(renderFitReview());

  assert.match(markup, /Fit review/);
  assert.match(markup, /Review fit/);
  assert.match(markup, /Proposed account/);
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
      proposed_account: {
        account_name: 'Taxable Brokerage',
        tax_treatment: 'taxable',
        policy_preferred_treatments: ['tax_free'],
      },
      contribution_guidance: {
        status: 'review',
        account_id: 'taxable',
        account_type: 'taxableBrokerage',
        tax_treatment: 'taxable',
        recommended_review: 'review_account_location',
        review_reasons: ['Proposed contribution account conflicts with preferred account-location policy.'],
      },
      investment_policy: {
        minimum_research_confidence: 'high',
        minimum_cash_runway_months: 9,
        max_asset_class_exposure_pct: { equity: 80 },
        simplicity_preference: 'high',
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
  assert.match(markup, /Research High · Cash floor 9 mo · Asset cap Equity 80% · Simplicity High · Tax High · Sector cap 30% · Avoid NVDA · Avoid Crypto/);
  assert.match(markup, /Technology 31\.4% · cap 30%/);
  assert.match(markup, /Taxable Brokerage · Taxable · prefers Tax Free/);
  assert.match(markup, /Contribution fit/);
  assert.match(markup, /Review · Taxable · Review Account Location · Proposed contribution account conflicts with preferred account-location policy\./);
  assert.match(markup, /Taxable, Tax Free/);
  assert.match(markup, /Taxable Brokerage · Taxable · \$1,250 gain\/loss · Mixed lots/);
  assert.match(markup, /href="#research\?symbol=VTI&amp;packet=research-evidence%3Ayfinance%3AVTI%3A6mo%3A1d"/);
  assert.match(markup, /Active plan horizon is long \(25 years\)\./);
  assert.match(markup, /research:partial/);
});

test('portfolio maintenance links stay inside native v2 sections', () => {
  const markup = String(renderLookCloser('transactions', {
    section: 'transactions',
    rows: [
      {
        date: '2026-01-02',
        symbol: 'VTI',
        action: 'BUY',
        quantity: 2,
        unit_price: 250,
        account: 'Taxable',
      },
    ],
  }));

  assert.match(markup, /#portfolio\?section=transactions/);
  assert.match(markup, /Portfolio maintenance/);
  assert.match(markup, /Recent portfolio activity/);
  assert.match(markup, /VTI/);
  assert.doesNotMatch(markup, /classic/i);
});

test('portfolio asset registry renders native review status', () => {
  const markup = String(renderLookCloser('assets', {
    section: 'assets',
    rows: [
      {
        quality_label: 'Needs review',
        symbol: 'ODD1',
        name: 'Odd Asset',
        asset_class: '',
        asset_type: '',
        current_value: null,
        current_price: null,
        tags: ['Custom'],
      },
    ],
  }));

  assert.match(markup, /Investments &amp; Assets/);
  assert.match(markup, /single searchable registry/);
  assert.match(markup, /Search assets/);
  assert.match(markup, /Status/);
  assert.match(markup, /Needs review/);
  assert.match(markup, /ODD1/);
  assert.match(markup, /Custom/);
  assert.doesNotMatch(markup, /classic/i);
});

test('portfolio audit renders import and follow-through findings', () => {
  const markup = String(renderLookCloser('audit', {
    section: 'audit',
    payload: {
      status: 'attention',
      summary: {
        open_findings: 2,
        import_reports: 1,
        pending_inbox_items: 1,
      },
      findings: [
        {
          id: 'import_rows_need_review',
          category: 'Imports',
          title: 'Imported rows need review',
          detail: 'Some rows from recent imports were not safe to rely on automatically.',
          severity: 'high',
          status: 'open',
          count: 1,
          href: '#import-sync',
          action_label: 'Open import reports',
        },
      ],
      recent_reports: [
        {
          created_at: '2026-05-09T12:00:00+00:00',
          source_file_name: 'broker.csv',
          imported_activities: 2,
          unresolved_count: 1,
          duplicate_count: 0,
        },
      ],
    },
  }));

  assert.match(markup, /Portfolio Audit/);
  assert.match(markup, /Open items/);
  assert.match(markup, /Imported rows need review/);
  assert.match(markup, /Recent import reports/);
  assert.match(markup, /broker\.csv/);
  assert.doesNotMatch(markup, /classic/i);
});

test('portfolio guardrails render editable plain-language risk limits', () => {
  const markup = String(renderLookCloser('risk-policy', {
    section: 'risk-policy',
    payload: {
      thresholds: {
        single_holding_max_pct: 25,
        top3_holdings_max_pct: 60,
        account_max_pct: 50,
        asset_class_max_pct: 82,
        sector_max_pct: 35,
        region_max_pct: 69,
        hhi_max: 0.2,
        effective_positions_min: 5,
      },
    },
    riskAlerts: {
      status: 'warning',
      breach_count: 1,
      watch_count: 1,
      alerts: [
        {
          state: 'breach',
          severity: 'medium',
          label: 'Largest sector concentration',
          unit: 'pct',
          direction: 'max',
          observed: 40,
          threshold: 35,
          recommendation: 'Use new purchases to broaden sector exposure.',
        },
      ],
    },
  }));

  assert.match(markup, /Portfolio Guardrails/);
  assert.match(markup, /How BuildWealth reads this/);
  assert.match(markup, /One investment max/);
  assert.match(markup, /Top 3 investments max/);
  assert.match(markup, /One investment type max/);
  assert.match(markup, /Concentration score max/);
  assert.match(markup, /Minimum spread/);
  assert.match(markup, /Save guardrails/);
  assert.match(markup, /High/);
  assert.match(markup, /Far past the limit/);
  assert.match(markup, /Largest sector concentration/);
  assert.match(markup, /40% now · 35% limit/);
  assert.doesNotMatch(markup, /Ghostfolio/);
  assert.doesNotMatch(markup, /Ignidash/);
  assert.doesNotMatch(markup, /sidecar/);
  assert.doesNotMatch(markup, /classic/i);
});

test('portfolio analytics renders performance benchmarks and contributors', () => {
  const markup = String(renderAnalytics({
    status: 'ready',
    performance: {
      total_return_usd: 1250,
      price_return_usd: 1000,
      income_return_usd: 250,
      twr_annualized_return_pct: 12.4,
      xirr_annualized_return_pct: 10.2,
      net_contributions: 5000,
    },
    benchmark: {
      status: 'ready',
      portfolio_return_pct: 12.4,
      max_drawdown_pct: -3.1,
      rows: [{ symbol: 'SPY', benchmark_return_pct: 8.2, alpha_pct: 4.2 }],
    },
    attribution: {
      status: 'ready',
      contributors: [{ symbol: 'VTI', name: 'Total Market', total_return: 1250, contribution_pct: 100 }],
      detractors: [],
    },
    warnings: ['Benchmark service disabled; using local fallback'],
  }));

  assert.match(markup, /Performance/);
  assert.match(markup, /Total return/);
  assert.match(markup, /Benchmarks/);
  assert.match(markup, /SPY/);
  assert.match(markup, /alpha/);
  assert.match(markup, /Return contributors/);
  assert.match(markup, /VTI/);
  assert.doesNotMatch(markup, /Ghostfolio/);
  assert.doesNotMatch(markup, /sidecar/);
});

test('api portfolio risk policy helpers call native guardrail endpoint', async (t) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ thresholds: {} }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await api.portfolioRiskPolicy();
  await api.updatePortfolioRiskPolicy({ single_holding_max_pct: 30 });

  assert.equal(calls[0].url, '/api/portfolio/risk-policy');
  assert.equal(calls[1].url, '/api/portfolio/risk-policy');
  assert.equal(calls[1].options.method, 'PUT');
  assert.equal(JSON.parse(calls[1].options.body).single_holding_max_pct, 30);
});

test('api portfolio analytics helper calls native analytics endpoint', async (t) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    return new Response(JSON.stringify({ status: 'ready' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await api.portfolioAnalytics({ symbols: 'SPY,VTI', limit: 10, topN: 3 });

  assert.match(calls[0], /\/api\/portfolio\/analytics\?/);
  assert.match(calls[0], /symbols=SPY%2CVTI/);
  assert.match(calls[0], /limit=10/);
  assert.match(calls[0], /top_n=3/);
});
