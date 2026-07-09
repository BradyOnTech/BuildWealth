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

test('Copilot renders context-use trace from a chat response', async ({ page }) => {
  let chatPayload = null;

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

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: true,
        completion_percent: 100,
        profile_readiness: { status: 'ready' },
        steps: [],
      }));
      return;
    }

    if (url.pathname === '/api/copilot/chat' && request.method() === 'POST') {
      chatPayload = request.postDataJSON();
      await route.fulfill(jsonResponse({
        conversation_id: 'conv-trace',
        answer: 'I checked the current context before answering.',
        tool_calls: [],
        model: 'fake-model',
        created_at: '2026-05-08T12:00:00.000Z',
        context_trace: {
          plan_id: 'plan-1',
          symbols: ['NVDA'],
          retrieval: {
            returned_count: 5,
            citation_count: 2,
            truncated: false,
          },
          conflict_review_items: {
            count: 1,
            ids: ['rec-conflict'],
          },
          context_warnings: [
            {
              type: 'missing_or_stale_context',
              message: 'Tax profile needs review before decision-grade advice.',
            },
          ],
          captured_context_candidates: [
            {
              id: 'ctx-tax',
              target_domain: 'profile',
              lifecycle_state: 'pending_review',
              prompt_influence: 'mention_only',
              review_item: { recommendation_id: 'rec-context' },
            },
          ],
        },
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#copilot');
  await page.getByPlaceholder(/Ask anything/).fill('Should I review NVDA?');
  await page.getByRole('button', { name: /Ask Copilot/ }).click();

  await page.getByText('I checked the current context before answering.').waitFor({ state: 'visible' });
  await page.getByText(/plan scoped · 1 symbol · 5 retrieved · 2 citations · 1 capture · 1 context issue/).waitFor({ state: 'visible' });
  await page.locator('.context-trace-summary summary').click();
  await page.getByRole('link', { name: 'Open Plan' }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'NVDA fit' }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'NVDA research' }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Review context issue' }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Review captured Profile' }).waitFor({ state: 'visible' });
  await page.getByText('Tax profile needs review before decision-grade advice.').waitFor({ state: 'visible' });

  assert.equal(chatPayload.question, 'Should I review NVDA?');
  assert.equal(chatPayload.context_options.detail_level, 'light');
});
