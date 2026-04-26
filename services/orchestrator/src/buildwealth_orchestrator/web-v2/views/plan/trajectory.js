// Movement II — The trajectory.
// Plan-vs-actual tracking. Status pull-quote + editorial stats.

import { html, raw } from '../../lib/dom.js';
import { fmtUsd, fmtUsdSigned, fmtPct, fmtPctSigned } from '../../lib/format.js';

export function renderTrajectory(state) {
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement II</span>
        <h2 class="section-title">The trajectory.</h2>
        <p class="section-lede">Where the plan said you'd be against where you actually are.</p>
      </header>
      ${renderTrajectoryBody(state)}
    </section>
  `;
}

function renderTrajectoryBody(state) {
  if (state.busy) {
    return html`<div class="skeleton" style="height: 180px;">.</div>`;
  }
  if (state.error) {
    return html`<p class="error-banner">${state.error}</p>`;
  }
  const t = state.tracking;
  if (!t) {
    return html`
      <p class="trajectory-quote insufficient">
        <span class="glyph">§</span>
        Tracking data isn't available for this plan yet.
      </p>
      <p class="marginalia">Plan vs actual needs at least two snapshots and recorded contributions.</p>
    `;
  }

  const status = (t.status || 'insufficient_data').toLowerCase();
  const quote = phraseFor(t, status);
  const cls = quoteClass(status);

  return html`
    <p class="trajectory-quote ${cls}">
      <span class="glyph">§</span>
      ${quote}
    </p>
    <p class="trajectory-marginalia">
      Tracked over the last ${t.tracking_window_days} day${t.tracking_window_days === 1 ? '' : 's'}
      · ${t.snapshot_count} snapshot${t.snapshot_count === 1 ? '' : 's'}
    </p>

    <dl class="trajectory-stats">
      ${stat('Current value',   fmtUsd(t.current_value_usd))}
      ${stat('Projected value', fmtUsd(t.projected_value_usd))}
      ${stat('Value drift',
        html`${fmtUsdSigned(t.value_drift_usd)}<span class="delta ${t.value_drift_usd >= 0 ? 'up' : 'down'}">${fmtPctSigned(t.value_drift_pct)}</span>`)}

      ${stat('Actual return',
        html`${fmtPct(t.actual_annualized_return_pct)}<span class="source-tag">${humanText(t.actual_return_method)}</span>`)}
      ${stat('Expected return',
        html`${fmtPct(t.expected_annualized_return_pct)}<span class="source-tag">${humanText(t.expected_return_method)}</span>`)}
      ${stat('Return drift',
        html`${fmtPctSigned(t.return_drift_pct)}<span class="delta ${t.return_drift_pct >= 0 ? 'up' : 'down'}"></span>`)}

      ${stat('Contribution pace',
        html`${fmtPct(t.contribution_pace_pct)}<span class="source-tag">${fmtUsd(t.actual_contributions_usd)} of ${fmtUsd(t.expected_contributions_usd)} expected</span>`)}
      ${stat('Market growth',   fmtUsdSigned(t.market_growth_usd))}
      ${stat('Window',
        html`${formatDate(t.window_start)} → ${formatDate(t.window_end)}`)}
    </dl>
  `;
}

function stat(label, value) {
  return html`
    <div class="trajectory-stat">
      <dt>${label}</dt>
      <dd>${value}</dd>
    </div>
  `;
}

function phraseFor(t, status) {
  if (status === 'on_track') return 'On track.';
  if (status === 'ahead') {
    const usd = Math.abs(t.value_drift_usd);
    return `Ahead of plan by ${fmtUsd(usd)}.`;
  }
  if (status === 'behind') {
    const usd = Math.abs(t.value_drift_usd);
    return `Behind plan by ${fmtUsd(usd)}.`;
  }
  return 'Not enough data yet to call it.';
}

function quoteClass(status) {
  if (status === 'on_track') return 'on-track';
  if (status === 'ahead')    return 'ahead';
  if (status === 'behind')   return 'behind';
  return 'insufficient';
}

function humanText(v) {
  if (!v) return '';
  return String(v).replace(/_/g, ' ');
}

function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
