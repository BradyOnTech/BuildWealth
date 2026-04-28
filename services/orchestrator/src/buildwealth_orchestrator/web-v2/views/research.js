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
  const compareSymbols = normalizeCompareSymbols(params.compare || '');
  const symbol = String(params.symbol || compareSymbols[0] || '').trim().toUpperCase();
  const period = String(params.period || '6mo').trim() || '6mo';
  const interval = String(params.interval || '1d').trim() || '1d';

  if (compareSymbols.length >= 2) {
    setView(root, renderResearchLoading(compareSymbols.join(' / '), 'compare'));
    try {
      const [compare, packets] = await Promise.all([
        api.researchCompare({ symbols: compareSymbols, period, interval, baseline_symbol: compareSymbols[0] }),
        Promise.all(compareSymbols.map(compareSymbol => api.researchEvidencePacket({
          symbol: compareSymbol,
          period,
          interval,
        }).catch(err => ({
          symbol: compareSymbol,
          provider: '',
          period,
          interval,
          generated_at: '',
          coverage: { warnings: [err?.message || 'Evidence packet unavailable.'] },
          freshness: { status: 'unavailable' },
          metrics: {},
          risk: {},
          quality: { confidence: 'low', coverage_score: 0, blocking_gaps: ['research:evidence_packet'] },
          provenance: {},
        })))),
      ]);
      setView(root, renderCompareSurface(compare, packets));
    } catch (err) {
      setView(root, renderResearchError(compareSymbols.join(' / '), err));
    }
    return;
  }

  if (!symbol) {
    setView(root, renderResearchEmpty());
    return;
  }

  setView(root, renderResearchLoading(symbol));
  try {
    const packet = await api.researchEvidencePacket({ symbol, period, interval });
    setView(root, renderResearchPage(packet, { requestedPacketId: params.packet || '' }));
  } catch (err) {
    setView(root, renderResearchError(symbol, err));
  }
}

