// Quality — Movement III.
// Quiet pull-quote about how past suggestions actually played out.

import { html, raw } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export function renderQuality(closure) {
  return html`
    <section>
      ${raw(sectionHead('III', 'Quality.', 'How past suggestions actually played out.'))}
      ${raw(renderQualityBody(closure))}
    </section>
  `;
}

function renderQualityBody(closure) {
  if (!closure) {
    return html`<p class="marginalia">Calibration data is being prepared.</p>`;
  }

  const summary = closure.calibration_summary || {};
  const measured = numberOrNull(summary.measured_count);
  const matchRate = numberOrNull(summary.future_value_direction_match_rate_pct);
  const mae = numberOrNull(summary.mean_future_value_abs_error_usd);
  const tracked = closure.count ?? null;

  if (!measured || measured === 0) {
    const phrase = tracked
      ? `${tracked} suggestion${tracked === 1 ? '' : 's'} on file — none have been measured against an outcome yet.`
      : 'No outcomes have been logged yet — quality calibration begins after a few are tracked.';
    return html`
      <p class="quality-quote">${phrase}</p>
      <p class="marginalia">Apply a suggestion, then come back and log an outcome to start calibration.</p>
    `;
  }

  const matchedCount = matchRate != null ? Math.round((measured * matchRate) / 100) : null;
  const directionPhrase = matchedCount != null
    ? `${matchedCount} of ${measured} moved in the predicted direction`
    : `${measured} measured`;

  return html`
    <p class="quality-quote">
      Of ${measured} suggestion${measured === 1 ? '' : 's'} tracked through to an outcome,
      ${directionPhrase}.
    </p>
    <dl class="quality-stats">
      ${matchRate != null ? html`
        <div class="quality-stat">
          <dt>Directional match</dt>
          <dd>${Math.round(matchRate)}%</dd>
        </div>
      ` : ''}
      ${mae != null ? html`
        <div class="quality-stat">
          <dt>Mean absolute error</dt>
          <dd>${fmtUsd(mae)}</dd>
        </div>
      ` : ''}
      ${measured ? html`
        <div class="quality-stat">
          <dt>Measured</dt>
          <dd>${measured}</dd>
        </div>
      ` : ''}
    </dl>
  `;
}

function numberOrNull(v) {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function sectionHead(numeral, title, lede) {
  return html`
    <header class="section-head">
      <span class="section-eyebrow">Movement ${numeral}</span>
      <h2 class="section-title">${title}</h2>
      ${lede ? html`<p class="section-lede">${lede}</p>` : ''}
    </header>
  `;
}
