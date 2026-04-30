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

test('Today daily review routes command cards into review flows', async ({ page }) => {
  let reviewRecorded = false;
  const todayPayload = () => ({
    generated_at: '2026-04-26T12:00:00Z',
    currency: 'USD',
    state: 'MN',
    sync_status: { running: false, runs_total: 1, runs_failed: 0 },
    net_worth_usd: 300000,
    monthly_surplus_usd: 2500,
    savings_rate_pct: 25,
    command_cards: [
      {
        id: 'profile-readiness',
        title: 'Profile readiness',
        status: 'warning',
        detail: 'Next gap: Tax profile.',
        metric_label: 'Complete',
        metric_value: '80%',
        action_label: 'Complete context',
        href: '#copilot?intent=complete-context',
      },
      {
        id: 'what-changed',
        title: 'What changed',
        status: reviewRecorded ? 'ready' : 'warning',
        detail: reviewRecorded
          ? 'No meaningful changes since the last completed daily review.'
          : 'Cash runway is 2.5 months lower. Research readiness changed from ready to warning. 2 new Copilot-drafted review(s) are waiting.',
        metric_label: 'Changes',
        metric_value: reviewRecorded ? '0' : '2',
        action_label: 'Mark reviewed',
        href: '#today?review=complete',
      },
      {
        id: 'stale-assumptions',
        title: 'Stale assumptions',
        status: 'warning',
        detail: '1 assumption review is open before advice can be fully trusted.',
        metric_label: 'Open',
        metric_value: '1',
        action_label: 'Review assumptions',
        href: '#inbox?focus=rec-stale',
      },
    ],
    top_next_actions: [
      {
        recommendation_id: 'rec-stale',
        title: 'Review stale assumptions',
        detail: 'Tax assumptions need review.',
        priority: 'medium',
        source: 'generator:stale_assumptions',
        action_hint: 'Open Recommendation Inbox to review.',
      },
    ],
    context_state: 'warning',
    context_notes: ['Profile readiness: next gap is Tax profile.'],
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

    if (url.pathname === '/api/dashboard/today') {
      await route.fulfill(jsonResponse(todayPayload()));
      return;
    }

    if (url.pathname === '/api/dashboard/today/review-checkpoint' && request.method() === 'POST') {
      reviewRecorded = true;
      await route.fulfill(jsonResponse(todayPayload()));
      return;
    }

    if (url.pathname === '/api/engines/status') {
      await route.fulfill(jsonResponse({
        enabled_count: 2,
        reachable_count: 1,
        degraded_count: 1,
        engines: [],
      }));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      await route.fulfill(jsonResponse([
        {
          id: 'rec-stale',
          title: 'Review stale assumptions',
          detail: 'Tax assumptions need review.',
          priority: 'medium',
          status: 'proposed',
          source: 'generator:stale_assumptions',
          recommendation_type: 'general',
          action_payload: { quality: { actionability: 'review_only' } },
        },
      ]));
      return;
    }

    if (url.pathname === '/api/recommendations/closure-analytics') {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: false,
        completion_percent: 80,
        profile_readiness: { next_gap_title: 'Tax profile' },
        steps: [],
      }));
      return;
    }

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/');
  await page.getByText('Command center').waitFor({ state: 'visible' });
  await page.getByText('Engine health').waitFor({ state: 'visible' });
  await page.getByText('Cash runway is 2.5 months lower.').waitFor({ state: 'visible' });
  await page.getByText('Research readiness changed from ready to warning.').waitFor({ state: 'visible' });
  await page.getByText('2 new Copilot-drafted review(s) are waiting.').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Mark reviewed' }).click();
  await page.waitForURL('**/#today');
  await page.getByText('No meaningful changes since the last completed daily review.').waitFor({ state: 'visible' });
  assert.equal(reviewRecorded, true);

  await page.getByRole('link', { name: 'Review assumptions' }).click();
  await page.waitForURL('**/#inbox?focus=rec-stale');
  await page.getByText('Review stale assumptions').waitFor({ state: 'visible' });

  await page.goto('http://buildwealth-v2.test/');
  await page.getByRole('link', { name: 'Complete context' }).click();
  await page.waitForURL('**/#copilot?intent=complete-context');
});
