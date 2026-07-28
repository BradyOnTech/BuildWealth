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
    confidence_domains: [
      {
        id: 'profile',
        label: 'Profile',
        status: 'missing_context',
        detail: 'Tax profile blocks decision-grade advice.',
        metric_label: 'Ready',
        metric_value: '80%',
        href: '#copilot?intent=complete-context',
      },
      {
        id: 'research',
        label: 'Research',
        status: 'usable_with_caveats',
        detail: 'Research evidence needs review before stronger advice.',
        metric_label: 'Ready',
        metric_value: '1/2',
        href: '#today?refresh=research',
      },
    ],
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

    if (url.pathname === '/api/services/status') {
      await route.fulfill(jsonResponse({
        enabled_count: 2,
        reachable_count: 1,
        degraded_count: 1,
        services: [],
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

  // Quiet cards and the confidence map live behind the command-center
  // overflow expander; open it before asserting on their content.
  const openOverflow = async () => {
    const overflow = page.locator('details.command-overflow > summary');
    if (await overflow.count()) await overflow.click();
  };

  await page.goto('http://buildwealth-v2.test/');
  await page.getByText('Command center').waitFor({ state: 'visible' });
  await openOverflow();
  await page.getByText('Confidence heat map').waitFor({ state: 'visible' });
  await page.getByText('Tax profile blocks decision-grade advice.').waitFor({ state: 'visible' });
  await page.getByText('Service readiness').waitFor({ state: 'visible' });
  await page.getByText('Cash runway is 2.5 months lower.').waitFor({ state: 'visible' });
  await page.getByText('Research readiness changed from ready to warning.').waitFor({ state: 'visible' });
  await page.getByText('2 new Copilot-drafted review(s) are waiting.').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Mark reviewed' }).click();
  await page.waitForURL('**/#today');
  await openOverflow();
  await page.getByText('No meaningful changes since the last completed daily review.').waitFor({ state: 'visible' });
  assert.equal(reviewRecorded, true);

  await page.getByRole('link', { name: 'Review assumptions' }).click();
  await page.waitForURL('**/#inbox?focus=rec-stale');
  await page.getByText('Review stale assumptions').waitFor({ state: 'visible' });

  await page.goto('http://buildwealth-v2.test/');
  await openOverflow();
  await page.getByRole('link', { name: 'Complete context' }).click();
  await page.waitForURL('**/#copilot?intent=complete-context');

  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('http://buildwealth-v2.test/#today');
  await page.getByText('Command center').waitFor({ state: 'visible' });

  const mobileShell = await page.evaluate(() => {
    const content = document.querySelector('.content');
    const topbarActions = document.querySelector('.topbar-actions')?.getBoundingClientRect();
    const navItems = [...document.querySelectorAll('.nav-item')]
      .map(item => item.getBoundingClientRect().height);
    return {
      viewportWidth: document.documentElement.clientWidth,
      contentClientWidth: content?.clientWidth,
      contentScrollWidth: content?.scrollWidth,
      topbarLeft: topbarActions?.left,
      topbarRight: topbarActions?.right,
      minimumNavHeight: Math.min(...navItems),
    };
  });

  assert.equal(
    mobileShell.contentScrollWidth,
    mobileShell.contentClientWidth,
    'Today content should not clip or scroll horizontally at 320px',
  );
  assert.ok(
    mobileShell.topbarLeft >= 0 && mobileShell.topbarRight <= mobileShell.viewportWidth,
    'all mobile topbar actions should remain inside the viewport',
  );
  assert.ok(
    mobileShell.minimumNavHeight >= 40,
    `mobile navigation should retain 40px hit areas (measured ${mobileShell.minimumNavHeight}px)`,
  );

  await page.goto('http://buildwealth-v2.test/#inbox');
  await page.locator('.inbox-shell').waitFor({ state: 'visible' });
  const minimumInboxControlHeight = await page.locator('.inbox-filters button').evaluateAll(
    buttons => Math.min(...buttons.map(button => button.getBoundingClientRect().height)),
  );
  assert.ok(
    minimumInboxControlHeight >= 40,
    `mobile Inbox filters should retain 40px hit areas (measured ${minimumInboxControlHeight}px)`,
  );
});
