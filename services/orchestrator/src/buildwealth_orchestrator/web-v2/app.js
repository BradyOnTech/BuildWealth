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
import * as importSync from './views/import_sync.js';
import * as workflows from './views/workflows.js';

import { state } from './lib/state.js';
import { api } from './lib/api.js';
import { html, raw, $ } from './lib/dom.js';
import { fmtDateLong } from './lib/format.js';

const VIEWS = [today, inbox, plan, portfolio, profile, copilot, research, atelier, settings, importSync, workflows];

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
    label: 'Data',
    items: [
      { id: 'import-sync',  label: 'Import & Review',     hint: 'Preview, reconcile, and apply statement activity' },
    ],
  },
  {
    label: 'Automation',
    items: [
      { id: 'workflows',    label: 'Workflows',           hint: 'Run pre-built routines' },
    ],
  },
  {
    label: 'Research',
    items: [
      { id: 'research',     label: 'Research Library',   hint: 'Dossiers, evidence, compare' },
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

// Hash aliases preserve earlier navigation links from the IA migration.
// Each entry rewrites the fragment in place and re-fires route() so the
// canonical hash lands in the address bar (and browser history).
const HASH_ALIASES = {
  'data-recovery':    'atelier',                  // future home of Backups/Protection/Git; today routes to atelier
  'tracking':         'plan?section=trajectory',
  'plans':            'plan',
  'sync':             'import-sync',
  'import-statement': 'import-sync?section=statement',
  'recommendations':  'inbox',
};

function route() {
  let fragment = location.hash.slice(1) || 'today';
  const [hashRaw] = fragment.split('?');
  if (HASH_ALIASES[hashRaw]) {
    // Preserve any extra query the user kept on the alias by appending it
    // after the alias target's own query (target-wins on conflict).
    const target = HASH_ALIASES[hashRaw];
    const [, originalQuery] = fragment.split('?');
    const next = originalQuery && !target.includes('?') ? `${target}?${originalQuery}` : target;
    location.replace(`#${next}`);
    return;
  }
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
  if (folio) {
    const numeral = view.meta.numeral;
    const showNumeral = numeral && numeral !== '·' && view.meta.group === 'primary';
    const prefix = showNumeral ? `${numeral} · ` : '';
    folio.textContent = `${prefix}${view.meta.label} · ${fmtDateLong(new Date())}`;
  }
  renderTopbarChips();
}

/* ─────────────  Top-bar status chips  ─────────────
   Per IA strategy: a small row of chips that answer "is the system ready
   to give me good advice right now?" Each chip is a deep-link to the page
   that fixes it when it's not. */

function renderTopbarChips() {
  const host = $('#topbar-status');
  if (!host) return;
  const chips = [];

  if (state.lastError) {
    chips.push({ tone: 'warn', label: 'attention', href: null, hint: state.lastError });
  }
  chips.push(profileChip());
  chips.push(copilotChip());
  chips.push(dataChip());
  chips.push(backupChip());

  host.innerHTML = chips.filter(Boolean).map(renderChip).join('');
}

function renderChip(chip) {
  const cls = `topbar-chip ${chip.tone || 'ok'}`;
  const inner = `<span class="dot"></span><span>${chip.label}</span>`;
  if (!chip.href) return `<span class="${cls}" title="${chip.hint || ''}">${inner}</span>`;
  return `<a class="${cls}" href="${chip.href}" data-route title="${chip.hint || ''}">${inner}</a>`;
}

function profileChip() {
  const status = state.systemStatus?.profile;
  if (!status) return { tone: 'quiet', label: 'profile · …', href: '#profile' };
  if (status.ready) return { tone: 'ok',   label: 'profile · ready',   href: '#profile', hint: `${status.completion}% complete` };
  if (status.completion >= 50) return { tone: 'warn', label: 'profile · review needed', href: '#profile', hint: `${status.completion}% complete` };
  return { tone: 'attn', label: 'profile · setup', href: '#profile', hint: `${status.completion}% complete` };
}

function copilotChip() {
  const status = state.systemStatus?.copilot;
  if (!status) return { tone: 'quiet', label: 'copilot · …', href: '#settings' };
  if (status.configured) return { tone: 'ok', label: 'copilot · ready', href: '#settings', hint: status.provider ? `${status.provider} · ${status.model || 'configured'}` : 'configured' };
  return { tone: 'warn', label: 'copilot · fallback', href: '#settings', hint: 'API key missing — set in Connections & AI' };
}

function dataChip() {
  const status = state.systemStatus?.data;
  if (!status) return { tone: 'quiet', label: 'data · …', href: '#today' };
  if (status.fresh) return { tone: 'ok', label: 'data · fresh', href: '#today', hint: status.lastSync ? `Synced ${status.lastSync}` : '' };
  if (status.never) return { tone: 'warn', label: 'data · never synced', href: '#today', hint: 'No sync recorded' };
  return { tone: 'warn', label: 'data · stale', href: '#today', hint: status.lastSync ? `Last sync ${status.lastSync}` : '' };
}

function backupChip() {
  const status = state.systemStatus?.backup;
  if (!status) return { tone: 'quiet', label: 'backup · …', href: '#atelier' };
  if (status.count > 0) return { tone: 'ok', label: `backup · ${status.count}`, href: '#atelier', hint: status.latest ? `Latest ${status.latest}` : '' };
  return { tone: 'warn', label: 'backup · none', href: '#atelier', hint: 'No backups recorded — create one in Data & Recovery' };
}

async function refreshSystemStatus() {
  // Load all four chips in parallel, ignore individual failures so a slow
  // endpoint never blocks the others. Each result lands on state.systemStatus
  // and a single re-render paints the chips.
  const next = { ...(state.systemStatus || {}) };

  const [onboarding, settingsResp, sync, backups] = await Promise.allSettled([
    api.onboarding(),
    api.settings(),
    api.syncStatus(),
    api.storageBackups(),
  ]);

  if (onboarding.status === 'fulfilled') {
    const v = onboarding.value || {};
    next.profile = {
      completion: Math.round(Number(v.completion_percent || 0)),
      ready: Boolean(v.ready_for_daily_review),
    };
  }

  if (settingsResp.status === 'fulfilled') {
    const s = settingsResp.value || {};
    next.copilot = {
      configured: Boolean(s.llm_api_key),
      provider: s.llm_provider,
      model: s.llm_model,
    };
  }

  if (sync.status === 'fulfilled') {
    const s = sync.value || {};
    const last = s.last_completed_at || s.last_started_at;
    if (!last) {
      next.data = { fresh: false, never: true };
    } else {
      const ageMs = Date.now() - new Date(last).getTime();
      // Anything older than ~24h is considered stale; tweak as needed.
      next.data = { fresh: ageMs < 24 * 60 * 60 * 1000, never: false, lastSync: humanRelative(last) };
    }
  }

  if (backups.status === 'fulfilled') {
    const list = Array.isArray(backups.value?.backups) ? backups.value.backups : (Array.isArray(backups.value) ? backups.value : []);
    const latest = list[0]?.created_at || list[0]?.timestamp;
    next.backup = { count: list.length, latest: latest ? humanRelative(latest) : null };
  }

  state.systemStatus = next;
  renderTopbarChips();
}

function humanRelative(value) {
  try {
    const ms = Date.now() - new Date(value).getTime();
    const m = Math.round(ms / 60000);
    if (m < 1)  return 'moments ago';
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.round(h / 24)}d ago`;
  } catch { return ''; }
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
            <div class="topbar-chips" id="topbar-status"></div>
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
  // Status chips refresh in the background after the first paint and on a
  // gentle 60s cadence — long enough not to be noisy, short enough that the
  // user sees a fresh signal after any save.
  refreshSystemStatus();
  setInterval(refreshSystemStatus, 60_000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { boot().catch(e => console.error(e)); });
} else {
  boot().catch(e => console.error(e));
}
