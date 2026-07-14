import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { buildPlanReviewPrompt } from '../views/copilot.js';
import { renderThread } from '../views/copilot/thread.js';

test('copilot thread shows durable stopped and failed turn state', () => {
  const html = String(renderThread([
    {
      id: 'message-1',
      turn_id: 'turn-1',
      turn_status: 'failed',
      role: 'user',
      content: 'Try this question',
      created_at: '2026-07-14T12:00:00.000Z',
      metadata: {},
    },
  ]));

  assert.match(html, /turn-status failed/);
  assert.match(html, />Failed</);
});

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
                goal_items: [{
                  label: 'Home down payment',
                  target_amount_usd: 80000,
                  target_date: '2028-06-01T00:00:00.000Z',
                  priority: 'high',
                  notes: 'Keep the goal separate from emergency reserves.',
                }],
                physical_assets: [{
                  label: 'Primary residence',
                  current_value_usd: 450000,
                  asset_type: 'real_estate',
                  annual_growth_rate: 0.03,
                  purchase_date: '2020-05-15T00:00:00.000Z',
                }],
                tax_profile: {
                  filing_status: 'married_filing_jointly',
                  marginal_tax_rate: 0.24,
                  state: 'MN',
                },
                investment_policy: {
                  max_single_symbol_exposure_pct: 10,
                  max_sector_exposure_pct: 30,
                  minimum_research_confidence: 'medium',
                  minimum_cash_runway_months: 9,
                  max_asset_class_exposure_pct: { equity: 80 },
                  simplicity_preference: 'high',
                  tax_sensitivity: 'high',
                  restricted_symbols: ['NVDA'],
                  restricted_sectors: ['Crypto'],
                },
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
  assert.match(html, /Home down payment/);
  assert.match(html, /\$80,000/);
  assert.match(html, /Jun 1, 2028/);
  assert.match(html, /High priority/);
  assert.match(html, /Keep the goal separate from emergency reserves\./);
  assert.match(html, /Primary residence/);
  assert.match(html, /\$450,000/);
  assert.match(html, /Real estate/);
  assert.match(html, /Purchased May 15, 2020/);
  assert.match(html, /Growth 3%\/yr/);
  assert.match(html, /Tax profile/);
  assert.match(html, /Married filing jointly/);
  assert.match(html, /Marginal 24% · State MN/);
  assert.match(html, /Investment policy/);
  assert.match(html, /Max single symbol 10%/);
  assert.match(html, /Max sector 30%/);
  assert.match(html, /Research confidence Medium/);
  assert.match(html, /Cash floor 9 mo/);
  assert.match(html, /Asset-class cap Equity 80%/);
  assert.match(html, /Simplicity High/);
  assert.match(html, /Tax sensitivity High/);
  assert.match(html, /Avoid NVDA/);
  assert.match(html, /Avoid sectors Crypto/);
  assert.match(html, /No debt/);
  assert.match(html, /data-profile-draft=/);
  assert.match(html, /Apply profile update/);
});

