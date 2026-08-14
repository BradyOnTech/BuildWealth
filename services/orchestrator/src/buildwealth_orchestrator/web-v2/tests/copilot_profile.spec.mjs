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
  let pendingSequence = 0;
  let directProfileWrites = 0;
  const pendingProfiles = new Map();
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
      let status = {
        ready_for_daily_review: false,
        completion_percent: 25,
        profile_readiness: {
          next_gap_detail: 'Add income so cash-flow recommendations can be ranked.',
          blocking_recommendation_sources: ['profile_completeness', 'cash_liquidity'],
        },
        steps: [
          { key: 'income', title: 'Add income', status: 'pending' },
          { key: 'expenses', title: 'Add expenses', status: 'pending' },
        ],
      };
      if (savedProfile?.physical_assets?.length) {
        status = {
          ready_for_daily_review: true,
          completion_percent: 100,
          steps: [
            { key: 'income', title: 'Add income', status: 'complete' },
            { key: 'expenses', title: 'Add expenses', status: 'complete' },
            { key: 'goals', title: 'Add goals', status: 'complete' },
            { key: 'tax_profile', title: 'Add tax basics', status: 'complete' },
            { key: 'physical_assets', title: 'Add physical assets', status: 'complete' },
          ],
        };
      } else if (savedProfile?.tax_profile?.marginal_tax_rate != null) {
        status = {
          ready_for_daily_review: false,
          completion_percent: 90,
          steps: [
            { key: 'income', title: 'Add income', status: 'complete' },
            { key: 'expenses', title: 'Add expenses', status: 'complete' },
            { key: 'goals', title: 'Add goals', status: 'complete' },
            { key: 'tax_profile', title: 'Add tax basics', status: 'complete' },
            { key: 'physical_assets', title: 'Add physical assets', status: 'pending' },
          ],
        };
      } else if (savedProfile?.goal_items?.length) {
        status = {
          ready_for_daily_review: false,
          completion_percent: 82,
          steps: [
            { key: 'income', title: 'Add income', status: 'complete' },
            { key: 'expenses', title: 'Add expenses', status: 'complete' },
            { key: 'goals', title: 'Add goals', status: 'complete' },
            { key: 'tax_profile', title: 'Add tax basics', status: 'pending' },
            { key: 'physical_assets', title: 'Add physical assets', status: 'pending' },
          ],
        };
      } else if (savedProfile) {
        status = {
            ready_for_daily_review: false,
            completion_percent: 75,
            steps: [
              { key: 'income', title: 'Add income', status: 'complete' },
              { key: 'expenses', title: 'Add expenses', status: 'complete' },
              { key: 'goals', title: 'Add goals', status: 'pending' },
            ],
          };
      }
      await route.fulfill(jsonResponse(status));
      return;
    }

    if (url.pathname === '/api/copilot/chat' && request.method() === 'POST') {
      const chatPayload = request.postDataJSON();
      chatPayloads.push(chatPayload);
      const isGoalPrompt = /add financial goals/i.test(chatPayload.question || '');
      const isAssetPrompt = /add physical assets/i.test(chatPayload.question || '');
      const isTaxPrompt = /add tax basics/i.test(chatPayload.question || '');
      const toolResult = isAssetPrompt
        ? {
            draft_kind: 'financial_profile_update',
            summary: 'Drafted a physical asset for review.',
            section_counts: { physical_assets: 1 },
            patch_payload: {
              physical_assets: [{
                id: 'asset_primary_residence',
                label: 'Primary residence',
                current_value_usd: 450000,
                asset_type: 'real_estate',
                annual_growth_rate: 0.03,
                purchase_date: '2020-05-15T00:00:00.000Z',
              }],
            },
            proposed_profile: {
              ...(savedProfile || baseProfile),
              physical_assets: [{
                id: 'asset_primary_residence',
                label: 'Primary residence',
                current_value_usd: 450000,
                asset_type: 'real_estate',
                annual_growth_rate: 0.03,
                purchase_date: '2020-05-15T00:00:00.000Z',
              }],
            },
            requires_confirmation: true,
          }
        : isTaxPrompt
        ? {
            draft_kind: 'financial_profile_update',
            summary: 'Drafted tax basics for review.',
            section_counts: { tax_profile: 1 },
            patch_payload: {
              tax_profile: {
                filing_status: 'married_filing_jointly',
                marginal_tax_rate: 0.24,
                state: 'MN',
              },
            },
            proposed_profile: {
              ...(savedProfile || baseProfile),
              tax_profile: {
                ...(savedProfile || baseProfile).tax_profile,
                filing_status: 'married_filing_jointly',
                marginal_tax_rate: 0.24,
                state: 'MN',
              },
            },
            requires_confirmation: true,
          }
        : isGoalPrompt
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
              ...baseProfile,
              income_items: [{ id: 'income_salary', label: 'Salary', monthly_amount_usd: 11000 }],
              expense_items: [{ id: 'expense_rent', label: 'Rent', monthly_amount_usd: 2600 }],
            },
            requires_confirmation: true,
          };
      const actionId = `pfa-browser-${++pendingSequence}`;
      toolResult.pending_action = {
        action_id: actionId,
        status: 'pending',
        expires_at: '2026-08-01T12:30:00.000Z',
        summary: toolResult.summary,
      };
      pendingProfiles.set(actionId, toolResult.proposed_profile);
      await route.fulfill(jsonResponse({
        conversation_id: isAssetPrompt
          ? 'conversation-asset-setup'
          : isTaxPrompt
            ? 'conversation-tax-setup'
            : isGoalPrompt
              ? 'conversation-goal-setup'
              : 'conversation-profile-setup',
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

    const pendingApplyMatch = url.pathname.match(
      /^\/api\/copilot\/pending-actions\/([^/]+)\/apply$/,
    );
    if (pendingApplyMatch && request.method() === 'POST') {
      const actionId = decodeURIComponent(pendingApplyMatch[1]);
      const proposedProfile = pendingProfiles.get(actionId);
      assert.ok(proposedProfile, `unknown pending action ${actionId}`);
      savedProfile = proposedProfile;
      await route.fulfill(jsonResponse({
        action: {
          action_id: actionId,
          status: 'applied',
          applied_at: '2026-07-31T12:00:00.000Z',
          status_reason: 'Applied after explicit user confirmation.',
        },
        result: {
          already_applied: false,
          profile: savedProfile,
        },
      }));
      return;
    }

    if (url.pathname === '/api/financial-profile' && request.method() === 'GET') {
      await route.fulfill(jsonResponse(savedProfile || baseProfile));
      return;
    }

    if (url.pathname === '/api/financial-profile' && request.method() === 'PUT') {
      directProfileWrites += 1;
      await route.fulfill(jsonResponse({ detail: 'Copilot must use pending actions.' }, 409));
      return;
    }

    await route.fulfill(jsonResponse({ detail: `Unhandled test route: ${request.method()} ${url.pathname}` }, 404));
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('http://buildwealth-v2.test/#copilot');

  const onboardingButton = page.getByRole('button', { name: /fill it out with copilot/i });
  await onboardingButton.waitFor({ state: 'visible' });
  await page.getByText('Add income so cash-flow recommendations can be ranked. Needed for profile completeness and cash liquidity.').waitFor({ state: 'visible' });
  await onboardingButton.click();

  const textarea = page.locator('#composer-textarea');
  const draft = await textarea.inputValue();
  assert.match(draft, /get_onboarding_status/);
  assert.match(draft, /draft_financial_profile_update/);
  assert.match(draft, /server-owned pending action/i);
  assert.match(draft, /you cannot apply it/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Review profile update').waitFor({ state: 'visible' });
  await page.getByText('$11,000').waitFor({ state: 'visible' });
  await page.getByText('$2,600').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 1);
  assert.match(chatPayloads[0].question, /Help me fill out my financial profile/);
  assert.equal(chatPayloads[0].use_live_snapshot, false);

  await page.getByRole('button', { name: /apply profile update/i }).click();
  await page.getByText('Applied to your financial profile.').waitFor({ state: 'visible' });

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
  assert.equal(directProfileWrites, 0);
  assert.equal(onboardingStatusCalls, 3);

  await page.getByRole('button', { name: /new chat/i }).click();
  await page.getByText('Build your first forecast. Next: Add goals.').waitFor({ state: 'visible' });

  const goalsButton = page.getByRole('button', { name: /add goals with copilot/i });
  await goalsButton.click();

  const goalsDraft = await textarea.inputValue();
  assert.match(goalsDraft, /Help me add financial goals/);
  assert.match(goalsDraft, /goal_items/);
  assert.match(goalsDraft, /target_amount_usd/);
  assert.match(goalsDraft, /target_date/);
  assert.match(goalsDraft, /priority/);
  assert.match(goalsDraft, /server-owned pending action/i);
  assert.match(goalsDraft, /you cannot apply it/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Home down payment').waitFor({ state: 'visible' });
  await page.getByText('$80,000').waitFor({ state: 'visible' });
  await page.getByText('Target Jun 1, 2028 · High priority').waitFor({ state: 'visible' });
  await page.getByText('Keep this goal separate from emergency reserves.').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 2);
  assert.match(chatPayloads[1].question, /Help me add financial goals/);

  await page.locator('[data-pending-action-apply]').last().click();
  await page.getByText('Applied to your financial profile.').last().waitFor({ state: 'visible' });

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

  await page.getByRole('button', { name: /new chat/i }).click();
  await page.getByText('Build your first forecast. Next: Add tax basics.').waitFor({ state: 'visible' });

  const taxButton = page.getByRole('button', { name: /add tax basics with copilot/i });
  await taxButton.click();

  const taxDraft = await textarea.inputValue();
  assert.match(taxDraft, /Help me add tax basics/);
  assert.match(taxDraft, /tax_profile/);
  assert.match(taxDraft, /filing_status/);
  assert.match(taxDraft, /marginal_tax_rate/);
  assert.match(taxDraft, /state/);
  assert.match(taxDraft, /server-owned pending action/i);
  assert.match(taxDraft, /you cannot apply it/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Tax profile').waitFor({ state: 'visible' });
  await page.getByText('Married filing jointly').waitFor({ state: 'visible' });
  await page.getByText('Marginal 24% · State MN').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 3);
  assert.match(chatPayloads[2].question, /Help me add tax basics/);

  await page.locator('[data-pending-action-apply]').last().click();
  await page.getByText('Applied to your financial profile.').last().waitFor({ state: 'visible' });

  assert.deepEqual(savedProfile.tax_profile, {
    filing_status: 'married_filing_jointly',
    marginal_tax_rate: 0.24,
    state: 'MN',
  });
  assert.deepEqual(savedProfile.goal_items, [{
    id: 'goal_home_down_payment',
    label: 'Home down payment',
    target_amount_usd: 80000,
    target_date: '2028-06-01T00:00:00.000Z',
    priority: 'high',
    notes: 'Keep this goal separate from emergency reserves.',
  }]);

  await page.getByRole('button', { name: /new chat/i }).click();
  await page.getByText('Build your first forecast. Next: Add physical assets.').waitFor({ state: 'visible' });

  const assetsButton = page.getByRole('button', { name: /add assets with copilot/i });
  await assetsButton.click();

  const assetsDraft = await textarea.inputValue();
  assert.match(assetsDraft, /Help me add physical assets/);
  assert.match(assetsDraft, /physical_assets/);
  assert.match(assetsDraft, /current_value_usd/);
  assert.match(assetsDraft, /asset_type/);
  assert.match(assetsDraft, /purchase_date/);
  assert.match(assetsDraft, /annual_growth_rate/);
  assert.match(assetsDraft, /server-owned pending action/i);
  assert.match(assetsDraft, /you cannot apply it/i);

  await page.locator('#composer-submit').click();
  await page.getByText('Primary residence').waitFor({ state: 'visible' });
  await page.getByText('$450,000').waitFor({ state: 'visible' });
  await page.getByText('Real estate · Purchased May 15, 2020 · Growth 3%/yr').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 4);
  assert.match(chatPayloads[3].question, /Help me add physical assets/);

  await page.locator('[data-pending-action-apply]').last().click();
  await page.getByText('Applied to your financial profile.').last().waitFor({ state: 'visible' });

  assert.deepEqual(savedProfile.physical_assets, [{
    id: 'asset_primary_residence',
    label: 'Primary residence',
    current_value_usd: 450000,
    asset_type: 'real_estate',
    annual_growth_rate: 0.03,
    purchase_date: '2020-05-15T00:00:00.000Z',
  }]);
  assert.deepEqual(savedProfile.goal_items, [{
    id: 'goal_home_down_payment',
    label: 'Home down payment',
    target_amount_usd: 80000,
    target_date: '2028-06-01T00:00:00.000Z',
    priority: 'high',
    notes: 'Keep this goal separate from emergency reserves.',
  }]);
});

