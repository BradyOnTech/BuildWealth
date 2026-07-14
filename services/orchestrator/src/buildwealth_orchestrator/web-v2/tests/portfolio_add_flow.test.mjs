// Add-to-portfolio front door — tab markup, two-required-fields shape,
// More-detail disclosure, body building, and the estimated-basis note.
// Pure string assertions; no DOM.

import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const {
  renderAddFlow,
  renderAddResult,
  buildAddBody,
  addFlowState,
  ADD_FLOW_TABS,
} = await import('../views/portfolio/add_flow.js');

function resetState() {
  addFlowState.open = false;
  addFlowState.tab = 'investment';
  addFlowState.result = null;
  addFlowState.prefill = null;
}

const ACCOUNTS = [
  { id: 'default', name: 'Default Brokerage' },
  { id: 'roth', name: 'Fidelity Roth' },
];

/* ─────────────  Markup  ───────────── */

test('card renders three flow tabs plus the Import-a-statement link', () => {
  resetState();
  const markup = String(renderAddFlow({ accounts: ACCOUNTS }));
  assert.deepEqual(ADD_FLOW_TABS.map(([id]) => id), ['investment', 'cash', 'property']);
  assert.match(markup, /data-add-tab="investment"[^>]*aria-selected="true"/);
  assert.match(markup, /data-add-tab="cash"[^>]*aria-selected="false"/);
  assert.match(markup, /data-add-tab="property"/);
  assert.match(markup, /Import a statement/);
  assert.match(markup, /href="#import-sync"/);
  assert.match(markup, /Add to portfolio/);
});

test('card starts closed; open state renders it visible', () => {
  resetState();
  assert.match(String(renderAddFlow({})), /data-add-card hidden/);
  addFlowState.open = true;
  assert.doesNotMatch(String(renderAddFlow({})), /data-add-card hidden/);
});

test('investment panel keeps cost basis visible and only dates behind More detail', () => {
  resetState();
  const markup = String(renderAddFlow({ accounts: ACCOUNTS }));

  // Two decisions up front: symbol, and either shares or current value.
  assert.match(markup, /name="symbol"[^>]*required/);
  assert.match(markup, /name="quantity"/);
  assert.match(markup, /name="value_usd"/);
  // Registry-backed autocomplete wiring.
  assert.match(markup, /list="portfolio-add-symbols"/);
  assert.match(markup, /<datalist id="portfolio-add-symbols">/);
  // Accounts include existing ones and the inline "New account…" option.
  assert.match(markup, /<option value="roth">Fidelity Roth<\/option>/);
  assert.match(markup, /value="__new__">New account…/);
  // Cost basis stays visible because it may be required when a quote is unavailable.
  const beforeMore = markup.slice(markup.indexOf('data-add-panel="investment"'), markup.indexOf('<details'));
  assert.match(beforeMore, /name="unit_cost"/);
  assert.match(beforeMore, /estimate is okay/i);
  // Acquisition date remains optional detail.
  assert.match(markup, /<summary>More detail<\/summary>/);
  const moreDetail = markup.slice(markup.indexOf('<details'), markup.indexOf('</details>'));
  assert.doesNotMatch(moreDetail, /name="unit_cost"/);
  assert.match(moreDetail, /name="acquired_date"/);
  // Buy/sell toggle for the inline "Record buy/sell" action.
  assert.match(markup, /name="action" value="BUY" checked/);
  assert.match(markup, /name="action" value="SELL"/);
});

test('cash panel is account + amount; property panel is label + value + type', () => {
  resetState();
  const markup = String(renderAddFlow({ accounts: ACCOUNTS }));
  const cash = markup.slice(markup.indexOf('data-add-panel="cash"'), markup.indexOf('data-add-panel="property"'));
  assert.match(cash, /name="amount_usd"[^>]*required/);
  assert.match(cash, /name="account_id"/);

  const property = markup.slice(markup.indexOf('data-add-panel="property"'));
  assert.match(property, /name="label"[^>]*required/);
  assert.match(property, /name="value_usd"[^>]*required/);
  assert.match(property, /name="asset_type"/);
  assert.match(property, /value="real_estate"/);
  assert.match(property, /value="vehicle"/);
});

