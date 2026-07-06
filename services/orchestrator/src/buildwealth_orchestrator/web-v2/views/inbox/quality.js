// Quality — Movement III.
// Quiet pull-quote about how past suggestions actually played out.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export function renderQuality(closure) {
  // Before any outcomes exist there's nothing to say — one quiet line, not a
  // full Movement of display type about an empty state.
  const summary = closure?.calibration_summary || {};
  const measured = numberOrNull(summary.measured_count);
  if (!measured) {
    return html`
      <section class="quality-section">
        <span class="section-eyebrow">Quality</span>
        <p class="marginalia">
          ${closure?.count
            ? `${closure.count} suggestion${closure.count === 1 ? '' : 's'} on file — apply one and log an outcome to start calibration.`
            : 'How past suggestions played out will appear here once a few outcomes are logged.'}
        </p>
        ${raw(String(renderProcessCalibration(closure || {})))}
      </section>
    `;
  }
  return html`
    <section>
      ${raw(sectionHead('II', 'Quality.', 'How past suggestions actually played out.'))}
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
      ${raw(renderProcessCalibration(closure))}
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
    ${raw(renderProcessCalibration(closure))}
  `;
}

function renderProcessCalibration(closure) {
  const summary = closure?.process_calibration_summary || {};
  const count = numberOrNull(summary.count);
  if (!count || count <= 0) return '';

  const useful = numberOrNull(summary.useful_count) ?? 0;
  const weak = numberOrNull(summary.weak_count) ?? 0;
  const usefulRate = numberOrNull(summary.useful_rate_pct);
  const rows = Array.isArray(closure.process_calibration_by_outcome)
    ? closure.process_calibration_by_outcome.slice(0, 4)
    : [];

  return html`
    <div class="quality-process">
      <p class="quality-quote small">
        Investment review calibration: ${useful} of ${count} investment/research reviews were useful${weak ? `; ${weak} flagged weak evidence or low usefulness` : ''}.
      </p>
      <dl class="quality-stats">
        ${usefulRate != null ? html`
          <div class="quality-stat">
            <dt>Useful process</dt>
            <dd>${Math.round(usefulRate)}%</dd>
          </div>
        ` : ''}
        ${raw(rows.map(row => html`
          <div class="quality-stat">
            <dt>${esc(outcomeLabel(row.key))}</dt>
            <dd>${esc(row.count ?? 0)}</dd>
          </div>
        `).join(''))}
      </dl>
    </div>
  `;
}

function numberOrNull(v) {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function labelCase(value) {
  const text = String(value || '').replace(/[_.-]/g, ' ').trim().toLowerCase();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function outcomeLabel(value) {
  const key = String(value || '').trim().toLowerCase();
  const labels = {
    useful_review: 'Useful review',
    insufficient_evidence: 'Evidence insufficient',
    acted_elsewhere: 'Acted elsewhere',
    not_useful: 'Not useful',
    deferred: 'Deferred',
  };
  return labels[key] || labelCase(key);
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
