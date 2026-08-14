// Profile "Needs you" band — walks the band against a fully route-mocked API.
// Ported from the deleted setup_rail.spec.mjs: the band replaced the rail, and
// this keeps the one end-to-end guarantee that mattered — that "Use the
// estimates" PUTs the suggested *decimal* rates into tax_profile. The band also
// has to route each gap at the editor that actually owns it, which the rail
// never did.

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

const emptyProfile = () => ({
  household_members: [],
  income_items: [],
  expense_items: [],
  debt_items: [],
  goal_items: [],
  physical_assets: [],
  tax_profile: {},
  flags: {},
});

const READINESS_KEYS = [
  ['household', 'Household'],
  ['income', 'Income'],
  ['expenses', 'Expenses'],
  ['debt', 'Debt'],
  ['goals', 'Goals'],
  ['tax_profile', 'Tax profile'],
  ['investment_policy', 'Investment policy'],
  ['physical_assets', 'Physical assets'],
];

const readinessSections = (completeKeys = []) => READINESS_KEYS.map(([key, title]) => ({
  key,
  title,
  status: completeKeys.includes(key) ? 'complete' : 'incomplete',
  detail: completeKeys.includes(key) ? 'Looks good.' : `Add ${title.toLowerCase()} so planning can rely on it.`,
}));

// Route-mocks the whole app. `options.readinessComplete` fixes which readiness
// sections report complete; `options.suggestions` serves /api/profile/defaults.
async function installRoutes(page, profileState, puts, options = {}) {
  let profile = profileState;
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
    if (url.pathname === '/api/financial-profile') {
      if (request.method() === 'PUT') {
        const body = request.postDataJSON();
        puts.push(body);
        profile = body;
        await route.fulfill(jsonResponse(body));
        return;
      }
      await route.fulfill(jsonResponse(profile));
      return;
    }
    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: false,
        completion_percent: 30,
        profile_readiness: {
          status: 'partial',
          sections: readinessSections(options.readinessComplete || []),
        },
        steps: [],
      }));
      return;
    }
    if (url.pathname === '/api/profile/defaults') {
      await route.fulfill(jsonResponse({ suggestions: options.suggestions || {} }));
      return;
    }
    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([]));
      return;
    }
    await route.fulfill(jsonResponse({}));
  });
}

const nextPut = page => page.waitForResponse(r =>
  r.url().includes('/api/financial-profile') && r.request().method() === 'PUT');

test('band ranks the open gaps, says what each unlocks, and routes to real editors', async ({ page }) => {
  const puts = [];
  await installRoutes(page, emptyProfile(), puts);
  await page.goto('http://buildwealth-v2.test/#profile');

  const band = page.locator('aside.profile-needs');
  await band.waitFor({ state: 'visible' });
  await band.getByText('Needs you').waitFor({ state: 'visible' });

  // Eight sections are incomplete; the band shows three and says so rather than
  // truncating silently.
  await band.getByText('8 things are holding the plan back').waitFor({ state: 'visible' });
  await band.getByText(/Showing the three that unlock the most/).waitFor({ state: 'visible' });
  assert.equal(await band.locator('.profile-needs-item').count(), 3);

  // Every row states its consequence, and links at the section that owns it —
  // never a raw readiness key or a fallback to Overview.
  await band.getByText('Unlocks dependent-aware tax and goal logic.').waitFor({ state: 'visible' });
  const hrefs = await band.locator('.profile-needs-item a').evaluateAll(
    links => links.map(a => a.getAttribute('href')),
  );
  assert.deepEqual(hrefs, [
    '#profile?section=household',
    '#profile?section=income',
    '#profile?section=expenses',
  ]);
  for (const href of hrefs) {
    assert.doesNotMatch(href, /section=overview$/, 'a gap must never route to Overview');
  }

  // The alternates row keeps every escape hatch the rail owned.
  await band.getByRole('button', { name: 'From a document' }).waitFor({ state: 'visible' });
  await band.getByRole('button', { name: 'I have no debt' }).waitFor({ state: 'visible' });
  const chatLink = band.getByRole('link', { name: 'Ask me in chat' });
  assert.equal(await chatLink.getAttribute('href'), '#copilot?intent=profile-setup');

  // The band embeds no editor, so the page's own navigation stays on screen.
  const railTop = await page.locator('nav.profile-rail').evaluate(el => el.getBoundingClientRect().top);
  assert.ok(railTop < 900, `section rail must be visible on load (measured top ${railTop}px)`);
  assert.equal(puts.length, 0, 'rendering the band must not persist anything');
});