test('only the active tab panel is visible', () => {
  resetState();
  addFlowState.tab = 'cash';
  const markup = String(renderAddFlow({ accounts: ACCOUNTS }));
  assert.match(markup, /data-add-panel="investment" hidden/);
  assert.doesNotMatch(markup, /data-add-panel="cash" hidden/);
  assert.match(markup, /data-add-panel="property" hidden/);
});

test('prefill lands in the investment panel (Record buy/sell path)', () => {
  resetState();
  addFlowState.prefill = { symbol: 'VTI', account: 'roth', action: 'SELL' };
  const markup = String(renderAddFlow({ accounts: ACCOUNTS }));
  assert.match(markup, /name="symbol"[^>]*value="VTI"/);
  assert.match(markup, /<option value="roth" selected>/);
  assert.match(markup, /value="SELL" checked/);
});

/* ─────────────  Result line  ───────────── */

test('success line shows the detail sentence; estimated basis adds the note', () => {
  const plain = String(renderAddResult({ detail: 'Recorded a buy of 4 VTI at $250.00 per share in Default Brokerage.' }));
  assert.match(plain, /Recorded a buy of 4 VTI/);
  assert.doesNotMatch(plain, /estimated/);

  const estimated = String(renderAddResult({ detail: 'Recorded a buy.', estimated_basis: true }));
  assert.match(estimated, /Cost basis was estimated from the current price/);
  assert.match(estimated, /Records &amp; tools/);
});

test('valuation-only success is honest without duplicating the estimated-basis message', () => {
  const markup = String(renderAddResult({
    detail: 'Added VTI at your $25,000.00 current-value estimate in Default Brokerage.',
    estimated_basis: true,
    valuation_only: true,
  }));

  assert.match(markup, /current-value estimate/);
  assert.match(markup, /your total is useful now/);
  assert.match(markup, /Add the real share count and cost/);
  assert.doesNotMatch(markup, /Cost basis was estimated from the current price/);
});

/* ─────────────  buildAddBody  ───────────── */

test('buildAddBody: investment with value only', () => {
  const body = buildAddBody('investment', {
    symbol: ' vti ', value_usd: '1000', account_id: 'default', action: 'BUY',
  });
  assert.deepEqual(body, { flow: 'investment', symbol: 'VTI', value_usd: 1000, account_id: 'default' });
});

test('buildAddBody: investment with quantity, basis, date, and SELL', () => {
  const body = buildAddBody('investment', {
    symbol: 'VTI', quantity: '2', unit_cost: '240', acquired_date: '2026-06-01',
    action: 'SELL', account_id: 'roth',
  });
  assert.equal(body.action, 'SELL');
  assert.equal(body.transfer, undefined);
  assert.equal(body.quantity, 2);
  assert.equal(body.unit_cost, 240);
  assert.equal(body.acquired_date, '2026-06-01');
});

test('buildAddBody: new account inline replaces account_id', () => {
  const body = buildAddBody('cash', {
    amount_usd: '500', account_id: '__new__', new_account_name: 'Ally Savings', new_account_type: 'cash',
  });
  assert.deepEqual(body, {
    flow: 'cash',
    amount_usd: 500,
    new_account: { name: 'Ally Savings', type: 'cash' },
  });
});

test('buildAddBody: property carries label, value, and type', () => {
  const body = buildAddBody('property', { label: ' Home ', value_usd: '450000', asset_type: 'real_estate' });
  assert.deepEqual(body, { flow: 'property', label: 'Home', value_usd: 450000, asset_type: 'real_estate' });
});

test('buildAddBody: blanks and non-numbers are simply omitted', () => {
  const body = buildAddBody('investment', { symbol: 'VTI', quantity: '', value_usd: 'abc', account_id: '' });
  assert.deepEqual(body, { flow: 'investment', symbol: 'VTI' });
});
