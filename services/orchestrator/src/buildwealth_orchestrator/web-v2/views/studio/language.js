// Plain-language helpers for Studio.
// Non-expert users should never see raw finance jargon without a gloss.

import { compactUsd } from '../../lib/chart.js';

/** User-facing name for a Plan Strength label from the engine. */
export function strengthHeadline(label) {
  const key = String(label || '').trim().toLowerCase();
  if (key === 'strong') return 'Looking solid';
  if (key === 'workable') return 'Mostly on track';
  if (key === 'fragile' || key === 'needs attention') return 'Needs attention';
  if (key === 'not ready to rely on' || key === 'not ready') return 'Not ready to rely on';
  return label ? String(label) : 'Not rated yet';
}

/** One-sentence gloss for Plan Strength. */
export function strengthExplain(label) {
  const key = String(label || '').trim().toLowerCase();
  if (key === 'strong') {
    return 'In almost all of the market histories we tried, the money lasted through the full period.';
  }
  if (key === 'workable') {
    return 'Most of the time the money lasted, but some tougher market histories still ran short.';
  }
  if (key === 'fragile' || key === 'needs attention') {
    return 'A meaningful share of market histories ran short before the end of the period.';
  }
  if (key === 'not ready to rely on' || key === 'not ready') {
    return 'Too many market histories ran short. Treat this as a draft, not a plan to count on yet.';
  }
  return 'We score how often your savings would still cover the plan under many possible market paths.';
}

/** “How often the money lasted” — replaces “funded trial rate”. */
export function fundedPhrase(pct) {
  const n = Number(pct);
  if (!Number.isFinite(n)) return '—';
  return `${formatPct(n)} of market histories lasted the full period`;
}

/** Spread gloss: avoid “p10–p90” in primary UI. */
export function spreadPhrase(lo, hi, { real = true } = {}) {
  const low = compactUsd(lo);
  const high = compactUsd(hi);
  const unit = real ? ' in today’s dollars' : '';
  return `In tougher markets you might end near ${low}; in better ones near ${high}${unit}.`;
}

/** Median gloss. */
export function medianPhrase(value, { real = true } = {}) {
  const amount = compactUsd(value);
  const unit = real ? ' in today’s dollars' : ' (not adjusted for inflation)';
  return `The middle outcome across all histories is about ${amount}${unit}.`;
}

export function formatPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const rounded = Math.abs(n - Math.round(n)) < 1e-6 ? Math.round(n) : Math.round(n * 10) / 10;
  return `${rounded}%`;
}

export function formatReturnPct(rate) {
  const n = Number(rate);
  if (!Number.isFinite(n)) return '—';
  const pct = n * 100;
  const text = pct.toFixed(2).replace(/\.?0+$/, '');
  return `${text}% / year`;
}

export function formatMoneyPerYear(value) {
  return `${compactUsd(value)} / year`;
}

export function formatYears(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n === 1 ? '1 year' : `${n} years`;
}

export function formatAge(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `age ${Math.round(n)}`;
}

export function formatExpenseScale(scale) {
  const n = Number(scale);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n - 1) < 1e-6) return 'same as today';
  if (n < 1) return `${formatPct((1 - n) * 100)} less spending`;
  return `${formatPct((n - 1) * 100)} more spending`;
}

/** Delta text for two numbers (candidate − baseline). */
export function deltaMoney(candidate, baseline) {
  const a = Number(candidate);
  const b = Number(baseline);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const d = a - b;
  if (Math.abs(d) < 1) return { text: 'about the same', dir: 'flat' };
  const sign = d > 0 ? '+' : '−';
  return { text: `${sign}${compactUsd(Math.abs(d))}`, dir: d > 0 ? 'up' : 'down' };
}

export function deltaPoints(candidate, baseline) {
  const a = Number(candidate);
  const b = Number(baseline);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const d = a - b;
  if (Math.abs(d) < 0.05) return { text: 'about the same', dir: 'flat' };
  const sign = d > 0 ? '+' : '−';
  return { text: `${sign}${formatPct(Math.abs(d))}`, dir: d > 0 ? 'up' : 'down' };
}

/**
 * Glossary entries for tooltips / “What does this mean?” panels.
 * Keys are stable ids used in the UI.
 */