// The band is capped at three rows, so a workspace whose only remaining gap is
// property must still route that one gap correctly — this is the case that
// shipped a button reading "Open physical_assets" pointed at Overview.
test('a lone unmapped-looking gap still resolves to a human label and its editor', async ({ page }) => {
  const puts = [];
  await installRoutes(page, emptyProfile(), puts, {
    readinessComplete: ['household', 'income', 'expenses', 'debt', 'goals', 'tax_profile', 'investment_policy'],
  });
  await page.goto('http://buildwealth-v2.test/#profile');

  const band = page.locator('aside.profile-needs');
  await band.waitFor({ state: 'visible' });
  await band.getByText('One thing is holding the plan back').waitFor({ state: 'visible' });
  const row = band.locator('.profile-needs-item').first();
  const label = await row.locator('a').innerText();
  assert.equal(label.trim(), 'Open property');
  assert.doesNotMatch(label, /physical_assets/, 'a raw readiness key must never reach the UI');
  assert.equal(await row.locator('a').getAttribute('href'), '#profile?section=assets');
  await row.getByText('Unlocks net worth beyond accounts, and property as plan funding.').waitFor();
});

test('on a section the band collapses to one line and drops the gap being worked', async ({ page }) => {
  await installRoutes(page, emptyProfile(), []);
  await page.goto('http://buildwealth-v2.test/#profile?section=income');

  const line = page.locator('aside.profile-needs-line');
  await line.waitFor({ state: 'visible' });
  // The full band is Overview's job — a workbench gets one line.
  assert.equal(await page.locator('aside.profile-needs').count(), 0);
  assert.ok(await line.evaluate(el => el.getBoundingClientRect().height) <= 80,
    'the section-page cue must stay a single line');

  // The whole point: standing in Income, nothing tells you to add income.
  const text = await line.innerText();
  assert.doesNotMatch(text, /comes in each month/i, 'must not prompt for the section being edited');
  assert.doesNotMatch(text, /Open income/, 'must not link at the section already open');
  // Household is first in readiness order once income is excluded.
  await line.getByRole('link', { name: 'Open household' }).waitFor({ state: 'visible' });
  // Seven others are open, not the eight the raw payload reports — the count and
  // the link have to agree about which gaps are being counted.
  assert.match(text, /7 other sections still need you/);

  // Switching to Overview restores the full band, in place, without a reload.
  await page.locator('nav.profile-rail a[data-tab="overview"]').click();
  await page.locator('aside.profile-needs').waitFor({ state: 'visible' });
  assert.equal(await page.locator('aside.profile-needs-line').count(), 0);
});

test('the cue goes silent when the only gap left is the section you are on', async ({ page }) => {
  await installRoutes(page, emptyProfile(), [], {
    readinessComplete: ['household', 'expenses', 'debt', 'goals', 'tax_profile', 'investment_policy', 'physical_assets'],
  });
  await page.goto('http://buildwealth-v2.test/#profile?section=income');
  await page.locator('.profile-rail').waitFor({ state: 'visible' });

  assert.equal(await page.locator('aside.profile-needs-line').count(), 0,
    'nothing to say when you are already fixing the only gap');
  assert.equal(await page.locator('aside.profile-needs').count(), 0);
});

test('band: Use the estimates PUTs the suggested decimal rates into tax_profile', async ({ page }) => {
  const puts = [];
  await installRoutes(page, emptyProfile(), puts, {
    readinessComplete: ['household', 'income', 'expenses', 'debt', 'goals'],
    suggestions: {
      'tax_profile.marginal_tax_rate': {
        field_path: 'tax_profile.marginal_tax_rate',
        value: 0.22, display: '22%', basis: 'computed',
        explanation: 'Estimated from your income and filing status.',
      },
      'tax_profile.effective_tax_rate': {
        field_path: 'tax_profile.effective_tax_rate',
        value: 0.15, display: '15%', basis: 'computed',
        explanation: 'Average federal rate across your income.',
      },
      'tax_profile.state_tax_rate': {
        field_path: 'tax_profile.state_tax_rate',
        value: 0.05, display: '5%', basis: 'typical',
        explanation: 'Flat approximation for your state.',
      },
    },
  });
  await page.goto('http://buildwealth-v2.test/#profile');

  const band = page.locator('aside.profile-needs');
  await band.waitFor({ state: 'visible' });

  const put = nextPut(page);
  await band.getByRole('button', { name: 'Use the estimates' }).click();
  await put;

  assert.equal(puts.length, 1);
  assert.equal(puts[0].tax_profile.marginal_tax_rate, 0.22);
  assert.equal(puts[0].tax_profile.effective_tax_rate, 0.15);
  assert.equal(puts[0].tax_profile.state_tax_rate, 0.05);
});