test('copilot thread renders portfolio fit tool results as review cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I checked whether this investment fits your current plan.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'assess_portfolio_fit',
            arguments: { symbol: 'NVDA' },
            result: {
              symbol: 'NVDA',
              fit_status: 'does_not_fit',
              fit_score: 25,
              recommended_next_step: 'review_concentration',
              fit_reasons: [
                'Your active plan horizon is long enough to evaluate growth exposure.',
              ],
              fit_risks: [
                'NVDA already represents 40.0% of the portfolio.',
              ],
              blocking_gaps: [
                'Concentration is above the configured single-symbol limit.',
              ],
              evidence: {
                freshness_status: 'fresh',
                confidence: 'high',
                packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
              },
              plan_impact: {
                time_horizon: 'long',
                years: 25,
              },
              portfolio_impact: {
                existing_position: true,
                current_weight_pct: 40,
                single_holding_max_pct: 10,
                single_holding_policy_source: 'profile.investment_policy',
                candidate_sector: 'Technology',
                sector_weight_after_trade_pct: 31.43,
                sector_max_pct: 30,
                sector_policy_source: 'profile.investment_policy',
                proposed_account: {
                  account_name: 'Taxable Brokerage',
                  tax_treatment: 'taxable',
                  policy_preferred_treatments: ['tax_free'],
                },
                contribution_guidance: {
                  status: 'review',
                  account_id: 'taxable',
                  account_type: 'taxableBrokerage',
                  tax_treatment: 'taxable',
                  recommended_review: 'review_account_location',
                  review_reasons: ['Proposed contribution account conflicts with preferred account-location policy.'],
                },
                investment_policy: {
                  minimum_research_confidence: 'high',
                  minimum_cash_runway_months: 9,
                  max_asset_class_exposure_pct: { equity: 80 },
                  simplicity_preference: 'high',
                  tax_sensitivity: 'high',
                  max_sector_exposure_pct: 30,
                  restricted_symbols: ['NVDA'],
                  restricted_sectors: ['Crypto'],
                },
                account_location: {
                  status: 'partial',
                  tax_lot_coverage: 'missing',
                  tax_treatments: ['taxable'],
                  accounts: [
                    {
                      account_name: 'Taxable Brokerage',
                      tax_treatment: 'taxable',
                      unrealized_gain_loss_usd: 12500,
                      lot_term_mix: 'unknown',
                    },
                  ],
                },
              },
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Investment-fit review/);
  assert.match(html, /NVDA/);
  assert.match(html, /Does not fit/);
  assert.match(html, /25\/100/);
  assert.match(html, /Review concentration/);
  assert.match(html, /Fresh · High/);
  assert.match(html, /Long · 25y/);
  assert.match(html, /40% held/);
  assert.match(html, /10% · Personal policy/);
  assert.match(html, /Research High · Cash floor 9 mo · Asset cap Equity 80% · Simplicity High · Tax High · Sector cap 30% · Avoid NVDA · Avoid Crypto/);
  assert.match(html, /Technology 31\.4% · cap 30%/);
  assert.match(html, /Taxable Brokerage · Taxable · prefers Tax Free/);
  assert.match(html, /Contribution fit/);
  assert.match(html, /Review · Taxable · Review account location · Proposed contribution account conflicts with preferred account-location policy\./);
  assert.match(html, /Taxable · Tax lots missing/);
  assert.match(html, /Taxable Brokerage · Taxable · \$12,500 gain\/loss/);
  assert.match(html, /href="#research\?symbol=NVDA&amp;packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d"/);
  assert.match(html, /active plan horizon is long enough/);
  assert.match(html, /already represents 40\.0% of the portfolio/);
  assert.match(html, /Concentration is above/);
  assert.doesNotMatch(html, /"fit_status"/);
});

test('copilot thread renders drafted investment recommendation tool results as review cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I drafted a review step for your Inbox.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'draft_investment_research_recommendation',
            arguments: { symbol: 'NVDA' },
            result: {
              draft_kind: 'investment_research_recommendation',
              requires_review: true,
              recommendation: {
                id: 'rec-invest-draft',
                title: 'Review NVDA fit before changing exposure',
                detail: 'NVDA conflicts with current concentration policy. Review fit context before making any portfolio decision.',
                priority: 'high',
                status: 'proposed',
                recommendation_type: 'workflow_action',
                source: 'copilot:investment_fit',
                action_payload: {
                  evidence: {
                    symbol: 'NVDA',
                    freshness_status: 'fresh',
                    confidence: 'high',
                    fit_status: 'does_not_fit',
                  },
                  suggested_action: {
                    kind: 'review_portfolio_fit',
                    symbol: 'NVDA',
                  },
                  quality: {
                    actionability: 'review_only',
                    decision_grade: true,
                  },
                },
              },
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Drafted investment review/);
  assert.match(html, /Review NVDA fit before changing exposure/);
  assert.match(html, /NVDA · Fresh · High/);
  assert.match(html, /Review portfolio fit/);
  assert.match(html, /Review only/);
  assert.match(html, /Decision-grade/);
  assert.match(html, /href="#inbox\?focus=rec-invest-draft"/);
  assert.doesNotMatch(html, /"draft_kind"/);
});

