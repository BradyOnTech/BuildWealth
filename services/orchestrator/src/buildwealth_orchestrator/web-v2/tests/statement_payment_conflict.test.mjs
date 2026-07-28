import assert from 'node:assert/strict';
import test from 'node:test';

import { renderStatementClarifications } from '../views/import_sync/budget_reader.js';
import { renderStatementPaymentConflict } from '../views/copilot.js';

const candidate = {
  id: 'candidate-payment-1',
  lifecycle_state: 'pending_review',
  metadata: {
    clarification_kind: 'statement_payment_conflict',
    question: 'Is "ACH Withdrawal" at $410.00 per month the same payment as "Fishing boat loan" already in your Profile, or is it a separate expense?',
    statement_suggestion: {
      label: 'ACH Withdrawal',
      monthly_amount_usd: 410,
    },
    profile_matches: [
      {
        kind: 'debt',
        id: 'debt-boat',
        label: 'Fishing boat loan',
        monthly_amount_usd: 410,
      },
    ],
  },
};

test('statement apply result routes held payment questions to Copilot', () => {
  const markup = String(renderStatementClarifications({
    clarifications: [
      {
        candidate_id: candidate.id,
        question: candidate.metadata.question,
        copilot_href: `#copilot?intent=statement-payment-conflict&focus=${candidate.id}`,
      },
    ],
  }));

  assert.match(markup, /Possible duplicate payments/);
  assert.match(markup, /These were not added to Profile/);
  assert.match(markup, /Answer with Copilot/);
  assert.match(markup, /intent=statement-payment-conflict/);
});

test('Copilot asks the focused payment question before any mutation', () => {
  const markup = String(renderStatementPaymentConflict(candidate));

  assert.match(markup, /payment held safely/);
  assert.match(markup, /ACH Withdrawal/);
  assert.match(markup, /Fishing boat loan/);
  assert.match(markup, /has not been added/);
  assert.match(markup, /Same payment/);
  assert.match(markup, /Separate expense/);
  assert.match(markup, /Ignore this line/);
});

test('Copilot explains that a same-payment answer added nothing', () => {
  const markup = String(renderStatementPaymentConflict(
    { ...candidate, lifecycle_state: 'applied' },
    {
      result: {
        resolution: 'same_as_existing',
        added_expenses: 0,
      },
    },
  ));

  assert.match(markup, /No new expense was added/);
  assert.match(markup, /Back to Import/);
  assert.doesNotMatch(markup, /data-statement-conflict-resolution/);
});
