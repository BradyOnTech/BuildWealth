import test from 'node:test';
import assert from 'node:assert/strict';
import {
  strengthHeadline,
  strengthExplain,
  fundedPhrase,
  spreadPhrase,
  medianPhrase,
  formatExpenseScale,
  deltaMoney,
  deltaPoints,
  improvementChips,
  changedLevers,
  isDirty,
  failureSentence,
  GLOSSARY,
} from '../views/studio/language.js';
import {
  heroFigure,
  terminalFigure,
  failureFigure,
  scenarioStrip,
} from '../views/studio/charts.js';

const ROWS = Array.from({ length: 11 }, (_, index) => {
  const year = 2030 + index;
  const step = year - 2029;
  return {
    year,
    age: 40 + index,
    p10_ending_balance_usd: step * 1000,
    p25_ending_balance_usd: step * 2000,
    p50_ending_balance_usd: step * 3000,
    p75_ending_balance_usd: step * 4000,
    p90_ending_balance_usd: step * 5000,
    p10_ending_balance_real_usd: step * 800,
    p25_ending_balance_real_usd: step * 1600,
    p50_ending_balance_real_usd: step * 2400,
    p75_ending_balance_real_usd: step * 3200,
    p90_ending_balance_real_usd: step * 4000,
  };
});

const MC = {
  runs: 1000,
  plan_strength_label: 'Workable',
  plan_strength_score: 82,
  plan_strength_summary: 'Most simulated paths stayed funded.',
  funded_trial_rate_pct: 82,
  p10_future_value_usd: 200000,
  p50_future_value_usd: 500000,
  p90_future_value_usd: 900000,
  p10_real_value_usd: 150000,
  p50_real_value_usd: 380000,
  p90_real_value_usd: 700000,
  percentile_timeline: ROWS,
  failure_analysis: {
    failed_trial_count: 180,
    first_failure_year_median: 2045,
    first_failure_year_distribution: [
      { year: 2040, count: 40, trial_share_pct: 4 },
      { year: 2045, count: 80, trial_share_pct: 8 },
      { year: 2050, count: 60, trial_share_pct: 6 },
    ],
  },
  terminal_distribution: {
    bins: [
      { lo_usd: 0, hi_usd: 250000, count: 100, share_pct: 10 },
      { lo_usd: 250000, hi_usd: 500000, count: 400, share_pct: 40 },
      { lo_usd: 500000, hi_usd: 750000, count: 350, share_pct: 35 },
      { lo_usd: 750000, hi_usd: 1000000, count: 150, share_pct: 15 },
    ],
  },
  sampled_paths: {
    years: ROWS.map(r => r.year),
    paths: [
      { values_usd: ROWS.map(r => r.p50_ending_balance_usd), failed: false },
      { values_usd: ROWS.map(r => r.p10_ending_balance_usd), failed: true },
    ],
  },
};

const RESULT = {
  monte_carlo: MC,
  scenarios: [
    {
      label: 'baseline',
      future_value_usd: 500000,
      real_value_usd: 380000,
      timeline_points: ROWS.map(r => ({
        year: r.year,
        age: r.age,
        ending_balance_usd: r.p50_ending_balance_usd,
        contributions_usd: 20000,
        withdrawals_usd: r.year >= 2045 ? 40000 : 0,
        starting_balance_usd: r.p50_ending_balance_usd - 10000,
        growth_usd: 5000,
      })),
    },
    { label: 'optimistic', future_value_usd: 700000, real_value_usd: 520000 },
    { label: 'conservative', future_value_usd: 350000, real_value_usd: 260000 },
  ],
};

test('strength headlines avoid raw engine jargon for common labels', () => {
  assert.equal(strengthHeadline('Strong'), 'Looking solid');
  assert.equal(strengthHeadline('Workable'), 'Mostly on track');
  assert.equal(strengthHeadline('Needs attention'), 'Needs attention');
  assert.match(strengthExplain('Workable'), /market histories/i);
});

test('funded and spread phrases never say p10 or funded trial', () => {
  const funded = fundedPhrase(82);
  const spread = spreadPhrase(150000, 700000, { real: true });
  const median = medianPhrase(380000, { real: true });
  for (const text of [funded, spread, median]) {
    assert.doesNotMatch(text, /\bp10\b/i);
    assert.doesNotMatch(text, /\bp90\b/i);
    assert.doesNotMatch(text, /funded trial/i);
    assert.doesNotMatch(text, /percentile/i);
  }
  assert.match(funded, /82%/);
  assert.match(spread, /today/i);
});

