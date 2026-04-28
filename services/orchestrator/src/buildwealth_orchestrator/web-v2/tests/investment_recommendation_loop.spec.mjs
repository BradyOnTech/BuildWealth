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
        evidence: { freshness_status: 'fresh', confidence: 'high' },
        simulation_required: false,
        recommended_next_step: 'review_concentration',
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

  await page.getByRole('link', { name: /Review fit/ }).first().click();
  await page.waitForURL('**/#portfolio?fit=NVDA&focus=rec-invest');
  await page.locator('input[name="symbol"]').waitFor({ state: 'visible' });
  await assertInputValue(page, 'input[name="symbol"]', 'NVDA');
  await page.getByText('Does Not Fit').waitFor({ state: 'visible' });
  await page.getByText('NVDA would worsen concentration risk.').waitFor({ state: 'visible' });
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

async function assertInputValue(page, selector, expected) {
  const value = await page.locator(selector).inputValue();
  assert.equal(value, expected);
}
