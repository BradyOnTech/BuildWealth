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
import * as review from './views/review.js';
import { authScreen } from './views/auth.js';

import { state } from './lib/state.js';
import './lib/chart_hover.js'; // side effect: binds chart hover readouts once at document level
import { api, setActiveWorkspaceId } from './lib/api.js';
import { html, raw, $, $$, esc } from './lib/dom.js';
import { fmtDateLong } from './lib/format.js';

const VIEWS = [today, inbox, plan, portfolio, profile, copilot, research, atelier, settings, importSync, workflows, review];

const VIEW_BY_ID = new Map(VIEWS.map(v => [v.meta.id, v]));

// Primary sidebar order (fixed). Anything not listed here that has a primary
// group still appears, but the canonical six should match the IA strategy.
const PRIMARY_ORDER = ['today', 'inbox', 'plan', 'portfolio', 'profile', 'copilot'];

// Data & Tools menu — utility surfaces that don't belong in the main sidebar.
// Items reference v2 view ids when available, or external hrefs when not.
const TOOLS_GROUPS = [
  {
    label: 'The Almanac',
    items: [
      { id: 'review',       label: 'Annual Edition',     hint: 'The year in review, printable' },
    ],
  },
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
let workspaceMenuOpen = false;
let accountMenuOpen = false;
let statusMenuOpen = false;
let globalEventsWired = false;
let authEventsWired = false;
let statusRefreshTimer = null;

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
    // Keep the date; drop roman + view name — the sidebar already marks the active section.
    folio.textContent = fmtDateLong(new Date());
  }
  renderTopbarStatus();
  renderWorkspaceMenu();
  renderAccountMenu();
}

/* ─────────────  Top-bar system status  ─────────────
   Answers "is the system ready to give me good advice?" without a permanent
   four-chip strip. One compact control; expand for deep links when needed. */

function collectStatusChips() {
  const chips = [];
  if (state.lastError) {
    chips.push({ tone: 'warn', label: 'Attention', href: null, hint: state.lastError });
  }
  chips.push(profileChip());
  chips.push(copilotChip());
  chips.push(dataChip());
  chips.push(backupChip());
  return chips.filter(Boolean);
}

function renderTopbarStatus() {
  const host = $('#topbar-status');
  if (!host) return;
  const chips = collectStatusChips();
  const issues = chips.filter(c => c.tone === 'warn' || c.tone === 'attn');
  const loading = chips.some(c => c.tone === 'quiet');
  let summaryTone = 'ok';
  let summaryLabel = 'Ready';
  if (loading && !issues.length) {
    summaryTone = 'quiet';
    summaryLabel = 'Checking…';
  } else if (issues.length === 1) {
    summaryTone = issues[0].tone;
    summaryLabel = issues[0].label;
  } else if (issues.length > 1) {
    summaryTone = issues.some(c => c.tone === 'attn') ? 'attn' : 'warn';
    summaryLabel = `${issues.length} need attention`;
  }

  host.innerHTML = html`
    <div class="status-menu">
      <button
        type="button"
        class="status-button ${summaryTone}"
        id="status-toggle"
        aria-expanded="${statusMenuOpen ? 'true' : 'false'}"
        title="System readiness"
      >
        <span class="dot"></span>
        <span class="status-label">${summaryLabel}</span>
      </button>
      ${statusMenuOpen ? raw(renderStatusDropdown(chips, issues.length)) : ''}
    </div>
  `;
  announceStatus(summaryLabel);
}

// Screen-reader announcement for async status changes. The chip repaints on
// every interaction; only speak when the summary actually changed.
let lastStatusAnnouncement = '';
function announceStatus(summaryLabel) {
  const announcer = $('#status-announcer');
  if (!announcer) return;
  const message = `System status: ${summaryLabel}`;
  if (message === lastStatusAnnouncement) return;
  lastStatusAnnouncement = message;
  announcer.textContent = message;
}

