// TODAY — the standing, the move, the room.
// One Fraunces number. Three editorial entries. A quiet panel of diagnostics.

import { api } from '../lib/api.js';
import { state, emit } from '../lib/state.js';
import { html, raw, setView, $, esc, stripHtml } from '../lib/dom.js';
import {
  fmtUsd, splitUsd, fmtUsdSigned, fmtPctSigned, fmtRelative,
  fmtDateLong, fmtTimeShort, roman,
} from '../lib/format.js';

export const meta = {
  id: 'today',
  label: 'Today',
  numeral: 'I',
  group: 'daily',
};

export function template() {
  return html`
    <section class="page" id="today-page">
      ${raw(skeletonHero())}
      ${raw(skeletonSection('II', 'Command center'))}
      ${raw(skeletonSection('III', 'The move'))}
      ${raw(skeletonSection('IV', 'The room'))}
    </section>
  `;
}

export async function init(params = {}) {
  await load(params);
}

async function load(params = {}) {
  const root = $('#today-page');
  if (!root) return;

  let payload = null;
  let engines = null;
  try {
    const shouldRefreshResearch = String(params.refresh || '').toLowerCase() === 'research';
    const shouldRecordReview = String(params.review || '').toLowerCase() === 'complete';
    [payload, engines] = await Promise.all([
      shouldRecordReview
        ? api.recordTodayReview()
        : shouldRefreshResearch
          ? api.refreshTodayResearch()
          : api.today(),
      api.engines().catch(() => null),
    ]);
    state.today = payload;
    state.engines = engines;
    state.lastError = null;
    emit('today:loaded', payload);
  } catch (err) {
    state.lastError = err.message;
    setView(root, html`
      <section>
        ${raw(heroEyebrow(new Date()))}
        <p class="error-banner">${err.message}</p>
      </section>
    `);
    return;
  }

  setView(root, html`
    ${raw(renderHero(payload))}
    ${raw(renderCommandCards(payload, engines))}
    ${raw(renderMove(payload))}
    ${raw(renderRoom(payload, engines))}
  `);
  if (
    String(params.refresh || '').toLowerCase() === 'research'
    || String(params.review || '').toLowerCase() === 'complete'
  ) {
    history.replaceState(null, '', '#today');
  }
}

/* ─────────────  THE STANDING (hero)  ───────────── */

function renderHero(payload) {
  const value = payload.net_worth_usd ?? payload.total_value_usd ?? 0;
  const { currency, number } = splitUsd(value);
  const generated = payload.generated_at ? new Date(payload.generated_at) : new Date();

  const performance = payload.net_performance_usd;
  const surplus = payload.monthly_surplus_usd;
  const savings = payload.savings_rate_pct;
  const runway = computeRunway(payload);

  const marginalia = [
    performance != null ? marginaliaItem('net performance', fmtUsdSigned(performance), performance >= 0 ? 'up' : 'down') : null,
    surplus != null ? marginaliaItem('monthly surplus', fmtUsd(surplus), surplus >= 0 ? 'up' : 'down') : null,
    savings != null ? marginaliaItem('savings rate', `${Math.round(savings)}%`, 'up') : null,
    runway != null ? marginaliaItem('runway', `${runway} mo`, 'up') : null,
  ].filter(Boolean);

  return html`
    <section class="hero-stack">
      ${raw(heroEyebrow(generated))}
      <h1 class="hero-number">
        <span class="currency">${currency}</span>${number}
      </h1>
      <p class="hero-marginalia">
        ${raw(marginalia.join(''))}
      </p>
    </section>
  `;
}

function heroEyebrow(date) {
  return html`
    <p class="hero-eyebrow">
      As of ${fmtDateLong(date)} · ${fmtTimeShort(date)}
    </p>
  `;
}

function marginaliaItem(label, value, dir) {
  const cls = dir === 'down' ? 'delta-down' : 'delta-up';
  return html`
    <span class="${cls}">
      <span class="glyph">·</span>
      <b class="num-mono">${value}</b>
      <span class="marginalia"> ${label}</span>
    </span>
  `;
}

