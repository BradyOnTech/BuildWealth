import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { api } from '../lib/api.js';
import { loadPlaidLink, PLAID_LINK_SCRIPT_SRC } from '../views/import_sync.js';

test('financial connection API helpers use the Phase 1 routes and exact bodies', async (t) => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ ok: true, items: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
  t.after(() => { globalThis.fetch = originalFetch; });

  await api.financialConnections();
  await api.createPlaidLinkToken();
  await api.exchangePlaidPublicToken({
    public_token: 'public-sandbox-token',
    institution: { institution_id: 'ins_1', name: 'Hills Bank' },
  });
  await api.financialConnectionPreview('connection 1');
  await api.activateFinancialConnection('connection 1', {
    accounts: [{
      provider_account_id: 'provider-account-1',
      include: true,
      buildwealth_account_id: 'manual-account-1',
    }],
  });
  await api.syncFinancialConnection('connection 1');
  await api.createFinancialConnectionUpdateLinkToken('connection 1');
  await api.financialConnectionDisconnectPreview('connection 1');
  await api.disconnectFinancialConnection('connection 1', 'keep_frozen');
  await api.disconnectFinancialConnection('connection 1', 'remove_connected_data');

  assert.deepEqual(calls.map(call => [call.options.method || 'GET', call.url]), [
    ['GET', '/api/connections'],
    ['POST', '/api/connections/plaid/link-token'],
    ['POST', '/api/connections/plaid/exchange'],
    ['GET', '/api/connections/connection%201/preview'],
    ['POST', '/api/connections/connection%201/activate'],
    ['POST', '/api/connections/connection%201/sync'],
    ['POST', '/api/connections/connection%201/update-link-token'],
    ['POST', '/api/connections/connection%201/disconnect-preview'],
    ['DELETE', '/api/connections/connection%201'],
    ['DELETE', '/api/connections/connection%201'],
  ]);
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    public_token: 'public-sandbox-token',
    institution: { institution_id: 'ins_1', name: 'Hills Bank' },
  });
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    accounts: [{
      provider_account_id: 'provider-account-1',
      include: true,
      buildwealth_account_id: 'manual-account-1',
    }],
  });
  assert.deepEqual(JSON.parse(calls[8].options.body), { retention: 'keep_frozen' });
  assert.deepEqual(JSON.parse(calls[9].options.body), { retention: 'remove_connected_data' });
});

test('Plaid Link loads from the official CDN only when the loader is called', async () => {
  const listeners = new Map();
  const appended = [];
  const fakeWindow = {};
  const script = {
    async: false,
    dataset: {},
    src: '',
    addEventListener(name, callback) { listeners.set(name, callback); },
  };
  const fakeDocument = {
    querySelector() { return null; },
    createElement(tag) {
      assert.equal(tag, 'script');
      return script;
    },
    head: {
      appendChild(node) {
        appended.push(node);
        fakeWindow.Plaid = { create() {} };
        listeners.get('load')();
      },
    },
  };

  assert.equal(appended.length, 0);
  const Plaid = await loadPlaidLink({ documentRef: fakeDocument, windowRef: fakeWindow });

  assert.equal(appended.length, 1);
  assert.equal(script.src, 'https://cdn.plaid.com/link/v2/stable/link-initialize.js');
  assert.equal(script.src, PLAID_LINK_SCRIPT_SRC);
  assert.equal(script.async, true);
  assert.equal(script.dataset.buildwealthPlaidLink, 'true');
  assert.equal(typeof Plaid.create, 'function');
});

test('Import & Review covers connection lifecycle while preserving manual and CSV paths', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/import_sync.js'), 'utf8');
  const index = readFileSync(resolve(currentDir, '../index.html'), 'utf8');
  const portfolio = readFileSync(resolve(currentDir, '../views/portfolio.js'), 'utf8');
  const composition = readFileSync(resolve(currentDir, '../views/portfolio/composition.js'), 'utf8');

  assert.match(source, /Connect investment account/);
  assert.match(source, /never receives\s+your bank password/);
  assert.match(source, /cannot trade or move money/);
  assert.match(source, /Connections are turned off/);
  assert.match(source, /Plaid needs to be configured/);
  assert.match(source, /Pending review/);
  assert.match(source, /Choose accounts and confirm every match/);
  assert.match(source, /Nothing is merged or added until you activate/);
  assert.match(source, /Repair connection/);
  assert.match(source, /Check for updates/);
  assert.match(source, /Keep a frozen copy/);
  assert.match(source, /Remove connected data/);
  assert.match(source, /Not imported yet/);
  assert.match(source, /stale/);
  assert.match(source, /receivedRedirectUri/);
  assert.match(source, /oauth_state_id/);
  assert.match(source, /already connected\. Use Repair/);
  assert.match(source, /Enter an account manually/);
  assert.match(source, /Use the CSV workbench below/);
  assert.match(source, /Import workbench/);
  assert.match(index, /styles\/import-sync\.css/);
  assert.match(portfolio, /Read-only connection/);
  assert.match(portfolio, /Connected by/);
  assert.match(portfolio, /Last provider update/);
  assert.match(composition, /Manage read-only source/);
  assert.match(composition, /institution value fallback/);
});
