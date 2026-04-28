// INBOX — three movements.
//   I.  The list  · ranked / created_at, filtered by status and plan
//   II. A new sweep · run all factories and create candidates
//   III. Quality · how past suggestions played out

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, delegate } from '../lib/dom.js';
import { renderEntries } from './inbox/entries.js';
import { renderSweep, runPreview, runCreate } from './inbox/sweep.js';
import { renderQuality } from './inbox/quality.js';

export const meta = {
  id: 'inbox',
  label: 'Inbox',
  numeral: '·',
  group: 'hidden',
};

const STATUSES = ['proposed', 'applied', 'rejected', 'archived'];

const inbox = {
  status: 'proposed',
  sort:   'ranked',
  planId: 'all',
  items:  [],
  busy:   false,
  error:  null,
  expanded: null,                          // { id, mode, busy, preview, error }
  sweep:  { phase: 'idle', busy: false },  // 'idle' | 'previewing' | 'preview-ready' | 'creating' | 'done' | 'error'
  closure: null,
  counts: {},                              // { proposed: 3, applied: 7, ... }
  planLookup: new Map(),
  initialFocus: null,
};

export function template() {
  return html`
    <section class="page" id="inbox-page">
      <header>
        <span class="section-eyebrow">Movement I</span>
        <h2 class="section-title">The list.</h2>
        <p class="section-lede">Decisions waiting for your call. Ranked by impact, confidence, urgency, and reversibility.</p>
      </header>
      <div id="inbox-controls"></div>
      <div id="inbox-list">${raw(loadingPlaceholder())}</div>
      <div id="inbox-sweep"></div>
      <div id="inbox-quality"></div>
    </section>
  `;
}

export async function init(params = {}) {
  inbox.initialFocus = params.focus || null;
  inbox.planLookup = new Map((state.plans || []).map(p => [p.id, p.title || p.id]));
  attachHandlers();
  await loadList();
  rerenderAll();
  loadClosure().then(() => rerenderQuality()).catch(() => {});
}

/* ─────────────  data  ───────────── */

async function loadList() {
  inbox.busy = true;
  inbox.error = null;
  rerenderControls();
  try {
    const res = await api.recommendations({
      status: inbox.status,
      sort: inbox.sort,
      planId: inbox.planId,
    });
    inbox.items = Array.isArray(res) ? res : (res.items || []);
    // Counts for status chips — fetch a separate compact pull for each status when on 'all'.
    if (inbox.status !== 'all') {
      inbox.counts[inbox.status] = inbox.items.length;
    }
  } catch (err) {
    inbox.error = err.message;
    inbox.items = [];
  } finally {
    inbox.busy = false;
  }
}

async function loadClosure() {
  try {
    inbox.closure = await api.closure();
  } catch {
    inbox.closure = null;
  }
}

/* ─────────────  rendering  ───────────── */

function rerenderAll() {
  rerenderControls();
  rerenderList();
  rerenderSweep();
  rerenderQuality();
}

function rerenderControls() {
  const root = $('#inbox-controls');
  if (!root) return;
  root.innerHTML = html`
    <div class="inbox-filters">
      <div class="filter-chips" role="tablist">
        ${raw(STATUSES.concat('all').map(s => chip(s, s === inbox.status, inbox.counts[s])).join(''))}
      </div>
      <div class="sort-toggle" role="group" aria-label="Sort">
        <span class="label">sort</span>
        <button data-sort="ranked"  aria-pressed="${inbox.sort === 'ranked'}">ranked</button>
        <span aria-hidden="true">·</span>
        <button data-sort="created_at"  aria-pressed="${inbox.sort === 'created_at'}">newest</button>
      </div>
    </div>
  `;
}

function chip(status, active, count) {
  const label = status === 'rejected' ? 'declined' : status;
  const countMark = (active && count != null) ? `<span class="count">${count}</span>` : '';
  return html`
    <button class="chip" data-status="${status}" aria-pressed="${active}">
      ${label}${raw(countMark)}
    </button>
  `;
}