test('copilot thread renders compact context-use trace links', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I checked your current context.',
      created_at: '2026-05-08T12:00:00.000Z',
      metadata: {
        context_trace: {
          plan_id: 'plan-1',
          saved_simulation_id: 'saved-simulation-1',
          saved_simulation_title: 'Early retirement simulation',
          symbols: ['NVDA'],
          retrieval: {
            returned_count: 4,
            citation_count: 2,
            truncated: true,
          },
          conflict_review_items: {
            count: 1,
            ids: ['rec-conflict'],
          },
          context_warnings: [
            {
              type: 'missing_or_stale_context',
              message: 'Tax profile needs review before decision-grade advice.',
            },
          ],
          captured_context_candidates: [
            {
              id: 'ctx-tax',
              target_domain: 'profile',
              target_field: 'tax_profile.marginal_tax_rate',
              lifecycle_state: 'pending_review',
              prompt_influence: 'mention_only',
              review_item: {
                recommendation_id: 'rec-context',
              },
            },
          ],
        },
      },
    },
  ]));

  assert.match(html, /Context used/);
  assert.match(html, /plan scoped · 1 saved simulation · 1 symbol · 4 retrieved · 2 citations · 1 capture · 1 context issue/);
  assert.match(html, /href="#plan\?id=plan-1"/);
  assert.match(html, /href="#plan\?id=plan-1&amp;section=scenarios&amp;saved=saved-simulation-1"/);
  assert.match(html, /Early retirement simulation/);
  assert.match(html, /href="#portfolio\?fit=NVDA"/);
  assert.match(html, /href="#research\?symbol=NVDA"/);
  assert.match(html, /href="#inbox\?focus=rec-conflict"/);
  assert.match(html, /href="#inbox\?focus=rec-context"/);
  assert.match(html, /Tax profile needs review before decision-grade advice\./);
  assert.match(html, /Context was trimmed to fit\./);
  assert.match(html, /New captures are waiting for review\./);
});

test('copilot plan review prompts request bounded context', () => {
  const prompt = buildPlanReviewPrompt('review_plan_assumptions', { planId: 'plan-abc' });

  assert.match(prompt, /plan-abc/);
  assert.match(prompt, /get_plan_review_context/);
  assert.match(prompt, /active assumption set/i);
  assert.match(prompt, /top 5/i);
  assert.match(prompt, /health signals/i);
  assert.match(prompt, /selected artifact ids and citations/i);
  assert.match(prompt, /Do not request full artifact contents/i);
  assert.match(prompt, /Do not request long decision history/i);
});

test('copilot and plan views wire plan review routes', () => {
  const copilotSource = readFileSync(
    resolve(import.meta.dirname, '../views/copilot.js'),
    'utf8',
  );
  const planSource = readFileSync(
    resolve(import.meta.dirname, '../views/plan.js'),
    'utf8',
  );

  assert.match(copilotSource, /review_plan_assumptions/);
  assert.match(copilotSource, /explain_scenario_diff/);
  assert.match(copilotSource, /params\.plan/);
  assert.match(planSource, /#copilot\?intent=review_plan_assumptions&amp;plan=/);
  assert.match(planSource, /#copilot\?intent=explain_scenario_diff&amp;plan=/);
});

test('copilot thread renders bounded plan review trace cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I reviewed the plan context.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'get_plan_review_context',
            arguments: { plan_id: 'plan-1' },
            result: {
              plan_id: 'plan-1',
              title: 'Retirement Plan',
              active_assumption_set: {
                id: 'policy',
                name: 'Policy baseline',
                summary: {
                  expected_return_baseline: 0.065,
                  marginal_tax_rate: null,
                },
              },
              health_signals: [
                {
                  id: 'tax-assumptions',
                  severity: 'weak',
                  title: 'Tax assumptions need review',
                  detail: 'Marginal tax rate is missing.',
                  section: 'assumptions',
                },
              ],
              selected_artifacts: [
                {
                  id: 'artifact-dossier-msft',
                  title: 'Research Dossier - MSFT',
                  citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
                  content: 'This full artifact body should not render.',
                },
              ],
              suggested_next_step: {
                label: 'Review assumptions',
                section: 'assumptions',
              },
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Plan review context/);
  assert.match(html, /Retirement Plan/);
  assert.match(html, /Policy baseline/);
  assert.match(html, /Tax assumptions need review/);
  assert.match(html, /Marginal tax rate is missing\./);
  assert.match(html, /research-evidence:yfinance:MSFT:6mo:1d/);
  assert.match(html, /href="#plan\?id=plan-1&amp;section=assumptions"/);
  assert.match(html, /Review assumptions/);
  assert.doesNotMatch(html, /full artifact body/);
  assert.doesNotMatch(html, /"health_signals"/);
});

test('copilot thread renders plan simulation trace cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I compared the scenario.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'run_plan_scenario_diff',
            arguments: { plan_id: 'plan-1', annual_contribution_usd: 30000 },
            result: {
              plan_id: 'plan-1',
              scenario_deltas: [
                {
                  label: 'baseline',
                  base_future_value_usd: 1000000,
                  candidate_future_value_usd: 1042000,
                  delta_future_value_usd: 42000,
                  delta_real_value_usd: 30000,
                },
              ],
              monte_carlo_delta: { success_probability_delta: 0.04 },
              warnings: ['Contribution rule coverage is partial.'],
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Plan simulation/);
  assert.match(html, /Baseline/);
  assert.match(html, /\+\$42,000/);
  assert.match(html, /\+4%/);
  assert.match(html, /Contribution rule coverage is partial\./);
  assert.match(html, /href="#plan\?id=plan-1&amp;section=scenarios"/);
  assert.doesNotMatch(html, /"scenario_deltas"/);
});

