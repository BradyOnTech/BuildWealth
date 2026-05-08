// App shell — sidebar, topbar, routing, page transitions.
// Hash-based router, ES modules, no build step.

import * as today from './views/today.js';
import * as portfolio from './views/portfolio.js';
import * as plan from './views/plan.js';
import * as copilot from './views/copilot.js';
import * as atelier from './views/atelier.js';
import * as inbox from './views/inbox.js';
import * as research from './views/research.js';
import * as profile from './views/profile.js';
import * as settings from './views/settings.js';

import { state } from './lib/state.js';
import { api } from './lib/api.js';
import { html, raw, $ } from './lib/dom.js';
import { fmtDateLong } from './lib/format.js';

const VIEWS = [today, inbox, plan, portfolio, profile, copilot, research, atelier, settings];

const VIEW_BY_ID = new Map(VIEWS.map(v => [v.meta.id, v]));

// Primary sidebar order (fixed). Anything not listed here that has a primary
// group still appears, but the canonical six should match the IA strategy.
const PRIMARY_ORDER = ['today', 'inbox', 'plan', 'portfolio', 'profile', 'copilot'];

// Data & Tools menu — utility surfaces that don't belong in the main sidebar.
// Items reference v2 view ids when available, or external hrefs when not.
const TOOLS_GROUPS = [
  {
    label: 'System',
    items: [
      { id: 'settings',     label: 'Connections & AI',   hint: 'AI provider, keys, context' },
      { id: 'atelier',      label: 'Data & Recovery',    hint: 'Backups, protection, history' },
    ],
  },
  {
    label: 'Research',
    items: [
      { id: 'research',     label: 'Research Library',   hint: 'Dossiers, evidence, compare' },
    ],
  },
  {
    label: 'Bridges',
    items: [
      { href: '/',                                       label: 'Classic UI',         hint: 'Full v1 surface' },
      { href: 'http://localhost:3333', external: true,   label: 'Ghostfolio',         hint: 'External holdings' },
      { href: 'http://localhost:3000', external: true,   label: 'Ignidash',           hint: 'External dashboards' },
    ],
  },
];

let currentView = null;
let toolsOpen = false;

function primaryViews() {
  return PRIMARY_ORDER
    .map(id => VIEW_BY_ID.get(id))
    .filter(v => v && v.meta.group === 'primary');
}

function renderSidebar() {
  const items = primaryViews();
  const navHtml = html`
    ${raw(items.map(navItem).join(''))}
  `;
  $('#nav').innerHTML = navHtml;
  renderToolsToggle();
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

function renderToolsToggle() {
  const toggle = $('#tools-toggle');
  if (!toggle) return;
  toggle.setAttribute('aria-expanded', toolsOpen ? 'true' : 'false');
}

function renderToolsDrawer() {
  const drawer = $('#tools-drawer');
  if (!drawer) return;
  if (!toolsOpen) {
    drawer.setAttribute('aria-hidden', 'true');
    drawer.innerHTML = '';
    return;
  }
  drawer.setAttribute('aria-hidden', 'false');
  drawer.innerHTML = html`
    <div class="tools-drawer-card">
      <header class="tools-drawer-head">
        <span class="tools-eyebrow">§ Data &amp; Tools</span>
        <button class="tools-close" id="tools-close" aria-label="Close menu">×</button>
      </header>
      <p class="tools-lede">
        Lower-frequency utilities. Keep the main sidebar quiet; everything else lives here.
      </p>
      ${raw(TOOLS_GROUPS.map(renderToolsGroup).join(''))}
    </div>
  `;
}

function renderToolsGroup(group) {
  return html`
    <section class="tools-group">
      <h3 class="tools-group-label">${group.label}</h3>
      <ul class="tools-list">
        ${raw(group.items.map(renderToolsItem).join(''))}
      </ul>
    </section>
  `;
}

function renderToolsItem(item) {
  if (item.id) {
    const view = VIEW_BY_ID.get(item.id);
    const isActive = currentView && currentView.meta.id === item.id;
    return html`
      <li>
        <a class="tools-item ${isActive ? 'active' : ''}"
           href="#${item.id}" data-route data-tools-item>
          <span class="tools-item-label">${item.label}</span>
          <span class="tools-item-hint">${item.hint || (view && view.meta.label) || ''}</span>
        </a>
      </li>
    `;
  }
  const target = item.external ? '_blank' : '_self';
  const rel = item.external ? 'noopener' : '';
  return html`
    <li>
      <a class="tools-item" href="${item.href}" target="${target}" rel="${rel}" data-tools-item>
        <span class="tools-item-label">${item.label}${item.external ? ' ↗' : ''}</span>
        <span class="tools-item-hint">${item.hint || ''}</span>
      </a>
    </li>
  `;
}

function setToolsOpen(open) {
  toolsOpen = Boolean(open);
  renderToolsToggle();
  renderToolsDrawer();
}

function route() {
  const fragment = location.hash.slice(1) || 'today';
  const [hash, query] = fragment.split('?');
  const params = Object.fromEntries(new URLSearchParams(query || ''));
  const view = VIEW_BY_ID.get(hash) || VIEW_BY_ID.get('today');
  const previousView = currentView;
  currentView = view;

  // Closing the tools drawer on navigation matches the "drawer dismisses on use"
  // behavior every command-menu/quick-pick has trained users to expect.
  setToolsOpen(false);

  // Reset scroll on top-level route change so a long previous page doesn't
  // strand the new page below the fold. Section-level changes (?section=...)
  // are handled inside the view and shouldn't snap.
  if (previousView !== view) window.scrollTo(0, 0);

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
    const showNumeral = numeral && numeral !== '·' && view.meta.group === 'primary';
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
          <button class="tools-toggle" id="tools-toggle" type="button" aria-expanded="false" aria-controls="tools-drawer">
            <span class="tools-toggle-glyph">§</span>
            <span class="tools-toggle-label">Data &amp; Tools</span>
            <span class="tools-toggle-caret">↗</span>
          </button>
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
    <aside class="tools-drawer" id="tools-drawer" aria-hidden="true"></aside>
    <div class="tools-scrim" id="tools-scrim" aria-hidden="true"></div>
  `;
}

function wireGlobalEvents() {
  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('#tools-toggle');
    if (toggle) {
      event.preventDefault();
      setToolsOpen(!toolsOpen);
      return;
    }
    const close = event.target.closest('#tools-close');
    if (close) {
      event.preventDefault();
      setToolsOpen(false);
      return;
    }
    const scrim = event.target.closest('#tools-scrim');
    if (scrim && toolsOpen) {
      setToolsOpen(false);
      return;
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toolsOpen) {
      setToolsOpen(false);
    }
  });
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
  // Take scroll into our own hands — the browser's automatic scroll
  // restoration races with route()'s scrollTo(0, 0) on reload and wins,
  // leaving the user landed mid-page on a freshly-loaded view.
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  bootShell();
  state.bootedAt = new Date();
  window.addEventListener('hashchange', route);
  wireGlobalEvents();
  await preloadGlobalState();
  route();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { boot().catch(e => console.error(e)); });
} else {
  boot().catch(e => console.error(e));
}