function rerenderList() {
  const root = $('#inbox-list');
  if (!root) return;
  if (inbox.busy && !inbox.items.length) {
    root.innerHTML = loadingPlaceholder();
    return;
  }
  if (inbox.error) {
    root.innerHTML = html`<p class="error-banner">${inbox.error}</p>`;
    return;
  }
  const ctx = {
    expanded: inbox.expanded,
    planLookup: inbox.planLookup,
    emptyMessage: emptyMessageFor(inbox.status),
  };
  root.innerHTML = renderEntries(inbox.items, ctx);
  if (inbox.initialFocus) {
    const target = root.querySelector(`[data-id="${cssEscape(inbox.initialFocus)}"]`);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    inbox.initialFocus = null;
  }
}

function rerenderSweep() {
  const root = $('#inbox-sweep');
  if (!root) return;
  root.innerHTML = renderSweep(inbox.sweep);
}

function rerenderQuality() {
  const root = $('#inbox-quality');
  if (!root) return;
  root.innerHTML = renderQuality(inbox.closure);
}

function loadingPlaceholder() {
  return `<div class="skeleton" style="height: 240px;">.</div>`;
}

function emptyMessageFor(status) {
  if (status === 'proposed') return 'The proposed lane is clear.';
  if (status === 'applied')  return 'No applied suggestions yet.';
  if (status === 'rejected') return 'Nothing has been declined.';
  if (status === 'archived') return 'The archive is empty.';
  return 'No suggestions match this filter.';
}

/* ─────────────  events  ───────────── */

function attachHandlers() {
  const page = $('#inbox-page');
  if (!page) return;

  delegate(page, 'click', '.chip[data-status]', (_, t) => {
    setStatus(t.getAttribute('data-status'));
  });
  delegate(page, 'click', '[data-sort]', (_, t) => {
    setSort(t.getAttribute('data-sort'));
  });
  delegate(page, 'click', '[data-action]', (_, t) => {
    const action = t.getAttribute('data-action');
    const id = t.getAttribute('data-id');
    if (action === 'archive') return doArchive(id);
    expandEntry(id, action);
  });
  delegate(page, 'click', '[data-cancel]', (_, t) => {
    const id = t.getAttribute('data-id');
    if (inbox.expanded && inbox.expanded.id === id) closeExpanded();
  });
  delegate(page, 'click', '[data-submit]', (_, t) => {
    submitForm(t.getAttribute('data-submit'), t.getAttribute('data-id'));
  });
  delegate(page, 'click', '[data-outcome-preset]', (_, t) => {
    appendOutcomePreset(t);
  });
  delegate(page, 'click', '[data-sweep]', (_, t) => {
    handleSweep(t.getAttribute('data-sweep'));
  });
}

async function setStatus(status) {
  if (inbox.status === status) return;
  inbox.status = status;
  inbox.expanded = null;
  await loadList();
  rerenderControls();
  rerenderList();
}

async function setSort(sort) {
  if (inbox.sort === sort) return;
  inbox.sort = sort;
  await loadList();
  rerenderControls();
  rerenderList();
}

async function expandEntry(id, mode) {
  if (inbox.expanded && inbox.expanded.id === id && inbox.expanded.mode === mode) {
    closeExpanded();
    return;
  }
  inbox.expanded = { id, mode, busy: false, preview: null, error: null };
  rerenderList();

  if (mode === 'apply') {
    inbox.expanded.busy = true;
    rerenderList();
    try {
      const item = inbox.items.find(it => it.id === id);
      const planId = item?.plan_id;
      const res = await api.preview(id, planId ? { plan_id: planId } : {});
      if (inbox.expanded?.id === id && inbox.expanded.mode === 'apply') {
        inbox.expanded.preview = res.preview || res;
        inbox.expanded.busy = false;
        rerenderList();
      }
    } catch (err) {
      if (inbox.expanded?.id === id && inbox.expanded.mode === 'apply') {
        inbox.expanded.busy = false;
        inbox.expanded.error = err.message;
        rerenderList();
      }
    }
  }
}

