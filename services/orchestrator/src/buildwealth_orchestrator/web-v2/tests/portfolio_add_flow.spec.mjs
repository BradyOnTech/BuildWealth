// Portfolio front door — drives the Add-to-portfolio card against a fully
// route-mocked API: the Investment flow posts /api/portfolio/add with symbol,
// account, and value; the Cash flow posts an amount; and Transactions
// Remove → Undo deletes then re-adds the same row.

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

const ACCOUNTS = [
  { id: 'default', name: 'Default Brokerage', type: 'taxable', currency: 'USD' },
  { id: 'roth', name: 'Fidelity Roth', type: 'roth', currency: 'USD' },
];

const holdingsPayload = () => ({
  total_value: 2500,
  total_cash: 0,
  total_portfolio_value: 2500,
  net_performance: 500,
  net_performance_pct: 25,
  updated_at: '2026-07-13T12:00:00Z',
  prices_updated_at: '2026-07-13T12:00:00Z',
  accounts: ACCOUNTS,
  holdings: {
    'default:VTI': {
      symbol: 'VTI',
      name: 'Vanguard Total Stock Market',
      account: 'default',
      quantity: 10,
      current_value: 2500,
      current_price: 250,
      allocation_pct: 100,
      gain_loss_pct: 25,
      price_source: 'LIVE',
      asset_class: 'US Stocks',
    },
  },
  holdings_by_symbol: {
    VTI: { symbol: 'VTI', current_price: 250, current_value: 2500 },
  },
  allocation_breakdowns: {},
  performance: {},
  risk_alerts: { status: 'ok', alerts: [], breach_count: 0, watch_count: 0, metrics: {} },
});

const TRANSACTIONS = [
  {
    id: 'txn-1',
    date: '2026-06-01',
    symbol: 'VTI',
    action: 'BUY',
    quantity: 10,
    unit_price: 200,
    fee: 1.25,
    account: 'default',
    currency: 'USD',
    note: 'first buy',
    lot_method: 'FIFO',
  },
];

// Route-mocks the whole app; `captured` collects add/transaction writes.
async function installRoutes(page, captured) {
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
    if (url.pathname === '/api/portfolio/holdings') {
      await route.fulfill(jsonResponse(holdingsPayload()));
      return;
    }
    if (url.pathname === '/api/portfolio/analytics') {
      await route.fulfill(jsonResponse({ status: 'unavailable', warnings: [] }));
      return;
    }
    if (url.pathname === '/api/portfolio/look-through') {
      await route.fulfill(jsonResponse({ coverage: {} }));
      return;
    }
    if (url.pathname === '/api/portfolio/assets/search') {
      await route.fulfill(jsonResponse({
        count: 1,
        items: [{ symbol: 'VTI', name: 'Vanguard Total Stock Market' }],
      }));
      return;
    }
    if (url.pathname === '/api/portfolio/add' && request.method() === 'POST') {
      const body = request.postDataJSON();
      captured.adds.push(body);
      await route.fulfill(jsonResponse({
        created: { id: 'txn-new' },
        account_id: body.account_id || 'default',
        estimated_basis: !('unit_cost' in body) && body.flow === 'investment',
        detail: 'Recorded a buy of 4 VTI at $250.00 per share in Default Brokerage.',
      }));
      return;
    }
    if (url.pathname === '/api/portfolio/transactions' && request.method() === 'POST') {
      captured.transactionPosts.push(request.postDataJSON());
      await route.fulfill(jsonResponse({ id: 'txn-readded' }));
      return;
    }
    if (url.pathname.startsWith('/api/portfolio/transactions/') && request.method() === 'DELETE') {
      captured.deletes.push(url.pathname.split('/').pop());
      await route.fulfill(jsonResponse({ deleted: true }));
      return;
    }
    if (url.pathname === '/api/portfolio/transactions') {
      const remaining = TRANSACTIONS.filter(t => !captured.deletes.includes(t.id));
      await route.fulfill(jsonResponse(remaining));
      return;
    }
    await route.fulfill(jsonResponse({}));
  });
}

