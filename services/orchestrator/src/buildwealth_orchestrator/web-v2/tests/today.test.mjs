import test from 'node:test';
import assert from 'node:assert/strict';
import { renderCommandCards, renderMove } from '../views/today.js';

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

test('today command cards render decision state with actions', () => {
  const markup = String(renderCommandCards({
    command_cards: [
      {
        id: 'profile-readiness',
        title: 'Profile readiness',
        status: 'warning',
        detail: 'Next gap: Tax profile.',
        metric_label: 'Complete',
        metric_value: '80%',
        action_label: 'Complete context',
        href: '#copilot?intent=complete-context',
      },
      {
        id: 'portfolio-risk',
        title: 'Portfolio risk',
        status: 'critical',
        detail: 'Top holding concentration is high around AAPL.',
        metric_label: 'Top holding',
        metric_value: '40%',
        action_label: 'Review risk',
        href: '#portfolio',
      },
    ],
  }));

  assert.match(markup, /Command center/);
  assert.match(markup, /Profile readiness/);
  assert.match(markup, /Complete context/);
  assert.match(markup, /href="#copilot\?intent=complete-context"/);
  assert.match(markup, /Portfolio risk/);
  assert.match(markup, /40%/);
});
