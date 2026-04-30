import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, extname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { test } from '@playwright/test';

const currentDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(currentDir, '..');

const CONTENT_TYPES = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
};

const jsonResponse = (body, status = 200) => ({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

async function staticResponse(pathname) {
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/static-v2\//, '');
  const filePath = resolve(webRoot, relativePath);
  const distance = relative(webRoot, filePath);
  assert.ok(
    distance && !distance.startsWith('..') && !isAbsolute(distance),
    `refusing to serve path outside web root: ${pathname}`,
  );
  return {
    status: 200,
    contentType: CONTENT_TYPES[extname(filePath)] || 'text/plain',
    body: await readFile(filePath, 'utf8'),
  };
}

test('generated investment recommendation routes through Inbox, Portfolio, and Copilot', async ({ page }) => {
  let recommendationCreated = false;
  let sweepCreatePayload = null;
  let fitRequestPayload = null;
  let researchPacketPayload = null;
  let comparePayload = null;

  const investmentRecommendation = () => ({
    id: 'rec-invest',
    title: 'Review why NVDA does not currently fit',
    detail: 'NVDA currently conflicts with portfolio-fit checks. Review the fit risks before taking action.',
    priority: 'high',
    status: 'proposed',
    source: 'generator:watchlist_research',
    recommendation_type: 'workflow_action',
    created_at: '2026-04-26T12:00:00Z',
    updated_at: '2026-04-26T12:00:00Z',
    action_payload: {
      generator: {
        signal_type: 'watchlist_research',
        signal_key: 'fit_conflict',
      },
      evidence: {
        symbol: 'NVDA',
        provider: 'yfinance',
        freshness_status: 'fresh',
        confidence: 'high',
        coverage_score: 100,
        fit_status: 'does_not_fit',
        fit_score: 25,
        fit_risks: ['Simulated trade worsens concentration risk.'],
        research_evidence_packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
      },
      suggested_action: {
        kind: 'review_portfolio_fit',
        symbol: 'NVDA',
        fit_status: 'does_not_fit',
        next_step: 'review_concentration',
      },
      quality: {
        actionability: 'review_only',
        confidence_level: 'medium',
        freshness_status: 'fresh',
        reversibility: 'high',
        impact: { level: 'high' },
        blocking_context: [],
        decision_grade: true,
      },
    },
    score: {
      total: 91,
      rank: 1,
      reasons: ['Fit assessment found a concentration conflict.'],
    },
  });

  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.hostname !== 'buildwealth-v2.test') {
      await route.abort();
      return;
    }

    if (url.pathname === '/' || url.pathname.startsWith('/static-v2/')) {
      await route.fulfill(await staticResponse(url.pathname));
      return;
    }

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan', is_active: true }]));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      const requestedStatus = url.searchParams.get('status') || 'proposed';
      await route.fulfill(jsonResponse(recommendationCreated && requestedStatus === 'proposed' ? [investmentRecommendation()] : []));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/recommendations/generate/run-all' && request.method() === 'POST') {
      const payload = request.postDataJSON();
      if (payload.dry_run) {
        await route.fulfill(jsonResponse({
          generated_count: 1,
          skipped_count: 0,
          factories: {
            watchlist_research: {
              generated_count: 1,
              skipped_count: 0,
              candidates: [investmentRecommendation()],
              created: [],
              skipped: [],
              dry_run: true,
            },
          },
          dry_run: true,
        }));
        return;
      }
      sweepCreatePayload = payload;
      recommendationCreated = true;
      await route.fulfill(jsonResponse({
        generated_count: 1,
        skipped_count: 0,
        factories: {
          watchlist_research: {
            generated_count: 1,
            skipped_count: 0,
            candidates: [],
            created: [investmentRecommendation()],
            skipped: [],
            dry_run: false,
          },
        },
        dry_run: false,
      }));
      return;
    }

    if (url.pathname === '/api/portfolio/holdings') {
      await route.fulfill(jsonResponse({
        updated_at: '2026-04-26T12:00:00Z',
        total_value: 100000,
        total_cash: 5000,
        holdings: {
          'default:AAPL': { symbol: 'AAPL', name: 'Apple', current_value: 40000, allocation_percent: 40 },
          'default:VTI': { symbol: 'VTI', name: 'Total Market', current_value: 60000, allocation_percent: 60 },
        },
        risk_alerts: [],
      }));
      return;
    }

    if (url.pathname === '/api/portfolio/fit-assessment' && request.method() === 'POST') {
      fitRequestPayload = request.postDataJSON();
      assert.equal(fitRequestPayload.symbol, 'NVDA');
      const symbol = String(fitRequestPayload.symbol).toUpperCase();
      await route.fulfill(jsonResponse({
        symbol,
        fit_status: 'does_not_fit',
        fit_score: 25,
        fit_reasons: ['Active plan horizon is long (25 years).'],
        fit_risks: [`${symbol} would worsen concentration risk.`],
        blocking_gaps: ['concentration'],
        portfolio_impact: { existing_position: false },
        plan_impact: { time_horizon: 'long', years: 25 },
        evidence: {
          freshness_status: 'fresh',
          confidence: 'high',
          packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
        },
        simulation_required: false,
        recommended_next_step: 'review_concentration',
      }));
      return;
    }

    if (url.pathname === '/api/research/evidence-packet' && request.method() === 'POST') {
      researchPacketPayload = request.postDataJSON();
      const symbol = String(researchPacketPayload.symbol || '').toUpperCase();
      assert.ok(['NVDA', 'MSFT'].includes(symbol));
      await route.fulfill(jsonResponse({
        packet_id: `research-evidence:yfinance:${symbol}:6mo:1d`,
        symbol,
        name: symbol === 'NVDA' ? 'NVIDIA' : 'Microsoft',
        provider: 'yfinance',
        period: '6mo',
        interval: '1d',
        generated_at: '2026-04-26T12:00:00Z',
        coverage: {
          quote_available: true,
          history_available: true,
          provider_status: 'available',
          endpoints_attempted: ['quote', 'price_history'],
          warnings: [],
        },
        freshness: { status: 'fresh', quote_as_of: '2026-04-26T12:00:00Z' },
        metrics: {
          last_price: symbol === 'NVDA' ? 875.42 : 410.18,
          period_change_pct: symbol === 'NVDA' ? 12.4 : 4.2,
          volatility_pct: symbol === 'NVDA' ? 28.7 : 19.1,
        },
        risk: { drawdown_from_high_pct: symbol === 'NVDA' ? -8.2 : -3.1 },
        quality: { confidence: 'high', coverage_score: 100, blocking_gaps: [] },
        provenance: { warnings: [] },
      }));
      return;
    }

    if (url.pathname === '/api/research/compare' && request.method() === 'POST') {
      comparePayload = request.postDataJSON();
      assert.deepEqual(comparePayload.symbols, ['NVDA', 'MSFT']);
      await route.fulfill(jsonResponse({
        provider: 'yfinance',
        period: '6mo',
        interval: '1d',
        generated_at: '2026-04-26T12:00:00Z',
        symbols: ['NVDA', 'MSFT'],
        summary: {
          requested_symbols: 2,
          compared_symbols: 2,
          available_symbols: 2,
          baseline_symbol: 'NVDA',
          ranked_symbols: ['NVDA', 'MSFT'],
          best_period_return_symbol: 'NVDA',
          worst_period_return_symbol: 'MSFT',
          highest_volatility_symbol: 'NVDA',
          lowest_volatility_symbol: 'MSFT',
          baseline_relative_return_pct: { NVDA: 0, MSFT: -8.2 },
        },
        items: [
          {
            symbol: 'NVDA',
            available: true,
            message: 'Research data available.',
            rank: 1,
            score: 84,
            last_price: 875.42,
            period_change_pct: 12.4,
            volatility_pct: 28.7,
            quote_records: 1,
            history_records: 120,
            research_evidence_packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
            research_provider: 'yfinance',
            research_freshness_status: 'fresh',
            research_confidence: 'high',
            research_coverage_score: 100,
            research_blocking_gaps: [],
          },
          {
            symbol: 'MSFT',
            available: true,
            message: 'Research data available.',
            rank: 2,
            score: 71,
            last_price: 410.18,
            period_change_pct: 4.2,
            volatility_pct: 19.1,
            quote_records: 1,
            history_records: 120,
            research_evidence_packet_id: 'research-evidence:yfinance:MSFT:6mo:1d',
            research_provider: 'yfinance',
            research_freshness_status: 'fresh',
            research_confidence: 'high',
            research_coverage_score: 100,
            research_blocking_gaps: [],
          },
        ],
        warnings: [],
      }));
      return;
    }

    if (url.pathname === '/api/research/dossiers') {
      await route.fulfill(jsonResponse({
        plan_id: 'plan-1',
        count: 1,
        items: [
          {
            artifact_id: 'artifact-dossier',
            file_name: '2026-research-dossier-nvda-msft.md',
            title: 'Research Dossier - NVDA vs MSFT',
            created_at: '2026-04-26T12:00:00Z',
            plan_id: 'plan-1',
            symbols: ['NVDA', 'MSFT'],
            content_preview: [
              '## Evidence Packets',
              '',
              '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
              '| --- | --- | --- | --- | --- | ---: | --- |',
              '| NVDA | research-evidence:yfinance:NVDA:6mo:1d | yfinance | fresh | high | 100% | none |',
            ].join('\n'),
          },
        ],
        warnings: [],
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/artifacts/artifact-dossier') {
      await route.fulfill(jsonResponse({
        id: 'artifact-dossier',
        file_name: '2026-research-dossier-nvda-msft.md',
        title: 'Research Dossier - NVDA vs MSFT',
        created_at: '2026-04-26T12:00:00Z',
        content: [
          '# Research Dossier: NVDA vs MSFT',
          '',
          '## Thesis',
          '',
          'Compare AI infrastructure exposure.',
          '',
          '## Evidence Packets',
          '',
          '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
          '| --- | --- | --- | --- | --- | ---: | --- |',
          '| NVDA | research-evidence:yfinance:NVDA:6mo:1d | yfinance | fresh | high | 100% | none |',
          '| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | fresh | high | 100% | none |',
        ].join('\n'),
      }));
      return;
    }

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({ profile_readiness: { status: 'ready', completion_percent: 100 }, steps: [] }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.getByRole('button', { name: /Sweep for new suggestions/ }).click();
  await page.getByText('watchlist research').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /Create 1 suggestion/ }).click();

  assert.equal(sweepCreatePayload.dry_run, false);
  await page.getByText('Review why NVDA does not currently fit').waitFor({ state: 'visible' });
  await page.getByText('Investment-fit route').waitFor({ state: 'visible' });
  await page.getByText('symbol NVDA · fresh evidence · via yfinance · does not fit fit').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Research →', exact: true }).click();
  await page.waitForURL('**/#research?symbol=NVDA&packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d');
  await page.getByText('Evidence packet').waitFor({ state: 'visible' });
  await page.getByText('NVIDIA').first().waitFor({ state: 'visible' });
  assert.equal(researchPacketPayload.symbol, 'NVDA');

  await page.goto('http://buildwealth-v2.test/#research?compare=NVDA,MSFT');
  await page.getByText('Compare evidence').waitFor({ state: 'visible' });
  await page.getByText('NVDA / MSFT').waitFor({ state: 'visible' });
  await page.getByText('Rank 1').waitFor({ state: 'visible' });
  await page.getByText('Microsoft').waitFor({ state: 'visible' });
  assert.deepEqual(comparePayload.symbols, ['NVDA', 'MSFT']);

  await page.goto('http://buildwealth-v2.test/#research?dossiers=1');
  await page.getByText('Research dossiers').waitFor({ state: 'visible' });
  await page.getByText('Research Dossier - NVDA vs MSFT').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /Open dossier/ }).click();
  await page.waitForURL('**/#research?dossier=artifact-dossier&plan=plan-1');
  await page.getByText('Dossier detail').waitFor({ state: 'visible' });
  await page.getByText('Packet citations').waitFor({ state: 'visible' });
  await page.getByText('Compare AI infrastructure exposure.').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /research-evidence:yfinance:NVDA:6mo:1d/ }).click();
  await page.waitForURL('**/#research?symbol=NVDA&packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d');

  await page.goto('http://buildwealth-v2.test/#inbox?focus=rec-invest');
  await page.getByRole('link', { name: /Review fit/ }).first().click();
  await page.waitForURL('**/#portfolio?fit=NVDA&focus=rec-invest');
  await page.locator('input[name="symbol"]').waitFor({ state: 'visible' });
  await assertInputValue(page, 'input[name="symbol"]', 'NVDA');
  await page.getByText('Does Not Fit').waitFor({ state: 'visible' });
  await page.getByText('NVDA would worsen concentration risk.').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /Open evidence/ }).click();
  await page.waitForURL('**/#research?symbol=NVDA&packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d');
  await page.getByText('Evidence packet').waitFor({ state: 'visible' });
  assert.equal(fitRequestPayload.symbol, 'NVDA');

  await page.goto('http://buildwealth-v2.test/#inbox?focus=rec-invest');
  await page.getByText('Investment-fit route').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Copilot →', exact: true }).click();
  await page.waitForURL('**/#copilot?focus=rec-invest&intent=investment-fit');
  await page.locator('#composer-textarea').waitFor({ state: 'visible' });

  const draft = await page.locator('#composer-textarea').inputValue();
  assert.match(draft, /Review investment-fit recommendation rec-invest with me\./);
  assert.match(draft, /provider freshness/);
  assert.match(draft, /Do not give hidden buy\/sell advice/);
});