function computeRunway(payload) {
  // months of expenses covered by liquid net worth — best-effort, fine to be null.
  const surplus = payload.monthly_surplus_usd;
  const nw = payload.net_worth_usd ?? payload.total_value_usd;
  if (!surplus || surplus <= 0 || !nw) return null;
  return Math.round(nw / Math.max(surplus, 1) / 12);
}

/* ─────────────  COMMAND CENTER  ───────────── */

export function renderCommandCards(payload, engines = null) {
  const cards = Array.isArray(payload.command_cards) ? [...payload.command_cards] : [];
  const engineCard = buildEngineCommandCard(engines);
  if (engineCard) cards.push(engineCard);
  const visibleCards = cards.slice(0, 10);
  if (!visibleCards.length) {
    return html``;
  }

  const criticalCount = visibleCards.filter((card) => card.status === 'critical').length;
  const warningCount = visibleCards.filter((card) => card.status === 'warning').length;
  const lede = criticalCount
    ? `${criticalCount} area${criticalCount === 1 ? '' : 's'} need immediate attention.`
    : warningCount
      ? `${warningCount} area${warningCount === 1 ? '' : 's'} need review before high-confidence advice.`
      : 'The inputs behind today’s advice are ready.';

  return html`
    <section>
      ${raw(sectionHead('II', 'Command center', lede))}
      <div class="command-card-grid">
        ${raw(visibleCards.map(renderCommandCard).join(''))}
      </div>
      ${raw(renderConfidenceHeatMap(payload))}
    </section>
  `;
}

function buildEngineCommandCard(engines) {
  if (!engines || typeof engines !== 'object') return null;
  const enabled = Number(engines.enabled_count ?? 0);
  const reachable = Number(engines.reachable_count ?? 0);
  const degraded = Number(engines.degraded_count ?? 0);
  const status = degraded > 0 || reachable < enabled ? 'warning' : 'ready';
  return {
    id: 'engine-health',
    title: 'Engine health',
    status,
    detail: degraded > 0
      ? `${degraded} degraded event${degraded === 1 ? '' : 's'} recorded across compute engines.`
      : reachable < enabled
        ? 'Some configured compute engines are not reachable.'
        : 'Compute engines are reachable with no degraded events.',
    metric_label: 'Reachable',
    metric_value: `${reachable}/${enabled}`,
    action_label: 'Open operations',
    href: '#atelier',
  };
}

function renderCommandCard(card) {
  const status = normalizeCardStatus(card.status);
  const href = card.href ? String(card.href) : '';
  const action = card.action_label && href
    ? `<a class="link-editorial" href="${esc(href)}" data-route>${esc(card.action_label)}</a>`
    : '';

  return html`
    <article class="command-card ${status}">
      <div class="command-card-topline">
        <span class="command-card-status">${status}</span>
        ${card.metric_value ? raw(`
          <span class="command-card-metric">
            ${card.metric_label ? `${esc(card.metric_label)} ` : ''}<b>${esc(card.metric_value)}</b>
          </span>
        `) : ''}
      </div>
      <h3>${stripHtml(card.title || 'Command card')}</h3>
      <p>${stripHtml(card.detail || '')}</p>
      ${action ? raw(`<div class="command-card-action">${action}</div>`) : ''}
    </article>
  `;
}

function normalizeCardStatus(status) {
  if (status === 'critical' || status === 'warning' || status === 'ready') return status;
  return 'ready';
}

function renderConfidenceHeatMap(payload) {
  const domains = Array.isArray(payload.confidence_domains) ? payload.confidence_domains.slice(0, 10) : [];
  if (!domains.length) return html``;
  return html`
    <div class="confidence-heat-map" aria-label="Confidence heat map">
      <div class="confidence-heat-map-head">
        <span>Confidence heat map</span>
        <p>Decision-grade inputs versus weak, stale, or degraded context.</p>
      </div>
      <div class="confidence-domain-grid">
        ${raw(domains.map(renderConfidenceDomain).join(''))}
      </div>
    </div>
  `;
}

