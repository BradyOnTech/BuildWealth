import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { renderEntries } from '../views/inbox/entries.js';
import { renderQuality } from '../views/inbox/quality.js';

test('inbox newest sort control uses backend created_at sort value', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/inbox.js'), 'utf8');

  assert.match(source, /data-sort="created_at"/);
  assert.doesNotMatch(source, /data-sort="newest"/);
});

test('inbox wires outcome preset buttons into outcome notes', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/inbox.js'), 'utf8');

  assert.match(source, /data-outcome-preset/);
  assert.match(source, /appendOutcomePreset/);
});

test('inbox quality renders investment process calibration summary', () => {
  const markup = String(renderQuality({
    count: 4,
    calibration_summary: {
      measured_count: 1,
      future_value_direction_match_rate_pct: 100,
      mean_future_value_abs_error_usd: 500,
    },
    process_calibration_summary: {
      count: 3,
      useful_count: 2,
      weak_count: 1,
      useful_rate_pct: 66.67,
    },
    process_calibration_by_outcome: [
      { key: 'useful_review', count: 2 },
      { key: 'insufficient_evidence', count: 1 },
    ],
  }));

  assert.match(markup, /Investment review calibration/);
  assert.match(markup, /2 of 3 investment\/research reviews were useful/);
  assert.match(markup, /Useful review/);
  assert.match(markup, /Evidence insufficient/);
  assert.match(markup, /67%/);
});

test('inbox entries render recommendation quality metadata', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-1',
      status: 'proposed',
      priority: 'high',
      source: 'generator:cash_liquidity',
      recommendation_type: 'workflow_action',
      title: 'Build emergency cash reserve',
      detail: 'Cash covers less than the target reserve.',
      action_payload: {
        quality: {
          confidence_level: 'high',
          freshness_status: 'fresh',
          actionability: 'review_only',
          reversibility: 'high',
          impact: {
            level: 'high',
            summary: 'Build toward a three-month reserve.',
          },
          blocking_context: [],
          decision_grade: true,
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /high confidence/);
  assert.match(markup, /fresh evidence/);
  assert.match(markup, /review only/);
  assert.match(markup, /high impact/);
  assert.match(markup, /decision grade/);
});

