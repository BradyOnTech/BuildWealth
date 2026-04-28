// App shell — sidebar, topbar, routing, page transitions.
// Hash-based router, ES modules, no build step.

import * as today from './views/today.js';
import * as portfolio from './views/portfolio.js';
import * as plan from './views/plan.js';
import * as copilot from './views/copilot.js';
import * as atelier from './views/atelier.js';
import * as inbox from './views/inbox.js';
import * as research from './views/research.js';

import { state } from './lib/state.js';
import { api } from './lib/api.js';
import { html, raw, $ } from './lib/dom.js';
import { fmtDateLong } from './lib/format.js';

const VIEWS = [today, portfolio, plan, copilot, research, atelier, inbox];

const VIEW_BY_ID = new Map(VIEWS.map(v => [v.meta.id, v]));
const SIDEBAR_VIEWS = VIEWS.filter(v => v.meta.group !== 'hidden');

let currentView = null;

function renderSidebar() {
  const dailyItems = SIDEBAR_VIEWS.filter(v => v.meta.group === 'daily');
  const studioItems = SIDEBAR_VIEWS.filter(v => v.meta.group === 'studio');

  const navHtml = html`
    <span class="nav-section-label">Daily</span>
    ${raw(dailyItems.map(navItem).join(''))}
    <span class="nav-section-label">Studio</span>
    ${raw(studioItems.map(navItem).join(''))}
  `;

  $('#nav').innerHTML = navHtml;
}

function navItem(view) {
  const isActive = currentView && currentView.meta.id === view.meta.id;
  return html`
    <a class="nav-item ${isActive ? 'active' : ''}" href="#${view.meta.id}" data-route data-view="${view.meta.id}">
      <span class="nav-roman">${view.meta.numeral}</span>
      <span class="nav-label">${view.meta.label}</span>
    </a>
  `;
}

function route() {
  const fragment = location.hash.slice(1) || 'today';
  const [hash, query] = fragment.split('?');
  const params = Object.fromEntries(new URLSearchParams(query || ''));
  const view = VIEW_BY_ID.get(hash) || VIEW_BY_ID.get('today');
  currentView = view;

  const content = $('#content');
  content.innerHTML = view.template();

  renderSidebar();
  updateTopbar(view);

  try {
    const result = view.init(params);
    if (result && typeof result.then === 'function') {
      result.catch(err => console.error('[v2 view init]', view.meta.id, err));
    }
  } catch (err) {
    console.error('[v2 view init]', view.meta.id, err);
  }
}

function updateTopbar(view) {
  const folio = $('#topbar-folio');
  const status = $('#topbar-status');
  if (folio) {
    const numeral = view.meta.numeral;
    const showNumeral = numeral && numeral !== '·' && view.meta.group !== 'hidden';
    const prefix = showNumeral ? `${numeral} · ` : '';
    folio.textContent = `${prefix}${view.meta.label} · ${fmtDateLong(new Date())}`;
  }
  if (status) {
    const text = state.lastError ? 'attention' : 'quiet';
    status.className = `topbar-status ${state.lastError ? 'warn' : ''}`;
    status.innerHTML = `<span class="dot"></span><span>${text}</span>`;
  }
}

function bootShell() {
  document.body.innerHTML = `
    <div class="app-shell">
      <nav class="sidebar">
        <div class="sidebar-brand">
          <p class="brand-monogram">B<span class="ampersand">&amp;</span>W</p>
          <p class="brand-eyebrow">The Wealth Almanac</p>
        </div>
        <div class="nav" id="nav"></div>
        <div class="sidebar-foot">
          <a href="/" title="Open the classic UI in this tab">↩ Classic UI</a>
          <a href="http://localhost:3333" target="_blank" rel="noopener">Ghostfolio ↗</a>
          <a href="http://localhost:3000" target="_blank" rel="noopener">Ignidash ↗</a>
        </div>
      </nav>
      <div>
        <header class="topbar">
          <div class="topbar-eyebrow">
            <span class="topbar-folio" id="topbar-folio"></span>
          </div>
          <div class="topbar-actions">
            <span class="topbar-status" id="topbar-status">
              <span class="dot"></span><span>quiet</span>
            </span>
          </div>
        </header>
        <main class="content" id="content"></main>
      </div>
    </div>
  `;
}

async function preloadGlobalState() {
  try {
    const plans = await api.plans();
    state.plans = Array.isArray(plans) ? plans : [];
    if (!state.activePlanId && state.plans.length) {
      const active = state.plans.find(p => p.is_active);
      state.activePlanId = active ? active.id : state.plans[0].id;
    }
  } catch (err) {
    console.warn('[v2 boot] plans preload failed:', err.message);
  }
}

async function boot() {
  bootShell();
  state.bootedAt = new Date();
  window.addEventListener('hashchange', route);
  await preloadGlobalState();
  route();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { boot().catch(e => console.error(e)); });
} else {
  boot().catch(e => console.error(e));
}
