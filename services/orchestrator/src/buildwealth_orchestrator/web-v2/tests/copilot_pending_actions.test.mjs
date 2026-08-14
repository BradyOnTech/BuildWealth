import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderThread } from '../views/copilot/thread.js';

const CURRENT_DIR = dirname(fileURLToPath(import.meta.url));
const COPILOT_SOURCE = readFileSync(resolve(CURRENT_DIR, '../views/copilot.js'), 'utf8');
const API_SOURCE = readFileSync(resolve(CURRENT_DIR, '../lib/api.js'), 'utf8');

function profileDraftMessage({
  status = 'pending',
  actionId = 'pfa_profile_contract',
} = {}) {
  return {
    id: `assistant-${status}`,
    role: 'assistant',
    content: 'I prepared a profile update for your review.',
    created_at: '2026-07-31T12:00:00.000Z',
    metadata: {
      tool_calls: [
        {
          name: 'draft_financial_profile_update',
          arguments: {},
          result: {
            draft_kind: 'financial_profile_update',
            summary: 'Add the reviewed salary item.',
            proposed_profile: {
              income_items: [{ label: 'Salary', monthly_amount_usd: 10_000 }],
            },
            // This must remain display data, never authority encoded into a control.
            patch_payload: {
              income_items: [{ label: 'AUTHORITY_LEAK_SENTINEL', monthly_amount_usd: 10_000 }],
            },
            pending_action: {
              action_id: actionId,
              status,
              expires_at: '2026-07-31T12:30:00.000Z',
            },
            requires_confirmation: true,
          },
        },
      ],
    },
  };
}

function functionSource(source, functionName, nextFunctionName) {
  const start = source.indexOf(`async function ${functionName}(`);
  const asyncEnd = source.indexOf(`async function ${nextFunctionName}(`, start + 1);
  const syncEnd = source.indexOf(`function ${nextFunctionName}(`, start + 1);
  const end = [asyncEnd, syncEnd].filter(index => index !== -1).sort((a, b) => a - b)[0] ?? -1;
  assert.notEqual(start, -1, `${functionName} must exist`);
  assert.notEqual(end, -1, `${nextFunctionName} must follow ${functionName}`);
  return source.slice(start, end);
}

test('pending profile controls carry only the opaque action id, never patch authority', () => {
  const output = String(renderThread([profileDraftMessage()]));
  const applyButton = output.match(/<button[^>]*data-pending-action-apply="[^"]+"[^>]*>/)?.[0] || '';
  const rejectButton = output.match(/<button[^>]*data-pending-action-reject="[^"]+"[^>]*>/)?.[0] || '';

  assert.match(applyButton, /data-pending-action-apply="pfa_profile_contract"/);
  assert.match(rejectButton, /data-pending-action-reject="pfa_profile_contract"/);
  assert.doesNotMatch(applyButton, /data-(?:patch|payload|profile)=|AUTHORITY_LEAK_SENTINEL/i);
  assert.doesNotMatch(rejectButton, /data-(?:patch|payload|profile)=|AUTHORITY_LEAK_SENTINEL/i);
  assert.doesNotMatch(output, /AUTHORITY_LEAK_SENTINEL/);
});

test('terminal pending-action states are durable and non-actionable', () => {
  const expectedCopy = {
    applied: /Applied to your financial profile\./,
    rejected: /Declined\. No profile change was made\./,
    stale: /Needs a fresh review because your profile changed/,
    expired: /Expired\. Ask Copilot to prepare a fresh review/,
  };

  for (const [status, copy] of Object.entries(expectedCopy)) {
    const output = String(renderThread([
      profileDraftMessage({ status, actionId: `pfa_profile_${status}` }),
    ]));

    assert.match(output, new RegExp(`pending-action-card ${status}`));
    assert.match(output, copy);
    assert.match(output, /role="status"/);
    assert.doesNotMatch(output, /data-pending-action-apply=/);
    assert.doesNotMatch(output, /data-pending-action-reject=/);
  }
});