export const GLOSSARY = {
  plan_strength: {
    title: 'Plan strength',
    body: 'A plain reading of how often your savings would still cover the plan when we replay many different market histories. It is not a guarantee.',
  },
  market_histories: {
    title: 'Market histories',
    body: 'We roll the dice on yearly investment returns thousands of times. Each “history” is one possible path markets could take.',
  },
  middle_outcome: {
    title: 'Middle outcome',
    body: 'If you lined up every simulated ending balance from worst to best, this is the one in the middle. Half of the histories end higher; half end lower.',
  },
  tough_good_range: {
    title: 'Tougher to better range',
    body: 'The lower end is a rough “bad markets” ending balance (only about 1 in 10 histories ends worse). The upper end is a rough “good markets” ending (only about 1 in 10 ends better).',
  },
  todays_dollars: {
    title: 'Today’s dollars',
    body: 'Numbers adjusted for inflation so $100 later feels more like what $100 buys today. Easier to compare to your life now.',
  },
  future_dollars: {
    title: 'Future dollars',
    body: 'The raw number on a future statement, not adjusted for rising prices. Looks larger, but buys less than the same number today.',
  },
  when_plans_break: {
    title: 'When money runs short',
    body: 'Among the histories that could not fund the full plan, the year the balance first hit zero (or the reserve floor). Helps you see when the tight years cluster.',
  },
  your_plan: {
    title: 'Your plan line',
    body: 'The middle outcome if you keep today’s plan settings. Compare it to the solid line (your experiment) to see whether a change helps.',
  },
  volatility: {
    title: 'Market ups and downs',
    body: 'How bumpy yearly returns are. Higher means bigger swings year to year — not the same as the average return.',
  },
  expected_return: {
    title: 'Expected yearly growth',
    body: 'The average yearly investment return we assume before testing many ups and downs around it. A guess, not a promise.',
  },
  inflation: {
    title: 'Inflation',
    body: 'How fast everyday prices rise each year. Higher inflation makes the same future balance feel smaller in today’s dollars.',
  },
  seed: {
    title: 'Same market deck',
    body: 'One fixed set of random market histories. Keeping the same deck means when you move a slider, only your choices change — not the “weather.”',
  },
  historical: {
    title: 'Historical replay',
    body: 'Instead of many random futures, we walk your plan through one stretch of real past market returns (for example starting in 2000). Good for stress checks; not a forecast.',
  },
};

/** Short control help text shown under each life lever. */
export const CONTROL_HELP = {
  annual_contribution_usd: 'How much you add to investments each year from income.',
  years: 'How many years of the future this picture covers.',
  target_retirement_age: 'The age you start living more on savings than on work income.',
  expense_scale: 'Turn overall yearly spending up or down vs what is in your profile today.',
  expected_return_baseline: 'Average yearly growth we assume for investments.',
  return_volatility: 'How wild yearly returns can be around that average.',
  inflation_rate: 'How fast prices rise, used for “today’s dollars.”',
  simulation_historical_start_year: 'Calendar year where the historical replay begins.',
};

export function trajectoryStatusPhrase(tracking) {
  if (!tracking) return null;
  const status = String(tracking.status || '').toLowerCase();
  const drift = Number(tracking.value_drift_usd);
  if (status === 'ahead' && Number.isFinite(drift)) {
    return `Ahead of plan by about ${compactUsd(Math.abs(drift))}.`;
  }
  if (status === 'behind' && Number.isFinite(drift)) {
    return `Behind plan by about ${compactUsd(Math.abs(drift))}.`;
  }
  if (status === 'on_track') return 'On track with the plan so far.';
  return null;
}

export function failureSentence(failure = {}, runs) {
  const failed = Number(failure.failed_trial_count);
  const total = Number(runs);
  if (!Number.isFinite(failed) || failed <= 0) {
    return 'Every market history we tried still had money at the end under these settings.';
  }
  const median = failure.first_failure_year_median;
  const share = Number.isFinite(total) && total > 0
    ? formatPct((failed / total) * 100)
    : null;
  const when = median ? ` Shortfalls most often first show up around ${median}.` : '';
  if (share) {
    return `About ${share} of market histories ran short before the end.${when}`;
  }
  return `${failed.toLocaleString('en-US')} market histories ran short before the end.${when}`;
}

/**
 * Suggest simple one-click experiments from a result.
 * Returns chips: { id, label, detail, patch }
 */
