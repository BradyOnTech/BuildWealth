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

test('Inbox thesis review opens v2 Research and refreshes review metadata', async ({ page }) => {
  let thesisReviewed = false;
  let applyPayload = null;

  const recommendation = () => ({
    id: 'rec-thesis-expired',
    title: 'Refresh stale research thesis for MSFT / VTI',
    detail: 'The saved research thesis is past the review window.',
    priority: 'medium',
    status: thesisReviewed ? 'applied' : 'proposed',
    source: 'generator:research_thesis_expiration',
    recommendation_type: 'workflow_action',
    plan_id: 'plan-1',
    created_at: '2026-04-26T12:00:00Z',
    updated_at: thesisReviewed ? '2026-04-29T12:00:00Z' : '2026-04-26T12:00:00Z',
    action_payload: {
      generator: {
        signal_type: 'research_thesis_expiration',
        signal_key: 'thesis_expired',
      },
      evidence: {
        artifact_id: 'artifact-dossier-msft',
        plan_id: 'plan-1',
        symbols: ['MSFT', 'VTI'],
        freshness_status: 'stale',
        reference_price_usd: 410,
        material_price_change_pct: 12.2,
        packet_citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
      },
      suggested_action: {
        kind: 'review_research_thesis',
        artifact_id: 'artifact-dossier-msft',
        plan_id: 'plan-1',
        symbols: ['MSFT', 'VTI'],
      },
      quality: {
        actionability: 'review_only',
        confidence_level: 'medium',
        freshness_status: 'stale',
        blocking_context: ['research.thesis_expired'],
      },
    },
  });

  const artifact = () => ({
    id: 'artifact-dossier-msft',
    file_name: '2026-research-dossier-msft-vti.md',
    title: 'Research Dossier - MSFT vs VTI',
    created_at: '2026-03-17T12:00:00Z',
    thesis_review: thesisReviewed
      ? {
          status: 'current',
          age_days: 0,
          stale_after_days: 30,
          reviewed_at: '2026-04-29T12:00:00Z',
          expires_at: '2026-05-29T12:00:00Z',
          reference_price_usd: 460.02,
        }
      : {
          status: 'expired',
          age_days: 42,
          stale_after_days: 30,
          reviewed_at: '2026-03-17T12:00:00Z',
          expires_at: '2026-04-16T12:00:00Z',
          reference_price_usd: 410,
        },
    content: [
      '# Research Dossier: MSFT vs VTI',
      '',
      '## Thesis',
      '',
      'Compare durable software cash flow against broad market exposure.',
      '',
      '## Evidence Packets',
      '',
      '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
      '| --- | --- | --- | --- | --- | ---: | --- |',
      '| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | stale | medium | 82% | none |',
      '| VTI | research-evidence:yfinance:VTI:6mo:1d | yfinance | fresh | high | 96% | none |',
    ].join('\n'),
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
      await route.fulfill(jsonResponse(requestedStatus === recommendation().status ? [recommendation()] : []));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/recommendations/rec-thesis-expired') {
      await route.fulfill(jsonResponse(recommendation()));
      return;
    }

    if (url.pathname === '/api/recommendations/rec-thesis-expired/apply' && request.method() === 'POST') {
      applyPayload = request.postDataJSON();
      thesisReviewed = true;
      await route.fulfill(jsonResponse({
        recommendation: recommendation(),
        thesis_review: {
          status: 'refreshed',
          target: 'dossier',
          artifact_id: 'artifact-dossier-msft',
          plan_id: 'plan-1',
          symbols: ['MSFT', 'VTI'],
          reviewed_at: '2026-04-29T12:00:00Z',
          expires_at: '2026-05-29T12:00:00Z',
          reference_price_usd: 460.02,
        },
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/artifacts/artifact-dossier-msft') {
      await route.fulfill(jsonResponse(artifact()));
      return;
    }

    if (url.pathname === '/api/research/evidence-packet' && request.method() === 'POST') {
      const payload = request.postDataJSON();
      assert.equal(payload.symbol, 'MSFT');
      await route.fulfill(jsonResponse({
        packet_id: 'research-evidence:yfinance:MSFT:6mo:1d',
        symbol: 'MSFT',
        name: 'Microsoft',
        provider: 'yfinance',
        period: '6mo',
        interval: '1d',
        generated_at: '2026-04-29T12:00:00Z',
        coverage: {
          quote_available: true,
          history_available: true,
          provider_status: 'available',
          endpoints_attempted: ['quote', 'price_history'],
          warnings: [],
        },
        freshness: { status: thesisReviewed ? 'fresh' : 'stale' },
        metrics: {
          last_price: 460.02,
          period_change_pct: 10.8,
          volatility_pct: 19.1,
        },
        risk: { drawdown_from_high_pct: -3.1 },
        quality: { confidence: 'medium', coverage_score: 82, blocking_gaps: [] },
        provenance: { warnings: [] },
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.getByText('Refresh stale research thesis for MSFT / VTI').waitFor({ state: 'visible' });
  await page.getByRole('link', { name: /Review thesis/ }).click();

  await page.waitForURL('**/#research?thesisReview=artifact-dossier-msft&plan=plan-1&focus=rec-thesis-expired');
  await page.getByText('Thesis review').waitFor({ state: 'visible' });
  await page.getByText('Review due', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('$410.00').first().waitFor({ state: 'visible' });
  await page.getByText('$460.02').first().waitFor({ state: 'visible' });
  await page.getByText('+12.2%').first().waitFor({ state: 'visible' });

  await page.getByRole('button', { name: /Mark thesis reviewed/ }).click();

  assert.equal(applyPayload.decision_status, 'reviewed');
  assert.equal(applyPayload.create_decision_packet, false);
  assert.equal(applyPayload.capture_scenario_diff, false);
  assert.equal(applyPayload.pin_research_bridge, false);
  await page.getByText(/Thesis current/).waitFor({ state: 'visible' });
  await page.getByText('$460.02').first().waitFor({ state: 'visible' });
  await page.getByText('Review metadata refreshed').waitFor({ state: 'visible' });
});
