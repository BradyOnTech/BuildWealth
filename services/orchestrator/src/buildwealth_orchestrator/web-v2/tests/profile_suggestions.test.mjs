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

const { suggestionLine, getSuggestion } = await import('../views/profile/suggestions.js');
const { renderTaxes } = await import('../views/profile/taxes.js');
const { renderInvesting } = await import('../views/profile/investing.js');

const SUGGESTIONS = {
  'tax_profile.marginal_tax_rate': {
    field_path: 'tax_profile.marginal_tax_rate',
    value: 0.22,
    display: '22%',
    basis: 'computed',
    explanation: 'Estimated from $90,000/yr income, filing single, 2026 federal brackets.',
  },
  'investment_policy.risk_tolerance': {
    field_path: 'investment_policy.risk_tolerance',
    value: 'aggressive',
    display: 'aggressive',
    basis: 'computed',
    explanation: 'At 30, a long horizon usually supports growth risk — pick what lets you sleep.',
  },
  'investment_policy.target_asset_class_allocation_pct': {
    field_path: 'investment_policy.target_asset_class_allocation_pct',
    value: { equity: 80, fixed_income: 15, real_estate: 0, cash: 5 },
    display: '80% stocks / 15% bonds / 5% cash',
    basis: 'computed',
    explanation: 'Age-based starting point.',
    presets: [
      { name: 'Three-fund 80/20', mix: { equity: 80, fixed_income: 20, real_estate: 0, cash: 0 } },
      { name: 'Classic 60/40', mix: { equity: 60, fixed_income: 40, real_estate: 0, cash: 0 } },
    ],
  },
};

test('suggestionLine renders a Use button with target + converted value', () => {
  const markup = String(suggestionLine(SUGGESTIONS, 'tax_profile.marginal_tax_rate', {
    target: 'taxes-marginal',
    format: v => (Number(v) * 100).toFixed(1).replace(/\.0$/, ''),
  }));
  assert.match(markup, /Use 22%/);
  assert.match(markup, /data-suggestion-target="taxes-marginal"/);
  assert.match(markup, /data-suggestion-value="22"/);
  assert.match(markup, /Estimated from \$90,000\/yr income/);
  assert.equal(String(suggestionLine(SUGGESTIONS, 'tax_profile.state_tax_rate', { target: 'x' })), '');
});

test('taxes form shows the suggestion and the reassurance banner', () => {
  const markup = String(renderTaxes({
    profile: { tax_profile: {}, flags: {} },
    suggestions: SUGGESTIONS,
  }));
  assert.match(markup, /Use 22%/);
  assert.match(markup, /Don't know these\? Use the estimates/);
});

test('taxes form stays quiet when nothing is estimable', () => {
  const markup = String(renderTaxes({ profile: { tax_profile: {}, flags: {} }, suggestions: {} }));
  assert.doesNotMatch(markup, /Use the estimates/);
  assert.doesNotMatch(markup, /data-use-suggestion/);
});

test('investing renders guardrail suggestion and target-mix presets', () => {
  const markup = String(renderInvesting({
    profile: { investment_policy: {} },
    suggestions: SUGGESTIONS,
  }));
  assert.match(markup, /Use aggressive/);
  assert.match(markup, /data-suggestion-target="inv-risk"/);
  assert.match(markup, /Three-fund 80\/20/);
  assert.match(markup, /data-mix-preset=/);
});

test('getSuggestion tolerates malformed maps', () => {
  assert.equal(getSuggestion(null, 'x'), null);
  assert.equal(getSuggestion({ x: 'not-an-object' }, 'x'), null);
});