function renderConfidenceDomain(domain) {
  const status = normalizeConfidenceStatus(domain.status);
  const href = domain.href ? String(domain.href) : '';
  const metric = domain.metric_value
    ? `<span class="confidence-domain-metric">${domain.metric_label ? `${esc(domain.metric_label)} ` : ''}<b>${esc(domain.metric_value)}</b></span>`
    : '';
  const body = html`
    <span class="confidence-domain-status">${confidenceStatusLabel(status)}</span>
    <strong>${stripHtml(domain.label || 'Domain')}</strong>
    <small>${stripHtml(domain.detail || '')}</small>
    ${raw(metric)}
  `;
  if (!href) {
    return html`<div class="confidence-domain ${status}">${raw(body)}</div>`;
  }
  return html`
    <a class="confidence-domain ${status}" href="${esc(href)}" data-route>
      ${raw(body)}
    </a>
  `;
}

function normalizeConfidenceStatus(status) {
  const value = String(status || '').toLowerCase();
  if (
    value === 'decision_grade'
    || value === 'usable_with_caveats'
    || value === 'stale'
    || value === 'missing_context'
    || value === 'degraded'
  ) {
    return value;
  }
  return 'usable_with_caveats';
}

function confidenceStatusLabel(status) {
  return status.replaceAll('_', ' ');
}

/* ─────────────  THE MOVE  ───────────── */

export function renderMove(payload) {
  const actions = (payload.top_next_actions || []).slice(0, 3);
  if (!actions.length) {
    return html`
      <section>
        ${raw(sectionHead('III', 'The move', 'Nothing pressing today.'))}
        <div class="empty-block">
          <span class="glyph">¶</span>
          <p>The inbox is quiet. Come back tomorrow.</p>
        </div>
      </section>
    `;
  }

  const lede = actions.length === 3
    ? 'Three things worth doing this week.'
    : `${actions.length === 1 ? 'One' : actions.length} thing${actions.length === 1 ? '' : 's'} worth doing this week.`;

  return html`
    <section>
      ${raw(sectionHead('III', 'The move', lede))}
      <ol class="entry-list">
        ${raw(actions.map((a, i) => renderAction(a, i + 1)).join(''))}
      </ol>
    </section>
  `;
}

function renderAction(action, index) {
  const priority = (action.priority || 'medium').toLowerCase();
  const source = humanSource(action.source);
  const reasons = (action.score_reasons || []).slice(0, 2);

  return html`
    <li class="entry">
      <span class="entry-numeral">${roman(index)}.</span>
      <div class="entry-body">
        <span class="entry-tag">
          <span class="priority ${priority}"></span>
          ${priority} priority
          ${source ? raw(`<span aria-hidden="true">·</span> ${esc(source)}`) : ''}
        </span>
        <h3 class="entry-title">${stripHtml(action.title)}</h3>
        <p class="entry-rationale">${stripHtml(action.detail || '')}</p>
        ${action.quality_summary ? raw(`
          <p class="marginalia">
            <span class="glyph">›</span> ${esc(action.quality_summary)}
          </p>
        `) : ''}
        ${reasons.length ? raw(`
          <p class="marginalia">
            <span class="glyph">›</span> ${reasons.map(esc).join(' · ')}
          </p>
        `) : ''}
        <div class="entry-meta">
          ${raw(actionLink(action))}
          ${action.action_hint ? raw(`<span class="marginalia">${esc(action.action_hint)}</span>`) : ''}
        </div>
      </div>
    </li>
  `;
}

function actionLink(action) {
  const target = recommendationLinkTarget(action);
  return html`
    <a class="link-editorial" href="${target.href}" data-route>
      ${target.label}
    </a>
  `;
}