function renderStatusDropdown(chips, issueCount) {
  const rows = chips.map(chip => {
    const cls = `status-row ${chip.tone || 'ok'}`;
    const body = html`
      <span class="dot"></span>
      <span class="status-row-main">
        <span class="status-row-label">${chip.label}</span>
        ${chip.hint ? html`<span class="status-row-hint">${chip.hint}</span>` : ''}
      </span>
    `;
    if (chip.href) {
      return html`<a class="${cls}" href="${chip.href}" data-route>${body}</a>`;
    }
    return html`<div class="${cls}">${body}</div>`;
  }).join('');

  return html`
    <div class="status-dropdown" role="menu">
      <header class="status-dropdown-head">
        <span>System status</span>
        <span class="status-dropdown-meta">${issueCount ? `${issueCount} to review` : 'All clear'}</span>
      </header>
      ${raw(rows)}
    </div>
  `;
}

function activeWorkspace() {
  return (state.workspaces || []).find(w => w.id === state.activeWorkspaceId)
    || state.session?.workspace
    || null;
}

function renderWorkspaceMenu() {
  const host = $('#workspace-menu');
  if (!host) return;
  const workspace = activeWorkspace();
  const workspaces = Array.isArray(state.workspaces) ? state.workspaces : [];
  const label = workspace?.name || 'Workspace';
  const isDemo = Boolean(workspace?.is_demo || workspace?.workspace_type === 'demo');
  host.innerHTML = html`
    <button class="workspace-button ${isDemo ? 'demo' : ''}" id="workspace-toggle" type="button" aria-expanded="${workspaceMenuOpen ? 'true' : 'false'}">
      <span class="workspace-dot"></span>
      <span class="workspace-label">${label}</span>
      ${isDemo ? html`<span class="workspace-badge">Demo</span>` : ''}
    </button>
    ${workspaceMenuOpen ? raw(renderWorkspaceDropdown(workspaces)) : ''}
  `;
}

function renderWorkspaceDropdown(workspaces) {
  const rows = workspaces.length
    ? workspaces.map(workspace => html`
        <button class="workspace-option ${workspace.id === state.activeWorkspaceId ? 'active' : ''}"
                type="button"
                data-workspace-select="${esc(workspace.id)}">
          <span class="workspace-option-name">${workspace.name || workspace.id}</span>
          <span class="workspace-option-meta">${workspace.is_demo || workspace.workspace_type === 'demo' ? 'Demo household' : 'Household'}</span>
        </button>
      `).join('')
    : html`<p class="workspace-empty">No workspaces loaded.</p>`;
  return html`
    <div class="workspace-dropdown" role="menu">
      ${raw(rows)}
      <a class="workspace-settings-link" href="#settings" data-route>Workspace settings</a>
    </div>
  `;
}

function renderAccountMenu() {
  const host = $('#account-menu');
  if (!host) return;
  const user = state.session?.user || {};
  const displayName = user.display_name || user.email || 'Account';
  host.innerHTML = html`
    <button class="account-button" id="account-toggle" type="button" aria-expanded="${accountMenuOpen ? 'true' : 'false'}">
      <span class="account-avatar">${initials(displayName)}</span>
      <span class="account-name">${displayName}</span>
    </button>
    ${accountMenuOpen ? raw(renderAccountDropdown(user)) : ''}
  `;
}

function renderAccountDropdown(user) {
  const workspace = activeWorkspace();
  return html`
    <div class="account-dropdown" role="menu">
      <div class="account-summary">
        <strong>${user.display_name || 'BuildWealth user'}</strong>
        <span>${user.email || ''}</span>
      </div>
      <div class="account-meta">
        <span>${workspace?.name || 'Workspace'}</span>
        <span>${state.session?.role || 'owner'}</span>
      </div>
      <a class="account-link" href="#settings" data-route>Account settings</a>
      <a class="account-link" href="/privacy" target="_blank" rel="noopener noreferrer">Privacy notice</a>
      <a class="account-link" href="/terms" target="_blank" rel="noopener noreferrer">Terms</a>
      <a class="account-link" href="/ai-disclosure" target="_blank" rel="noopener noreferrer">AI disclosure</a>
      <button class="account-link danger" id="auth-logout" type="button">Sign out</button>
    </div>
  `;
}

