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

test('Inbox reviews a pending profile context capture through source resolution', async ({ page }) => {
  let candidateState = 'pending_review';
  let candidateInfluence = 'mention_only';
  let lifecyclePayload = null;

  const candidate = () => ({
    id: 'ctx-tax-rate',
    lifecycle_state: candidateState,
    prompt_influence: candidateInfluence,
    source_domain: 'conversation',
    source_ref: 'conversation/tax#message.1',
    extracted_claim: 'My marginal tax rate is 32%.',
    target_domain: 'profile',
    target_area: 'tax_profile',
    target_field: 'tax_profile.marginal_tax_rate',
    target_value: 0.32,
    confidence: 'medium',
    materiality: 'high',
    materiality_rationale: 'Review before relying on this because it can change planning, policy, tax, risk, or recommendation fit.',
    action_readiness: 'Review before relying on this',
    review_route: {
      route: 'profile',
      label: 'Profile',
      target: 'tax_profile',
      reason: 'Profile candidates must use the existing profile draft and apply flow.',
    },
    created_at: '2026-05-08T12:00:00Z',
    updated_at: '2026-05-08T12:00:00Z',
    metadata: {},
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

    if (url.pathname === '/api/recommendations' || url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse(url.pathname === '/api/recommendations' ? [] : {}));
      return;
    }

    if (url.pathname === '/api/context/candidates' && request.method() === 'GET') {
      const requestedState = url.searchParams.get('lifecycle_state') || 'all';
      const items = requestedState === 'all' || requestedState === candidateState ? [candidate()] : [];
      await route.fulfill(jsonResponse({ items }));
      return;
    }

    if (url.pathname === '/api/context/candidates/ctx-tax-rate/lifecycle' && request.method() === 'PATCH') {
      lifecyclePayload = request.postDataJSON();
      candidateState = lifecyclePayload.lifecycle_state;
      candidateInfluence = lifecyclePayload.prompt_influence;
      await route.fulfill(jsonResponse(candidate()));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.getByText('Context that needs a decision.').waitFor({ state: 'visible' });
  await page.getByText('My marginal tax rate is 32%.').waitFor({ state: 'visible' });

  const contextLane = page.locator('#inbox-context-captures');
  await contextLane.getByRole('button', { name: /Resolve/ }).click();
  await page.getByText('Finish after source review').waitFor({ state: 'visible' });
  await page.locator('textarea[name="review_note"]').fill('Updated the tax profile after checking the source.');
  await contextLane.getByRole('button', { name: /I updated Profile/ }).click();

  assert.equal(lifecyclePayload.lifecycle_state, 'applied');
  assert.equal(lifecyclePayload.prompt_influence, 'authoritative');
  assert.equal(lifecyclePayload.metadata.resolution_state, 'resolved_by_source_update');
  assert.equal(lifecyclePayload.metadata.review_note, 'Updated the tax profile after checking the source.');

  await contextLane.getByText('No pending context captures.').waitFor({ state: 'visible' });
  await contextLane.getByRole('button', { name: /remembered/ }).click();
  await contextLane.getByText('My marginal tax rate is 32%.').waitFor({ state: 'visible' });
});