test('inbox actions use quality actionability semantics', () => {
  const markup = String(renderEntries([
    {
      id: 'previewable',
      status: 'proposed',
      priority: 'high',
      recommendation_type: 'plan_settings_update',
      title: 'Increase contributions',
      detail: 'Preview before applying.',
      action_payload: { quality: { actionability: 'previewable', blocking_context: [] } },
    },
    {
      id: 'review-only',
      status: 'proposed',
      priority: 'medium',
      recommendation_type: 'workflow_action',
      title: 'Review cash reserve',
      detail: 'Review the reserve target.',
      action_payload: { quality: { actionability: 'review_only', blocking_context: [] } },
    },
    {
      id: 'context-gap',
      status: 'proposed',
      priority: 'medium',
      recommendation_type: 'workflow_action',
      title: 'Complete expense profile',
      detail: 'Expenses are missing.',
      action_payload: {
        quality: {
          actionability: 'context_gathering',
          blocking_context: ['financial_profile.expenses'],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /Preview &amp; apply/);
  assert.match(markup, /Review decision/);
  assert.match(markup, /Complete context/);
  assert.match(markup, /financial profile expenses/);
  assert.match(markup, /href="#copilot\?focus=context-gap&amp;intent=complete-context"/);
  assert.doesNotMatch(markup, /data-action="apply" data-id="context-gap"/);
});

test('inbox outcome form is guided by recommendation source and actionability', () => {
  const markup = String(renderEntries([
    {
      id: 'stale-assumptions',
      status: 'applied',
      priority: 'medium',
      recommendation_type: 'workflow_action',
      source: 'generator:stale_assumptions',
      title: 'Review stale assumptions',
      detail: 'Plan assumptions are stale.',
      action_payload: {
        quality: {
          actionability: 'review_only',
          blocking_context: [],
        },
      },
    },
    {
      id: 'profile-gap',
      status: 'applied',
      priority: 'medium',
      recommendation_type: 'workflow_action',
      source: 'generator:profile_completeness',
      title: 'Complete expense profile',
      detail: 'Expenses were missing.',
      action_payload: {
        quality: {
          actionability: 'context_gathering',
          blocking_context: ['financial_profile.expenses'],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: { id: 'stale-assumptions', mode: 'outcome', busy: false, error: null },
    emptyMessage: '',
  }));

  assert.match(markup, /What changed after the assumption review\?/);
  assert.match(markup, /Assumptions reviewed/);
  assert.match(markup, /manual assumption review/);
  assert.match(markup, /reviewed assumptions, changes made, follow-up needed/);

  const profileMarkup = String(renderEntries([
    {
      id: 'profile-gap',
      status: 'applied',
      priority: 'medium',
      recommendation_type: 'workflow_action',
      source: 'generator:profile_completeness',
      title: 'Complete expense profile',
      detail: 'Expenses were missing.',
      action_payload: {
        quality: {
          actionability: 'context_gathering',
          blocking_context: ['financial_profile.expenses'],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: { id: 'profile-gap', mode: 'outcome', busy: false, error: null },
    emptyMessage: '',
  }));

  assert.match(profileMarkup, /Was the missing context completed\?/);
  assert.match(profileMarkup, /Context completed/);
  assert.match(profileMarkup, /profile readiness review/);
});

test('inbox investment research rows render fit routing instead of generic workflow only', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-invest',
      status: 'proposed',
      priority: 'high',
      source: 'generator:watchlist_research',
      recommendation_type: 'workflow_action',
      title: 'Review why NVDA does not currently fit',
      detail: 'NVDA currently conflicts with portfolio-fit checks.',
      action_payload: {
        generator: {
          signal_type: 'watchlist_research',
        },
        evidence: {
          symbol: 'NVDA',
          provider: 'yfinance',
          freshness_status: 'fresh',
          fit_status: 'does_not_fit',
          research_evidence_packet_id: 'research-evidence:yfinance:NVDA:6mo:1d',
        },
        suggested_action: {
          kind: 'review_portfolio_fit',
          symbol: 'NVDA',
          fit_status: 'does_not_fit',
        },
        quality: {
          actionability: 'review_only',
          confidence_level: 'medium',
          freshness_status: 'fresh',
          blocking_context: [],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /Investment-fit route/);
  assert.match(markup, /symbol NVDA · fresh evidence · via yfinance · does not fit fit/);
  assert.match(markup, /href="#portfolio\?fit=NVDA&amp;focus=rec-invest"/);
  assert.match(markup, /href="#research\?symbol=NVDA&amp;packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d"/);
  assert.match(markup, /href="#research\?compare=NVDA&amp;packet=research-evidence%3Ayfinance%3ANVDA%3A6mo%3A1d"/);
  assert.match(markup, /href="#copilot\?focus=rec-invest&amp;intent=investment-fit"/);
  assert.match(markup, />Review fit <span class="arrow">→<\/span>/);
});

test('inbox copilot investment drafts render fit routing', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-copilot-invest',
      status: 'proposed',
      priority: 'high',
      source: 'copilot:investment_fit',
      recommendation_type: 'workflow_action',
      title: 'Review NVDA fit before changing exposure',
      detail: 'NVDA conflicts with current concentration policy.',
      action_payload: {
        generator: {
          signal_type: 'investment_fit_discussion',
        },
        evidence: {
          symbol: 'NVDA',
          provider: 'yfinance',
          freshness_status: 'fresh',
          fit_status: 'does_not_fit',
        },
        suggested_action: {
          kind: 'review_portfolio_fit',
          symbol: 'NVDA',
          fit_status: 'does_not_fit',
        },
        quality: {
          actionability: 'review_only',
          confidence_level: 'high',
          freshness_status: 'fresh',
          blocking_context: [],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /Investment-fit route/);
  assert.match(markup, /symbol NVDA · fresh evidence · via yfinance · does not fit fit/);
  assert.match(markup, /href="#portfolio\?fit=NVDA&amp;focus=rec-copilot-invest"/);
  assert.match(markup, /href="#copilot\?focus=rec-copilot-invest&amp;intent=investment-fit"/);
});

test('inbox research thesis expiration rows route to saved dossier review', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-thesis-expired',
      status: 'proposed',
      priority: 'medium',
      source: 'generator:research_thesis_expiration',
      recommendation_type: 'workflow_action',
      title: 'Refresh stale research thesis for MSFT / VTI',
      detail: 'The saved research thesis is past the review window.',
      plan_id: 'plan-1',
      action_payload: {
        generator: {
          signal_type: 'research_thesis_expiration',
        },
        evidence: {
          artifact_id: 'artifact-dossier-msft',
          plan_id: 'plan-1',
          symbols: ['MSFT', 'VTI'],
          freshness_status: 'stale',
          packet_citations: ['research-evidence:yfinance:MSFT:6mo:1d'],
        },
        suggested_action: {
          kind: 'review_research_thesis',
          artifact_id: 'artifact-dossier-msft',
          plan_id: 'plan-1',
          symbols: ['MSFT', 'VTI'],
        },
        quality: {
          actionability: 'review_only',
          confidence_level: 'medium',
          freshness_status: 'stale',
          blocking_context: ['research.thesis_expired'],
        },
      },
    },
  ], {
    planLookup: new Map([['plan-1', 'Primary Plan']]),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /Investment-fit route/);
  assert.match(markup, /symbol MSFT · stale evidence/);
  assert.match(markup, /href="#research\?thesisReview=artifact-dossier-msft&amp;plan=plan-1&amp;focus=rec-thesis-expired"/);
  assert.match(markup, /Review thesis\s*<span class="arrow">→<\/span>/);
});

test('inbox copilot investment outcome form captures process calibration', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-copilot-invest',
      status: 'applied',
      priority: 'high',
      source: 'copilot:investment_fit',
      recommendation_type: 'workflow_action',
      title: 'Review NVDA fit before changing exposure',
      detail: 'NVDA conflicts with current concentration policy.',
      action_payload: {
        generator: {
          signal_type: 'investment_fit_discussion',
        },
        evidence: {
          symbol: 'NVDA',
          freshness_status: 'fresh',
        },
        quality: {
          actionability: 'review_only',
          calibration: {
            domain: 'investment_research',
            track_process_outcome: true,
          },
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: { id: 'rec-copilot-invest', mode: 'outcome', busy: false, error: null },
    emptyMessage: '',
  }));

  assert.match(markup, /Did the investment-fit review help\?/);
  assert.match(markup, /name="process_outcome"/);
  assert.match(markup, /data-outcome-code="useful_review"/);
  assert.match(markup, /Evidence insufficient/);
  assert.match(markup, /copilot investment review/);
});

test('inbox investment research refresh rows route primary action to research', () => {
  const markup = String(renderEntries([
    {
      id: 'rec-refresh',
      status: 'proposed',
      priority: 'medium',
      source: 'generator:watchlist_research',
      recommendation_type: 'workflow_action',
      title: 'Refresh research evidence for MSFT',
      detail: 'Research evidence is partial.',
      action_payload: {
        generator: { signal_type: 'watchlist_research' },
        evidence: {
          symbol: 'MSFT',
          provider: 'yfinance',
          freshness_status: 'partial',
        },
        suggested_action: {
          kind: 'refresh_research_evidence',
          symbol: 'MSFT',
        },
        quality: {
          actionability: 'context_gathering',
          blocking_context: ['research.history'],
        },
      },
    },
  ], {
    planLookup: new Map(),
    expanded: null,
    emptyMessage: '',
  }));

  assert.match(markup, /Open research/);
  assert.match(markup, /href="#research\?symbol=MSFT"/);
  assert.doesNotMatch(markup, /Complete context <span class="arrow">→<\/span>/);
});
