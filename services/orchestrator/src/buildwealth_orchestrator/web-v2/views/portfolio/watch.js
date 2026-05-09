// Movement III — The watch.
// Concentration / risk alerts as editorial callouts, or a quiet
// all-clear quote with the current concentration metrics.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPct } from '../../lib/format.js';

export function renderWatch(data) {
  const risk = data.risk_alerts || {};
  const alerts = Array.isArray(risk.alerts) ? risk.alerts : [];
  const breachCount = risk.breach_count ?? 0;
  const watchCount = risk.watch_count ?? 0;
  const metrics = risk.metrics || {};

  return html`
    <section>
      ${raw(sectionHead('IV', 'The watch.', null))}
      ${raw(alerts.length ? renderAlerts(alerts, breachCount, watchCount) : renderAllClear(metrics))}
    </section>
  `;
}

function renderAlerts(alerts, breachCount, watchCount) {
  const headline = breachCount > 0
    ? `${breachCount} concentration breach${breachCount === 1 ? '' : 'es'}${watchCount ? ` · ${watchCount} on watch` : ''}.`
    : `${watchCount} threshold${watchCount === 1 ? '' : 's'} on watch.`;

  return html`
    <p class="quiet-statement">
      <span class="glyph">§</span>
      ${headline}
    </p>
    <div>
      ${raw(alerts.map(renderAlert).join(''))}
    </div>
  `;
}

function renderAlert(a) {
  const state = String(a.state || a.severity || '').toLowerCase();
  const tier = state === 'breach' ? 'breach' : 'watch';
  const tag = `${(a.category || a.kind || 'concentration').replace(/_/g, ' ')} · ${tier}`;
  const title = a.title || a.message || 'Concentration outside policy.';
  const detail = a.detail || a.recommendation || a.remediation || '';
  const drift = a.drift_pct ?? a.drift ?? null;
  const observed = a.observed_pct ?? a.observed_value ?? null;
  const threshold = a.threshold_pct ?? a.threshold ?? null;

  const meta = [];
  if (observed != null && threshold != null) {
    meta.push(`observed ${formatMaybePct(observed)} · threshold ${formatMaybePct(threshold)}`);
  }
  if (drift != null) meta.push(`drift ${formatMaybePct(drift, true)}`);

  return html`
    <article class="alert ${tier}">
      <span class="alert-glyph">${tier === 'breach' ? '!' : '*'}</span>
      <div>
        <span class="alert-tag">${esc(tag)}</span>
        <h3 class="alert-title">${esc(String(title))}</h3>
        ${detail ? html`<p class="alert-detail">${esc(String(detail))}</p>` : ''}
        ${meta.length ? html`<div class="alert-meta">${raw(meta.map(esc).join(' · '))}</div>` : ''}
      </div>
    </article>
  `;
}

function renderAllClear(metrics) {
  const top = metrics.top_holding_pct;
  const top3 = metrics.top3_holdings_pct;
  const eff = metrics.effective_positions;
  const positions = metrics.positions_count;

  const phrase = positions
    ? `All concentrations sit within policy.`
    : `Nothing yet to watch — record some holdings to set a baseline.`;

  return html`
    <p class="allclear-quote">${phrase}</p>
    <dl class="allclear-stats">
      ${top != null ? html`
        <div class="allclear-stat">
          <dt>Top holding</dt>
          <dd>${fmtPct(top)}${metrics.top_holding_symbol ? raw(` <span class="marginalia">${esc(String(metrics.top_holding_symbol))}</span>`) : ''}</dd>
        </div>
      ` : ''}
      ${top3 != null ? html`
        <div class="allclear-stat">
          <dt>Top three</dt>
          <dd>${fmtPct(top3)}</dd>
        </div>
      ` : ''}
      ${eff != null ? html`
        <div class="allclear-stat">
          <dt>Effective positions</dt>
          <dd>${Number(eff).toFixed(1)}</dd>
        </div>
      ` : ''}
      ${positions != null ? html`
        <div class="allclear-stat">
          <dt>Positions</dt>
          <dd>${positions}</dd>
        </div>
      ` : ''}
    </dl>
  `;
}

function formatMaybePct(value, signed = false) {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const formatted = `${signed && n > 0 ? '+' : ''}${n.toFixed(1)}%`;
  return formatted;
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