test('expense scale formats as plain spending change', () => {
  assert.equal(formatExpenseScale(1), 'same as today');
  assert.match(formatExpenseScale(0.9), /less spending/);
  assert.match(formatExpenseScale(1.1), /more spending/);
});

test('deltas report direction for money and percentages', () => {
  const money = deltaMoney(400000, 350000);
  assert.equal(money.dir, 'up');
  assert.match(money.text, /^\+/);
  const pts = deltaPoints(70, 82);
  assert.equal(pts.dir, 'down');
  assert.equal(deltaMoney(100, 100).dir, 'flat');
});

test('changed levers and dirty detection', () => {
  const baseline = {
    annual_contribution_usd: 20000,
    years: 30,
    target_retirement_age: 65,
    expense_scale: 1,
    expected_return_baseline: 0.06,
    return_volatility: 0.15,
    inflation_rate: 0.025,
  };
  const draft = { ...baseline, annual_contribution_usd: 25000, target_retirement_age: 66 };
  const changes = changedLevers(draft, baseline);
  assert.equal(changes.length, 2);
  assert.ok(changes.some(c => c.key === 'annual_contribution_usd'));
  assert.equal(isDirty(draft, baseline), true);
  assert.equal(isDirty(baseline, baseline), false);
});

test('improvement chips suggest understandable life changes', () => {
  const chips = improvementChips({
    draft: {
      annual_contribution_usd: 20000,
      target_retirement_age: 62,
      expense_scale: 1,
    },
    baseline: { annual_contribution_usd: 20000 },
    result: { monte_carlo: { funded_trial_rate_pct: 68, failure_analysis: { failed_trial_count: 320 } } },
  });
  assert.ok(chips.length >= 1);
  for (const chip of chips) {
    assert.ok(chip.label);
    assert.ok(chip.patch);
    assert.doesNotMatch(chip.label, /\bp10\b/i);
    assert.doesNotMatch(chip.label, /volatility/i);
  }
});

test('failure sentence is plain language', () => {
  const text = failureSentence({ failed_trial_count: 180, first_failure_year_median: 2045 }, 1000);
  assert.match(text, /ran short|market histories/i);
  assert.doesNotMatch(text, /trial/i);
  assert.doesNotMatch(text, /p10/i);
});

test('glossary covers plan strength and middle outcome', () => {
  assert.ok(GLOSSARY.plan_strength?.body);
  assert.ok(GLOSSARY.middle_outcome?.body);
  assert.ok(GLOSSARY.tough_good_range?.body);
  assert.doesNotMatch(GLOSSARY.tough_good_range.body, /\bP10\b/);
});

test('hero figure uses plain legend labels', () => {
  const markup = heroFigure(RESULT, null, { dollarsMode: 'real' });
  assert.match(markup, /Middle outcome/);
  assert.match(markup, /Most outcomes/);
  assert.doesNotMatch(markup, />P10</);
  assert.doesNotMatch(markup, />P90</);
  assert.doesNotMatch(markup, /percentile/i);
});

test('hero figure can overlay plan baseline median', () => {
  const baseline = {
    monte_carlo: {
      ...MC,
      percentile_timeline: ROWS.map(r => ({
        ...r,
        p50_ending_balance_usd: r.p50_ending_balance_usd * 0.9,
        p50_ending_balance_real_usd: r.p50_ending_balance_real_usd * 0.9,
      })),
    },
  };
  const markup = heroFigure(RESULT, baseline, { dollarsMode: 'real' });
  assert.match(markup, /Your plan/);
  assert.match(markup, /chart-line-compare/);
});

test('terminal and failure figures avoid percentile jargon in captions', () => {
  const terminal = terminalFigure(RESULT, { dollarsMode: 'real' });
  assert.match(terminal, /Tougher|Middle|Better/);
  assert.doesNotMatch(terminal, />P10</);
  const failure = failureFigure(RESULT);
  assert.match(failure, /ran short|short/i);
  assert.doesNotMatch(failure, /percentile/i);
});

test('failure figure all-clear copy when no shortfalls', () => {
  const clear = failureFigure({
    monte_carlo: { failure_analysis: { first_failure_year_distribution: [] }, runs: 1000 },
  });
  assert.match(clear, /Good news|every market history/i);
});

test('scenario strip uses friendly labels', () => {
  const markup = scenarioStrip(RESULT);
  assert.match(markup, /Steady path/);
  assert.match(markup, /Stronger growth/);
  assert.match(markup, /Weaker growth/);
  assert.doesNotMatch(markup, /Optimistic/i);
});
