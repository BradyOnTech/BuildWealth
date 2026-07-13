// Guided setup rail — walks the rail against a fully route-mocked API:
// household step first, Skip advances client-side, and "Use the estimates"
// on the taxes step PUTs the suggested decimal rates into tax_profile.

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

test('rail opens on the household step; Skip for now advances to Money in & out', async ({ page }) => {
  const puts = [];
  await installRoutes(page, emptyProfile(), puts);
  await page.goto('http://buildwealth-v2.test/#profile');

  const rail = page.locator('aside.setup-rail');
  await rail.waitFor({ state: 'visible' });
  await rail.getByText('step 1 of 5').waitFor({ state: 'visible' });
  assert.equal(await rail.locator('.setup-rail-title').innerText(), 'Household');

  // Alternates row is present on every step.
  await rail.getByRole('button', { name: 'From a document' }).waitFor({ state: 'visible' });
  const chatLink = rail.getByRole('link', { name: 'Ask me in chat' });
  assert.equal(await chatLink.getAttribute('href'), '#copilot?intent=profile-setup');

  // The household editor is the same table composer the Household tab uses.
  await rail.getByRole('button', { name: 'Add member' }).waitFor({ state: 'visible' });

  // Skip advances client-side without writing anything.
  await rail.getByRole('button', { name: 'Skip for now' }).click();
  await rail.getByText('step 2 of 5').waitFor({ state: 'visible' });
  assert.equal(await rail.locator('.setup-rail-title').innerText(), 'Money in & out');
  await rail.getByRole('button', { name: 'Add income' }).waitFor({ state: 'visible' });
  await rail.getByRole('button', { name: 'Add expense' }).waitFor({ state: 'visible' });
  assert.equal(puts.length, 0, 'skipping must not persist anything');
});

test('taxes step: Use the estimates PUTs the suggested decimal rates', async ({ page }) => {
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

  const rail = page.locator('aside.setup-rail');
  await rail.getByText('step 4 of 5').waitFor({ state: 'visible' });
  assert.equal(await rail.locator('.setup-rail-title').innerText(), 'Taxes');

  const put = nextPut(page);
  await rail.getByRole('button', { name: 'Use the estimates' }).click();
  await put;

  assert.equal(puts.length, 1);
  assert.equal(puts[0].tax_profile.marginal_tax_rate, 0.22);
  assert.equal(puts[0].tax_profile.effective_tax_rate, 0.15);
  assert.equal(puts[0].tax_profile.state_tax_rate, 0.05);
});