function freshCapture() {
  return { adds: [], transactionPosts: [], deletes: [] };
}

test('investment flow: symbol + account + current value posts /api/portfolio/add', async ({ page }) => {
  const captured = freshCapture();
  await installRoutes(page, captured);
  await page.goto('http://buildwealth-v2.test/#portfolio');

  await page.getByRole('button', { name: 'Add to portfolio' }).click();
  const card = page.locator('[data-add-card]');
  await card.waitFor({ state: 'visible' });

  const investment = card.locator('[data-add-panel="investment"]');
  await investment.locator('input[name="symbol"]').fill('VTI');
  await investment.locator('select[name="account_id"]').selectOption('roth');
  await investment.locator('input[name="value_usd"]').fill('1000');

  const post = page.waitForResponse(r =>
    r.url().includes('/api/portfolio/add') && r.request().method() === 'POST');
  await investment.getByRole('button', { name: 'Add investment' }).click();
  await post;

  assert.equal(captured.adds.length, 1);
  assert.deepEqual(captured.adds[0], {
    flow: 'investment',
    symbol: 'VTI',
    value_usd: 1000,
    account_id: 'roth',
  });

  // The card survives the holdings refresh with its success + estimate note.
  await page.locator('[data-add-status]').getByText('Recorded a buy of 4 VTI').waitFor({ state: 'visible' });
  await page.locator('[data-add-status]').getByText('Cost basis was estimated').waitFor({ state: 'visible' });
});

test('cash flow posts a CASH_DEPOSIT-shaped body', async ({ page }) => {
  const captured = freshCapture();
  await installRoutes(page, captured);
  await page.goto('http://buildwealth-v2.test/#portfolio');

  await page.getByRole('button', { name: 'Add to portfolio' }).click();
  const card = page.locator('[data-add-card]');
  await card.waitFor({ state: 'visible' });
  await card.getByRole('tab', { name: 'Cash' }).click();

  const cash = card.locator('[data-add-panel="cash"]');
  await cash.locator('input[name="amount_usd"]').fill('500');

  const post = page.waitForResponse(r =>
    r.url().includes('/api/portfolio/add') && r.request().method() === 'POST');
  await cash.getByRole('button', { name: 'Add cash' }).click();
  await post;

  assert.equal(captured.adds.length, 1);
  assert.deepEqual(captured.adds[0], { flow: 'cash', amount_usd: 500, account_id: 'default' });
});

test('transactions: Remove deletes, Undo re-adds the same row', async ({ page }) => {
  const captured = freshCapture();
  await installRoutes(page, captured);
  await page.goto('http://buildwealth-v2.test/#portfolio?section=transactions');

  const removeButton = page.locator('[data-remove-transaction="txn-1"]');
  await removeButton.waitFor({ state: 'visible' });

  const deleted = page.waitForResponse(r =>
    r.url().includes('/api/portfolio/transactions/txn-1') && r.request().method() === 'DELETE');
  await removeButton.click();
  await deleted;
  assert.deepEqual(captured.deletes, ['txn-1']);

  // Undo toast re-adds the removed row via POST /api/portfolio/transactions.
  const toast = page.locator('.undo-toast');
  await toast.getByText('Removed Buy of VTI on 2026-06-01.').waitFor({ state: 'visible' });

  const readd = page.waitForResponse(r =>
    r.url().endsWith('/api/portfolio/transactions') && r.request().method() === 'POST');
  await toast.getByRole('button', { name: 'Undo' }).click();
  await readd;

  assert.equal(captured.transactionPosts.length, 1);
  assert.deepEqual(captured.transactionPosts[0], {
    date: '2026-06-01',
    symbol: 'VTI',
    action: 'BUY',
    quantity: 10,
    unit_price: 200,
    fee: 1.25,
    account: 'default',
    currency: 'USD',
    note: 'first buy',
    lot_method: 'FIFO',
  });
});
