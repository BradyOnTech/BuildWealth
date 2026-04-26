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
      ${raw(skeletonSection('II', 'The move'))}
      ${raw(skeletonSection('III', 'The room'))}
    </section>
  `;
}

export async function init() {
  await load();
}

async function load() {
  const root = $('#today-page');
  if (!root) return;

  let payload = null;
  let engines = null;
  try {
    [payload, engines] = await Promise.all([
      api.today(),
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
    ${raw(renderMove(payload))}
    ${raw(renderRoom(payload, engines))}
  `);
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

/* ─────────────  THE MOVE  ───────────── */

export function renderMove(payload) {
  const actions = (payload.top_next_actions || []).slice(0, 3);
  if (!actions.length) {
    return html`
      <section>
        ${raw(sectionHead('II', 'The move', 'Nothing pressing today.'))}
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
      ${raw(sectionHead('II', 'The move', lede))}
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
      ${raw(sectionHead('III', 'The room', null))}
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