function closeExpanded() {
  inbox.expanded = null;
  rerenderList();
}

async function submitForm(mode, id) {
  if (!inbox.expanded || inbox.expanded.id !== id) return;
  const formEl = document.querySelector(`[data-form="${mode}"][data-id="${cssEscape(id)}"]`);
  if (!formEl) return;
  const data = collectFormData(formEl);
  inbox.expanded.busy = true;
  inbox.expanded.error = null;
  rerenderList();

  try {
    if (mode === 'apply')   await api.apply(id, data);
    if (mode === 'decline') await api.reject(id, data);
    if (mode === 'outcome') await api.outcome(id, data);
    inbox.expanded = null;
    await loadList();
    rerenderList();
  } catch (err) {
    if (inbox.expanded) {
      inbox.expanded.busy = false;
      inbox.expanded.error = err.message;
      rerenderList();
    }
  }
}

async function doArchive(id) {
  try {
    await api.archive(id, {});
    if (inbox.expanded?.id === id) inbox.expanded = null;
    await loadList();
    rerenderControls();
    rerenderList();
  } catch (err) {
    inbox.error = err.message;
    rerenderList();
  }
}

async function handleSweep(action) {
  if (action === 'reset') {
    inbox.sweep = { phase: 'idle', busy: false };
    rerenderSweep();
    return;
  }
  if (action === 'preview') {
    inbox.sweep = { phase: 'previewing', busy: true };
    rerenderSweep();
    try {
      const summary = await runPreview();
      inbox.sweep = { phase: 'preview-ready', preview: summary, busy: false };
    } catch (err) {
      inbox.sweep = { phase: 'error', error: err.message, busy: false };
    }
    rerenderSweep();
    return;
  }
  if (action === 'create') {
    inbox.sweep = { ...inbox.sweep, phase: 'creating', busy: true };
    rerenderSweep();
    try {
      const summary = await runCreate();
      inbox.sweep = { phase: 'done', created: summary.created || summary.total || 0, busy: false };
      await loadList();
      rerenderControls();
      rerenderList();
    } catch (err) {
      inbox.sweep = { phase: 'error', error: err.message, busy: false };
    }
    rerenderSweep();
  }
}

/* ─────────────  helpers  ───────────── */

function collectFormData(formEl) {
  const data = {};
  for (const field of formEl.querySelectorAll('input, textarea, select')) {
    let name = field.name;
    if (!name) continue;
    let value = field.value;
    if (field.type === 'number' && value !== '') value = Number(value);
    if (value === '' || value == null) continue;
    if (name === 'outcome_note') name = 'note';
    if (name === 'future_value_delta_usd') name = 'realized_delta_future_value_usd';
    if (name === 'real_value_delta_usd') name = 'realized_delta_real_value_usd';
    if (name === 'measurement_window_days') name = 'observation_window_days';
    data[name] = value;
  }
  return data;
}

function appendOutcomePreset(button) {
  const preset = String(button.getAttribute('data-outcome-preset') || '').trim();
  if (!preset) return;
  const form = button.closest('[data-form="outcome"]');
  const textarea = form?.querySelector('textarea[name="outcome_note"]');
  if (!textarea) return;
  const current = String(textarea.value || '').trim();
  textarea.value = current ? `${current}; ${preset}` : preset;
  const processOutcome = String(button.getAttribute('data-outcome-code') || '').trim();
  const evidenceSufficiency = String(button.getAttribute('data-evidence-sufficiency') || '').trim();
  const processField = form.querySelector('input[name="process_outcome"]');
  const evidenceField = form.querySelector('input[name="evidence_sufficiency"]');
  if (processField && processOutcome) processField.value = processOutcome;
  if (evidenceField && evidenceSufficiency) evidenceField.value = evidenceSufficiency;
  textarea.focus();
}

function cssEscape(s) {
  return String(s).replace(/["\\]/g, '\\$&');
}
