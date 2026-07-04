import test from 'node:test';
import assert from 'node:assert/strict';
import { renderInlineForm } from '../views/inbox/forms.js';

const ITEM = {
  id: 'rec-1',
  title: 'Trim the concentrated position',
  action_payload: {
    decision_closure: {
      pre_mortem: {
        expected_benefit: 'Concentration drops below the cap.',
        review_date: '2026-06-20T00:00:00+00:00',
      },
    },
  },
};

const PREFILL = {
  status: 'ready',
  applied_at: '2026-06-01T00:00:00+00:00',
  observation_window_days: 33,
  baseline_value_usd: 500000,
  current_value_usd: 520000,
  suggested_future_value_delta_usd: 20000,
  expected_future_value_delta_usd: 15000,
  measurement_source: 'portfolio_sync',
  warnings: ['Portfolio-level change includes contributions and market moves — attribute it to this decision with judgment.'],
};

test('outcome form pre-fills measured values with provenance', () => {
  const markup = String(renderInlineForm(ITEM, { mode: 'outcome', busy: false, error: null, prefill: PREFILL }, {}));

  assert.match(markup, /Measured for you/);
  assert.match(markup, /name="future_value_delta_usd"[^>]*value="20000"/);
  assert.match(markup, /name="measurement_window_days"[^>]*value="33"/);
  assert.match(markup, /name="measurement_source"[^>]*value="portfolio_sync"/);
  assert.match(markup, /\$500,000/);
  assert.match(markup, /\$520,000/);
  assert.match(markup, /expected \+\$15,000/);
  assert.match(markup, /contributions and market moves/);
});

test('outcome form works without a prefill', () => {
  const bare = String(renderInlineForm(ITEM, { mode: 'outcome', busy: false, error: null, prefill: null }, {}));
  assert.doesNotMatch(bare, /Measured for you/);
  assert.match(bare, /name="future_value_delta_usd"(?![^>]*value=)/);

  const unavailable = String(renderInlineForm(ITEM, { mode: 'outcome', busy: false, error: null, prefill: { status: 'unavailable' } }, {}));
  assert.doesNotMatch(unavailable, /Measured for you/);
});
