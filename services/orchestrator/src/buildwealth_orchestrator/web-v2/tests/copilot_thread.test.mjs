import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { renderThread } from '../views/copilot/thread.js';

test('copilot thread renders financial profile draft review card', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I drafted the profile update for review.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'draft_financial_profile_update',
            arguments: {},
            result: {
              draft_kind: 'financial_profile_update',
              summary: 'Drafted financial profile updates for income items, expense items.',
              section_counts: { income_items: 1, expense_items: 1, flags: 1 },
              patch_payload: {
                income_items: [{ label: 'Salary', monthly_amount_usd: 11000 }],
                expense_items: [{ label: 'Rent', monthly_amount_usd: 2600 }],
                flags: { no_debt: true },
              },
              proposed_profile: {
                income_items: [{ label: 'Salary', monthly_amount_usd: 11000 }],
                expense_items: [{ label: 'Rent', monthly_amount_usd: 2600 }],
                debt_items: [],
                goal_items: [],
                physical_assets: [],
                tax_profile: {},
                flags: { no_debt: true },
                notes: '',
              },
              requires_confirmation: true,
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Review profile update/);
  assert.match(html, /Income items/);
  assert.match(html, /\$11,000/);
  assert.match(html, /Expense items/);
  assert.match(html, /\$2,600/);
  assert.match(html, /No debt/);
  assert.match(html, /data-profile-draft=/);
  assert.match(html, /Apply profile update/);
});

test('copilot view wires profile draft apply action to profile API', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');
  const apiSource = readFileSync(resolve(currentDir, '../lib/api.js'), 'utf8');

  assert.match(apiSource, /updateProfile/);
  assert.match(apiSource, /profile:/);
  assert.match(apiSource, /\/api\/financial-profile/);
  assert.match(copilotSource, /\[data-profile-draft\]/);
  assert.match(copilotSource, /api\.profile/);
  assert.match(copilotSource, /mergeProfileDraft/);
  assert.match(copilotSource, /api\.updateProfile/);
  assert.match(copilotSource, /Profile update applied/);
});

test('copilot view exposes guided profile onboarding entry point', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');
  const apiSource = readFileSync(resolve(currentDir, '../lib/api.js'), 'utf8');

  assert.match(apiSource, /onboarding/);
  assert.match(apiSource, /\/api\/onboarding\/status/);
  assert.match(copilotSource, /loadOnboarding/);
  assert.match(copilotSource, /data-profile-onboarding-prompt/);
  assert.match(copilotSource, /get_onboarding_status/);
  assert.match(copilotSource, /draft_financial_profile_update/);
  assert.match(copilotSource, /do not save/);
});
