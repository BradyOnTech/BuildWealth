import { fetchJson } from './lib/api.js';
import { state } from './lib/state.js';
import { byId, writeLog } from './lib/utils.js';

import * as dashboard from './views/dashboard.js';
import * as profile from './views/profile.js';
import * as copilot from './views/copilot.js';
import * as plans from './views/plans.js';
import * as recommendations from './views/recommendations.js';
import * as workflows from './views/workflows.js';
import * as tracking from './views/tracking.js';
import * as sync from './views/sync.js';
import * as snapshot from './views/snapshot.js';

const views = [dashboard, profile, copilot, plans, tracking, recommendations, workflows, sync, snapshot];
let currentView = null;
let pendingParams = null;

function renderNav() {
  const nav = byId('nav-list');
  nav.innerHTML = '';

  for (const v of views) {
    const a = document.createElement('a');
    a.href = `#${v.id}`;
    a.className = `nav-item${v.id === currentView?.id ? ' active' : ''}`;
    a.innerHTML = `<span class="nav-icon">${v.icon}</span><span class="nav-label">${v.label}</span>`;
    nav.appendChild(a);
  }

  nav.innerHTML += `
    <div class="nav-divider"></div>
    <a href="http://localhost:3333" target="_blank" rel="noopener" class="nav-item external">
      <span class="nav-icon"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3h6v6"/><path d="M17 3L9 11"/><path d="M15 11v5a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1h5"/></svg></span>
      <span class="nav-label">Ghostfolio</span>
    </a>
    <a href="http://localhost:3000" target="_blank" rel="noopener" class="nav-item external">
      <span class="nav-icon"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3h6v6"/><path d="M17 3L9 11"/><path d="M15 11v5a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1h5"/></svg></span>
      <span class="nav-label">Ignidash</span>
    </a>`;
}

function route() {
  const raw = location.hash.slice(1) || 'dashboard';
  const [hash, query] = raw.split('?');
  const urlParams = Object.fromEntries(new URLSearchParams(query || ''));
  const view = views.find(v => v.id === hash) || dashboard;
  currentView = view;

  const content = byId('content');
  content.innerHTML = view.template();
  content.classList.remove('view-enter');
  void content.offsetWidth;
  content.classList.add('view-enter');

  byId('view-title').textContent = view.label;
  renderNav();

  const params = pendingParams || urlParams;
  pendingParams = null;
  view.init(params || {});
}

function toggleLog() {
  const drawer = byId('log-drawer');
  drawer.hidden = !drawer.hidden;
}

async function loadGlobalState() {
  try {
    const p = await fetchJson('/api/plans?limit=200');
    state.plans = Array.isArray(p) ? p : [];
    if (!state.currentPlanId && state.plans.length) {
      const active = state.plans.find(p => p.is_active);
      state.currentPlanId = active ? active.id : state.plans[0].id;
      state.copilotPlanId = state.currentPlanId;
    }
  } catch (e) { writeLog(`Plans load failed: ${e.message}`, null, true); }
}

async function boot() {
  byId('toggle-log').addEventListener('click', toggleLog);
  byId('close-log').addEventListener('click', toggleLog);
  byId('clear-log').addEventListener('click', () => { byId('log').innerHTML = ''; });

  window.addEventListener('hashchange', route);

  await loadGlobalState();
  route();

  writeLog('BuildWealth UI ready.');
}

boot().catch(e => writeLog(`Init failed: ${e.message}`, null, true));
