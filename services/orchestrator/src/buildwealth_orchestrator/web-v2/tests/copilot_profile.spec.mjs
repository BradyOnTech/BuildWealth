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

test('Copilot guides profile setup, renders a draft, and applies the reviewed patch', async ({ page }) => {
  const chatPayloads = [];
  let onboardingStatusCalls = 0;
  let savedProfile = null;
  const baseProfile = {
    income_items: [],
    expense_items: [],
    debt_items: [{ id: 'debt_keep', label: 'Student loan', balance_usd: 5000 }],
    goal_items: [],
    physical_assets: [],
    tax_profile: { filing_status: 'single' },
    flags: { no_debt: false },
    notes: 'Keep this note.',
  };

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

    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      onboardingStatusCalls += 1;
      const status = savedProfile
        ? {
            ready_for_daily_review: false,
            completion_percent: 75,
            steps: [
              { key: 'income', title: 'Add income', status: 'complete' },
              { key: 'expenses', title: 'Add expenses', status: 'complete' },
              { key: 'goals', title: 'Add goals', status: 'pending' },
            ],
          }
        : {
            ready_for_daily_review: false,
            completion_percent: 25,
            steps: [
              { key: 'income', title: 'Add income', status: 'pending' },
              { key: 'expenses', title: 'Add expenses', status: 'pending' },
            ],
          };
      await route.fulfill(jsonResponse(status));
      return;
    }

    if (url.pathname === '/api/copilot/chat' && request.method() === 'POST') {
      const chatPayload = request.postDataJSON();
      chatPayloads.push(chatPayload);
      const isGoalPrompt = /add financial goals/i.test(chatPayload.question || '');
      const toolResult = isGoalPrompt
        ? {
            draft_kind: 'financial_profile_update',
            summary: 'Drafted a financial goal for review.',
            section_counts: { goal_items: 1 },
            patch_payload: {
              goal_items: [{
                id: 'goal_home_down_payment',
                label: 'Home down payment',
                target_amount_usd: 80000,
                target_date: '2028-06-01T00:00:00.000Z',
                priority: 'high',
                notes: 'Keep this goal separate from emergency reserves.',
              }],
            },
            proposed_profile: {
              ...(savedProfile || baseProfile),
              goal_items: [{
                id: 'goal_home_down_payment',
                label: 'Home down payment',
                target_amount_usd: 80000,
                target_date: '2028-06-01T00:00:00.000Z',
                priority: 'high',
                notes: 'Keep this goal separate from emergency reserves.',
              }],
            },
            requires_confirmation: true,
          }
        : {
            draft_kind: 'financial_profile_update',
            summary: 'Drafted profile updates for income and expenses.',
            section_counts: { income_items: 1, expense_items: 1 },
            patch_payload: {
              income_items: [{ id: 'income_salary', label: 'Salary', monthly_amount_usd: 11000 }],
              expense_items: [{ id: 'expense_rent', label: 'Rent', monthly_amount_usd: 2600 }],
            },
            proposed_profile: {
              income_items: [{ id: 'income_salary', label: 'Salary', monthly_amount_usd: 11000 }],
              expense_items: [{ id: 'expense_rent', label: 'Rent', monthly_amount_usd: 2600 }],
              debt_items: [],
              goal_items: [],
              physical_assets: [],
              tax_profile: {},
              flags: {},
              notes: '',
            },
            requires_confirmation: true,
          };
      await route.fulfill(jsonResponse({
        conversation_id: isGoalPrompt ? 'conversation-goal-setup' : 'conversation-profile-setup',
        answer: 'I drafted a profile update for your review.',
        created_at: '2026-04-26T12:00:00.000Z',
        model: 'browser-test',
        tool_calls: [
          {
            name: 'draft_financial_profile_update',
            arguments: {},
            result: toolResult,
          },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/financial-profile' && request.method() === 'GET') {
      await route.fulfill(jsonResponse(savedProfile || baseProfile));
      return;
    }

    if (url.pathname === '/api/financial-profile' && request.method() === 'PUT') {
      savedProfile = request.postDataJSON();
      await route.fulfill(jsonResponse(savedProfile));
      return;
    }

    await route.fulfill(jsonResponse({ detail: `Unhandled test route: ${request.method()} ${url.pathname}` }, 404));
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('http://buildwealth-v2.test/#copilot');

  const onboardingButton = page.getByRole('button', { name: /fill it out with copilot/i });
  await onboardingButton.waitFor({ state: 'visible' });
  await onboardingButton.click();

  const textarea = page.locator('#composer-textarea');
  const draft = await textarea.inputValue();
  assert.match(draft, /get_onboarding_status/);
  assert.match(draft, /draft_financial_profile_update/);
  assert.match(draft, /do not save anything/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Review profile update').waitFor({ state: 'visible' });
  await page.getByText('$11,000').waitFor({ state: 'visible' });
  await page.getByText('$2,600').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 1);
  assert.match(chatPayloads[0].question, /Help me fill out my financial profile/);
  assert.equal(chatPayloads[0].use_live_snapshot, false);

  await page.getByRole('button', { name: /apply profile update/i }).click();
  await page.getByText('Profile update applied').waitFor({ state: 'visible' });

  assert.ok(savedProfile, 'expected profile update request to be sent');
  assert.deepEqual(savedProfile.income_items, [
    { id: 'income_salary', label: 'Salary', monthly_amount_usd: 11000 },
  ]);
  assert.deepEqual(savedProfile.expense_items, [
    { id: 'expense_rent', label: 'Rent', monthly_amount_usd: 2600 },
  ]);
  assert.deepEqual(savedProfile.debt_items, [
    { id: 'debt_keep', label: 'Student loan', balance_usd: 5000 },
  ]);
  assert.deepEqual(savedProfile.tax_profile, { filing_status: 'single' });
  assert.equal(savedProfile.notes, 'Keep this note.');
  assert.equal(onboardingStatusCalls, 2);

  await page.getByRole('button', { name: /new conversation/i }).click();
  await page.getByText('Your profile is 75% complete. Next: Add goals.').waitFor({ state: 'visible' });

  const goalsButton = page.getByRole('button', { name: /add goals with copilot/i });
  await goalsButton.click();

  const goalsDraft = await textarea.inputValue();
  assert.match(goalsDraft, /Help me add financial goals/);
  assert.match(goalsDraft, /goal_items/);
  assert.match(goalsDraft, /target_amount_usd/);
  assert.match(goalsDraft, /target_date/);
  assert.match(goalsDraft, /priority/);
  assert.match(goalsDraft, /do not save anything/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Home down payment').waitFor({ state: 'visible' });
  await page.getByText('$80,000').waitFor({ state: 'visible' });
  await page.getByText('Target Jun 1, 2028 · High priority').waitFor({ state: 'visible' });
  await page.getByText('Keep this goal separate from emergency reserves.').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 2);
  assert.match(chatPayloads[1].question, /Help me add financial goals/);

  await page.locator('[data-profile-draft]').last().click();
  await page.getByText('Profile update applied').last().waitFor({ state: 'visible' });

  assert.deepEqual(savedProfile.goal_items, [{
    id: 'goal_home_down_payment',
    label: 'Home down payment',
    target_amount_usd: 80000,
    target_date: '2028-06-01T00:00:00.000Z',
    priority: 'high',
    notes: 'Keep this goal separate from emergency reserves.',
  }]);
  assert.deepEqual(savedProfile.income_items, [
    { id: 'income_salary', label: 'Salary', monthly_amount_usd: 11000 },
  ]);
});
