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

  // Density contract: at most three attention cards sit in the scroll path;
  // everything else (including the heat map) is behind the overflow expander.
  const [beforeOverflow, insideOverflow] = markup.split('<details class="command-overflow">');
  assert.ok(insideOverflow, 'overflow expander renders when there are quiet cards');
  assert.match(beforeOverflow, /Portfolio risk/); // the one critical card leads
  assert.doesNotMatch(beforeOverflow, /Research readiness/); // ready cards are tucked
  assert.doesNotMatch(beforeOverflow, /Confidence heat map/);
  assert.match(insideOverflow, /Research readiness/);
  assert.match(insideOverflow, /Confidence heat map/);
  const shownCount = (beforeOverflow.match(/command-card /g) || []).length;
  assert.ok(shownCount <= 3, `expected at most 3 visible cards, saw ${shownCount}`);
});

test('today command center with all-quiet cards shows no cards in the scroll path', () => {
  const markup = String(renderCommandCards({
    command_cards: [
      { id: 'a', title: 'Research readiness', status: 'ready', detail: 'Fresh.' },
      { id: 'b', title: 'Profile readiness', status: 'ready', detail: 'Complete.' },
    ],
  }));
  const [beforeOverflow, insideOverflow] = markup.split('<details class="command-overflow">');
  assert.match(beforeOverflow, /inputs behind today’s advice are ready/);
  assert.doesNotMatch(beforeOverflow, /command-card /);
  assert.match(insideOverflow, /All 2 inputs are quiet/);
  assert.match(insideOverflow, /Research readiness/);
});

/* ─────────────  The income bend on Today  ───────────── */

test('income bend: earliest recurring income reduction wins, noise ignored', async () => {
  const { findIncomeBend, findCushionGoal } = await import('../views/today.js');
  const bend = findIncomeBend([
    { label: 'Raise', impact_type: 'income', amount_usd: 500, recurring_frequency: 'monthly', date: '2027-01-01' },
    { label: 'Home down payment', impact_type: 'expense', amount_usd: 70000, recurring_frequency: 'one_time', date: '2029-01-01' },
    { label: 'Part-time', impact_type: 'income', amount_usd: -1500, recurring_frequency: 'monthly', date: '2029-03-01' },
    { label: 'Stay-at-home', impact_type: 'income', amount_usd: -2000, recurring_frequency: 'monthly', date: '2028-01-01' },
    { label: 'Undated', impact_type: 'income', amount_usd: -900, recurring_frequency: 'monthly', date: '' },
  ]);
  assert.equal(bend.label, 'Stay-at-home');

  assert.equal(findIncomeBend([]), null);
  assert.equal(findIncomeBend(null), null);

  const cushion = findCushionGoal([
    { label: 'Home down payment', target_amount_usd: 70000 },
    { label: 'Income step-down cushion', target_amount_usd: 12000 },
  ]);
  assert.equal(cushion.target_amount_usd, 12000);
});

test('today hero wires the income bend into the marginalia', async () => {
  const { readFileSync } = await import('node:fs');
  const { resolve } = await import('node:path');
  const source = readFileSync(resolve(import.meta.dirname, '../views/today.js'), 'utf8');
  assert.match(source, /loadIncomeBend\(\)/);
  assert.match(source, /incomeBendMarginaliaItem\(incomeBend\)/);
  // Honest tense: a bend already underway reads as "since", not a forecast.
  assert.match(source, /income stepped down \(since/);
  assert.match(source, /income steps down/);
  // The tooltip says the trajectory already models it.
  assert.match(source, /already models this/);
});

test('first-run welcome path routes to the life-plans interview', async () => {
  const { renderWelcomeHero } = await import('../views/today.js');
  const markup = String(renderWelcomeHero(new Date('2026-07-07T00:00:00Z')));
  // Four numbered rows: three actions plus the payoff.
  for (const numeral of ['I.', 'II.', 'III.', 'IV.']) {
    assert.match(markup, new RegExp(numeral.replace('.', '\\.')));
  }
  // The interview earns its own first-run step, pointing at Profile → Goals.
  assert.match(markup, /Tell it what's coming/);
  assert.match(markup, /The five-minute interview/);
  assert.match(markup, /href="#profile\?section=goals"/);
  // The lede promises foresight, not just the current number.
  assert.match(markup, /what's ahead/);
});