function initials(value) {
  const parts = String(value || 'BW').trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : (parts[0] || 'BW').slice(0, 2);
  return letters.toUpperCase();
}

function profileChip() {
  const status = state.systemStatus?.profile;
  if (!status) return { tone: 'quiet', label: 'Profile', href: '#profile', hint: 'Checking…' };
  if (status.ready) return { tone: 'ok', label: 'Profile', href: '#profile', hint: `${status.completion}% complete · ready` };
  if (status.completion >= 50) return { tone: 'warn', label: 'Profile', href: '#profile', hint: `${status.completion}% complete · review needed` };
  return { tone: 'attn', label: 'Profile', href: '#profile', hint: `${status.completion}% complete · setup needed` };
}

function copilotChip() {
  const status = state.systemStatus?.copilot;
  if (!status) return { tone: 'quiet', label: 'Copilot', href: '#settings', hint: 'Checking…' };
  if (status.configured) {
    return {
      tone: 'ok',
      label: 'Copilot',
      href: '#settings',
      hint: status.provider ? `${status.provider} · ${status.model || 'configured'}` : 'Configured',
    };
  }
  return { tone: 'warn', label: 'Copilot', href: '#settings', hint: 'API key missing — set in Connections & AI' };
}

function dataChip() {
  const status = state.systemStatus?.data;
  if (!status) return { tone: 'quiet', label: 'Data', href: '#today', hint: 'Checking…' };
  if (status.fresh) return { tone: 'ok', label: 'Data', href: '#today', hint: status.lastSync ? `Synced ${status.lastSync}` : 'Fresh' };
  if (status.never) return { tone: 'warn', label: 'Data', href: '#today', hint: 'No sync recorded' };
  return { tone: 'warn', label: 'Data', href: '#today', hint: status.lastSync ? `Last sync ${status.lastSync}` : 'Stale' };
}