test('copilot thread renders saved simulation trace cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I checked that saved simulation.',
      created_at: '2026-04-26T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'compare_plan_saved_simulation_current',
            arguments: { plan_id: 'plan-1', saved_simulation_id: 'saved-simulation-1' },
            result: {
              plan_id: 'plan-1',
              saved_simulation_id: 'saved-simulation-1',
              summary: 'This saved simulation was run against older assumptions.',
              changed_since_saved: true,
              setting_differences: [
                {
                  field: 'annual_contribution_usd',
                  label: 'Annual contribution',
                  saved_value: '$20,000',
                  current_value: '$24,000',
                },
              ],
              saved_simulation: {
                id: 'saved-simulation-1',
                title: 'Early retirement',
              },
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Saved Simulation/);
  assert.match(html, /Early retirement/);
  assert.match(html, /Needs rerun/);
  assert.match(html, /This saved simulation was run against older assumptions\./);
  assert.match(html, /Annual contribution moved from \$20,000 to \$24,000/);
  assert.match(html, /href="#plan\?id=plan-1&amp;section=scenarios&amp;saved=saved-simulation-1"/);
  assert.doesNotMatch(html, /"setting_differences"/);
});

test('copilot thread renders watchlist thesis revision draft cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I drafted a revised watchlist thesis for review.',
      created_at: '2026-04-29T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'draft_watchlist_thesis_revision',
            arguments: { symbol: 'NVDA' },
            result: {
              draft_kind: 'watchlist_thesis_revision',
              requires_confirmation: true,
              target: { type: 'watchlist', symbol: 'NVDA', data_source: 'OPENBB' },
              current: {
                thesis: 'Old NVDA thesis.',
                reference_price_usd: 800,
              },
              proposed: {
                thesis: 'Only keep NVDA on the watchlist if concentration and valuation stay inside policy.',
                note: 'Revisit if evidence freshness degrades.',
                reference_price_usd: 898,
                review_window_days: 45,
              },
              rationale: 'Price moved materially from the prior thesis reference.',
              evidence_gaps: ['Tax lot impact not reviewed.'],
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Review thesis revision/);
  assert.match(html, /NVDA · OPENBB/);
  assert.match(html, /Old NVDA thesis\./);
  assert.match(html, /Only keep NVDA on the watchlist/);
  assert.match(html, /Revisit if evidence freshness degrades\./);
  assert.match(html, /\$800/);
  assert.match(html, /\$898/);
  assert.match(html, /45 days/);
  assert.match(html, /Price moved materially/);
  assert.match(html, /Tax lot impact not reviewed\./);
  assert.match(html, /data-thesis-draft=/);
  assert.match(html, /Save revised thesis/);
  assert.doesNotMatch(html, /"draft_kind"/);
});

