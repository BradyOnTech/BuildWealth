import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderLookCloser } from '../views/plan.js';
import { buildPlanSettingsPatch, renderAssumptions } from '../views/plan/assumptions.js';
import { classifyPlanArtifact, renderArtifacts } from '../views/plan/artifacts.js';
import { renderDecisions } from '../views/plan/decisions.js';
import { derivePlanHealth, renderPlanHealth } from '../views/plan/health.js';
import { buildScenarioBranchPayload, renderBranches } from '../views/plan/branches.js';
import { buildScenarioDiffPayload, renderScenarios } from '../views/plan/scenarios.js';
import { buildTimelinePayload, renderTimeline } from '../views/plan/timeline.js';
import { buildContributionRulesPayload, renderContributions } from '../views/plan/contributions.js';
import { buildWithdrawalComparePayload, renderWithdrawals } from '../views/plan/withdrawals.js';

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
  assert.match(apiSource, /planWhatIfReviewLevel:\s*\(id,\s*body/);
  assert.match(apiSource, /\/api\/plans\/.*\/what-if-review-level/);
  assert.match(apiSource, /planBranchTemplates:\s*\(id\)/);
  assert.match(apiSource, /\/api\/plans\/.*\/branch-templates/);
  assert.match(apiSource, /updatePlanBranchTemplates:\s*\(id,\s*body/);
  assert.match(apiSource, /planScenarioBranch:\s*\(id,\s*body/);
  assert.match(apiSource, /\/api\/plans\/.*\/scenario-branch/);
  assert.match(apiSource, /planSavedSimulations:\s*\(id,\s*limit/);
  assert.match(apiSource, /\/api\/plans\/.*\/simulations\/saved/);
  assert.match(apiSource, /savePlanSimulation:\s*\(id,\s*body/);
  assert.match(apiSource, /comparePlanSavedSimulationCurrent:\s*\(id,\s*savedSimulationId/);
  assert.match(apiSource, /rerunPlanSavedSimulation:\s*\(id,\s*savedSimulationId,\s*body/);
  assert.match(apiSource, /attachPlanSavedSimulationDecision:\s*\(id,\s*savedSimulationId,\s*body/);
  assert.match(apiSource, /planWithdrawalStrategyCompare:\s*\(id,\s*body/);
  assert.match(apiSource, /\/api\/plans\/.*\/withdrawal-strategy-compare/);
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
  assert.match(planSource, /params\.artifact/);
  assert.match(planSource, /loadFocusedArtifact/);
  assert.match(planSource, /api\.planArtifact/);
  assert.match(planSource, /focusedArtifactId/);
});

test('plan view wires simulation workspace actions', () => {
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );

  assert.match(planSource, /renderScenarios/);
  assert.match(planSource, /renderBranches/);
  assert.match(planSource, /renderWithdrawals/);
  assert.match(planSource, /buildScenarioDiffPayload/);
  assert.match(planSource, /buildScenarioBranchPayload/);
  assert.match(planSource, /buildWithdrawalComparePayload/);
  assert.match(planSource, /api\.planScenarioDiff/);
  assert.match(planSource, /api\.explainPlanSimulation/);
  assert.match(planSource, /api\.planWhatIfReviewLevel/);
  assert.match(planSource, /api\.planBranchTemplates/);
  assert.match(planSource, /api\.planScenarioBranch/);
  assert.match(planSource, /api\.planSavedSimulations/);
  assert.match(planSource, /api\.savePlanSimulation/);
  assert.match(planSource, /api\.comparePlanSavedSimulationCurrent/);
  assert.match(planSource, /api\.rerunPlanSavedSimulation/);
  assert.match(planSource, /api\.attachPlanSavedSimulationDecision/);
  assert.match(planSource, /api\.planWithdrawalStrategyCompare/);
  assert.match(planSource, /data-scenario-field/);
  assert.match(planSource, /data-scenario-action="run"/);
  assert.match(planSource, /data-scenario-action="save-simulation"/);
  assert.match(planSource, /data-scenario-action="save-decision"/);
  assert.match(planSource, /data-branch-action="run"/);
  assert.match(planSource, /data-branch-action="save-simulation"/);
  assert.match(planSource, /data-withdrawal-action="run"/);
});

test('plan view wires timeline and contribution rule workspaces', () => {
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );

  assert.match(planSource, /renderTimeline/);
  assert.match(planSource, /renderContributions/);
  assert.match(planSource, /buildTimelinePayload/);
  assert.match(planSource, /buildContributionRulesPayload/);
  assert.match(planSource, /api\.planTimeline/);
  assert.match(planSource, /api\.updatePlanTimeline/);
  assert.match(planSource, /api\.planContributionRules/);
  assert.match(planSource, /api\.updatePlanContributionRules/);
  assert.match(planSource, /data-timeline-action="save"/);
  assert.match(planSource, /data-contribution-action="save"/);
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

test('plan look-closer keeps common plan work in v2', () => {
  const markup = String(renderLookCloser({
    id: 'plan-1',
    artifacts: [],
  }));

  assert.match(markup, /href="#plan\?id=plan-1&amp;section=assumptions"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=timeline"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=contributions"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=scenarios"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=branches"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=withdrawals"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts"/);
  assert.doesNotMatch(markup, /href="\/#plans\?id=plan-1">Edit settings/);
  assert.doesNotMatch(markup, /href="\/#plans\?id=plan-1">Advanced branch/);
  assert.doesNotMatch(markup, /href="\/#plans\?id=plan-1">Advanced withdrawals/);
  assert.doesNotMatch(markup, /href="\/#plans\?id=plan-1">Browse artifacts/);
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
    title: 'Simulation report',
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
        title: 'Simulation report',
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
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts&amp;artifact=artifact-scenario"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts&amp;artifact=artifact-note"/);
  assert.doesNotMatch(markup, /href="\/#plans\?id=plan-1&amp;artifact=artifact-scenario"/);
  assert.match(markup, /Thesis revision/);
  assert.match(markup, /research-evidence:yfinance:NVDA:6mo:1d/);
  assert.match(markup, /Outcome\/closure/);
  assert.match(markup, /Simulation report/);
  assert.match(markup, /General artifact/);
});

test('plan artifact center renders focused generic artifact detail safely', () => {
  const markup = String(renderArtifacts({
    id: 'plan-1',
    artifacts: [
      {
        id: 'artifact-note',
        title: 'Loose planning note',
        created_at: '2026-04-20T12:00:00Z',
      },
    ],
  }, {
    focusedArtifactId: 'artifact-note',
    focusedArtifact: {
      id: 'artifact-note',
      file_name: 'loose-planning-note.md',
      title: 'Loose planning note',
      created_at: '2026-04-20T12:00:00Z',
      content: [
        '# Loose planning note',
        '',
        '<script>alert("nope")</script>',
        '',
        'Reviewed research-evidence:yfinance:VTI:6mo:1d.',
      ].join('\n'),
    },
  }));

  assert.match(markup, /Artifact detail/);
  assert.match(markup, /Loose planning note/);
  assert.match(markup, /loose-planning-note\.md/);
  assert.match(markup, /&lt;script&gt;alert\(&quot;nope&quot;\)&lt;\/script&gt;/);
  assert.doesNotMatch(markup, /<script>alert/);
  assert.match(markup, /research-evidence:yfinance:VTI:6mo:1d/);
  assert.match(markup, /href="#research\?packet=VTI"/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts"/);
});

test('plan decisions render recommendation, artifact, expected outcome, and scenario metadata', () => {
  const markup = String(renderDecisions({
    id: 'plan-1',
    decisions: [
      {
        id: 'decision-1',
        status: 'accepted',
        summary: 'Accepted contribution increase',
        rationale: 'Better aligns the savings rate with the active plan.',
        created_at: '2026-04-01T12:00:00Z',
        recommendation_id: 'rec-contribution',
        action_payload: {
          decision_packet: {
            artifact_id: 'artifact-decision',
          },
          decision_closure_artifact: {
            artifact_id: 'artifact-closure',
          },
          decision_closure: {
            expected_outcome: {
              expected_delta_future_value_usd: 1200,
              expected_delta_context_quality: 'contribution reviewed',
            },
            scenario_diff_preview: {
              status: 'captured',
              summary: 'Raises projected final net worth.',
            },
          },
          saved_simulation_id: 'saved-simulation-1',
          saved_simulation_title: 'Contribution increase simulation',
        },
      },
    ],
  }, { appendOpen: false }));

  assert.match(markup, /Open in Inbox/);
  assert.match(markup, /href="#inbox\?focus=rec-contribution"/);
  assert.match(markup, /Decision packet/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts&amp;artifact=artifact-decision"/);
  assert.match(markup, /Closure summary/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=artifacts&amp;artifact=artifact-closure"/);
  assert.match(markup, /Saved Simulation/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=scenarios&amp;saved=saved-simulation-1"/);
  assert.match(markup, /Contribution increase simulation/);
  assert.match(markup, /Expected outcome/);
  assert.match(markup, /\+\$1,200/);
  assert.match(markup, /contribution reviewed/);
  assert.match(markup, /Scenario preview/);
  assert.match(markup, /Raises projected final net worth\./);
  assert.match(markup, /Outcome captured/);
});

test('plan decisions link legacy saved simulation rationale ids', () => {
  const markup = String(renderDecisions({
    id: 'plan-1',
    decisions: [
      {
        id: 'decision-legacy',
        status: 'proposed',
        summary: 'Reviewed older saved run',
        rationale: 'User wants to revisit this. Saved simulation id: saved-legacy-1.',
        created_at: '2026-04-02T12:00:00Z',
      },
    ],
  }, { appendOpen: false }));

  assert.match(markup, /Saved Simulation/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=scenarios&amp;saved=saved-legacy-1"/);
});

test('plan decisions flag accepted decisions without closure outcome', () => {
  const markup = String(renderDecisions({
    id: 'plan-1',
    decisions: [
      {
        id: 'decision-1',
        status: 'accepted',
        summary: 'Accepted tax review',
        created_at: '2026-02-01T12:00:00Z',
        recommendation_id: 'rec-tax',
      },
    ],
  }, { appendOpen: false }));

  assert.match(markup, /Outcome not captured yet/);
  assert.match(markup, /href="#inbox\?focus=rec-tax"/);
});

test('plan scenario workspace builds scenario-diff payload from staged edits', () => {
  const payload = buildScenarioDiffPayload({
    annual_contribution_usd: '30000',
    expected_return_baseline: '7.2',
    inflation_rate: '2.8',
    marginal_tax_rate: '',
    years: '30',
    current_portfolio_value_usd: '500000',
    assumption_set_id: 'base',
    candidate_assumption_set_id: 'policy',
  });

  assert.deepEqual(payload, {
    current_portfolio_value_usd: 500000,
    assumption_set_id: 'base',
    candidate_assumption_set_id: 'policy',
    compare_settings: {
      annual_contribution_usd: 30000,
      expected_return_baseline: 0.072,
      inflation_rate: 0.028,
      years: 30,
    },
  });
});

test('plan branch workspace builds branch payload from selected template and overrides', () => {
  const template = {
    id: 'job_loss_6_months',
    branch_name: 'Job Loss 6 Months',
    assumption_set_id: 'default',
    compare_settings: { years: 25 },
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
  };

  const payload = buildScenarioBranchPayload(template, {
    branch_name: 'Layoff stress test',
    current_portfolio_value_usd: '500000',
    assumption_set_id: 'policy',
    annual_contribution_usd: '18000',
    expected_return_baseline: '6.5',
  });

  assert.deepEqual(payload, {
    branch_name: 'Layoff stress test',
    branch_template_id: 'job_loss_6_months',
    current_portfolio_value_usd: 500000,
    assumption_set_id: 'policy',
    compare_settings: {
      annual_contribution_usd: 18000,
      expected_return_baseline: 0.065,
      years: 25,
    },
    branch_events: template.branch_events,
  });
});

test('plan branch workspace renders templates, result, and review handoffs', () => {
  const markup = String(renderBranches({
    id: 'plan-1',
  }, {
    branchTemplates: {
      default_template_id: 'job_loss_6_months',
      templates: [
        {
          id: 'job_loss_6_months',
          name: 'Job Loss (6 Months)',
          description: 'Temporary income interruption.',
          branch_name: 'Job Loss 6 Months',
          branch_events: [
            {
              label: 'Temporary Job Loss',
              impact_type: 'income',
              amount_usd: -7500,
              recurring_frequency: 'monthly',
              duration_months: 6,
            },
          ],
        },
      ],
    },
    selectedTemplateId: 'job_loss_6_months',
    draft: {},
    result: {
      branch_name: 'Job Loss 6 Months',
      branch_template_name: 'Job Loss (6 Months)',
      scenario_deltas: [
        {
          label: 'baseline',
          base_future_value_usd: 1000000,
          branch_future_value_usd: 940000,
          candidate_future_value_usd: 940000,
          delta_future_value_usd: -60000,
          base_real_value_usd: 760000,
          branch_real_value_usd: 710000,
          candidate_real_value_usd: 710000,
          delta_real_value_usd: -50000,
        },
      ],
      monte_carlo_delta: { success_probability_delta: -0.02 },
      simulation_delta: { status: 'captured', summary: 'Branch reduced confidence.' },
    },
    explanation: {
      payload: {
        outcome_label: 'worse',
        confidence_level: 'medium',
        summary: 'This simulation weakens the active plan.',
        drivers: [
          { label: 'Future value', direction: 'negative', detail: 'The candidate result is -$60,000 versus the active plan.' },
        ],
        assumption_traces: [
          { explanation: 'Expected return changed from 6.0% to 4.0%.' },
        ],
        confidence_reasons: ['The result includes comparable active-plan and candidate deltas.'],
        yearly_metrics: [
          { year: 2026, age: 45, ending_balance_usd: 560000, net_cash_flow_usd: 20000 },
          { year: 2046, age: 65, ending_balance_usd: 1520000, net_cash_flow_usd: 0 },
        ],
        phase_summaries: [
          {
            label: 'Accumulation',
            start_year: 2026,
            end_year: 2045,
            ending_balance_usd: 1400000,
            total_taxes_usd: 420000,
            total_withdrawals_usd: 0,
          },
          {
            label: 'Transition',
            start_year: 2046,
            end_year: 2050,
            ending_balance_usd: 1520000,
            total_taxes_usd: 110000,
            total_withdrawals_usd: 280000,
          },
        ],
        percentile_bands: [
          { percentile: 'P10', future_value_usd: 850000 },
          { percentile: 'P50', future_value_usd: 1080000 },
          { percentile: 'P90', future_value_usd: 1300000 },
        ],
        field_review_links: [
          {
            label: 'Expected return',
            href: '#plan?id=plan-1&section=assumptions&field=expected_return_baseline',
            reason: 'Review this assumption before using the simulation for a decision.',
          },
        ],
      },
    },
    reviewLevel: {
      payload: {
        review_level: 'high',
        summary: 'High review: read the explanation, check the assumptions, and save a decision note before changing the active plan.',
        stage_one: {
          name: 'Change size',
          level: 'high',
          summary: 'This change is big enough to slow down and review.',
          reasons: ['Future value changes by $60,000 or more.'],
        },
        stage_two: {
          name: 'Result trust',
          level: 'high',
          summary: 'The result needs extra review before it supports a decision.',
          reasons: ['The result weakens the active plan.'],
        },
        recommended_actions: ['Save a decision note before applying this to the active plan.'],
      },
    },
  }, {
    assumptionSets: {
      active_assumption_set_id: 'default',
      sets: [{ id: 'default', name: 'Default' }, { id: 'policy', name: 'Policy baseline' }],
    },
  }));

  assert.match(markup, /What-ifs/);
  assert.match(markup, /Job Loss \(6 Months\)/);
  assert.match(markup, /Temporary Job Loss/);
  assert.match(markup, /Run what-if simulation/);
  assert.match(markup, /Simulation compared/);
  assert.match(markup, /-\$60,000/);
  assert.match(markup, /What this means/);
  assert.match(markup, /Looks weaker than the active plan/);
  assert.match(markup, /Medium confidence/);
  assert.match(markup, /Yearly metrics/);
  assert.match(markup, /2026 to 2046/);
  assert.match(markup, /Life phases/);
  assert.match(markup, /Accumulation \(2026-2045\)/);
  assert.match(markup, /Monte Carlo range/);
  assert.match(markup, /P50: future value \$1,080,000/);
  assert.match(markup, /Fields to review/);
  assert.match(markup, /href="#plan\?id=plan-1&amp;section=assumptions&amp;field=expected_return_baseline"/);
  assert.match(markup, /Review level/);
  assert.match(markup, /High review/);
  assert.match(markup, /Slow down before applying this/);
  assert.match(markup, /Discuss in Copilot/);
  assert.match(markup, /Save simulation/);
  assert.match(markup, /Save decision note/);
});

test('plan withdrawal workspace builds compare payload from selected strategies and context', () => {
  const payload = buildWithdrawalComparePayload({
    selectedStrategies: ['four_percent_rule', 'dynamic_guardrails', 'four_percent_rule'],
    current_portfolio_value_usd: '650000',
    assumption_set_id: 'policy',
    include_raw_results: true,
  });

  assert.deepEqual(payload, {
    strategies: ['four_percent_rule', 'dynamic_guardrails'],
    current_portfolio_value_usd: 650000,
    assumption_set_id: 'policy',
    include_raw_results: true,
  });
});

test('plan withdrawal workspace renders strategy comparison rows and review handoffs', () => {
  const markup = String(renderWithdrawals({
    id: 'plan-1',
  }, {
    selectedStrategies: ['four_percent_rule', 'dynamic_guardrails'],
    result: {
      plan_id: 'plan-1',
      current_portfolio_value_usd: 650000,
      strategies: ['four_percent_rule', 'dynamic_guardrails'],
      best_strategy_by_metric: {
        future_value: 'dynamic_guardrails',
        real_value: 'dynamic_guardrails',
        monte_carlo_p50: 'four_percent_rule',
      },
      warnings: ['Dynamic guardrails used local projection fallback.'],
      explanation: {
        recommended_strategy: 'dynamic_guardrails',
        summary: 'Dynamic Guardrails has the strongest overall result in this comparison. 4% Rule has the lowest projected taxes.',
        drivers: [
          {
            label: 'Highest ending value',
            direction: 'positive',
            detail: 'Dynamic Guardrails has the highest ending value: $1,250,000.',
          },
        ],
        tradeoffs: ['Dynamic Guardrails has the highest ending value, but 4% Rule projects $20,000 less in taxes.'],
        diagnostics: [
          {
            key: 'tax_drag',
            label: 'Tax drag',
            summary: 'Projected taxes range from $120,000 to $140,000.',
            level: 'medium',
          },
          {
            key: 'depletion_risk',
            label: 'Downside risk',
            summary: 'The lower-end simulation range bottoms at $760,000.',
            level: 'medium',
          },
        ],
        contribution_ordering: [
          'Before choosing a drawdown strategy, keep contributions ordered around free employer match, tax-advantaged room, and needed cash reserves.',
        ],
        review_level: {
          level: 'low',
          summary: 'Normal review is enough before saving this as a decision note.',
          reasons: ['No depletion, warning, or high-spread diagnostic was found.'],
        },
      },
      comparisons: [
        {
          strategy: 'dynamic_guardrails',
          baseline_future_value_usd: 1250000,
          baseline_real_value_usd: 930000,
          total_withdrawals_usd: 820000,
          total_taxes_usd: 140000,
          total_roth_conversions_usd: 60000,
          total_rmds_usd: 90000,
          terminal_age: 95,
          terminal_balance_usd: 510000,
          monte_carlo_p50_future_value_usd: 1180000,
          average_effective_tax_rate: 0.17,
          engine_status: 'degraded',
          warnings: ['Provider fallback used.'],
        },
        {
          strategy: 'four_percent_rule',
          baseline_future_value_usd: 1100000,
          baseline_real_value_usd: 820000,
          total_withdrawals_usd: 760000,
          total_taxes_usd: 120000,
          terminal_age: 95,
          terminal_balance_usd: 430000,
          monte_carlo_p50_future_value_usd: 1190000,
          average_effective_tax_rate: 0.15,
          engine_status: 'ok',
        },
      ],
    },
  }, {
    assumptionSets: {
      active_assumption_set_id: 'default',
      sets: [{ id: 'default', name: 'Default' }, { id: 'policy', name: 'Policy baseline' }],
    },
  }));

  assert.match(markup, /Withdrawal strategy comparison/);
  assert.match(markup, /Dynamic Guardrails/);
  assert.match(markup, /\$1,250,000/);
  assert.match(markup, /\$820,000/);
  assert.match(markup, /\$140,000/);
  assert.match(markup, /17%/);
  assert.match(markup, /Best future value/);
  assert.match(markup, /What this means/);
  assert.match(markup, /Dynamic Guardrails stands out/);
  assert.match(markup, /4% Rule has the lowest projected taxes/);
  assert.match(markup, /Diagnostics/);
  assert.match(markup, /Tax drag: Projected taxes range from \$120,000 to \$140,000/);
  assert.match(markup, /Contribution ordering/);
  assert.match(markup, /free employer match/);
  assert.match(markup, /Trade-offs/);
  assert.match(markup, /Review level/);
  assert.match(markup, /Normal review is enough/);
  assert.match(markup, /Provider fallback used\./);
  assert.match(markup, /Discuss in Copilot/);
  assert.match(markup, /Save decision note/);
});

test('plan scenario workspace renders compact results and decision handoff', () => {
  const markup = String(renderScenarios({
    id: 'plan-1',
    settings: {
      annual_contribution_usd: 25000,
      expected_return_baseline: 0.065,
      inflation_rate: 0.028,
      years: 25,
    },
  }, {
    draft: { annual_contribution_usd: '30000' },
    dirty: true,
    focusedRecommendationId: 'rec-scenario',
    result: {
      plan_id: 'plan-1',
      base_settings: {
        annual_contribution_usd: 25000,
        expected_return_baseline: 0.065,
      },
      candidate_settings: {
        annual_contribution_usd: 30000,
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
      monte_carlo_delta: {
        success_probability_delta: 0.04,
        base_p50_future_value_usd: 1200000,
      },
      simulation_delta: {
        base: { future_value_usd: 1000000 },
        candidate: { future_value_usd: 1042000 },
        changed: true,
        status: 'captured',
        summary: 'Monte Carlo confidence improved.',
      },
    },
    explanation: {
      payload: {
        outcome_label: 'better',
        confidence_level: 'high',
        summary: 'This simulation improves the active plan. Future value changes by +$42,000.',
        drivers: [
          { label: 'Future value', direction: 'positive', detail: 'The candidate result is +$42,000 versus the active plan.' },
          { label: 'Annual contribution', direction: 'neutral', detail: 'Annual contribution changed from $25,000 to $30,000.' },
        ],
        assumption_traces: [
          { explanation: 'Annual contribution changed from $25,000 to $30,000.' },
        ],
        confidence_reasons: ['Changed assumptions are visible and traceable.'],
      },
    },
    reviewLevel: {
      payload: {
        review_level: 'low',
        summary: 'Low review: this looks like a small, well-explained experiment that can stay in the normal simulation workflow.',
        stage_one: {
          name: 'Change size',
          level: 'low',
          summary: 'The changed values look small enough for normal review.',
          reasons: [],
        },
        stage_two: {
          name: 'Result trust',
          level: 'low',
          summary: 'The result is explained clearly enough for normal review.',
          reasons: [],
        },
        recommended_actions: ['Save the simulation if you may want to compare it later.'],
      },
    },
  }, {
    assumptionSets: {
      active_assumption_set_id: 'default',
      sets: [{ id: 'default', name: 'Default' }, { id: 'policy', name: 'Policy baseline' }],
    },
  }));

  assert.match(markup, /Simulations/);
  assert.match(markup, /value="30000"/);
  assert.match(markup, /Run simulation/);
  assert.match(markup, /Baseline/);
  assert.match(markup, /\+\$42,000/);
  assert.match(markup, /\+\$30,000/);
  assert.match(markup, /Monte Carlo/);
  assert.match(markup, /\+4%/);
  assert.match(markup, /\$1,200,000/);
  assert.match(markup, /Changed/);
  assert.match(markup, /Yes/);
  assert.doesNotMatch(markup, /\[object Object\]/);
  assert.match(markup, /Monte Carlo confidence improved\./);
  assert.match(markup, /What this means/);
  assert.match(markup, /Looks better than the active plan/);
  assert.match(markup, /High confidence/);
  assert.match(markup, /Review level/);
  assert.match(markup, /Low review/);
  assert.match(markup, /Normal review is enough/);
  assert.match(markup, /Annual contribution changed from \$25,000 to \$30,000/);
  assert.match(markup, /Discuss in Copilot/);
  assert.match(markup, /Save simulation/);
  assert.match(markup, /Save decision note/);
  assert.match(markup, /href="#inbox\?focus=rec-scenario"/);
});

test('plan scenario workspace renders immutable Saved Simulations', () => {
  const markup = String(renderScenarios({
    id: 'plan-1',
    settings: {},
  }, {
    savedSimulations: {
      payload: {
        simulations: [
          {
            id: 'saved-simulation-1',
            title: 'Early retirement',
            source: 'scenario_branch',
            summary: 'Life-event branch reviewed in v2 Plan.',
            created_at: '2026-05-09T12:00:00+00:00',
            immutable: true,
            result_payload: {
              scenario_deltas: [
                {
                  label: 'baseline',
                  delta_future_value_usd: -60000,
                  delta_real_value_usd: -50000,
                },
              ],
            },
          },
        ],
      },
      focusedComparison: {
        saved_simulation_id: 'saved-simulation-1',
        summary: 'Early retirement was saved against older plan assumptions. Rerun it before using it for a decision.',
        changed_since_saved: true,
        setting_differences: [
          {
            field: 'annual_contribution_usd',
            label: 'Annual contribution',
            saved_value: '$20,000',
            current_value: '$24,000',
          },
        ],
        saved_metrics: {
          delta_future_value_usd: -60000,
          delta_real_value_usd: -50000,
          success_probability_delta: -0.02,
        },
      },
      rerun: {
        saved_simulation: {
          id: 'saved-simulation-rerun',
          title: 'Rerun: Early retirement',
        },
      },
    },
  }, {
    assumptionSets: { sets: [] },
  }));

  assert.match(markup, /Saved Simulations/);
  assert.match(markup, /Experiments you can return to/);
  assert.match(markup, /Early retirement/);
  assert.match(markup, /immutable/);
  assert.match(markup, /Future -\$60,000/);
  assert.match(markup, /Discuss/);
  assert.match(markup, /Compare current/);
  assert.match(markup, /Rerun and save/);
  assert.match(markup, /Attach decision/);
  assert.match(markup, /data-saved-simulation-id="saved-simulation-1"/);
  assert.match(markup, /Saved Simulation Detail/);
  assert.match(markup, /Current plan has changed/);
  assert.match(markup, /Annual contribution moved from \$20,000 to \$24,000/);
  assert.match(markup, /Saved future change/);
  assert.match(markup, /Rerun saved as Rerun: Early retirement/);
});

test('plan timeline workspace renders retirement structure and builds update payload', () => {
  const timeline = {
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
        notes: 'Stop W2 income.',
      },
    ],
  };

  const markup = String(renderTimeline({ id: 'plan-1' }, {
    timeline,
    draft: { target_retirement_age: '64' },
    dirty: true,
    editing: true,
  }));

  assert.match(markup, /Plan timeline/);
  assert.match(markup, /Retirement age/);
  assert.match(markup, /value="64"/);
  assert.match(markup, /2048/);
  assert.match(markup, /Guardrails/);
  assert.match(markup, /Taxable first/);
  assert.match(markup, /Retire/);
  assert.match(markup, /Save timeline/);

  assert.deepEqual(buildTimelinePayload(timeline, {
    target_retirement_age: '64',
    withdrawal_strategy: 'bucket',
    drawdown_order: 'roth_first',
  }), {
    schema_version: 2,
    events: timeline.events,
    retirement: {
      target_retirement_age: 64,
      target_retirement_year: 2048,
      withdrawal_strategy: 'bucket',
      drawdown_order: 'roth_first',
    },
  });
});

test('plan contribution workspace renders rule rows and builds update payload', () => {
  const contributionRules = {
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
      {
        id: 'rule-2',
        account_id: 'acct-roth',
        priority: 2,
        annual_target_usd: 7000,
      },
    ],
  };

  const markup = String(renderContributions({ id: 'plan-1' }, {
    contributionRules,
    draft: {
      employer_match_target_usd: '6500',
      base_rule_type: 'spend',
    },
    dirty: true,
    editing: true,
  }));

  assert.match(markup, /Contribution rules/);
  assert.match(markup, /acct-401k/);
  assert.match(markup, /acct-roth/);
  assert.match(markup, /\$10,000/);
  assert.match(markup, /\$7,000/);
  assert.match(markup, /value="6500"/);
  assert.match(markup, /Save contributions/);

  assert.deepEqual(buildContributionRulesPayload(contributionRules, {
    employer_match_target_usd: '6500',
    age: '41',
    base_rule_type: 'spend',
  }), {
    schema_version: 2,
    base_rule: { type: 'spend' },
    profile_id: 'custom_profile',
    employer_match_target_usd: 6500,
    age: 41,
    rules: contributionRules.rules,
  });
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