test('generated contribution account recommendation routes through fit review and Copilot', async ({ page }) => {
  let recommendationCreated = false;
  let sweepCreatePayload = null;
  let fitRequestPayload = null;

  const contributionRecommendation = () => ({
    id: 'rec-contribution-account',
    title: 'Review VTI contribution account fit',
    detail: 'VTI has contribution-account fit context to review under the personal investment policy (taxable). Review account placement before changing contribution routing or exposure.',
    priority: 'medium',
    status: 'proposed',
    source: 'generator:watchlist_research',
    recommendation_type: 'workflow_action',
    created_at: '2026-04-30T12:00:00Z',
    updated_at: '2026-04-30T12:00:00Z',
    action_payload: {
      generator: {
        signal_type: 'watchlist_research',
        signal_key: 'policy_contribution_account',
      },
      evidence: {
        symbol: 'VTI',
        provider: 'yfinance',
        freshness_status: 'fresh',
        confidence: 'high',
        coverage_score: 100,
        fit_status: 'mixed',
        fit_score: 56,
        fit_risks: ['Personal tax sensitivity is high; taxable contribution placement should be reviewed.'],
        fit_blocking_gaps: ['tax:contribution_account_policy', 'tax:account_location_policy'],
        research_evidence_packet_id: 'research-evidence:yfinance:VTI:6mo:1d',
        contribution_guidance: {
          status: 'review',
          account_id: 'taxable',
          account_type: 'taxableBrokerage',
          tax_treatment: 'taxable',
          policy_conflicts: ['tax:account_location_policy', 'tax:policy_review'],
          review_reasons: [
            'Proposed contribution account conflicts with preferred account-location policy.',
            'Personal tax sensitivity makes this account treatment worth reviewing.',
          ],
          recommended_review: 'review_account_location',
        },
      },
      suggested_action: {
        kind: 'review_portfolio_fit',
        symbol: 'VTI',
        fit_status: 'mixed',
        next_step: 'review_account_location',
        policy_gap: 'tax:contribution_account_policy',
      },
      quality: {
        actionability: 'review_only',
        confidence_level: 'medium',
        freshness_status: 'fresh',
        reversibility: 'high',
        impact: { level: 'medium' },
        blocking_context: ['tax.contribution_account_policy'],
        decision_grade: false,
      },
    },
    score: {
      total: 82,
      rank: 1,
      reasons: ['Account-location policy should be reviewed before changing contribution routing.'],
    },
  });

  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.hostname !== 'buildwealth-v2.test') {
      await route.abort();
      return;
    }

    if (url.pathname === '/' || url.pathname.startsWith('/static-v2/')) {
      await route.fulfill(await staticResponse(url.pathname));
      return;
    }

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan', is_active: true }]));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      const requestedStatus = url.searchParams.get('status') || 'proposed';
      await route.fulfill(jsonResponse(recommendationCreated && requestedStatus === 'proposed' ? [contributionRecommendation()] : []));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/recommendations/generate/run-all' && request.method() === 'POST') {
      const payload = request.postDataJSON();
      if (payload.dry_run) {
        await route.fulfill(jsonResponse({
          generated_count: 1,
          skipped_count: 0,
          factories: {
            watchlist_research: {
              generated_count: 1,
              skipped_count: 0,
              candidates: [contributionRecommendation()],
              created: [],
              skipped: [],
              dry_run: true,
            },
          },
          dry_run: true,
        }));
        return;
      }
      sweepCreatePayload = payload;
      recommendationCreated = true;
      await route.fulfill(jsonResponse({
        generated_count: 1,
        skipped_count: 0,
        factories: {
          watchlist_research: {
            generated_count: 1,
            skipped_count: 0,
            candidates: [],
            created: [contributionRecommendation()],
            skipped: [],
            dry_run: false,
          },
        },
        dry_run: false,
      }));
      return;
    }

    if (url.pathname === '/api/portfolio/holdings') {
      await route.fulfill(jsonResponse({
        updated_at: '2026-04-30T12:00:00Z',
        total_value: 100000,
        total_cash: 25000,
        holdings: {
          'taxable:VTI': { symbol: 'VTI', name: 'Total Market', current_value: 60000, allocation_percent: 60 },
          'roth:BND': { symbol: 'BND', name: 'Bond Market', current_value: 40000, allocation_percent: 40 },
        },
        risk_alerts: [],
      }));
      return;
    }

    if (url.pathname === '/api/portfolio/fit-assessment' && request.method() === 'POST') {
      fitRequestPayload = request.postDataJSON();
      assert.equal(fitRequestPayload.symbol, 'VTI');
      await route.fulfill(jsonResponse({
        symbol: 'VTI',
        fit_status: 'mixed',
        fit_score: 56,
        fit_reasons: ['Cash runway is at or above the 6-month target.'],
        fit_risks: ['Personal tax sensitivity is high; taxable contribution placement should be reviewed.'],
        blocking_gaps: ['tax:contribution_account_policy', 'tax:account_location_policy'],
        portfolio_impact: {
          existing_position: true,
          current_weight_pct: 60,
          proposed_account: {
            account_id: 'taxable',
            account_name: 'Taxable Brokerage',
            tax_treatment: 'taxable',
            policy_preferred_treatments: ['tax_free'],
          },
          contribution_guidance: {
            status: 'review',
            account_id: 'taxable',
            account_type: 'taxableBrokerage',
            tax_treatment: 'taxable',
            policy_conflicts: ['tax:account_location_policy', 'tax:policy_review'],
            review_reasons: [
              'Proposed contribution account conflicts with preferred account-location policy.',
              'Personal tax sensitivity makes this account treatment worth reviewing.',
            ],
            recommended_review: 'review_account_location',
          },
          investment_policy: {
            preferred_account_locations: { equity: ['tax_free'] },
            tax_sensitivity: 'high',
          },
        },
        plan_impact: { time_horizon: 'long', years: 25 },
        evidence: {
          freshness_status: 'fresh',
          confidence: 'high',
          packet_id: 'research-evidence:yfinance:VTI:6mo:1d',
        },
        simulation_required: false,
        recommended_next_step: 'review_account_location',
      }));
      return;
    }

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({ profile_readiness: { status: 'ready', completion_percent: 100 }, steps: [] }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.getByRole('button', { name: /Sweep for new suggestions/ }).click();
  await page.getByText('watchlist research').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /Create 1 suggestion/ }).click();

  assert.equal(sweepCreatePayload.dry_run, false);
  await page.getByText('Review VTI contribution account fit').waitFor({ state: 'visible' });
  await page.getByText('Investment-fit route').waitFor({ state: 'visible' });
  await page.getByText('symbol VTI · fresh evidence · via yfinance · mixed fit').waitFor({ state: 'visible' });
  await page.getByText('1 blocker: tax contribution account policy').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: /Review fit/ }).first().click();
  await page.waitForURL('**/#portfolio?fit=VTI&focus=rec-contribution-account');
  await page.locator('input[name="symbol"]').waitFor({ state: 'visible' });
  await assertInputValue(page, 'input[name="symbol"]', 'VTI');
  await page.getByText('Contribution fit').waitFor({ state: 'visible' });
  await page.getByText('Review · Taxable · Review Account Location · Proposed contribution account conflicts with preferred account-location policy.').waitFor({ state: 'visible' });
  await page.getByText('Personal tax sensitivity is high; taxable contribution placement should be reviewed.').waitFor({ state: 'visible' });
  assert.equal(fitRequestPayload.symbol, 'VTI');

  await page.goto('http://buildwealth-v2.test/#inbox?focus=rec-contribution-account');
  await page.getByText('Investment-fit route').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Copilot →', exact: true }).click();
  await page.waitForURL('**/#copilot?focus=rec-contribution-account&intent=investment-fit');
  await page.locator('#composer-textarea').waitFor({ state: 'visible' });

  const draft = await page.locator('#composer-textarea').inputValue();
  assert.match(draft, /Review investment-fit recommendation rec-contribution-account with me\./);
  assert.match(draft, /provider freshness/);
  assert.match(draft, /Do not give hidden buy\/sell advice/);
});

async function assertInputValue(page, selector, expected) {
  const value = await page.locator(selector).inputValue();
  assert.equal(value, expected);
}