test('Copilot keeps a legacy dossier thesis draft review-only and routes to Research', async ({ page }) => {
  const chatPayloads = [];

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
      await route.fulfill(jsonResponse([{ id: 'plan-1', title: 'Primary Plan', is_active: true }]));
      return;
    }

    if (url.pathname === '/api/copilot/conversations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/onboarding/status') {
      await route.fulfill(jsonResponse({
        ready_for_daily_review: true,
        completion_percent: 100,
        steps: [],
      }));
      return;
    }

    if (url.pathname === '/api/copilot/chat' && request.method() === 'POST') {
      const chatPayload = request.postDataJSON();
      chatPayloads.push(chatPayload);
      await route.fulfill(jsonResponse({
        conversation_id: 'conversation-dossier-thesis',
        answer: 'I drafted a dossier thesis revision for review.',
        created_at: '2026-04-29T12:00:00.000Z',
        model: 'browser-test',
        tool_calls: [
          {
            name: 'draft_dossier_thesis_revision',
            arguments: {
              plan_id: 'plan-1',
              artifact_id: 'dossier-msft-vti',
            },
            result: {
              draft_kind: 'dossier_thesis_revision',
              requires_confirmation: true,
              target: {
                type: 'dossier',
                plan_id: 'plan-1',
                artifact_id: 'dossier-msft-vti',
                title: 'Research Dossier: MSFT vs VTI',
              },
              current: {
                thesis: 'Current thesis prefers broad market exposure.',
                reference_price_usd: 390,
                reviewed_at: '2026-03-01T12:00:00Z',
                expires_at: '2026-04-01T12:00:00Z',
              },
              proposed: {
                thesis: 'Revised thesis keeps MSFT as a quality watch item but requires concentration review before action.',
                reference_price_usd: 410,
                review_window_days: 45,
              },
              rationale: 'New evidence increased conviction but portfolio concentration remains the gating issue.',
              evidence_gaps: ['Tax-lot impact still needs review.'],
              warnings: ['Do not treat this as a buy recommendation.'],
            },
          },
        ],
      }));
      return;
    }

    await route.fulfill(jsonResponse({ detail: `Unhandled test route: ${request.method()} ${url.pathname}` }, 404));
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('http://buildwealth-v2.test/#copilot?focus=rec-thesis&intent=investment-fit');

  const textarea = page.locator('#composer-textarea');
  const focusedDraft = await textarea.inputValue();
  assert.match(focusedDraft, /draft_dossier_thesis_revision/);

  await page.locator('#composer-submit').click();
  await page.getByText('Review thesis revision').waitFor({ state: 'visible' });
  await page.getByText('Research Dossier: MSFT vs VTI').waitFor({ state: 'visible' });
  await page.getByText('Current thesis prefers broad market exposure.').waitFor({ state: 'visible' });
  await page.getByText('Revised thesis keeps MSFT as a quality watch item but requires concentration review before action.').waitFor({ state: 'visible' });
  await page.getByText('Tax-lot impact still needs review.').waitFor({ state: 'visible' });

  assert.equal(chatPayloads.length, 1);
  assert.match(chatPayloads[0].question, /Review investment-fit recommendation rec-thesis/);

  await page.getByText(/legacy chat draft is review-only/i).waitFor({ state: 'visible' });
  const researchLink = page.getByRole('link', { name: /open research review/i });
  await researchLink.waitFor({ state: 'visible' });
  await expectNoSaveAuthority(page);
  assert.match(
    await researchLink.getAttribute('href'),
    /#research\?thesisReview=dossier-msft-vti&plan=plan-1/,
  );
});

async function expectNoSaveAuthority(page) {
  assert.equal(
    await page.getByRole('button', { name: /save revised thesis/i }).count(),
    0,
  );
}