function recommendationLinkTarget(action) {
  if (action.recommendation_id) {
    return { href: `#inbox?focus=${encodeURIComponent(action.recommendation_id)}`, label: 'Open in inbox' };
  }
  if (action.recommendation_type === 'plan_settings_update') {
    return { href: '#plan', label: 'Review plan' };
  }
  return { href: '#inbox', label: 'Review in inbox' };
}

function humanSource(source) {
  if (!source) return '';
  return String(source).replace(/_/g, ' ');
}

/* ─────────────  THE ROOM  ───────────── */

function renderRoom(payload, engines) {
  const sync = payload.sync_status || {};
  const enginesEnabled = engines?.enabled_count ?? 0;
  const enginesReachable = engines?.reachable_count ?? 0;
  const closure = stateFromContext(payload.context_state);
  const lastSync = sync.last_completed_at || sync.last_started_at;

  const allQuiet = (
    payload.context_state === 'ready' &&
    (engines?.degraded_count ?? 0) === 0 &&
    sync.failed_count === 0
  );

  const headline = allQuiet
    ? 'All systems quiet.'
    : payload.context_state === 'critical' ? 'Attention needed.'
    : 'A few things to look at.';

  return html`
    <section>
      ${raw(sectionHead('IV', 'The room', null))}
      <div class="quiet-panel">
        <p class="quiet-statement">
          <span class="glyph">§</span>
          ${headline}
          <span class="marginalia">
            Last sync ${lastSync ? fmtRelative(lastSync) : '—'} · ${enginesReachable}/${enginesEnabled} engines reachable
          </span>
        </p>
        <details class="diagnostics-toggle">
          <summary>Show diagnostics</summary>
          <div class="diagnostics">
            <dl><dt>Snapshot</dt><dd>${payload.snapshot_age_minutes != null ? `${payload.snapshot_age_minutes}m ago` : '—'}</dd></dl>
            <dl><dt>Inbox</dt><dd>${payload.inbox_open_count ?? 0} open · ${payload.inbox_high_priority_count ?? 0} high</dd></dl>
            <dl><dt>Concentration</dt><dd>${payload.concentration_risk || '—'}</dd></dl>
            <dl><dt>Onboarding</dt><dd>${Math.round(payload.onboarding_completion_percent || 0)}%</dd></dl>
            <dl><dt>Profile gap</dt><dd>${esc(payload.profile_readiness?.next_gap_title || '—')}</dd></dl>
            <dl><dt>Health</dt><dd>${humanHealth(payload.financial_health_status)}</dd></dl>
            <dl><dt>Context</dt><dd>${closure}</dd></dl>
          </div>
        </details>
      </div>
    </section>
  `;
}

function stateFromContext(ctx) {
  if (ctx === 'ready') return 'ready';
  if (ctx === 'warning') return 'warning';
  if (ctx === 'critical') return 'critical';
  return '—';
}

function humanHealth(status) {
  if (!status) return '—';
  return String(status).replace(/_/g, ' ');
}

/* ─────────────  Shared bits  ───────────── */

function sectionHead(numeral, title, lede) {
  return html`
    <header class="section-head">
      <span class="section-eyebrow">Movement ${numeral}</span>
      <h2 class="section-title">${title}</h2>
      ${lede ? raw(`<p class="section-lede">${esc(lede)}</p>`) : ''}
    </header>
  `;
}

function skeletonHero() {
  return html`
    <section class="hero-stack">
      <span class="hero-eyebrow skeleton" style="width: 320px;">.</span>
      <h1 class="hero-number skeleton" style="width: 65%; height: var(--t-hero);">.</h1>
      <p class="hero-marginalia skeleton" style="width: 480px;">.</p>
    </section>
  `;
}

function skeletonSection(numeral, title) {
  return html`
    <section>
      ${raw(sectionHead(numeral, title, null))}
      <div class="skeleton" style="height: 80px;">.</div>
    </section>
  `;
}
