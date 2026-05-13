import test from 'node:test';
import assert from 'node:assert/strict';
import { computeRunway, renderCommandCards, renderMove } from '../views/today.js';

test('today hero runway uses emergency-fund months from the dashboard payload', () => {
  assert.equal(computeRunway({
    emergency_fund_months: 4,
    monthly_surplus_usd: 3500,
    net_worth_usd: 580000,
  }), '4.0');
});

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
    confidence_domains: [
      {
        id: 'profile',
        label: 'Profile',
        status: 'missing_context',
        detail: 'Tax profile blocks decision-grade advice.',
        metric_label: 'Ready',
        metric_value: '70%',
        href: '#copilot?intent=complete-context',
      },
      {
        id: 'plan',
        label: 'Plan',
        status: 'usable_with_caveats',
        detail: 'Plan assumptions are mostly complete.',
        metric_label: 'Complete',
        metric_value: '72%',
        href: '#plan',
      },
      {
        id: 'research',
        label: 'Research',
        status: 'decision_grade',
        detail: 'Evidence packets are fresh.',
        metric_label: 'Ready',
        metric_value: '2/2',
        href: '#research',
      },
    ],
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
      {
        id: 'what-changed',
        title: 'What changed',
        status: 'warning',
        detail: 'Portfolio value is $15,000 higher since last review.',
        metric_label: 'Changes',
        metric_value: '2',
        action_label: 'Mark reviewed',
        href: '#today?review=complete',
      },
      {
        id: 'stale-assumptions',
        title: 'Stale assumptions',
        status: 'warning',
        detail: '1 assumption review is open.',
        metric_label: 'Open',
        metric_value: '1',
        action_label: 'Review assumptions',
        href: '#inbox?focus=rec-stale',
      },
      {
        id: 'research-readiness',
        title: 'Research readiness',
        status: 'ready',
        detail: 'Research evidence is fresh. Cached research age: <1m.',
        metric_label: 'Ready',
        metric_value: '2/2',
        action_label: 'Refresh research',
        href: '#today?refresh=research',
      },
      {
        id: 'copilot-drafts',
        title: 'Copilot prepared reviews',
        status: 'warning',
        detail: '1 Copilot-drafted review is waiting: NVDA · fresh evidence · review-only.',
        metric_label: 'Drafts',
        metric_value: '1',
        action_label: 'Review draft',
        href: '#inbox?focus=rec-copilot',
      },
      {
        id: 'investment-policy',
        title: 'Investment policy',
        status: 'warning',
        detail: 'Set personal investment guardrails such as max single-symbol exposure. Investment-fit confidence improves after these guardrails are defined.',
        metric_label: 'Guardrails',
        metric_value: 'Missing',
        action_label: 'Define policy',
        href: '#copilot?intent=investment-policy',
      },
    ],
  }, {
    enabled_count: 2,
    reachable_count: 1,
    degraded_count: 3,
  }));

  assert.match(markup, /Command center/);
  assert.match(markup, /Confidence heat map/);
  assert.match(markup, /missing context/);
  assert.match(markup, /usable with caveats/);
  assert.match(markup, /decision grade/);
  assert.match(markup, /href="#plan"/);
  assert.match(markup, /Profile readiness/);
  assert.match(markup, /Complete context/);
  assert.match(markup, /href="#copilot\?intent=complete-context"/);
  assert.match(markup, /Portfolio risk/);
  assert.match(markup, /40%/);
  assert.match(markup, /What changed/);
  assert.match(markup, /href="#today\?review=complete"/);
  assert.match(markup, /Stale assumptions/);
  assert.match(markup, /href="#inbox\?focus=rec-stale"/);
  assert.match(markup, /Research readiness/);
  assert.match(markup, /href="#today\?refresh=research"/);
  assert.match(markup, /Copilot prepared reviews/);
  assert.match(markup, /NVDA · fresh evidence · review-only/);
  assert.match(markup, /href="#inbox\?focus=rec-copilot"/);
  assert.match(markup, /Investment policy/);
  assert.match(markup, /Guardrails <b>Missing<\/b>/);
  assert.match(markup, /href="#copilot\?intent=investment-policy"/);
  assert.match(markup, /Service readiness/);
  assert.match(markup, /1\/2/);
  assert.match(markup, /3 service issue/);
});
