// RESEARCH — packet-native evidence inspection for investment-fit workflows.

import { api } from '../lib/api.js';
import { html, raw, $, setView } from '../lib/dom.js';
import { fmtPctSigned, fmtTimeShort, fmtUsd } from '../lib/format.js';

export const meta = {
  id: 'research',
  label: 'Research',
  numeral: 'V',
  group: 'studio',
};

export function template() {
  return html`
    <section class="page" id="research-page">
      ${raw(renderResearchEmpty())}
    </section>
  `;
}

export async function init(params = {}) {
  const root = $('#research-page');
  if (!root) return;
  const symbol = String(params.symbol || params.compare || '').trim().toUpperCase();
  const period = String(params.period || '6mo').trim() || '6mo';
  const interval = String(params.interval || '1d').trim() || '1d';
  const mode = params.compare ? 'compare' : 'evidence';

  if (!symbol) {
    setView(root, renderResearchEmpty());
    return;
  }

  setView(root, renderResearchLoading(symbol));
  try {
    const packet = await api.researchEvidencePacket({ symbol, period, interval });
    setView(root, renderResearchPage(packet, { mode, requestedPacketId: params.packet || '' }));
  } catch (err) {
    setView(root, renderResearchError(symbol, err));
  }
}

export function renderResearchEmpty() {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">Inspect a symbol</h1>
      <p class="hero-marginalia">Provider coverage, freshness, gaps, metrics, risk, and provenance live here before fit review turns them into personal context.</p>
    </section>
  `;
}

function renderResearchLoading(symbol) {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${symbol}</h1>
      <p class="hero-marginalia">Loading packet evidence.</p>
    </section>
  `;
}

function renderResearchError(symbol, err) {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${symbol}</h1>
      <p class="error-banner">${err?.message || 'Could not load research evidence.'}</p>
    </section>
  `;
}

function renderResearchPage(packet, { mode = 'evidence', requestedPacketId = '' } = {}) {
  const packetId = String(packet?.packet_id || requestedPacketId || '').trim();
  return html`
    ${raw(renderEvidencePacket(packet, { mode }))}
    <footer class="look-closer">
      <span class="section-eyebrow">Move through the loop</span>
      <div class="look-closer-row">
        <a class="link-editorial" href="#portfolio?fit=${encodeURIComponent(packet.symbol)}">Review fit</a>
        <a class="link-editorial" href="#copilot?intent=investment-fit">Discuss in Copilot</a>
        ${packetId ? html`<span class="marginalia">${packetId}</span>` : ''}
      </div>
    </footer>
  `;
}

export function renderEvidencePacket(packet, { mode = 'evidence' } = {}) {
  if (!packet || typeof packet !== 'object') return renderResearchEmpty();
  const coverage = packet.coverage || {};
  const freshness = packet.freshness || {};
  const metrics = packet.metrics || {};
  const risk = packet.risk || {};
  const quality = packet.quality || {};
  const provenance = packet.provenance || {};
  const blockingGaps = Array.isArray(quality.blocking_gaps) ? quality.blocking_gaps : [];
  const warnings = [
    ...(Array.isArray(coverage.warnings) ? coverage.warnings : []),
    ...(Array.isArray(provenance.warnings) ? provenance.warnings : []),
  ].filter(Boolean);

  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${packet.symbol}</h1>
      <p class="hero-marginalia">${packet.name || packet.asset_type || packet.provider || 'Evidence packet'}${mode === 'compare' ? ' · comparison seed' : ''}</p>
    </section>

    <section class="research-packet" aria-label="Research evidence packet">
      <header class="section-head">
        <span class="section-eyebrow">${packet.provider || 'provider'} · ${packet.period || 'period'} · ${packet.interval || 'interval'}</span>
        <h2 class="section-title">Evidence packet</h2>
      </header>

      <dl class="fit-meta research-meta">
        <div>
          <dt>Freshness</dt>
          <dd>${titleCase(freshness.status || 'unknown')}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>${titleCase(quality.confidence || 'unknown')}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>${formatCoverageScore(quality.coverage_score)}</dd>
        </div>
        <div>
          <dt>Generated</dt>
          <dd>${fmtTimeShort(packet.generated_at) || 'Unknown'}</dd>
        </div>
      </dl>

      <div class="research-grid">
        ${raw(renderMetricPanel('Market metrics', [
          ['Last price', fmtUsd(metrics.last_price, { cents: true })],
          ['Period return', fmtPctSigned(metrics.period_change_pct)],
          ['Volatility', formatPct(metrics.volatility_pct)],
          ['Market cap', fmtUsd(metrics.market_cap_usd)],
          ['P/E', formatNumber(metrics.pe_ratio)],
          ['Dividend yield', formatPct(metrics.dividend_yield_pct)],
        ]))}
        ${raw(renderMetricPanel('Risk context', [
          ['Drawdown from high', fmtPctSigned(risk.drawdown_from_high_pct)],
          ['Quote as of', fmtTimeShort(freshness.quote_as_of) || 'Unknown'],
          ['History as of', fmtTimeShort(freshness.history_as_of) || 'Unknown'],
        ]))}
        ${raw(renderMetricPanel('Provider coverage', [
          ['Quote', coverage.quote_available ? 'Available' : 'Unavailable'],
          ['History', coverage.history_available ? 'Available' : 'Unavailable'],
          ['Provider status', titleCase(coverage.provider_status || freshness.status || 'unknown')],
          ['Endpoints', formatEndpoints(coverage.endpoints_attempted)],
        ]))}
      </div>

      ${raw(renderListPanel('Blocking gaps', blockingGaps))}
      ${raw(renderListPanel('Warnings', warnings))}
      <p class="marginalia">${packet.packet_id || ''}</p>
    </section>
  `;
}

function renderMetricPanel(title, rows) {
  const visible = rows.filter(([, value]) => value && value !== '—');
  if (!visible.length) return '';
  return html`
    <article class="research-panel">
      <h3>${title}</h3>
      <dl>
        ${visible.map(([label, value]) => html`
          <div>
            <dt>${label}</dt>
            <dd>${value}</dd>
          </div>
        `)}
      </dl>
    </article>
  `;
}

function renderListPanel(title, items) {
  const visible = Array.isArray(items) ? items.filter(Boolean).slice(0, 6) : [];
  if (!visible.length) return '';
  return html`
    <div class="fit-list">
      <h3>${title}</h3>
      <ul>${visible.map(item => html`<li>${humanText(item)}</li>`)}</ul>
    </div>
  `;
}

function formatCoverageScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Unknown';
  return `${number.toLocaleString('en-US', { maximumFractionDigits: 0 })}%`;
}

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return `${number.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return number.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatEndpoints(value) {
  if (!Array.isArray(value) || !value.length) return '';
  return value.map(humanText).join(', ');
}

function humanText(value) {
  return String(value || '').replace(/[_-]+/g, ' ').trim();
}

function titleCase(value) {
  const text = humanText(value);
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}
