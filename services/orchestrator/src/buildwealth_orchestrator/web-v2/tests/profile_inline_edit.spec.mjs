// Profile tables — inline row editing, undo-on-remove, and the Annual toggle,
// driven end-to-end against a fully route-mocked /api/financial-profile.

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

// Route-mocks the whole app; GET /api/financial-profile serves `profileState`,
// PUTs are captured into `puts` and become the new state (server echo).
async function installRoutes(page, profileState, puts) {
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
        completion_percent: 40,
        profile_readiness: { status: 'partial' },
        steps: [],
      }));
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

test('income: annual composer add, inline edit, and undo-on-remove round-trip PUTs', async ({ page }) => {
  const puts = [];
  await installRoutes(page, emptyProfile(), puts);
  await page.goto('http://buildwealth-v2.test/#profile?section=income');

  // ── Add via composer with the Annual toggle: 96000/yr → 8000/mo
  const composer = page.locator('form.profile-composer');
  await composer.getByRole('textbox', { name: 'Label' }).fill('Salary');
  await composer.getByRole('button', { name: 'Annual' }).click();
  await composer.getByRole('spinbutton', { name: 'Amount' }).fill('96000');
  const addPut = nextPut(page);
  await page.getByRole('button', { name: 'Add income' }).click();
  await addPut;
  assert.equal(puts.length, 1);
  assert.equal(puts[0].income_items.length, 1);
  assert.equal(puts[0].income_items[0].label, 'Salary');
  assert.equal(puts[0].income_items[0].monthly_amount_usd, 8000);
  const rowId = puts[0].income_items[0].id;
  assert.ok(rowId);

  // ── Inline edit: unit is still Annual, so the input shows 96000
  await page.getByRole('row').filter({ hasText: 'Salary' })
    .getByRole('button', { name: 'Edit' }).click();
  const editRow = page.locator('tr.profile-row-editing');
  const amount = editRow.getByRole('spinbutton', { name: 'Amount' });
  assert.equal(await amount.inputValue(), '96000');
  await amount.fill('108000');
  const editPut = nextPut(page);
  await editRow.getByRole('button', { name: 'Save' }).click();
  await editPut;
  assert.equal(puts.length, 2);
  assert.equal(puts[1].income_items.length, 1);
  assert.equal(puts[1].income_items[0].monthly_amount_usd, 9000);
  assert.equal(puts[1].income_items[0].id, rowId, 'inline edit must preserve the row id');

  // ── Remove, then Undo from the toast restores the prior list
  const removePut = nextPut(page);
  await page.getByRole('row').filter({ hasText: 'Salary' })
    .getByRole('button', { name: 'Remove' }).click();
  await removePut;
  assert.equal(puts[2].income_items.length, 0);

  const toast = page.getByRole('status');
  await toast.getByText('Removed Salary').waitFor({ state: 'visible' });
  const undoPut = nextPut(page);
  await toast.getByRole('button', { name: 'Undo' }).click();
  await undoPut;
  assert.equal(puts.length, 4);
  assert.equal(puts[3].income_items.length, 1);
  assert.equal(puts[3].income_items[0].label, 'Salary');
  assert.equal(puts[3].income_items[0].monthly_amount_usd, 9000);
  assert.equal(puts[3].income_items[0].id, rowId);
});

test('inline edit keyboard: Escape cancels without saving, Enter saves', async ({ page }) => {
  const puts = [];
  const profile = emptyProfile();
  profile.income_items = [{
    id: 'inc-1',
    label: 'Salary',
    monthly_amount_usd: 5000,
    source_type: 'salary',
    is_pre_tax: false,
    annual_growth_rate: null,
    start_date: null,
    end_date: null,
  }];
  await installRoutes(page, profile, puts);
  await page.goto('http://buildwealth-v2.test/#profile?section=income');

  const salaryRow = page.getByRole('row').filter({ hasText: 'Salary' });
  await salaryRow.getByRole('button', { name: 'Edit' }).click();

  const editRow = page.locator('tr.profile-row-editing');
  const label = editRow.getByRole('textbox', { name: 'Label' });
  await label.fill('Contract');
  await label.press('Escape');
  await editRow.waitFor({ state: 'detached' });
  await salaryRow.getByText('Salary').first().waitFor({ state: 'visible' });
  assert.equal(puts.length, 0, 'Escape must not persist anything');

  await salaryRow.getByRole('button', { name: 'Edit' }).click();
  const label2 = editRow.getByRole('textbox', { name: 'Label' });
  await label2.fill('Contract');
  const savePut = nextPut(page);
  await label2.press('Enter');
  await savePut;
  assert.equal(puts.length, 1);
  assert.equal(puts[0].income_items[0].label, 'Contract');
  assert.equal(puts[0].income_items[0].id, 'inc-1');
  assert.equal(puts[0].income_items[0].monthly_amount_usd, 5000);
});
