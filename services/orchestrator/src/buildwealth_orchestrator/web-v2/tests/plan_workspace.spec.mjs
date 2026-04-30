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

test('v2 Plan workspace covers assumption save, evidence route, scenario decision, branch preview, and Copilot review', async ({ page }) => {
  let settingsPatch = null;
  let scenarioPayload = null;
  let branchPayload = null;
  let decisionPayload = null;
  let planSettings = {
    annual_contribution_usd: 25000,
    years: 25,
    expected_return_baseline: 0.065,
    inflation_rate: 0.028,
    marginal_tax_rate: null,
    filing_status: 'single',
    withdrawal_strategy: 'guardrails',
    drawdown_order: 'taxable_first',
    simulation_mode: 'monte_carlo',
  };
  const decisions = [
    {
      id: 'decision-seed',
      status: 'accepted',
      summary: 'Accepted baseline plan',
      rationale: 'Initial plan setup.',
      created_at: '2026-04-20T12:00:00Z',
    },
  ];

  const artifact = {
    id: 'artifact-dossier-msft',
    kind: 'research_dossier',
    title: 'Research Dossier - MSFT vs VTI',
    file_name: '2026-research-dossier-msft-vti.md',
    created_at: '2026-04-22T12:00:00Z',
    packet_citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
    content: [
      '# Research Dossier: MSFT vs VTI',
      '',
      '## Evidence Packets',
      '',
      '| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |',
      '| --- | --- | --- | --- | --- | ---: | --- |',
      '| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | fresh | high | 96% | none |',
      '| VTI | research-evidence:yfinance:VTI:6mo:1d | yfinance | fresh | high | 98% | none |',
    ].join('\n'),
  };

  const planDetail = () => ({
    id: 'plan-1',
    title: 'Primary Plan',
    description: 'Primary household financial thesis.',
    is_active: true,
    created_at: '2026-04-20T12:00:00Z',
    updated_at: '2026-04-29T12:00:00Z',
    schema_version: 2,
    settings: planSettings,
    decisions,
    artifacts: [artifact],
    top_next_actions: [],
  });

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

    if (url.pathname === '/api/plans/plan-1') {
      await route.fulfill(jsonResponse(planDetail()));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/settings' && request.method() === 'PATCH') {
      settingsPatch = request.postDataJSON();
      planSettings = { ...planSettings, ...settingsPatch };
      decisions.push({
        id: 'decision-settings',
        status: 'accepted',
        summary: 'Updated plan settings',
        rationale: 'Annual contribution reviewed in v2 Plan.',
        created_at: '2026-04-29T12:10:00Z',
      });
      await route.fulfill(jsonResponse(planDetail()));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/assumption-sets') {
      await route.fulfill(jsonResponse({
        schema_version: 2,
        active_assumption_set_id: 'default',
        sets: [
          { id: 'default', name: 'Default', settings: {} },
          { id: 'policy', name: 'Policy baseline', settings: { expected_return_baseline: 0.065 } },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/branch-templates') {
      await route.fulfill(jsonResponse({
        schema_version: 2,
        default_template_id: 'job_loss_6_months',
        templates: [
          {
            id: 'job_loss_6_months',
            name: 'Job Loss (6 Months)',
            description: 'Temporary income interruption.',
            branch_name: 'Job Loss 6 Months',
            assumption_set_id: null,
            compare_settings: {},
            branch_events: [
              {
                label: 'Temporary Job Loss',
                event_type: 'job_change',
                impact_type: 'income',
                amount_usd: -7500,
                recurring_frequency: 'monthly',
                start_year_offset: 0,
                duration_months: 6,
              },
            ],
          },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/timeline') {
      await route.fulfill(jsonResponse({
        schema_version: 2,
        retirement: {
          target_retirement_age: 62,
          target_retirement_year: 2048,
          withdrawal_strategy: 'guardrails',
          drawdown_order: 'taxable_first',
        },
        events: [
          {
            id: 'event-retire',
            date: '2048-01-01',
            label: 'Retire',
            event_type: 'retirement',
            impact_type: 'income_change',
            amount_usd: 0,
            recurring_frequency: 'one_time',
          },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/contribution-rules') {
      await route.fulfill(jsonResponse({
        schema_version: 2,
        base_rule: { type: 'save' },
        profile_id: 'custom_profile',
        employer_match_target_usd: 6000,
        age: 40,
        rules: [
          {
            id: 'rule-1',
            accountId: 'acct-401k',
            rank: 1,
            amount: { type: 'dollarAmount', dollarAmount: 10000 },
            employerMatch: 6000,
          },
        ],
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/tracking') {
      await route.fulfill(jsonResponse({
        plan_id: 'plan-1',
        status: 'on_track',
        snapshots_count: 90,
        annualized_actual_return: 0.07,
        expected_return_baseline: 0.065,
      }));
      return;
    }

    if (url.pathname === '/api/recommendations') {
      await route.fulfill(jsonResponse([]));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/scenario-diff' && request.method() === 'POST') {
      scenarioPayload = request.postDataJSON();
      await route.fulfill(jsonResponse({
        plan_id: 'plan-1',
        base_settings: {
          annual_contribution_usd: 30000,
          expected_return_baseline: 0.065,
        },
        candidate_settings: {
          annual_contribution_usd: 36000,
          expected_return_baseline: 0.065,
        },
        scenario_deltas: [
          {
            label: 'baseline',
            base_future_value_usd: 1000000,
            candidate_future_value_usd: 1042000,
            delta_future_value_usd: 42000,
            base_real_value_usd: 760000,
            candidate_real_value_usd: 790000,
            delta_real_value_usd: 30000,
          },
        ],
        monte_carlo_delta: { success_probability_delta: 0.04 },
        simulation_delta: {
          status: 'captured',
          summary: 'Monte Carlo confidence improved.',
        },
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/scenario-branch' && request.method() === 'POST') {
      branchPayload = request.postDataJSON();
      await route.fulfill(jsonResponse({
        plan_id: 'plan-1',
        branch_name: 'Job Loss 6 Months',
        branch_template_id: 'job_loss_6_months',
        branch_template_name: 'Job Loss (6 Months)',
        current_portfolio_value_usd: 500000,
        base_settings: {
          annual_contribution_usd: 30000,
          expected_return_baseline: 0.065,
        },
        branch_settings: {
          annual_contribution_usd: 30000,
          expected_return_baseline: 0.065,
        },
        branch_events: [],
        scenario_deltas: [
          {
            label: 'baseline',
            base_future_value_usd: 1000000,
            candidate_future_value_usd: 940000,
            delta_future_value_usd: -60000,
            base_real_value_usd: 760000,
            candidate_real_value_usd: 710000,
            delta_real_value_usd: -50000,
          },
        ],
        monte_carlo_delta: { success_probability_delta: -0.02 },
        simulation_delta: {
          status: 'captured',
          summary: 'Branch reduced confidence.',
        },
      }));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/decisions' && request.method() === 'POST') {
      decisionPayload = request.postDataJSON();
      decisions.push({
        id: 'decision-scenario',
        status: decisionPayload.status || 'proposed',
        summary: decisionPayload.summary,
        rationale: decisionPayload.rationale,
        created_at: '2026-04-29T12:20:00Z',
      });
      await route.fulfill(jsonResponse(planDetail()));
      return;
    }

    if (url.pathname === '/api/plans/plan-1/artifacts/artifact-dossier-msft') {
      await route.fulfill(jsonResponse(artifact));
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

    await route.fulfill(jsonResponse({}));
  });

  await page.goto('http://buildwealth-v2.test/#plan');
  await page.getByRole('heading', { name: 'Plan assumptions' }).waitFor({ state: 'visible' });

  const contributionInput = page.locator('[data-assumption-field="annual_contribution_usd"]');
  await contributionInput.fill('30000');
  await contributionInput.blur();
  await page.getByRole('button', { name: /Save assumptions/ }).click();

  assert.deepEqual(settingsPatch, { annual_contribution_usd: 30000 });
  await page.getByText('Updated plan settings').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Open dossier' }).click();
  await page.waitForURL('**/#research?dossier=artifact-dossier-msft&plan=plan-1');
  await page.getByText('Dossier detail').waitFor({ state: 'visible' });
  await page.getByText('research-evidence:yfinance:MSFT:6mo:1d').first().waitFor({ state: 'visible' });

  await page.goto('http://buildwealth-v2.test/#plan?id=plan-1&section=scenarios');
  await page.getByRole('heading', { name: 'Compare before deciding.' }).waitFor({ state: 'visible' });
  const scenarioContributionInput = page.locator('[data-scenario-field="annual_contribution_usd"]');
  await scenarioContributionInput.fill('36000');
  await scenarioContributionInput.blur();
  await page.getByRole('button', { name: /Run scenario diff/ }).click();

  assert.deepEqual(scenarioPayload, {
    compare_settings: { annual_contribution_usd: 36000 },
  });
  await page.getByText('Scenario compared.').waitFor({ state: 'visible' });
  await page.getByText('+$42,000').waitFor({ state: 'visible' });

  await page.locator('#plan-scenarios').getByRole('button', { name: /Save decision note/ }).click();
  assert.equal(decisionPayload.summary, 'Reviewed scenario diff');
  assert.equal(decisionPayload.status, 'proposed');
  await page.getByText('Reviewed scenario diff').waitFor({ state: 'visible' });

  await page.goto('http://buildwealth-v2.test/#plan?id=plan-1&section=branches');
  await page.getByRole('heading', { name: 'Preview a real-world change.' }).waitFor({ state: 'visible' });
  await page.getByRole('heading', { name: 'Job Loss (6 Months)' }).waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /Run branch preview/ }).click();

  assert.equal(branchPayload.branch_template_id, 'job_loss_6_months');
  assert.equal(branchPayload.branch_name, 'Job Loss 6 Months');
  assert.equal(branchPayload.branch_events[0].label, 'Temporary Job Loss');
  await page.getByText('Branch compared.').waitFor({ state: 'visible' });
  await page.getByText('-$60,000').waitFor({ state: 'visible' });

  await page.locator('#plan-branches').getByRole('button', { name: /Save decision note/ }).click();
  assert.equal(decisionPayload.summary, 'Reviewed life-event branch: Job Loss 6 Months');
  assert.equal(decisionPayload.status, 'proposed');
  await page.getByText('Reviewed life-event branch: Job Loss 6 Months').waitFor({ state: 'visible' });

  await page.getByRole('link', { name: 'Review with Copilot' }).click();
  await page.waitForURL('**/#copilot?intent=review_plan_assumptions&plan=plan-1');
  await page.locator('#composer-textarea').waitFor({ state: 'visible' });
  const draft = await page.locator('#composer-textarea').inputValue();
  assert.match(draft, /get_plan_review_context/);
  assert.match(draft, /plan_id="plan-1"/);
  assert.match(draft, /Do not request full artifact contents/);
  assert.match(draft, /Do not request long decision history/);
});
