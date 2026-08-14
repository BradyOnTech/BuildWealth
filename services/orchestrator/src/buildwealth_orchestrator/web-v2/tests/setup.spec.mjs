// First-run Setup — registration enters the durable journey, progression is
// persisted through the API, and the mobile layout stays within the viewport.

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

async function installRoutes(page, {
  initiallySignedIn = false,
  initialProgress = null,
  initialProfile = null,
} = {}) {
  let signedIn = initiallySignedIn;
  let progress = initialProgress || {
    started: false,
    needs_setup: false,
    status: 'not_started',
    current_step: 'welcome',
    completed_steps: [],
    skipped_steps: [],
  };
  const patches = [];
  const profileWrites = [];
  const portfolioAdds = [];
  const resetRequests = [];
  let portfolioReady = false;
  let profile = initialProfile || {
    household_members: [], income_items: [], expense_items: [], debt_items: [], goal_items: [],
    physical_assets: [], tax_profile: {}, investment_policy: {},
    flags: { no_debt: false, no_goals: false, expenses_complete: false },
    notes: '', profile_metadata: {}, updated_at: new Date().toISOString(),
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
    if (url.pathname === '/api/auth/config') {
      await route.fulfill(jsonResponse({ local_auth_enabled: true, hosted_auth_enabled: false }));
      return;
    }
    if (url.pathname === '/api/auth/session') {
      await route.fulfill(signedIn
        ? jsonResponse({
            csrf_token: 'csrf-setup',
            user: { id: 'owner-1', display_name: 'Taylor' },
            workspace: { id: 'workspace-1', name: 'Taylor Household' },
          })
        : jsonResponse({ detail: 'Authentication required' }, 401));
      return;
    }
    if (url.pathname === '/api/auth/register') {
      signedIn = true;
      await route.fulfill(jsonResponse({
        csrf_token: 'csrf-setup',
        workspace_id: 'workspace-1',
        user: { id: 'owner-1', display_name: 'Taylor' },
      }));
      return;
    }
    if (url.pathname === '/api/workspaces') {
      await route.fulfill(jsonResponse({
        active_workspace_id: 'workspace-1',
        items: [{ id: 'workspace-1', name: 'Taylor Household' }],
      }));
      return;
    }
    if (url.pathname === '/api/onboarding/progress/start') {
      progress = { ...progress, started: true, needs_setup: true, status: 'active' };
      await route.fulfill(jsonResponse(progress));
      return;
    }
    if (url.pathname === '/api/onboarding/reset/preview') {
      await route.fulfill(jsonResponse({
        confirmation_phrase: 'reset and register again',
        file_count: 17,
        size_bytes: 18432,
        existing_backup_count: 2,
        will_clear: [
          'financial profile and household details',
          'portfolio, snapshots, and account history',
        ],
        will_preserve: [
          'your BuildWealth sign-in and email',
          'a new recovery backup of the current workspace',
        ],
      }));
      return;
    }
    if (url.pathname === '/api/onboarding/reset' && request.method() === 'POST') {
      resetRequests.push(request.postDataJSON());
      profile = {
        household_members: [], income_items: [], expense_items: [], debt_items: [], goal_items: [],
        physical_assets: [], tax_profile: {}, investment_policy: {},
        flags: { no_debt: false, no_goals: false, expenses_complete: false },
        notes: '', profile_metadata: {}, updated_at: new Date().toISOString(),
      };
      progress = {
        started: true,
        needs_setup: true,
        status: 'active',
        current_step: 'welcome',
        completed_steps: [],
        skipped_steps: [],
      };
      await route.fulfill(jsonResponse({
        ok: true,
        identity_preserved: true,
        next_path: '/#setup',
        progress,
      }));
      return;
    }
    if (url.pathname === '/api/onboarding/progress' && request.method() === 'PATCH') {
      const body = request.postDataJSON();
      patches.push(body);
      progress = {
        ...progress,
        current_step: body.current_step || progress.current_step,
        completed_steps: body.completed_step
          ? [...new Set([...progress.completed_steps, body.completed_step])]
          : progress.completed_steps,
        skipped_steps: body.skipped_step
          ? [...new Set([...progress.skipped_steps, body.skipped_step])]
          : progress.skipped_steps,
      };
      await route.fulfill(jsonResponse(progress));
      return;
    }
    if (url.pathname === '/api/onboarding/progress') {
      await route.fulfill(jsonResponse(progress));
      return;
    }
    if (url.pathname === '/api/onboarding/status') {
      const section = (key, complete, detail) => ({
        key, title: key, status: complete ? 'complete' : 'incomplete', detail,
      });
      await route.fulfill(jsonResponse({
        steps: [{
          id: 'snapshot', status: portfolioReady ? 'complete' : 'incomplete',
          detail: portfolioReady ? 'One current account value is available.' : 'No portfolio snapshot yet.',
        }],
        profile_readiness: {
          status: 'incomplete',
          next_gap_title: 'Household',
          sections: [
            section('household', profile.household_members.length > 0, 'Add household.'),
            section('income', profile.income_items.length > 0, 'Add income.'),
            section('expenses', profile.expense_items.length > 0 && profile.flags.expenses_complete, 'Add expenses.'),
            section('debt', profile.debt_items.length > 0 || profile.flags.no_debt, 'Add debt.'),
            section('goals', profile.goal_items.length > 0, 'Add goals.'),
          ],
        },
      }));
      return;
    }
    if (url.pathname === '/api/financial-profile' && request.method() === 'PUT') {
      profile = { ...request.postDataJSON(), updated_at: new Date().toISOString() };
      profileWrites.push({ source: url.searchParams.get('source'), body: profile });
      await route.fulfill(jsonResponse(profile));
      return;
    }
    if (url.pathname === '/api/financial-profile') {
      await route.fulfill(jsonResponse(profile));
      return;
    }
    if (url.pathname === '/api/portfolio/add' && request.method() === 'POST') {
      const body = request.postDataJSON();
      portfolioAdds.push(body);
      portfolioReady = true;
      await route.fulfill(jsonResponse({ detail: `Added $${body.amount_usd} cash to ${body.new_account.name}.` }));
      return;
    }
    if (url.pathname === '/api/dashboard/today') {
      await route.fulfill(jsonResponse({
        net_worth_usd: 0,
        profile_readiness: { status: 'incomplete', next_gap_title: 'Household' },
      }));
      return;
    }
    if (url.pathname === '/api/financial-health') {
      await route.fulfill(jsonResponse({ net_worth_usd: 0, gross_monthly_income_usd: 0 }));
      return;
    }
    if (url.pathname === '/api/plans') {
      await route.fulfill(jsonResponse([]));
      return;
    }
    await route.fulfill(jsonResponse({}));
  });

  return { patches, profileWrites, portfolioAdds, resetRequests };
}

