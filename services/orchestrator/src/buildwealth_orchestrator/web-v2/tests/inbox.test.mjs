import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { renderEntries } from '../views/inbox/entries.js';

test('inbox newest sort control uses backend created_at sort value', () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(currentDir, '../views/inbox.js'), 'utf8');

  assert.match(source, /data-sort="created_at"/);
  assert.doesNotMatch(source, /data-sort="newest"/);
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
