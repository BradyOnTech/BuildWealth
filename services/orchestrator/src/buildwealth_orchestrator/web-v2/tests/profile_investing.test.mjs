import test from 'node:test';
import assert from 'node:assert/strict';
import { renderInvesting } from '../views/profile/investing.js';

test('investing: renders all guardrail rows with plain-language labels', () => {
  const ui = { profile: { investment_policy: {} } };
  const markup = String(renderInvesting(ui));
  for (const label of [
    'Single-investment limit',
    'Single-sector limit',
    'Minimum cash cushion',
    'Risk comfort',
    'Tax sensitivity',
    'Simplicity preference',
    'Required research confidence',
  ]) {
    assert.match(markup, new RegExp(label.replace(/[-]/g, '[-]')));
  }
  // Restricted symbols / sectors blocks render with empty hints
  assert.match(markup, /No symbols restricted/);
  assert.match(markup, /No sectors restricted/);
});

test('investing: pre-fills numeric and select values from existing policy', () => {
  const ui = {
    profile: {
      investment_policy: {
        max_single_symbol_exposure_pct: 10,
        minimum_cash_runway_months: 6,
        risk_tolerance: 'moderate',
        tax_sensitivity: 'high',
        restricted_symbols: ['XOM', 'BP'],
        restricted_sectors: ['tobacco'],
      },
    },
  };
  const markup = String(renderInvesting(ui));
  // Numeric values land in the corresponding inputs
  assert.match(markup, /value="10"/);
  assert.match(markup, /value="6"/);
  // Selects mark the right option as selected
  assert.match(markup, /value="moderate" selected/);
  assert.match(markup, /value="high" selected/);
  // Restricted lists render every chip
  assert.match(markup, /XOM/);
  assert.match(markup, /BP/);
  assert.match(markup, /tobacco/);
});

test('investing: links to Copilot for "help me choose"', () => {
  const ui = { profile: {} };
  const markup = String(renderInvesting(ui));
  assert.match(markup, /Ask Copilot to help me choose/);
  assert.match(markup, /href="#copilot\?intent=investment-policy"/);
});