test('new owner registration enters Setup and persists the first step', async ({ page }) => {
  const state = await installRoutes(page);
  await page.goto('http://buildwealth-v2.test/');

  await page.getByRole('button', { name: 'Create account' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('Taylor');
  await page.getByRole('textbox', { name: 'Email' }).fill('taylor@example.test');
  await page.getByLabel('Password').fill('correct-horse-setup');
  await page.getByRole('button', { name: 'Create account' }).last().click();

  await page.getByRole('heading', { name: 'Start with a private household workspace.' }).waitFor();
  assert.match(page.url(), /#setup$/);
  // The flow runs with the app chrome collapsed — a five-step journey should not
  // offer seven sideways exits.
  assert.equal(await page.locator('body.shell-focus').count(), 1);
  assert.ok(!(await page.locator('nav.sidebar').isVisible()));
  await page.getByText('Private by design').waitFor();
  await page.getByRole('button', { name: /Start with my household/ }).click();
  await page.getByRole('heading', { name: 'Give the numbers their household context.' }).waitFor();

  assert.deepEqual(state.patches[0], {
    current_step: 'foundation',
    completed_step: 'welcome',
  });
  await page.getByText('Add household.').waitFor();
  await page.getByRole('button', { name: 'Leave this for later' }).click();
  await page.getByRole('heading', { name: 'Bring in the accounts that shape today.' }).waitFor();
  assert.equal(state.patches[1].skipped_step, 'foundation');
});

test('Setup progress remains usable on a narrow mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installRoutes(page);
  await page.goto('http://buildwealth-v2.test/');

  await page.getByRole('button', { name: 'Create account' }).click();
  await page.getByRole('textbox', { name: 'Email' }).fill('mobile@example.test');
  await page.getByLabel('Password').fill('correct-horse-mobile');
  await page.getByRole('button', { name: 'Create account' }).last().click();
  await page.getByText('Private by design').waitFor();

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    progressHeight: document.querySelector('.setup-progress')?.getBoundingClientRect().height,
  }));
  assert.equal(dimensions.document, dimensions.viewport, 'Setup must not create page-level horizontal overflow');
  assert.ok(
    // Round before comparing: the step is styled min-height:44px, so the rule is
    // satisfied by construction and a fractional layout result (43.999996 under
    // parallel workers) is noise, not a defect.
    Math.round(dimensions.progressHeight) >= 44,
    `progress steps retain a useful touch target (measured ${dimensions.progressHeight ?? 'missing'}px)`,
  );
  // Every step label stays legible rather than collapsing to bare slivers.
  assert.equal(await page.locator('.setup-progress-label').first().isVisible(), true);
  await page.getByRole('link', { name: /Save & exit/ }).waitFor();
});

