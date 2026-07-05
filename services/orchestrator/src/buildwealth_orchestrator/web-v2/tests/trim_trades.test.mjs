import test from 'node:test';
import assert from 'node:assert/strict';
import { renderTrimTradesPanel } from '../views/inbox/entries.js';

test('trim trades panel renders concrete instructions with tax notes', () => {
  const markup = String(renderTrimTradesPanel({
    action_payload: {
      suggested_action: {
        trades: [
          { symbol: 'NVDA', account_id: 'my_401k', tax_treatment: 'tax_deferred', sell_value_usd: 10000, quantity: 100, estimated_long_term_gain_usd: 0, estimated_short_term_gain_usd: 0 },
          { symbol: 'NVDA', account_id: 'my_taxable', tax_treatment: 'taxable', sell_value_usd: 5000, quantity: 50, estimated_long_term_gain_usd: 2500, estimated_short_term_gain_usd: 0 },
        ],
        trim_plan_status: 'ready',
        residual_usd: 0,
        trim_plan_notes: [],
      },
    },
  }));

  assert.match(markup, /Suggested trades/);
  assert.match(markup, /100 sh · \$10,000/);
  assert.match(markup, /my_401k/);
  assert.match(markup, /no tax due now/);
  assert.match(markup, /≈ \$2,500 realized gains/);
  assert.match(markup, /Execute at your broker/);
});

test('trim trades panel stays silent without a plan and honest without tradables', () => {
  assert.equal(String(renderTrimTradesPanel({ action_payload: { suggested_action: {} } })), '');

  const notesOnly = String(renderTrimTradesPanel({
    action_payload: { suggested_action: { trades: [], trim_plan_notes: ['DEMO_HOME is not a market-tradable position; reduce its weight by directing future contributions elsewhere.'] } },
  }));
  assert.match(notesOnly, /not a market-tradable position/);
});
