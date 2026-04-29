import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderLookCloser } from '../views/plan.js';
import { buildPlanSettingsPatch, renderAssumptions } from '../views/plan/assumptions.js';

test('plan api exposes v2 workspace endpoints', () => {
  const apiSource = readFileSync(
    resolve(import.meta.dirname, '../lib/api.js'),
    'utf8',
  );

  assert.match(apiSource, /function patchJson/);
  assert.match(apiSource, /planSettings:\s*\(id,\s*body/);
  assert.match(apiSource, /\/api\/plans\/.*\/settings/);
  assert.match(apiSource, /planTimeline:\s*\(id\)/);
  assert.match(apiSource, /\/api\/plans\/.*\/timeline/);
  assert.match(apiSource, /updatePlanTimeline:\s*\(id,\s*body/);
  assert.match(apiSource, /planContributionRules:\s*\(id\)/);
  assert.match(apiSource, /\/api\/plans\/.*\/contribution-rules/);
  assert.match(apiSource, /updatePlanContributionRules:\s*\(id,\s*body/);
  assert.match(apiSource, /planAssumptionSets:\s*\(id\)/);
  assert.match(apiSource, /\/api\/plans\/.*\/assumption-sets/);
  assert.match(apiSource, /updatePlanAssumptionSets:\s*\(id,\s*body/);
  assert.match(apiSource, /planScenarioDiff:\s*\(id,\s*body/);
  assert.match(apiSource, /\/api\/plans\/.*\/scenario-diff/);
  assert.match(apiSource, /refreshPlanContext:\s*\(id\)/);
  assert.match(apiSource, /\/api\/plans\/.*\/refresh-context/);
});

test('plan view wires assumptions workspace loading and save actions', () => {
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );

  assert.match(planSource, /renderAssumptions/);
  assert.match(planSource, /api\.planAssumptionSets/);
  assert.match(planSource, /api\.planSettings/);
  assert.match(planSource, /api\.updatePlanAssumptionSets/);
  assert.match(planSource, /data-assumption-field/);
  assert.match(planSource, /data-assumption-action="save"/);
});

test('plan look-closer links saved research artifacts into v2 research surfaces', () => {
  const markup = String(renderLookCloser({
    id: 'plan-1',
    artifacts: [
      {
        id: 'artifact-dossier-msft',
        file_name: '2026-research-dossier-msft-vti.md',
        title: 'Research Dossier - MSFT vs VTI',
      },
      {
        id: 'artifact-closure',
        file_name: 'closure-summary.md',
        title: 'Closure Summary',
      },
    ],
  }));

  assert.match(markup, /Research Dossier - MSFT vs VTI/);
  assert.match(markup, /href="#research\?dossier=artifact-dossier-msft&plan=plan-1"/);
  assert.match(markup, /href="#research\?thesisReview=artifact-dossier-msft&plan=plan-1"/);
  assert.doesNotMatch(markup, /artifact-closure/);
});

test('plan assumptions workspace renders active set, weak fields, and staged save state', () => {
  const plan = {
    id: 'plan-1',
    settings: {
      annual_contribution_usd: null,
      years: 25,
      expected_return_baseline: 0.065,
      inflation_rate: 0.028,
      marginal_tax_rate: null,
      filing_status: 'single',
      withdrawal_strategy: 'guardrails',
      drawdown_order: 'taxable_first',
      simulation_mode: 'monte_carlo',
    },
  };
  const assumptionSets = {
    active_assumption_set_id: 'policy',
    sets: [
      { id: 'default', name: 'Default' },
      { id: 'policy', name: 'Policy baseline' },
    ],
  };

  const cleanMarkup = String(renderAssumptions(plan, {
    assumptionSets,
    draft: {},
    dirty: false,
    saving: false,
    error: '',
  }));

  assert.match(cleanMarkup, /Plan assumptions/);
  assert.match(cleanMarkup, /Policy baseline/);
  assert.match(cleanMarkup, /6\.5/);
  assert.match(cleanMarkup, /Tax assumption missing/);
  assert.match(cleanMarkup, /Contribution assumption missing/);
  assert.doesNotMatch(cleanMarkup, /Save assumptions/);

  const dirtyMarkup = String(renderAssumptions(plan, {
    assumptionSets,
    draft: { annual_contribution_usd: '30000' },
    dirty: true,
    saving: false,
    error: '',
  }));

  assert.match(dirtyMarkup, /value="30000"/);
  assert.match(dirtyMarkup, /Save assumptions/);
});

test('plan assumptions workspace builds precise settings patch from staged edits', () => {
  const patch = buildPlanSettingsPatch(
    {
      settings: {
        annual_contribution_usd: 25000,
        years: 25,
        expected_return_baseline: 0.065,
        inflation_rate: 0.028,
        marginal_tax_rate: 0.24,
        filing_status: 'single',
      },
    },
    {
      annual_contribution_usd: '30000',
      years: '25',
      expected_return_baseline: '7.2',
      inflation_rate: '2.8',
      marginal_tax_rate: '',
      filing_status: 'married_filing_jointly',
    },
  );

  assert.deepEqual(patch, {
    annual_contribution_usd: 30000,
    expected_return_baseline: 0.072,
    marginal_tax_rate: null,
    filing_status: 'married_filing_jointly',
  });
});
