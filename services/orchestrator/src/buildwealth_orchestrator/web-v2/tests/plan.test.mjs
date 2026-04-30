import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderLookCloser } from '../views/plan.js';
import { buildPlanSettingsPatch, renderAssumptions } from '../views/plan/assumptions.js';
import { classifyPlanArtifact, renderArtifacts } from '../views/plan/artifacts.js';
import { derivePlanHealth, renderPlanHealth } from '../views/plan/health.js';

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

test('plan view wires plan health data and section routing', () => {
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );
  const healthSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan/health.js'),
    'utf8',
  );

  assert.match(planSource, /renderPlanHealth/);
  assert.match(planSource, /api\.recommendations\(\{\s*planId/);
  assert.match(planSource, /params\.section/);
  assert.match(planSource, /focusRequestedSection/);
  assert.match(healthSource, /data-plan-section="health"/);
  assert.match(healthSource, /planSectionHref/);
  assert.match(healthSource, /'assumptions'/);
});

test('plan view wires typed artifact center into the page', () => {
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );

  assert.match(planSource, /renderArtifacts/);
  assert.match(planSource, /id="plan-artifacts"/);
  assert.match(planSource, /data-plan-section="artifacts"/);
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

test('plan artifact classifier groups durable evidence by purpose', () => {
  assert.equal(classifyPlanArtifact({
    kind: 'research_dossier',
    title: 'Research Dossier - MSFT vs VTI',
  }).kind, 'research_dossier');
  assert.equal(classifyPlanArtifact({
    kind: 'research_bridge',
    title: 'Research bridge pin - NVDA',
  }).kind, 'research_bridge');
  assert.equal(classifyPlanArtifact({
    title: 'Decision packet - increase contributions',
  }).kind, 'decision_packet');
  assert.equal(classifyPlanArtifact({
    title: 'Thesis revision - NVDA',
  }).kind, 'thesis_revision');
  assert.equal(classifyPlanArtifact({
    file_name: 'recommendation-closure-summary.md',
  }).kind, 'closure_summary');
  assert.equal(classifyPlanArtifact({
    title: 'Scenario diff report',
  }).kind, 'scenario_report');
  assert.equal(classifyPlanArtifact({
    title: 'Loose planning note',
  }).kind, 'general');
});

test('plan artifact center renders typed routes and packet citations', () => {
  const markup = String(renderArtifacts({
    id: 'plan-1',
    artifacts: [
      {
        id: 'artifact-dossier-msft',
        kind: 'research_dossier',
        title: 'Research Dossier - MSFT vs VTI',
        created_at: '2026-04-20T12:00:00Z',
        packet_citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
      },
      {
        id: 'artifact-bridge-nvda',
        kind: 'research_bridge',
        title: 'Research bridge pin - NVDA',
        symbols: ['NVDA'],
      },
      {
        id: 'artifact-decision',
        title: 'Decision packet - increase contributions',
        recommendation_id: 'rec-contribution',
      },
      {
        id: 'artifact-thesis',
        title: 'Thesis revision - NVDA',
        content_preview: 'Updated with research-evidence:yfinance:NVDA:6mo:1d after policy review.',
        symbols: ['NVDA'],
      },
      {
        id: 'artifact-closure',
        title: 'Recommendation closure summary',
      },
      {
        id: 'artifact-scenario',
        title: 'Scenario diff report',
      },
      {
        id: 'artifact-note',
        title: 'Loose planning note',
      },
    ],
  }));

  assert.match(markup, /Plan evidence/);
  assert.match(markup, /Research dossier/);
  assert.match(markup, /href="#research\?dossier=artifact-dossier-msft&amp;plan=plan-1"/);
  assert.match(markup, /href="#research\?thesisReview=artifact-dossier-msft&amp;plan=plan-1"/);
  assert.match(markup, /research-evidence:yfinance:MSFT:6mo:1d/);
  assert.match(markup, /Research bridge/);
  assert.match(markup, /Decision packet/);
  assert.match(markup, /href="#inbox\?focus=rec-contribution"/);
  assert.match(markup, /Thesis revision/);
  assert.match(markup, /research-evidence:yfinance:NVDA:6mo:1d/);
  assert.match(markup, /Outcome\/closure/);
  assert.match(markup, /Scenario report/);
  assert.match(markup, /General artifact/);
});

test('plan health renders weak assumptions and stale assumption review links', () => {
  const plan = {
    id: 'plan-1',
    settings: {
      annual_contribution_usd: 0,
      expected_return_baseline: 0.065,
      marginal_tax_rate: null,
    },
    decisions: [],
    artifacts: [],
    top_next_actions: [],
  };
  const recommendations = [
    {
      id: 'rec-stale-tax',
      source: 'generator:stale_assumptions',
      title: 'Review missing tax assumptions',
      detail: 'Tax context is missing.',
      plan_id: 'plan-1',
    },
  ];
  const health = derivePlanHealth(plan, {
    recommendations,
    tracking: { status: 'insufficient_history', snapshots_count: 2 },
  });
  const markup = String(renderPlanHealth(plan, health));

  assert.equal(health.status, 'weak');
  assert.match(markup, /Weak/);
  assert.match(markup, /Tax assumptions need review/);
  assert.match(markup, /Contribution assumptions need review/);
  assert.match(markup, /Open stale-assumption reviews/);
  assert.match(markup, /href="#inbox\?focus=rec-stale-tax"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=assumptions"/);
});

test('plan health reports ready when assumptions and tracking are decision-grade', () => {
  const health = derivePlanHealth({
    id: 'plan-1',
    settings: {
      annual_contribution_usd: 30000,
      expected_return_baseline: 0.065,
      marginal_tax_rate: 0.24,
    },
    decisions: [],
    artifacts: [],
    top_next_actions: [],
  }, {
    recommendations: [],
    tracking: { status: 'on_track', snapshots_count: 90 },
  });
  const markup = String(renderPlanHealth({ id: 'plan-1' }, health));

  assert.equal(health.status, 'ready');
  assert.match(markup, /Ready/);
  assert.match(markup, /Plan context is decision-grade/);
});

test('plan health surfaces expired linked research and accepted decisions without outcomes', () => {
  const plan = {
    id: 'plan-1',
    settings: {
      annual_contribution_usd: 30000,
      expected_return_baseline: 0.065,
      marginal_tax_rate: 0.24,
    },
    artifacts: [
      {
        id: 'artifact-dossier-msft',
        title: 'Research Dossier - MSFT vs VTI',
        file_name: 'research-dossier-msft-vti.md',
        thesis_review: {
          expires_at: '2026-04-01T00:00:00Z',
        },
      },
    ],
    decisions: [
      {
        id: 'decision-old',
        status: 'accepted',
        summary: 'Accepted contribution increase',
        created_at: '2026-02-01T00:00:00Z',
        recommendation_id: 'rec-contribution',
      },
    ],
    top_next_actions: [],
  };
  const health = derivePlanHealth(plan, {
    recommendations: [],
    tracking: { status: 'on_track', snapshots_count: 90 },
    now: '2026-04-29T00:00:00Z',
  });
  const markup = String(renderPlanHealth(plan, health));

  assert.equal(health.status, 'needs_review');
  assert.match(markup, /Linked research thesis needs review/);
  assert.match(markup, /href="#research\?thesisReview=artifact-dossier-msft&amp;plan=plan-1"/);
  assert.match(markup, /Accepted decisions need outcome capture/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=decisions"/);
});

test('plan health surfaces open research thesis recommendation reviews', () => {
  const plan = {
    id: 'plan-1',
    settings: {
      annual_contribution_usd: 30000,
      expected_return_baseline: 0.065,
      marginal_tax_rate: 0.24,
    },
    artifacts: [],
    decisions: [],
  };
  const health = derivePlanHealth(plan, {
    recommendations: [
      {
        id: 'rec-policy-thesis',
        source: 'generator:research_thesis_expiration',
        plan_id: 'plan-1',
        action_payload: {
          suggested_action: {
            kind: 'review_research_thesis',
            artifact_id: 'artifact-dossier-msft',
            plan_id: 'plan-1',
            symbols: ['MSFT'],
          },
        },
      },
    ],
    tracking: { status: 'on_track', snapshots_count: 90 },
  });
  const markup = String(renderPlanHealth(plan, health));

  assert.equal(health.status, 'needs_review');
  assert.match(markup, /Open research thesis reviews/);
  assert.match(markup, /href="#research\?thesisReview=artifact-dossier-msft&amp;plan=plan-1&amp;focus=rec-policy-thesis"/);
});