function backupChip() {
  const status = state.systemStatus?.backup;
  if (!status) return { tone: 'quiet', label: 'Backup', href: '#atelier', hint: 'Checking…' };
  if (status.count > 0) {
    return {
      tone: 'ok',
      label: 'Backup',
      href: '#atelier',
      hint: status.latest ? `${status.count} saved · latest ${status.latest}` : `${status.count} saved`,
    };
  }
  return { tone: 'warn', label: 'Backup', href: '#atelier', hint: 'No backups recorded — create one in Data & Recovery' };
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
      configured: Boolean(s.llm_api_key_configured || s.llm_api_key),
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
  renderTopbarStatus();
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
      <div class="app-main">
        <header class="topbar">
          <div class="topbar-eyebrow">
            <span class="topbar-folio" id="topbar-folio"></span>
          </div>
          <div class="topbar-actions">
            <div class="workspace-menu" id="workspace-menu"></div>
            <div class="account-menu" id="account-menu"></div>
            <div class="topbar-status" id="topbar-status"></div>
            <span class="sr-only" id="status-announcer" aria-live="polite"></span>
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
      statusMenuOpen = false;
      workspaceMenuOpen = false;
      accountMenuOpen = false;
      setToolsOpen(!toolsOpen);
      renderTopbarStatus();
      renderWorkspaceMenu();
      renderAccountMenu();
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
    const workspaceToggle = event.target.closest('#workspace-toggle');
    if (workspaceToggle) {
      event.preventDefault();
      workspaceMenuOpen = !workspaceMenuOpen;
      statusMenuOpen = false;
      accountMenuOpen = false;
      renderWorkspaceMenu();
      renderAccountMenu();
      renderTopbarStatus();
      return;
    }
    const workspaceSelect = event.target.closest('[data-workspace-select]');
    if (workspaceSelect) {
      event.preventDefault();
      switchWorkspace(workspaceSelect.getAttribute('data-workspace-select'));
      return;
    }
    const accountToggle = event.target.closest('#account-toggle');
    if (accountToggle) {
      event.preventDefault();
      accountMenuOpen = !accountMenuOpen;
      statusMenuOpen = false;
      workspaceMenuOpen = false;
      renderAccountMenu();
      renderWorkspaceMenu();
      renderTopbarStatus();
      return;
    }
    const statusToggle = event.target.closest('#status-toggle');
    if (statusToggle) {
      event.preventDefault();
      statusMenuOpen = !statusMenuOpen;
      workspaceMenuOpen = false;
      accountMenuOpen = false;
      renderTopbarStatus();
      renderWorkspaceMenu();
      renderAccountMenu();
      return;
    }
    const logout = event.target.closest('#auth-logout');
    if (logout) {
      event.preventDefault();
      signOut();
      return;
    }
    // Close status menu when following a deep-link row.
    if (event.target.closest('.status-row[href]')) {
      statusMenuOpen = false;
    }
    if (workspaceMenuOpen && !event.target.closest('#workspace-menu')) {
      workspaceMenuOpen = false;
      renderWorkspaceMenu();
    }
    if (accountMenuOpen && !event.target.closest('#account-menu')) {
      accountMenuOpen = false;
      renderAccountMenu();
    }
    if (statusMenuOpen && !event.target.closest('#topbar-status')) {
      statusMenuOpen = false;
      renderTopbarStatus();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      // Close and hand focus back to the toggle that opened the menu, so a
      // keyboard user isn't dropped at the top of the document. Focus must be
      // set after the re-render replaces the toggle element.
      if (toolsOpen) {
        setToolsOpen(false);
        $('#tools-toggle')?.focus();
      }
      if (workspaceMenuOpen) {
        workspaceMenuOpen = false;
        renderWorkspaceMenu();
        $('#workspace-toggle')?.focus();
      }
      if (accountMenuOpen) {
        accountMenuOpen = false;
        renderAccountMenu();
        $('#account-toggle')?.focus();
      }
      if (statusMenuOpen) {
        statusMenuOpen = false;
        renderTopbarStatus();
        $('#status-toggle')?.focus();
      }
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const menu = openMenuElement();
      if (!menu) return;
      const items = $$('a[href], button:not([disabled])', menu);
      if (!items.length) return;
      event.preventDefault();
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      const index = items.indexOf(document.activeElement);
      const next = index === -1
        ? (delta === 1 ? 0 : items.length - 1)
        : (index + delta + items.length) % items.length;
      items[next].focus();
    }
  });
}

// The dropdown (or drawer) currently open, if any. The click handlers keep at
// most one open at a time, so first match wins.
function openMenuElement() {
  if (workspaceMenuOpen) return $('.workspace-dropdown');
  if (accountMenuOpen) return $('.account-dropdown');
  if (statusMenuOpen) return $('.status-dropdown');
  if (toolsOpen) return $('#tools-drawer');
  return null;
}

