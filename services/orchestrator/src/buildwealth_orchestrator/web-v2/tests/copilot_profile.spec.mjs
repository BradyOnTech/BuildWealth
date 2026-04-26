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
  let chatPayload = null;
  let savedProfile = null;

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
      await route.fulfill(jsonResponse({
        ready_for_daily_review: false,
        completion_percent: 25,
        steps: [
          { key: 'income', title: 'Add income', status: 'pending' },
          { key: 'expenses', title: 'Add expenses', status: 'pending' },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/copilot/chat' && request.method() === 'POST') {
      chatPayload = request.postDataJSON();
      await route.fulfill(jsonResponse({
        conversation_id: 'conversation-profile-setup',
        answer: 'I drafted a profile update for your review.',
        created_at: '2026-04-26T12:00:00.000Z',
        model: 'browser-test',
        tool_calls: [
          {
            name: 'draft_financial_profile_update',
            arguments: {},
            result: {
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
            },
          },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/financial-profile' && request.method() === 'GET') {
      await route.fulfill(jsonResponse({
        income_items: [],
        expense_items: [],
        debt_items: [{ id: 'debt_keep', label: 'Student loan', balance_usd: 5000 }],
        goal_items: [],
        physical_assets: [],
        tax_profile: { filing_status: 'single' },
        flags: { no_debt: false },
        notes: 'Keep this note.',
      }));
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

  assert.ok(chatPayload, 'expected Copilot chat request to be sent');
  assert.match(chatPayload.question, /Help me fill out my financial profile/);
  assert.equal(chatPayload.use_live_snapshot, false);

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
});
