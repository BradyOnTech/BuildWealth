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
  assert.match(html, /Taxable · Tax lots missing/);
  assert.match(html, /Taxable Brokerage · Taxable · \$12,500 gain\/loss/);
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
  assert.match(copilotSource, /hidden buy\/sell advice/);
});