async function preloadGlobalState({ refreshWorkspace = true } = {}) {
  if (refreshWorkspace) await refreshWorkspaceState({ requireSession: true });
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

async function refreshWorkspaceState({ requireSession = false, retriedWorkspace = false } = {}) {
  try {
    const session = await api.authSession();
    const workspaces = await api.workspaces();
    state.authRequired = false;
    state.session = session;
    const items = Array.isArray(workspaces?.items) ? workspaces.items : [];
    state.workspaces = items;
    state.activeWorkspaceId = workspaces?.active_workspace_id || session?.workspace?.id || items[0]?.id || null;
    renderWorkspaceMenu();
  } catch (err) {
    if (err?.status === 401 && requireSession) {
      state.authRequired = true;
      throw err;
    }
    if (err?.status === 403 && !retriedWorkspace) {
      setActiveWorkspaceId('');
      state.activeWorkspaceId = null;
      return refreshWorkspaceState({ requireSession, retriedWorkspace: true });
    }
    console.warn('[v2 boot] workspace preload failed:', err.message);
  }
}

async function switchWorkspace(workspaceId) {
  if (!workspaceId || workspaceId === state.activeWorkspaceId) {
    workspaceMenuOpen = false;
    renderWorkspaceMenu();
    return;
  }
  try {
    await api.selectWorkspace(workspaceId);
    workspaceMenuOpen = false;
    state.activeWorkspaceId = workspaceId;
    state.activePlanId = null;
    state.plans = [];
    await refreshWorkspaceState();
    await preloadGlobalState();
    refreshSystemStatus();
    route();
  } catch (err) {
    state.lastError = err.message || 'Could not switch workspace.';
    workspaceMenuOpen = false;
    renderWorkspaceMenu();
    renderTopbarStatus();
  }
}

function renderAuthGate(mode = 'login', error = '') {
  clearAppTimers();
  state.authRequired = true;
  state.session = null;
  state.workspaces = [];
  state.activeWorkspaceId = null;
  document.body.innerHTML = authScreen({ mode, error, authConfig: state.authConfig });
}

function consumeAuthErrorFromLocation() {
  try {
    const params = new URLSearchParams(window.location.search || '');
    const message = params.get('auth_error') || '';
    if (!message) return '';
    params.delete('auth_error');
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
    window.history.replaceState({}, '', nextUrl);
    return message;
  } catch {
    return '';
  }
}

function setAuthBusy(mode, busy, error = '') {
  document.body.innerHTML = authScreen({ mode, busy, error, authConfig: state.authConfig });
}

function wireAuthEvents() {
  if (authEventsWired) return;
  authEventsWired = true;
  document.addEventListener('click', (event) => {
    const modeSwitch = event.target.closest('[data-auth-mode-switch]');
    if (!modeSwitch) return;
    event.preventDefault();
    renderAuthGate(modeSwitch.getAttribute('data-auth-mode-switch') || 'login');
  });
  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('#auth-form');
    if (!form) return;
    event.preventDefault();
    const mode = form.getAttribute('data-auth-mode') || 'login';
    const data = Object.fromEntries(new FormData(form).entries());
    setAuthBusy(mode, true);
    try {
      if (mode === 'register') await api.authRegister(data);
      else await api.authLogin(data);
      await bootAuthenticatedShell();
    } catch (err) {
      setAuthBusy(mode, false, err?.message || 'Could not sign in.');
    }
  });
}

async function signOut() {
  let redirectTo = '';
  try {
    const result = await api.authLogout();
    redirectTo = result?.redirect_to || '';
  } catch (err) {
    console.warn('[v2 auth] logout failed:', err.message);
  } finally {
    if (redirectTo) window.location.assign(redirectTo);
    else renderAuthGate('login');
  }
}

function wireShellEventsOnce() {
  if (globalEventsWired) return;
  globalEventsWired = true;
  window.addEventListener('hashchange', route);
  wireGlobalEvents();
}

function clearAppTimers() {
  if (statusRefreshTimer) {
    clearInterval(statusRefreshTimer);
    statusRefreshTimer = null;
  }
}

async function bootAuthenticatedShell() {
  bootShell();
  state.bootedAt = new Date();
  wireShellEventsOnce();
  await preloadGlobalState();
  route();
  refreshSystemStatus();
  clearAppTimers();
  statusRefreshTimer = setInterval(refreshSystemStatus, 60_000);
  document.addEventListener('buildwealth:settings-saved', () => {
    refreshSystemStatus();
  });
}

async function boot() {
  // Take scroll into our own hands — the browser's automatic scroll
  // restoration races with route()'s scrollTo(0, 0) on reload and wins,
  // leaving the user landed mid-page on a freshly-loaded view.
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  wireAuthEvents();
  try {
    state.authConfig = await api.authConfig();
  } catch (err) {
    console.warn('[v2 boot] auth config failed:', err.message);
    state.authConfig = null;
  }
  try {
    await refreshWorkspaceState({ requireSession: true });
  } catch (err) {
    if (err?.status === 401) {
      renderAuthGate('login', consumeAuthErrorFromLocation());
      return;
    }
    console.warn('[v2 boot] auth preflight failed:', err.message);
  }
  await bootAuthenticatedShell();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { boot().catch(e => console.error(e)); });
} else {
  boot().catch(e => console.error(e));
}