export function improvementChips({ draft = {}, baseline = {}, result = {}, context = {} } = {}) {
  const mc = result?.monte_carlo || {};
  const funded = Number(mc.funded_trial_rate_pct);
  const failure = mc.failure_analysis || {};
  const failed = Number(failure.failed_trial_count) || 0;
  const chips = [];
  const contribution = Number(draft.annual_contribution_usd);
  const retireAge = Number(draft.target_retirement_age);
  const expenseScale = Number(draft.expense_scale);
  const baseContribution = Number(baseline.annual_contribution_usd);

  if (Number.isFinite(funded) && funded < 92 && Number.isFinite(contribution)) {
    const bump = funded < 70 ? 10000 : 5000;
    const next = Math.min(150000, contribution + bump);
    if (next > contribution + 1) {
      chips.push({
        id: 'save-more',
        label: `Save ${compactUsd(bump)} more / year`,
        detail: 'Often the simplest way to strengthen the plan.',
        patch: { annual_contribution_usd: next },
      });
    }
  }

  if (Number.isFinite(retireAge) && retireAge < 75 && (failed > 0 || (Number.isFinite(funded) && funded < 90))) {
    chips.push({
      id: 'retire-later',
      label: `Retire at ${Math.round(retireAge) + 1} instead`,
      detail: 'One more year of work can ease early retirement pressure.',
      patch: { target_retirement_age: Math.round(retireAge) + 1 },
    });
  }

  if ((failed > 0 || (Number.isFinite(funded) && funded < 85)) && Number.isFinite(expenseScale) && expenseScale > 0.5) {
    const next = Math.max(0.5, Math.round((expenseScale - 0.1) * 100) / 100);
    if (next < expenseScale - 0.01) {
      chips.push({
        id: 'spend-less',
        label: 'Spend about 10% less',
        detail: 'Lower yearly spending vs what is in your profile.',
        patch: { expense_scale: next },
      });
    }
  }

  if (
    Number.isFinite(baseContribution)
    && Number.isFinite(contribution)
    && contribution + 1 < baseContribution
  ) {
    chips.push({
      id: 'restore-saving',
      label: 'Restore plan saving rate',
      detail: `Back to ${compactUsd(baseContribution)} / year from your plan.`,
      patch: { annual_contribution_usd: baseContribution },
    });
  }

  // Always offer a mild positive experiment when nothing else fired.
  if (!chips.length && Number.isFinite(contribution)) {
    const next = Math.min(150000, contribution + 2500);
    if (next > contribution) {
      chips.push({
        id: 'save-a-bit',
        label: `Try saving ${compactUsd(2500)} more / year`,
        detail: 'See how a small habit change moves the picture.',
        patch: { annual_contribution_usd: next },
      });
    }
  }

  return chips.slice(0, 3);
}

/** Compare draft vs baseline for “you changed X”. */
export function changedLevers(draft = {}, baseline = {}) {
  const fields = [
    { key: 'annual_contribution_usd', label: 'yearly saving', format: formatMoneyPerYear },
    { key: 'years', label: 'years ahead', format: formatYears },
    { key: 'target_retirement_age', label: 'retirement age', format: v => `age ${Math.round(Number(v))}` },
    { key: 'expense_scale', label: 'spending level', format: formatExpenseScale },
    { key: 'expected_return_baseline', label: 'expected growth', format: formatReturnPct },
    { key: 'return_volatility', label: 'market ups and downs', format: formatReturnPct },
    { key: 'inflation_rate', label: 'inflation', format: formatReturnPct },
  ];
  const out = [];
  for (const field of fields) {
    const a = Number(draft[field.key]);
    const b = Number(baseline[field.key]);
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    if (Math.abs(a - b) < 1e-9) continue;
    out.push({
      key: field.key,
      label: field.label,
      from: field.format(b),
      to: field.format(a),
    });
  }
  return out;
}

export function isDirty(draft = {}, baseline = {}) {
  if (changedLevers(draft, baseline).length > 0) return true;
  const modeA = String(draft.simulation_mode || 'monte_carlo');
  const modeB = String(baseline.simulation_mode || 'monte_carlo');
  if (modeA !== modeB) return true;
  const yearA = Number(draft.simulation_historical_start_year);
  const yearB = Number(baseline.simulation_historical_start_year);
  if (Number.isFinite(yearA) || Number.isFinite(yearB)) {
    if (yearA !== yearB) return true;
  }
  return false;
}
