import test from 'node:test';
import assert from 'node:assert/strict';
import { renderMove } from '../views/today.js';

test('today move renders top-action quality explanation', () => {
  const markup = String(renderMove({
    top_next_actions: [
      {
        recommendation_id: 'rec-1',
        title: 'Increase annual contributions',
        detail: 'Raise annual contribution after preview.',
        priority: 'high',
        source: 'generator:plan_tracking',
        quality_summary: 'high impact · medium confidence · fresh evidence · previewable · decision-grade',
        action_hint: 'Open Recommendation Inbox to preview before applying.',
        score_reasons: ['Recommendation can be previewed before apply.'],
      },
    ],
  }));

  assert.match(markup, /high impact · medium confidence · fresh evidence · previewable · decision-grade/);
  assert.match(markup, /Open Recommendation Inbox to preview before applying\./);
});
