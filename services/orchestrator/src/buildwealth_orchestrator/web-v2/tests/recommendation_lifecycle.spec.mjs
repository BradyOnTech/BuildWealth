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

test('Inbox previews, applies, and captures recommendation outcome', async ({ page }) => {
  let status = 'proposed';
  let applyPayload = null;
  let outcomePayload = null;

  const recommendation = () => ({
    id: 'rec-apply',
    title: 'Increase annual contributions',
    detail: 'Raise annual contribution after preview.',
    priority: 'high',
    status,
    source: 'generator:plan_tracking',
    recommendation_type: 'plan_settings_update',
    plan_id: 'plan-1',
    created_at: '2026-04-26T12:00:00Z',
    updated_at: '2026-04-26T12:00:00Z',
    action_payload: {
      quality: {
        actionability: 'previewable',
        confidence_level: 'medium',
        freshness_status: 'fresh',
        reversibility: 'high',
        impact: { level: 'high' },
        decision_grade: true,
        blocking_context: [],
      },
    },
    score: {
      total: 85,
      rank: 1,
      reasons: ['Recommendation can be previewed before apply.'],
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
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan' }]));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      const requestedStatus = url.searchParams.get('status') || 'proposed';
      await route.fulfill(jsonResponse(requestedStatus === status ? [recommendation()] : []));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/recommendations/rec-apply/preview') {
      await route.fulfill(jsonResponse({
        preview: {
          scenario_delta: {
            terminal_value_delta_usd: 12500,
            real_value_delta_usd: 8400,
            savings_rate_delta_pct: 2.5,
          },
        },
      }));
      return;
    }

    if (url.pathname === '/api/recommendations/rec-apply/apply' && request.method() === 'POST') {
      applyPayload = request.postDataJSON();
      status = 'applied';
      await route.fulfill(jsonResponse({ recommendation: recommendation() }));
      return;
    }

    if (url.pathname === '/api/recommendations/rec-apply/outcome' && request.method() === 'POST') {
      outcomePayload = request.postDataJSON();
      await route.fulfill(jsonResponse({ recommendation: recommendation() }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.getByText('Increase annual contributions').waitFor({ state: 'visible' });

  await page.getByRole('button', { name: /Preview & apply/ }).click();
  await page.getByText('terminal value').waitFor({ state: 'visible' });
  await page.getByText('Decision pre-mortem').waitFor({ state: 'visible' });
  await page.locator('textarea[name="rationale"]').fill('Makes sense after reviewing the scenario preview.');
  await page.locator('textarea[name="premortem_expected_benefit"]').fill('Retirement baseline improves.');
  await page.locator('textarea[name="premortem_main_risk"]').fill('Cash runway gets too tight.');
  await page.locator('textarea[name="premortem_disconfirming_signal"]').fill('Savings rate turns negative.');
  await page.locator('input[name="premortem_monitoring_plan"]').fill('Review cash runway after two pay cycles.');
  await page.locator('input[name="premortem_review_date"]').fill('2026-06-30');
  await page.getByRole('button', { name: 'Yes, apply' }).click();

  assert.equal(applyPayload.rationale, 'Makes sense after reviewing the scenario preview.');
  assert.equal(applyPayload.premortem_expected_benefit, 'Retirement baseline improves.');
  assert.equal(applyPayload.premortem_main_risk, 'Cash runway gets too tight.');
  assert.equal(applyPayload.premortem_disconfirming_signal, 'Savings rate turns negative.');
  assert.equal(applyPayload.premortem_monitoring_plan, 'Review cash runway after two pay cycles.');
  assert.equal(applyPayload.premortem_review_date, '2026-06-30');

  await page.getByRole('button', { name: 'applied' }).click();
  await page.getByText('Increase annual contributions').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /Log outcome/ }).click();
  await page.getByText('Did the plan change behave as expected?').waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Applied as previewed' }).click();
  await page.locator('input[name="future_value_delta_usd"]').fill('13500');
  await page.locator('input[name="real_value_delta_usd"]').fill('9000');
  await page.locator('input[name="measurement_window_days"]').fill('30');
  await page.locator('input[name="measurement_source"]').fill('manual browser review');
  await page.getByRole('button', { name: 'Save outcome' }).click();

  assert.equal(outcomePayload.realized_delta_future_value_usd, 13500);
  assert.equal(outcomePayload.realized_delta_real_value_usd, 9000);
  assert.equal(outcomePayload.observation_window_days, 30);
  assert.equal(outcomePayload.measurement_source, 'manual browser review');
  assert.match(outcomePayload.note, /Applied as previewed/);
});