test('legacy thesis drafts remain review-only and expose no save authority', () => {
  const output = String(renderThread([{
    id: 'assistant-thesis',
    role: 'assistant',
    content: 'I drafted a thesis revision for review.',
    metadata: {
      tool_calls: [{
        name: 'draft_watchlist_thesis_revision',
        arguments: { symbol: 'VTI' },
        result: {
          draft_kind: 'watchlist_thesis_revision',
          target: { type: 'watchlist', symbol: 'VTI', data_source: 'OPENBB' },
          current: { thesis: 'Broad market exposure remains the baseline.' },
          proposed: {
            thesis: 'Keep the baseline, subject to current concentration evidence.',
            review_window_days: 45,
          },
          rationale: 'The evidence should be refreshed before changing the saved thesis.',
        },
      }],
    },
  }]));

  assert.match(output, /legacy chat draft is review-only/i);
  assert.match(output, /Open Research/);
  assert.doesNotMatch(output, /data-thesis-draft|data-thesis-save|Save (?:this )?(?:draft|revision|thesis)/i);
});

test('Copilot sends interaction mode and mutations use only pending-action APIs', () => {
  assert.match(COPILOT_SOURCE, /interaction_mode:\s*ui\.interactionMode/);
  assert.match(COPILOT_SOURCE, /persist_interaction_mode:\s*true/);

  const applySource = functionSource(COPILOT_SOURCE, 'applyPendingAction', 'rejectPendingAction');
  const rejectSource = functionSource(COPILOT_SOURCE, 'rejectPendingAction', 'closePickersOnOutsideClick');
  assert.match(applySource, /api\.applyCopilotPendingAction\(actionId\)/);
  assert.match(rejectSource, /api\.rejectCopilotPendingAction\(actionId\)/);
  assert.doesNotMatch(`${applySource}\n${rejectSource}`, /api\.(?:updateProfile|saveWatchlistThesisRevision|saveDossierThesisRevision)/);

  assert.match(
    API_SOURCE,
    /applyCopilotPendingAction:[\s\S]*?\/api\/copilot\/pending-actions\/\$\{encodeURIComponent\(id\)\}\/apply/,
  );
  assert.match(
    API_SOURCE,
    /rejectCopilotPendingAction:[\s\S]*?\/api\/copilot\/pending-actions\/\$\{encodeURIComponent\(id\)\}\/reject/,
  );
});

test('typed stream activity is keyed by activity id and renders lifecycle failure', () => {
  assert.match(COPILOT_SOURCE, /key:\s*event\.activity_id\s*\|\|\s*event\.tool_call_id/);
  assert.match(COPILOT_SOURCE, /event\.lifecycle_status/);
  assert.match(COPILOT_SOURCE, /event\.status === 'error'\s*\?\s*'failed'/);

  const output = String(renderThread([], {
    streaming: {
      stage: 'thinking',
      activities: [{
        key: 'activity_tool_123',
        kind: 'tool',
        name: 'get_financial_profile',
        status: 'failed',
      }],
    },
  }));

  assert.match(output, /copilot-activity-row failed/);
  assert.match(output, /<span class="copilot-activity-icon" aria-hidden="true">!<\/span>/);
  assert.match(output, /Reviewing your financial profile/);
  assert.doesNotMatch(output, /get_financial_profile/);
});

test('exact context references are sent separately from focus and remain removable', () => {
  assert.match(
    COPILOT_SOURCE,
    /context_references:\s*normalizeContextReferences\(ui\.contextReferences\)/,
  );
  assert.match(COPILOT_SOURCE, /data-remove-context-reference=/);
  assert.match(COPILOT_SOURCE, /Exact references/);
  assert.doesNotMatch(
    COPILOT_SOURCE,
    /priority_note:\s*JSON\.stringify\(ui\.contextReferences\)/,
  );
});

test('thread shows exact references on the user turn and durable source trace', () => {
  const output = String(renderThread([
    {
      id: 'user-with-reference',
      role: 'user',
      content: 'Explain this exact decision.',
      metadata: {
        context_references: [{
          type: 'recommendation',
          id: 'rec-123',
          label: 'Review contribution increase',
        }],
      },
    },
    {
      id: 'assistant-with-reference',
      role: 'assistant',
      content: 'Here is the evidence-backed explanation.',
      metadata: {
        context_trace: {
          explicit_context_references: {
            count: 1,
            references: [{
              type: 'recommendation',
              id: 'rec-123',
              label: 'Review contribution increase',
              source_ref: 'recommendation:rec-123',
            }],
          },
        },
      },
    },
  ]));

  assert.match(output, /message-context-references/);
  assert.match(output, /Review contribution increase/);
  assert.match(output, /1 exact reference/);
  assert.match(output, /#inbox\?focus=rec-123/);
});