export function normalizeCompareSymbols(value) {
  const parts = String(value || '')
    .split(/[\s,]+/)
    .map(part => part.trim().toUpperCase())
    .filter(Boolean);
  const seen = new Set();
  const symbols = [];
  for (const symbol of parts) {
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    symbols.push(symbol);
    if (symbols.length >= 4) break;
  }
  return symbols;
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

function renderResearchLoading(symbol, mode = 'evidence') {
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">${mode === 'compare' ? 'Compare evidence' : 'Research evidence'}</span>
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

function renderResearchPage(packet, { requestedPacketId = '' } = {}) {
  const packetId = String(packet?.packet_id || requestedPacketId || '').trim();
  return html`
    ${raw(renderEvidencePacket(packet))}
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

export function renderEvidencePacket(packet) {
  if (!packet || typeof packet !== 'object') return renderResearchEmpty();
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Research evidence</span>
      <h1 class="hero-number">${packet.symbol}</h1>
      <p class="hero-marginalia">${packet.name || packet.asset_type || packet.provider || 'Evidence packet'}</p>
    </section>

    ${raw(renderEvidencePacketCard(packet))}
  `;
}

export function renderCompareSurface(compare, packets = []) {
  const symbols = normalizeCompareSymbols((compare?.symbols || []).join(','));
  const summary = compare?.summary || {};
  const items = Array.isArray(compare?.items) ? compare.items : [];
  const warnings = Array.isArray(compare?.warnings) ? compare.warnings : [];
  const packetBySymbol = new Map(
    packets
      .filter(packet => packet && typeof packet === 'object' && packet.symbol)
      .map(packet => [String(packet.symbol).toUpperCase(), packet])
  );
  return html`
    <section class="hero-stack research-hero">
      <span class="hero-eyebrow">Compare evidence</span>
      <h1 class="hero-number">${symbols.join(' / ') || 'Compare'}</h1>
      <p class="hero-marginalia">${compare?.provider || 'Provider'} · ${compare?.period || 'period'} · ${compare?.interval || 'interval'}</p>
    </section>

    <section class="research-packet" aria-label="Research compare">
      <header class="section-head">
        <span class="section-eyebrow">Small set comparison</span>
        <h2 class="section-title">Evidence ranking</h2>
      </header>
      <dl class="fit-meta research-meta">
        <div>
          <dt>Compared</dt>
          <dd>${summary.compared_symbols ?? items.length}</dd>
        </div>
        <div>
          <dt>Available</dt>
          <dd>${summary.available_symbols ?? items.filter(item => item.available).length}</dd>
        </div>
        <div>
          <dt>Baseline</dt>
          <dd>${summary.baseline_symbol || symbols[0] || 'Unknown'}</dd>
        </div>
        <div>
          <dt>Highest volatility</dt>
          <dd>${summary.highest_volatility_symbol || 'Unknown'}</dd>
        </div>
      </dl>

      <div class="research-compare-strip">
        ${items.slice(0, 4).map(item => raw(renderCompareRankItem(item, summary)))}
      </div>
      ${raw(renderListPanel('Warnings', warnings))}
    </section>

    <section class="research-compare-packets" aria-label="Compare evidence packets">
      ${symbols.map(symbol => raw(
        renderEvidencePacketCard(packetBySymbol.get(symbol) || compareItemToPacket(
          items.find(item => item.symbol === symbol),
          compare,
        ))
      ))}
    </section>
  `;
}

export function renderEvidencePacketCard(packet) {
  if (!packet || typeof packet !== 'object') return '';
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
    <section class="research-packet" aria-label="Research evidence packet">
      <header class="section-head">
        <span class="section-eyebrow">${packet.symbol || 'symbol'} · ${packet.provider || 'provider'} · ${packet.period || 'period'} · ${packet.interval || 'interval'}</span>
        <h2 class="section-title">${packet.symbol || 'Research'} evidence packet</h2>
        ${packet.name ? html`<p class="marginalia">${packet.name}</p>` : ''}
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

function renderCompareRankItem(item = {}, summary = {}) {
  const relative = summary.baseline_relative_return_pct && typeof summary.baseline_relative_return_pct === 'object'
    ? summary.baseline_relative_return_pct[item.symbol]
    : null;
  return html`
    <article class="research-rank-item">
      <span>Rank ${item.rank || '—'}</span>
      <b>${item.symbol || 'Unknown'}</b>
      <p>Score ${formatNumber(item.score) || '—'} · ${titleCase(item.research_freshness_status || 'unknown')} · ${titleCase(item.research_confidence || 'unknown')}</p>
      ${relative != null ? html`<p>vs baseline ${fmtPctSigned(relative)}</p>` : ''}
    </article>
  `;
}

function compareItemToPacket(item = {}, compare = {}) {
  return {
    packet_id: item?.research_evidence_packet_id,
    symbol: item?.symbol || 'Unknown',
    provider: item?.research_provider || compare?.provider || '',
    period: compare?.period || '6mo',
    interval: compare?.interval || '1d',
    generated_at: compare?.generated_at,
    coverage: {
      quote_available: Number(item?.quote_records || 0) > 0,
      history_available: Number(item?.history_records || 0) > 0,
      warnings: [],
    },
    freshness: { status: item?.research_freshness_status || 'unknown' },
    metrics: {
      last_price: item?.last_price,
      period_change_pct: item?.period_change_pct,
      volatility_pct: item?.volatility_pct,
      market_cap_usd: item?.market_cap_usd,
      pe_ratio: item?.pe_ratio,
      dividend_yield_pct: item?.dividend_yield_pct,
    },
    risk: {},
    quality: {
      confidence: item?.research_confidence,
      coverage_score: item?.research_coverage_score,
      blocking_gaps: Array.isArray(item?.research_blocking_gaps) ? item.research_blocking_gaps : [],
    },
    provenance: { warnings: item?.message ? [item.message] : [] },
  };
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