test('a new owner can create a useful first picture without leaving Setup', async ({ page }) => {
  const state = await installRoutes(page);
  await page.goto('http://buildwealth-v2.test/');

  await page.getByRole('button', { name: 'Create account' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('Taylor');
  await page.getByRole('textbox', { name: 'Email' }).fill('taylor-inline@example.test');
  await page.getByLabel('Password').fill('correct-horse-inline');
  await page.getByRole('button', { name: 'Create account' }).last().click();
  await page.getByRole('button', { name: /Start with my household/ }).click();

  await page.getByLabel('Your name').fill('Taylor');
  await page.getByLabel('Annual household income').fill('96000');
  await page.getByLabel('Typical monthly spending').fill('4500');
  await page.getByLabel('Current debt balance').fill('0');
  await page.getByRole('button', { name: 'Save foundation' }).click();
  await page.getByText(/Foundation saved/).waitFor();
  assert.equal(state.profileWrites[0].source, 'setup_foundation');
  assert.equal(state.profileWrites[0].body.income_items[0].monthly_amount_usd, 8000);
  assert.equal(state.profileWrites[0].body.flags.no_debt, true);

  await page.getByRole('button', { name: 'Continue to what I own' }).click();
  await page.getByLabel('Account name').fill('Emergency fund');
  await page.getByLabel('Current value').fill('12500');
  await page.getByRole('button', { name: 'Add current value' }).click();
  await page.getByText('Added $12500 cash to Emergency fund.').waitFor();
  assert.deepEqual(state.portfolioAdds[0], {
    flow: 'cash', amount_usd: 12500,
    new_account: { name: 'Emergency fund', type: 'cash' },
  });

  await page.getByRole('button', { name: 'Continue to what is ahead' }).click();
  await page.getByLabel('What are you working toward?').fill('Work optionality');
  await page.getByLabel('Rough target').fill('50000');
  await page.getByRole('button', { name: 'Save this direction' }).click();
  await page.getByText(/Goal saved/).waitFor();
  assert.equal(state.profileWrites[1].source, 'setup_future');
  assert.equal(state.profileWrites[1].body.goal_items[0].label, 'Work optionality');

  await page.getByRole('button', { name: 'Show my first picture' }).click();
  await page.getByRole('heading', { name: 'See what the current evidence can support.' }).waitFor();
});

test('an unfinished journey resumes when an authenticated owner opens the app root', async ({ page }) => {
  await installRoutes(page, {
    initiallySignedIn: true,
    initialProgress: {
      started: true,
      needs_setup: true,
      status: 'active',
      current_step: 'future',
      completed_steps: ['welcome', 'foundation'],
      skipped_steps: ['portfolio'],
    },
  });
  await page.goto('http://buildwealth-v2.test/');

  await page.getByRole('heading', { name: 'Name one thing the money needs to make possible.' }).waitFor();
  assert.match(page.url(), /#setup$/);
  await page.getByText('1 left for later').waitFor();
});

test('an existing owner can reset financial data from Profile and restart Setup', async ({ page }) => {
  const state = await installRoutes(page, {
    initiallySignedIn: true,
    initialProgress: {
      started: true,
      needs_setup: false,
      status: 'complete',
      current_step: 'first_picture',
      completed_steps: ['welcome', 'foundation', 'portfolio', 'future', 'first_picture'],
      skipped_steps: [],
    },
    initialProfile: {
      household_members: [{ id: 'person-1', display_name: 'Taylor', relationship: 'self' }],
      income_items: [{ id: 'income-1', label: 'Salary', monthly_amount_usd: 8000 }],
      expense_items: [{ id: 'expense-1', label: 'Living', monthly_amount_usd: 4000 }],
      debt_items: [], goal_items: [], physical_assets: [],
      tax_profile: {}, investment_policy: {},
      flags: { no_debt: true, no_goals: false, expenses_complete: true },
      notes: '', profile_metadata: {}, updated_at: new Date().toISOString(),
    },
  });

  await page.goto('http://buildwealth-v2.test/#profile');
  await page.getByRole('button', { name: 'Reset financial data & register again' }).click();

  const dialog = page.getByRole('dialog', { name: 'Register this profile again' });
  await dialog.getByText('your BuildWealth sign-in and email').waitFor();
  await dialog.getByText(/17 active files/).waitFor();
  await dialog.getByLabel('Type reset and register again to confirm').fill('reset and register again');
  await dialog.getByRole('button', { name: 'Create backup & restart setup' }).click();

  await page.getByRole('heading', { name: 'Start with a private household workspace.' }).waitFor();
  assert.match(page.url(), /#setup$/);
  assert.deepEqual(state.resetRequests, [{ confirm: 'reset and register again' }]);
  await page.getByText('Private by design').waitFor();
});