test('copilot thread renders dossier thesis revision draft cards', () => {
  const html = String(renderThread([
    {
      role: 'assistant',
      content: 'I drafted a dossier thesis revision for review.',
      created_at: '2026-04-29T12:00:00.000Z',
      metadata: {
        tool_calls: [
          {
            name: 'draft_dossier_thesis_revision',
            arguments: { artifact_id: 'artifact-dossier-msft' },
            result: {
              draft_kind: 'dossier_thesis_revision',
              requires_confirmation: true,
              target: {
                type: 'dossier',
                plan_id: 'plan-1',
                artifact_id: 'artifact-dossier-msft',
                title: 'Research Dossier - MSFT vs VTI',
              },
              current: {
                thesis: 'Old dossier thesis.',
                reference_price_usd: 390,
              },
              proposed: {
                thesis: 'Revised dossier thesis focused on fit, evidence freshness, and portfolio concentration.',
                reference_price_usd: 410,
                review_window_days: 60,
              },
              rationale: 'The prior thesis expired and provider evidence is stale.',
              evidence_gaps: ['Provider freshness should be refreshed.'],
            },
          },
        ],
      },
    },
  ]));

  assert.match(html, /Review thesis revision/);
  assert.match(html, /Research Dossier - MSFT vs VTI/);
  assert.match(html, /Old dossier thesis\./);
  assert.match(html, /Revised dossier thesis focused on fit/);
  assert.match(html, /\$390/);
  assert.match(html, /\$410/);
  assert.match(html, /60 days/);
  assert.match(html, /prior thesis expired/);
  assert.match(html, /Provider freshness should be refreshed\./);
  assert.match(html, /data-thesis-draft=/);
  assert.match(html, /Save revised thesis/);
  assert.doesNotMatch(html, /"draft_kind"/);
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

test('copilot view wires thesis draft save action to watchlist thesis API', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');
  const apiSource = readFileSync(resolve(currentDir, '../lib/api.js'), 'utf8');

  assert.match(apiSource, /saveWatchlistThesisRevision/);
  assert.match(apiSource, /saveDossierThesisRevision/);
  assert.match(apiSource, /\/api\/portfolio\/watchlist\/.*thesis/);
  assert.match(apiSource, /\/api\/plans\/.*artifacts.*thesis/);
  assert.match(copilotSource, /\[data-thesis-draft\]/);
  assert.match(copilotSource, /recommendationFocus/);
  assert.match(copilotSource, /patch\.recommendation_id/);
  assert.match(copilotSource, /api\.saveWatchlistThesisRevision/);
  assert.match(copilotSource, /api\.saveDossierThesisRevision/);
  assert.match(copilotSource, /Watchlist thesis updated/);
  assert.match(copilotSource, /Dossier thesis updated/);
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

test('copilot view exposes guided debt onboarding entry point', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');

  assert.match(copilotSource, /DEBT_SETUP_PROMPT/);
  assert.match(copilotSource, /Help me review debt for my financial profile/);
  assert.match(copilotSource, /debt_items/);
  assert.match(copilotSource, /no_debt/);
  assert.match(copilotSource, /Add debt with Copilot/);
});

test('copilot view maps inbox recommendation intents to focused draft prompts', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');

  assert.match(copilotSource, /recommendationFocusPrompt/);
  assert.match(copilotSource, /complete-context/);
  assert.match(copilotSource, /Review recommendation/);
  assert.match(copilotSource, /missing context/);
  assert.match(copilotSource, /investment-fit/);
  assert.match(copilotSource, /proposed_account_id/);
  assert.match(copilotSource, /draft_watchlist_thesis_revision/);
  assert.match(copilotSource, /draft_dossier_thesis_revision/);
  assert.match(copilotSource, /hidden buy\/sell advice/);
});

test('copilot view exposes investment policy guardrail prompt', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const copilotSource = readFileSync(resolve(currentDir, '../views/copilot.js'), 'utf8');

  assert.match(copilotSource, /INVESTMENT_POLICY_SETUP_PROMPT/);
  assert.match(copilotSource, /Help me define my personal investment policy/);
  assert.match(copilotSource, /max_single_symbol_exposure_pct/);
  assert.match(copilotSource, /max_sector_exposure_pct/);
  assert.match(copilotSource, /minimum_research_confidence/);
  assert.match(copilotSource, /minimum_cash_runway_months/);
  assert.match(copilotSource, /max_asset_class_exposure_pct/);
  assert.match(copilotSource, /simplicity_preference/);
  assert.match(copilotSource, /tax_sensitivity/);
  assert.match(copilotSource, /restricted_symbols/);
  assert.match(copilotSource, /restricted_sectors/);
  assert.match(copilotSource, /#copilot\\?intent=investment-policy|investment-policy/);
  assert.match(copilotSource, /Define policy with Copilot/);
});
